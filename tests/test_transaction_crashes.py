"""Kill actual CLIs on both sides of lifecycle commits, then recover real SQLite/Git."""

from __future__ import annotations

import json
from pathlib import Path

import test_claim_crashes as crashes
from test_hardening import HardeningCase, fixtures


class TransactionCrashes(HardeningCase):
    paused = crashes.ClaimCrashes.paused
    kill = crashes.ClaimCrashes.kill

    def meta(self, key):
        with self.board() as sw:
            return sw.meta(key)

    def snapshot(self):
        db = self.db()
        try:
            result = {table: [tuple(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                      for table in ("tasks", "agents", "questions", "task_contracts", "locks", "messages", "events")}
            if getattr(self, "allow_preflight_heartbeat", False):
                index = [r[1] for r in db.execute("PRAGMA table_info(agents)")].index("heartbeat_at")
                result["agents"] = [r[:index] + (None,) + r[index + 1:] for r in result["agents"]]
            return result
        finally:
            db.close()

    def boundary(self, command, label, check):
        self.sw("status")
        before = self.snapshot()
        target = self.git("rev-parse", "main")
        with self.paused(f"before_{label}_commit", *command) as child:
            self.kill(child)
        self.sw("status")
        self.assertEqual(self.snapshot(), before)
        with self.paused(f"after_{label}_commit", *command) as child:
            self.kill(child)
        self.sw("status")
        check()
        after = self.snapshot()
        self.sw("status")
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(self.git("rev-parse", "main"), target)

    def held(self, *, planned=False, running=False):
        self.join("ann")
        self.sw("claim", "T1", "--as", "ann")
        if planned or running:
            self.sw("plan", "--as", "ann", *fixtures.PLAN)
        if running:
            self.sw("start", "--as", "ann")

    def test_ec322_plan_commit_kills_retain_exact_revision_and_no_false_start(self):
        self.held()
        self.boundary(["plan", "--as", "ann", *fixtures.PLAN], "cmd_plan",
                      lambda: self.assertEqual(self.task("T1")["state"], "planning"))
        self.assertIsNotNone(self.task("T1")["plan"])
        self.assertIsNone(self.task("T1")["started_at"])

    def test_ec322_start_commit_kills_preserve_clocks_and_ownership(self):
        self.held(planned=True)
        self.boundary(["start", "--as", "ann"], "cmd_start",
                      lambda: self.assertEqual(self.task("T1")["state"], "in_progress"))
        self.assertIsNotNone(self.task("T1")["started_at"])

    def test_ec322_step_commit_kills_never_skip_a_step(self):
        self.held(running=True)
        self.boundary(["step", "1", "--as", "ann", "--evidence", "Retained evidence for the first implementation step"], "cmd_step",
                      lambda: self.assertEqual(self.task("T1")["step_idx"], 1))
        steps = json.loads(self.task("T1")["steps"])
        self.assertTrue(steps[0]["done"])
        self.assertFalse(steps[1]["done"])

    def test_ec322_submission_commit_kills_preserve_committed_work_without_integrating(self):
        self.held(running=True)
        tree = Path(self.task("T1")["worktree"])
        (tree / "src").mkdir(exist_ok=True)
        (tree / "src/work.txt").write_text("retained implementation", encoding="utf-8")
        self.sw("step", "1", "--as", "ann", "--evidence", "Implemented the retained source file")
        self.git("add", ".", cwd=tree)
        self.git("commit", "-qm", "retained implementation", cwd=tree)
        self.sw("step", "2", "--as", "ann", "--evidence", "Committed the retained implementation")
        # Submit commits a liveness observation before gathering Git evidence.
        # Its later publication must roll back exactly; that earlier heartbeat is legitimate.
        self.allow_preflight_heartbeat = True
        with self.board() as sw:
            observed_before = sw.agent("ann")["heartbeat_at"]
        self.boundary(["submit", "--as", "ann", "--evidence", "Implementation committed; merge will run configured checks"], "submit_publication",
                      lambda: self.assertEqual(self.task("T1")["state"], "ready_to_merge"))
        with self.board() as sw:
            self.assertGreaterEqual(sw.agent("ann")["heartbeat_at"], observed_before)
        self.assertEqual((tree / "src/work.txt").read_text(encoding="utf-8"), "retained implementation")

    def test_ec323_question_and_late_answer_commit_kills_preserve_start_refusal(self):
        self.held(planned=True)
        self.boundary(["ask", "Which API response is the accepted contract?", "--as", "ann", "--critical", "--to", "human"], "cmd_ask",
                      lambda: self.assertEqual(self.task("T1")["state"], "awaiting_answers"))
        with self.board() as sw:
            qid = sw.db.execute("SELECT max(id) FROM questions").fetchone()[0]
        self.boundary(["answer", str(qid), "Use the documented versioned API response contract"], "cmd_answer",
                      lambda: self.assertEqual(self.task("T1")["state"], "planning"))
        self.assertEqual(self.task("T1")["needs_replan"], 1)
        self.assertIn("plan", self.sw("start", "--as", "ann", ok=False))

    def test_ec323_pause_and_resume_commit_kills_preserve_global_control(self):
        self.held()
        self.boundary(["pause", "Inspect current work before allowing new execution"], "cmd_pause",
                      lambda: self.assertIsNotNone(self.meta("paused")))
        self.boundary(["resume"], "cmd_resume", lambda: self.assertIsNone(self.meta("paused")))

    def test_ec323_contract_offer_commit_kills_do_not_duplicate_terms_or_acceptance(self):
        self.join("ann")
        def check():
            with self.board() as sw:
                rows = sw.db.execute("SELECT * FROM task_contracts WHERE task='T1'").fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["state"], "offered")
        self.boundary(["contract", "offer", "T1", "ann", "--as", "human"], "cmd_contract", check)
