"""A delayed Git allocation must never mutate a newer assignment."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from unittest import mock

from test_hardening import HardeningCase, core


class ClaimAllocation(HardeningCase):
    def setUp(self):
        super().setUp()
        self.join("ann")
        self.join("bob")

    def claim_thread(self, task, errors, prepare=False):
        sw = core.Swarm(self.root)
        try:
            if prepare:
                core.prepare_agent(sw, "claude", "ann", "", "", task)
            else:
                core.claim(sw, "ann", task, False, False)
        except BaseException as exc:
            errors.append(exc)
        finally:
            sw.db.close()

    def race(self, task, replacement, *, failure, prepare=False, replacement_task=None):
        entered, resume = threading.Event(), threading.Event()
        original = core.ensure_worktree
        errors = []

        def allocation(sw, ident, branch):
            if threading.current_thread().name != "old-claim":
                return original(sw, ident, branch)
            path = None if failure else original(sw, ident, branch)
            entered.set()
            if not resume.wait(30):
                raise RuntimeError("fixture allocation control timed out")
            if failure:
                raise core.SwarmError("Controlled late allocation failure")
            return path

        with mock.patch.object(core, "ensure_worktree", side_effect=allocation):
            thread = threading.Thread(target=self.claim_thread, args=(task, errors, prepare), name="old-claim")
            thread.start()
            try:
                self.assertTrue(entered.wait(30), errors)
                self.sw("release", "--task", task, "Release pending setup so the next assignment can continue safely.")
                self.sw("claim", replacement_task or task, "--as", replacement)
                before = dict(self.task(replacement_task or task))
                tree = Path(before["worktree"])
                (tree / "new-owner.txt").write_text("preserve newer work", encoding="utf-8")
                settings = tree / ".test-settings"
                if settings.exists():
                    settings.unlink()
                if not failure:
                    (self.root / ".test-settings").write_text("stale setup must not copy this", encoding="utf-8")
            finally:
                resume.set()
                thread.join(30)
            self.assertFalse(thread.is_alive())
        after = dict(self.task(replacement_task or task))
        self.assertEqual(after, before)
        self.assertEqual((tree / "new-owner.txt").read_text(encoding="utf-8"), "preserve newer work")
        self.assertFalse(settings.exists())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], core.SwarmError)
        with self.board() as sw:
            self.assertEqual(sw.agent(replacement)["task"], replacement_task or task)
            self.assertEqual(sw.agent(replacement)["state"], "busy")
        return errors[0]

    def test_ec286_stale_allocation_failure_cannot_release_new_owner_or_new_epoch(self):
        for task, replacement in (("T5", "bob"), ("T1", "ann")):
            with self.subTest(replacement=replacement):
                error = self.race(task, replacement, failure=True)
                self.assertIn("Controlled late allocation failure", str(error))
                if task == "T5":
                    with self.board() as sw:
                        lock = sw.db.execute("SELECT agent,task FROM locks WHERE name='config'").fetchone()
                        self.assertEqual(tuple(lock), ("bob", "T5"))
        self.sw("release", "--as", "ann", "Preserve the newer work before exercising a fresh preparation attempt.")
        self.sw("leave", "--as", "ann")
        self.race("T2", "ann", failure=True, prepare=True, replacement_task="T1")

    def test_ec287_stale_success_cannot_publish_paths_or_copy_local_settings(self):
        ignore = self.root / ".gitignore"
        ignore.write_text(ignore.read_text(encoding="utf-8") + ".test-settings\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "ignore local test settings")
        self.config('[worktree]\ncopy = [".test-settings"]')
        (self.root / ".test-settings").write_text("initial local settings", encoding="utf-8")
        self.assertIn("Assignment changed", str(self.race("T1", "bob", failure=False)))

    def test_ec288_local_file_copy_holds_the_ownership_transaction(self):
        entered, resume = threading.Event(), threading.Event()
        original, errors = core.copy_into_worktree, []

        def copying(sw, path):
            entered.set()
            if not resume.wait(30):
                raise RuntimeError("fixture copy control timed out")
            return original(sw, path)

        with mock.patch.object(core, "copy_into_worktree", side_effect=copying):
            thread = threading.Thread(target=self.claim_thread, args=("T1", errors))
            thread.start()
            try:
                self.assertTrue(entered.wait(30), errors)
                db = self.db()
                try:
                    db.execute("PRAGMA busy_timeout=0")
                    with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                        db.execute("BEGIN IMMEDIATE")
                finally:
                    db.close()
            finally:
                resume.set()
                thread.join(30)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.task("T1")["assignee"], "ann")
        self.assertTrue(Path(self.task("T1")["worktree"]).exists())

    def test_ec289_copy_failure_keeps_known_worktree_and_partial_files_inspectable(self):
        def failed_copy(sw, path):
            (path / "partial-settings.txt").write_text("preserve partial copy", encoding="utf-8")
            raise OSError("controlled local-copy failure")

        with self.board() as sw, mock.patch.object(core, "copy_into_worktree", side_effect=failed_copy):
            with self.assertRaisesRegex(core.SwarmError, "Worktree retained"):
                core.claim(sw, "ann", "T1", False, False)
            task = sw.task("T1")
            self.assertEqual(task["state"], "claimed")
            self.assertEqual(task["assignee"], "ann")
            self.assertEqual(
                (Path(task["worktree"]) / "partial-settings.txt").read_text(encoding="utf-8"), "preserve partial copy"
            )
            self.assertEqual(
                sw.db.execute("SELECT count(*) FROM events WHERE kind='claim_setup_failed'").fetchone()[0], 1
            )

    def test_ec290_interrupted_allocation_keeps_a_path_for_checkpoint_and_handoff(self):
        entered, resume = threading.Event(), threading.Event()
        original, errors = core.ensure_worktree, []

        def allocation(sw, task, branch):
            entered.set()
            if not resume.wait(30):
                raise RuntimeError("fixture allocation control timed out")
            path = original(sw, task, branch)
            (path / "partial-work.txt").write_text("preserve setup work", encoding="utf-8")
            return path

        with mock.patch.object(core, "ensure_worktree", side_effect=allocation):
            thread = threading.Thread(target=self.claim_thread, args=("T1", errors))
            thread.start()
            try:
                self.assertTrue(entered.wait(30), errors)
                self.sw(
                    "interrupt",
                    "request",
                    "ann",
                    "--mode",
                    "pause",
                    "--reason",
                    "Pause while allocation is still preparing its Git worktree.",
                )
                with self.board() as sw:
                    control = sw.db.execute("SELECT max(id) FROM interrupts").fetchone()[0]
                task = self.task("T1")
                self.sw("interrupt", "ack", str(control), "--as", "ann", "--epoch", str(task["epoch"]))
                self.assertIsNotNone(task["worktree"])
                self.assertFalse(Path(task["worktree"]).exists())
                args = (
                    "checkpoint",
                    "--as",
                    "ann",
                    "--epoch",
                    str(task["epoch"]),
                    "--note",
                    "Allocation is interrupted before implementation begins",
                    "--next",
                    "Review the retained allocation before continuing implementation",
                )
                self.assertIn("still creating", self.sw(*args, ok=False))
            finally:
                resume.set()
                thread.join(30)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIn("Assignment changed", str(errors[0]))
        self.assertFalse(Path(task["worktree"]).exists())
        self.sw("allocation", "prepare", "T1", "--as", "ann")
        (Path(task["worktree"]) / "partial-work.txt").write_text("preserve setup work", encoding="utf-8")
        self.sw(*args)
        with self.board() as sw:
            checkpoint = sw.db.execute("SELECT max(id) FROM checkpoints").fetchone()[0]
        self.sw(
            "handoff",
            "--as",
            "ann",
            "--epoch",
            str(task["epoch"]),
            "--checkpoint",
            str(checkpoint),
            "--note",
            "Preserve allocation and checkpoint for the next bounded assignment",
        )
        self.assertEqual(self.task("T1")["state"], "open")
        self.assertEqual(
            (Path(task["worktree"]) / "partial-work.txt").read_text(encoding="utf-8"), "preserve setup work"
        )
