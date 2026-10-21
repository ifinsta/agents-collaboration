"""Owner loss preserves work while successors revalidate start gates and clocks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_hardening import core, fixtures
from test_processes import ProcessCase, contracts


class Takeover(ProcessCase):
    def owner(self, *, contracted=True, critical=False, progress=False):
        self.contracted = contracted
        self.join("ann")
        self.join("bob")
        if contracted:
            self.sw("contract", "offer", "T5", "ann", "--as", "human")
            self.sw("contract", "accept", "T5", "--as", "ann")
        self.worker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"], stdout=subprocess.DEVNULL)
        self.addCleanup(self.stop_worker)
        self.sw("join", "--as", "ann", "--kind", "fake", "--resume", "--pid", str(self.worker.pid))
        self.sw("claim", "T5", "--as", "ann")
        self.tree = Path(self.task("T5")["worktree"])
        plan = [value if value != "risks=low" or not critical else "risks=unknown" for value in fixtures.PLAN]
        self.sw("plan", "--as", "ann", *plan, cwd=self.tree)
        (self.tree / "src").mkdir(exist_ok=True)
        (self.tree / "src" / "retained.txt").write_text("preserve the original source work", encoding="utf-8")
        if progress:
            self.sw("start", "--as", "ann", cwd=self.tree)
            self.sw("step", "1", "--as", "ann", "--evidence", "Created src/retained.txt with the fixture source.", cwd=self.tree)
            if contracted:
                self.sql("UPDATE task_contracts SET active_since=? WHERE task='T5'", (core.iso(core.utcnow() - timedelta(seconds=60)),))
        self.git("add", "src", cwd=self.tree)
        self.git("commit", "-qm", "preserve source work", cwd=self.tree)
        self.saved = dict(self.task("T5"))
        self.head = self.git("rev-parse", "HEAD", cwd=self.tree).strip()
        self.target = self.git("rev-parse", "main").strip()

    def stop_worker(self):
        if self.worker.poll() is None:
            self.worker.kill()  # Actual Popen handle created here; no registry PID is signaled.
        self.worker.wait(timeout=10)

    def sql(self, statement, args=()):
        with self.board() as board, board.tx():
            board.db.execute(statement, args)

    def contract(self, *, first=False):
        with self.board() as board:
            return dict(board.db.execute(
                "SELECT * FROM task_contracts WHERE task='T5' ORDER BY id " + ("ASC" if first else "DESC") + " LIMIT 1"
            ).fetchone())

    def loss(self):
        self.stop_worker()
        self.sw("status")
        self.assertEqual(self.task("T5")["state"], "orphaned")
        if self.contracted:
            paused = self.contract()
            self.sw("status")
            self.assertEqual(self.contract(), paused)
            with self.board() as board:
                self.assertEqual(board.db.execute("SELECT count(*) FROM events WHERE kind='contract_paused' AND task='T5'").fetchone()[0], 1)

    def assert_work_preserved(self):
        task = self.task("T5")
        self.assertEqual(task["steps"], self.saved["steps"])
        self.assertEqual(task["step_idx"], self.saved["step_idx"])
        self.assertEqual(task["plan"], self.saved["plan"])
        self.assertEqual(task["branch"], self.saved["branch"])
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.tree).strip(), self.head)
        self.assertEqual(self.git("rev-parse", "main").strip(), self.target)
        self.assertEqual((self.tree / "src" / "retained.txt").read_text(encoding="utf-8"), "preserve the original source work")
        self.assertNotEqual(task["state"], "done")

    def critical_gate(self, *, contracted=True, resume=False):
        self.owner(contracted=contracted, critical=True)
        self.assertIn("Critical questions", self.sw("start", "--as", "ann", cwd=self.tree, ok=False))
        self.loss()
        who = "ann" if resume else "bob"
        if resume:
            self.sw("join", "--as", "ann", "--kind", "fake", "--resume", "--pid", str(os.getpid()))
        else:
            self.sw("claim", "T5", "--as", "bob", "--take-over")
        before = dict(self.task("T5"))
        self.assertEqual(before["state"], "awaiting_answers")
        self.assertIn("in progress", self.sw("step", "1", "--as", who, "--evidence", "The retained fixture still awaits a critical answer.", cwd=self.tree, ok=False))
        self.assertIn("Critical questions", self.sw("start", "--as", who, cwd=self.tree, ok=False))
        self.assertEqual(self.task("T5")["step_idx"], 0)
        self.assert_work_preserved()
        with self.board() as board:
            self.assertEqual(board.db.execute("SELECT count(*) FROM questions WHERE critical=1 AND answer IS NULL AND waived=0").fetchone()[0], 1)

    def test_ec351_dead_owners_uncommitted_work_is_snapshotted_and_flagged_unverified(self):
        self.owner(progress=True)
        (self.tree / "src" / "unsaved.txt").write_text("recorded as done but never committed", encoding="utf-8")
        status_before = self.git("status", "--porcelain", cwd=self.tree)
        self.loss()
        # The snapshot leaves the worktree, its index and its branch exactly as the dead owner left them.
        self.assertEqual(self.git("status", "--porcelain", cwd=self.tree), status_before)
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.tree).strip(), self.head)
        ref = self.git("for-each-ref", "--format=%(refname)", "refs/swarm/rescue/T5").strip()
        self.assertTrue(ref.startswith("refs/swarm/rescue/T5/e"), ref)
        self.assertEqual(self.git("show", f"{ref}:src/unsaved.txt").strip(), "recorded as done but never committed")
        self.assertEqual(self.git("rev-parse", f"{ref}^").strip(), self.head)
        with self.board() as sw:
            detail = sw.db.execute("SELECT detail FROM events WHERE kind='task_orphaned' AND task='T5'").fetchone()[0]
        self.assertIn("UNVERIFIED", detail)
        self.assertIn("1 uncommitted file(s)", detail)
        self.assertIn(ref, detail)
        explained = self.sw("explain", "T5")
        self.assertIn("progress: 1 step(s) recorded", explained)
        self.assertIn("UNVERIFIED", explained)
        claimed = self.sw("claim", "T5", "--as", "bob", "--take-over")
        self.assertIn("UNVERIFIED PROGRESS", claimed)
        self.assertIn("uncommitted: src/unsaved.txt", claimed)
        self.assertIn(ref, claimed)
        self.assertEqual((self.tree / "src" / "unsaved.txt").read_text(encoding="utf-8"), "recorded as done but never committed")
        with self.board() as sw:
            self.assertEqual(sw.db.execute("SELECT count(*) FROM events WHERE kind='takeover_unverified'").fetchone()[0], 1)

    def test_ec351_fully_committed_work_is_not_flagged_and_leaves_no_snapshot(self):
        self.owner(progress=True)
        self.loss()
        self.assertEqual(self.git("for-each-ref", "refs/swarm/rescue").strip(), "")
        with self.board() as sw:
            detail = sw.db.execute("SELECT detail FROM events WHERE kind='task_orphaned' AND task='T5'").fetchone()[0]
        self.assertNotIn("UNVERIFIED", detail)
        self.assertIn("0 uncommitted file(s)", detail)
        self.assertNotIn("UNVERIFIED", self.sw("claim", "T5", "--as", "bob", "--take-over"))

    def test_ec317_contracted_takeover_cannot_bypass_unanswered_start_questions(self):
        self.critical_gate()

    def test_ec317_legacy_takeover_uses_the_same_start_gate(self):
        self.critical_gate(contracted=False)

    def test_ec317_returning_owner_revalidates_unanswered_questions(self):
        self.critical_gate(resume=True)

    def test_ec317_answers_still_require_replanning_after_takeover(self):
        self.owner(critical=True)
        self.sw("answer", "1", "--from-human", "The fixture risk is low; preserve the current scope.")
        self.loss()
        self.sw("claim", "T5", "--as", "bob", "--take-over")
        self.assertEqual(self.task("T5")["state"], "planning")
        self.assertEqual(self.task("T5")["needs_replan"], 1)
        self.assertIn("re-run", self.sw("start", "--as", "bob", cwd=self.tree, ok=False))
        self.sw("plan", "--as", "bob", "--set", "risks=low", cwd=self.tree)
        self.sw("start", "--as", "bob", cwd=self.tree)
        self.assertIsNotNone(self.contract()["active_since"])
        self.assertEqual(self.task("T5")["state"], "in_progress")

    def test_ec318_running_takeover_preserves_progress_and_remaining_allowance_then_restarts_clock(self):
        self.owner(progress=True)
        original = self.contract()
        self.loss()
        lost = self.contract()
        self.assertIsNone(lost["active_since"])
        self.assertGreaterEqual(lost["active_seconds"], 60)
        self.assertIsNotNone(lost["blocked_at"])
        self.sql("UPDATE task_contracts SET blocked_at=? WHERE id=?", (core.iso(core.utcnow() - timedelta(seconds=30)), lost["id"]))
        self.sw("claim", "T5", "--as", "bob", "--take-over")
        current, closed = self.contract(), self.contract(first=True)
        terms, old_terms = json.loads(current["terms"]), json.loads(original["terms"])
        self.assertEqual(self.task("T5")["state"], "planning")
        self.assertEqual(self.task("T5")["epoch"], self.saved["epoch"] + 1)
        self.assertIsNone(current["active_since"])
        self.assertEqual(closed["state"], "closed")
        self.assertGreaterEqual(closed["blocked_seconds"], 30)
        self.assertEqual(terms["deadline_at"], old_terms["deadline_at"])
        self.assertEqual(terms["budget"], old_terms["budget"])
        self.assertAlmostEqual(terms["active_time_min"], old_terms["active_time_min"] - lost["active_seconds"] / 60)
        self.assert_work_preserved()
        self.assertIn("in progress", self.sw("step", "2", "--as", "bob", "--evidence", "The retained commit is ready for the resumed start gate.", cwd=self.tree, ok=False))
        self.sw("start", "--as", "bob", cwd=self.tree)
        self.assertIsNotNone(self.contract()["active_since"])
        self.sql("UPDATE task_contracts SET active_since=? WHERE id=?", (core.iso(core.utcnow() - timedelta(seconds=15)), current["id"]))
        self.sw("step", "2", "--as", "bob", "--evidence", "Committed the retained src/retained.txt source fixture.", cwd=self.tree)
        self.assertGreaterEqual(core.contract_elapsed(self.contract()), 15)
        self.sql("UPDATE task_contracts SET active_since=? WHERE id=?", (core.iso(core.utcnow() - timedelta(seconds=terms["active_time_min"] * 60 + 2)), current["id"]))
        self.sw("status")
        self.assertEqual(self.task("T5")["state"], "expired")
        self.assertTrue(self.tree.is_dir())
        self.assertEqual(self.git("rev-parse", "main").strip(), self.target)

    def test_ec318_returning_owner_resumes_the_same_clock_without_losing_progress(self):
        self.owner(progress=True)
        self.loss()
        lost = self.contract()
        self.assertIsNone(lost["active_since"])
        self.sql("UPDATE task_contracts SET blocked_at=? WHERE id=?", (core.iso(core.utcnow() - timedelta(seconds=30)), lost["id"]))
        self.sw("join", "--as", "ann", "--kind", "fake", "--resume", "--pid", str(os.getpid()))
        self.assertEqual(self.task("T5")["state"], "in_progress")  # nothing moved while away: the state is kept (EC-380)
        self.assertEqual(self.task("T5")["epoch"], self.saved["epoch"])
        self.assert_work_preserved()
        self.sw("start", "--as", "ann", cwd=self.tree)
        resumed = self.contract()
        self.assertEqual(resumed["id"], lost["id"])
        self.assertEqual(resumed["active_seconds"], lost["active_seconds"])
        self.assertIsNotNone(resumed["active_since"])
        self.assertIsNone(resumed["blocked_at"])
        self.assertGreaterEqual(resumed["blocked_seconds"], 30)

    def test_ec318_silent_owner_clock_pauses_before_reclaim_grace_and_rejoin_requires_start(self):
        self.owner(progress=True)
        self.sql("UPDATE agents SET heartbeat_at='2020-01-01T00:00:00+00:00' WHERE name='ann'")
        self.sw("status")
        lost = self.contract()
        self.assertEqual(self.task("T5")["state"], "in_progress")  # Still inside the reclaim grace period.
        self.assertIsNone(lost["active_since"])
        self.assertIsNotNone(lost["blocked_at"])
        self.sw("join", "--as", "ann", "--kind", "fake", "--resume", "--pid", str(os.getpid()))
        # Back within reclaim grace with nothing moved: the state and the running clock are restored (EC-380).
        self.assertEqual(self.task("T5")["state"], "in_progress")
        self.assertIsNotNone(self.contract()["active_since"])
        self.assert_work_preserved()

    def test_ec318_successor_deliberation_remains_bounded_before_restart(self):
        self.owner(progress=True)
        self.loss()
        self.sw("claim", "T5", "--as", "bob", "--take-over")
        self.assertEqual(self.task("T5")["state"], "planning")
        # A successor heard from during deliberation gets the one audited extension (EC-376): still bounded, at 2x.
        self.sql("UPDATE task_contracts SET deliberation_at=? WHERE id=?", (core.iso(core.utcnow() - timedelta(minutes=6)), self.contract()["id"]))
        self.sw("status")
        self.assertEqual(self.task("T5")["state"], "planning")
        self.sql("UPDATE task_contracts SET deliberation_at=? WHERE id=?", (core.iso(core.utcnow() - timedelta(minutes=11)), self.contract()["id"]))
        self.sw("status")
        self.assertEqual(self.task("T5")["state"], "expired")
        self.assertIn("expired", self.sw("start", "--as", "bob", cwd=self.tree, ok=False))
        self.assert_work_preserved()

    def test_ec318_owner_loss_cannot_cancel_an_elapsed_deliberation_cutoff(self):
        self.owner()
        self.sql("UPDATE task_contracts SET deliberation_at=? WHERE id=?", (core.iso(core.utcnow() - timedelta(minutes=6)), self.contract()["id"]))
        self.stop_worker()
        self.sw("status")
        self.assertEqual(self.contract()["state"], "expired")
        self.assertEqual(self.task("T5")["state"], "expired")
        self.assertIn("deliberation", self.sw("explain", "T5"))
        self.sw("claim", "T5", "--as", "bob", "--take-over", ok=False)
        self.assert_work_preserved()

    def test_ec318_observed_headless_exit_pauses_the_running_contract(self):
        self.configure_worker("cooperative")
        contracts.Architecture.build_goal(self)
        self.architecture("GL")
        self.sw("goal", "commit", "GL")
        try:
            self.sw("spawn", "hold", "--name", "bob", "--task", "H-api")
            tree = Path(self.task("H-api")["worktree"])
            self.wait_for(lambda: self.work_ready(tree))
            self.sw("plan", "--as", "bob", *fixtures.PLAN, cwd=tree)
            self.sw("start", "--as", "bob", cwd=tree)
            self.sql("UPDATE task_contracts SET active_since=? WHERE task='H-api'", (core.iso(core.utcnow() - timedelta(seconds=60)),))
            self.release.write_text("exit", encoding="utf-8")
            self.wait_for(lambda: self.execution()["state"] == "exited")
            with self.board() as board:
                contract = core.current_contract(board, "H-api")
                self.assertIsNone(contract["active_since"])
                self.assertGreaterEqual(contract["active_seconds"], 60)
                self.assertIsNotNone(contract["blocked_at"])
                self.assertEqual(board.task("H-api")["state"], "orphaned")
            self.assertTrue((tree / "unfinished.txt").is_file())
        finally:
            self.cleanup_worker()

    def test_ec318_observed_interactive_exit_pauses_the_running_contract(self):
        code = self.holding_program()
        self.configure_worker("cooperative", code=code)
        self.config("interactive = " + json.dumps([sys.executable, "-c", code]))
        contracts.Architecture.build_goal(self)
        self.architecture("GL")
        self.sw("goal", "commit", "GL")
        import threading

        errors, stop = [], threading.Event()

        def prepare_work():
            try:
                self.wait_for(lambda: stop.is_set() or self.task("H-api")["worktree"] and self.work_ready(Path(self.task("H-api")["worktree"])))
                if stop.is_set():
                    return
                tree = Path(self.task("H-api")["worktree"])
                self.sw("plan", "--as", "bob", *fixtures.PLAN, cwd=tree)
                self.sw("start", "--as", "bob", cwd=tree)
                self.sql("UPDATE task_contracts SET active_since=? WHERE task='H-api'", (core.iso(core.utcnow() - timedelta(seconds=60)),))
            except BaseException as exc:
                errors.append(exc)
            finally:
                self.release.write_text("exit", encoding="utf-8")

        controller = threading.Thread(target=prepare_work)
        controller.start()
        try:
            with (
                self.board() as board,
                mock.patch.object(core, "copy_to_clipboard", return_value=False),
                mock.patch.object(core.sys, "stdin", SimpleNamespace(isatty=lambda: False)),
            ):
                args = core.build_parser().parse_args(["launch", "hold", "--name", "bob", "--task", "H-api"])
                core.cmd_launch(board, args)
                controller.join(30)
                self.assertFalse(controller.is_alive())
                self.assertEqual(errors, [])
                contract = core.current_contract(board, "H-api")
                self.assertIsNone(contract["active_since"])
                self.assertGreaterEqual(contract["active_seconds"], 60)
                self.assertEqual(board.task("H-api")["state"], "orphaned")
                self.assertTrue((Path(board.task("H-api")["worktree"]) / "unfinished.txt").is_file())
        finally:
            stop.set()
            self.release.write_text("exit", encoding="utf-8")
            controller.join(30)
