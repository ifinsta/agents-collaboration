"""Interactive startup and exit must preserve replacement assignments/processes."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest import mock

import test_swarm as fixtures
from test_processes import ProcessCase, core


class InteractiveLaunch(ProcessCase):
    def launch_args(self, *extra, kind="fake"):
        return core.build_parser().parse_args(["launch", kind, "--name", "worker", *extra])

    def replace(self, old="T1", new="T2"):
        self.sw("release", "--task", old, "Preserve existing work before replacing the interactive assignment.")
        if new == old:
            self.sw("contract", "offer", new, "worker")
            self.sw("contract", "accept", new, "--as", "worker")
        self.sw("claim", new, "--as", "worker")
        with self.board() as board:
            return dict(board.agent("worker")), dict(board.task(new))

    def assert_stale_preparation_refused(self, *, automatic=False, same_task=False):
        self.join("ann")
        original = core.prepare_agent
        replacement = []

        def prepared(*args):
            task = original(*args)
            new = task["id"] if same_task else ("T2" if task["id"] == "T1" else "T1")
            replacement.append(self.replace(task["id"], new))
            return task

        args = self.launch_args(*([] if automatic else ["--task", "T1"]))
        with self.board() as board, mock.patch.object(core, "prepare_agent", side_effect=prepared):
            with self.assertRaisesRegex(core.SwarmError, "Assignment changed"):
                core.cmd_launch(board, args)
            agent, task = replacement[0]
            self.assertEqual(dict(board.agent("worker")), agent)
            self.assertEqual(dict(board.task(task["id"])), task)
            self.assertEqual(board.db.execute("SELECT count(*) FROM events WHERE kind='launched'").fetchone()[0], 0)

    def test_ec301_stale_explicit_interactive_preparation_is_refused(self):
        self.assert_stale_preparation_refused()

    def test_ec301_stale_automatic_interactive_preparation_is_refused(self):
        self.assert_stale_preparation_refused(automatic=True)

    def test_ec301_same_name_new_epoch_cannot_reuse_old_interactive_preparation(self):
        self.assert_stale_preparation_refused(same_task=True)

    def test_ec302_child_creation_and_pid_publication_share_the_ownership_fence(self):
        self.join("ann")
        original, observed = core.OwnedProcess, []

        def create(*args, **kwargs):
            if kwargs.get("interactive"):
                db = self.db()
                try:
                    db.execute("PRAGMA busy_timeout=0")
                    with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                        db.execute("BEGIN IMMEDIATE")
                finally:
                    db.close()
                observed.append(True)
            return original(*args, **kwargs)

        with self.board() as board, mock.patch.object(core, "OwnedProcess", side_effect=create):
            core.cmd_launch(board, self.launch_args("--task", "T1"))
            self.assertEqual(board.agent("worker")["state"], "offline")
            self.assertEqual(board.task("T1")["state"], "open")
        self.assertEqual(observed, [True])

    def assert_startup_control_refused(self, *, policy=False):
        self.join("ann")
        original = core.prepare_agent
        config = self.root / ".agents" / "swarm" / "config.toml"

        def prepared(*args):
            task = original(*args)
            if policy:
                config.write_text(config.read_text(encoding="utf-8") + "\n# changed startup policy\n", encoding="utf-8")
            else:
                self.sw("pause", "Pause while an interactive command is still being prepared.")
            return task

        with self.board() as board, mock.patch.object(core, "prepare_agent", side_effect=prepared):
            with self.assertRaisesRegex(core.SwarmError, "policy changed|paused"):
                core.cmd_launch(board, self.launch_args("--task", "T1"))
            self.assertEqual(board.agent("worker")["state"], "busy")
            self.assertIsNone(board.agent("worker")["pid"])
            self.assertEqual(board.task("T1")["state"], "claimed")

    def test_ec305_interactive_launch_rechecks_pause_after_preparation(self):
        self.assert_startup_control_refused()

    def test_ec305_interactive_launch_rechecks_policy_after_preparation(self):
        self.assert_startup_control_refused(policy=True)

    def test_ec301_replacement_process_in_the_same_lease_prevents_interactive_startup(self):
        self.join("ann")
        original = core.prepare_agent
        replacement = []

        def prepared(*args):
            task = original(*args)
            self.sw("join", "--kind", "fake", "--as", "worker", "--resume", "--pid", str(os.getpid()))
            with self.board() as board:
                replacement.append((dict(board.agent("worker")), dict(board.task("T1"))))
            return task

        with self.board() as board, mock.patch.object(core, "prepare_agent", side_effect=prepared):
            with self.assertRaisesRegex(core.SwarmError, "process changed"):
                core.cmd_launch(board, self.launch_args("--task", "T1"))
            agent, task = replacement[0]
            self.assertEqual(dict(board.agent("worker")), agent)
            self.assertEqual(dict(board.task("T1")), task)

    def test_ec305_stopped_coordinator_cannot_finish_interactive_startup(self):
        self.join("ann")
        parent = "c" * 32
        with self.board() as board, board.tx():
            board.db.execute(
                "INSERT INTO executions(id,agent,task,epoch,state,supervisor_pid,started_at,heartbeat_at,policy) VALUES(?,?,?,0,'running',?,?,?,?)",
                (parent, "ann", "T1", os.getpid(), core.iso(), core.iso(), json.dumps(board.config["spawn"])),
            )
        original = core.prepare_agent

        def prepared(*args):
            task = original(*args)
            self.sw("execution", "stop", parent, "--reason", "Stop the coordinator during interactive preparation.")
            return task

        with (
            self.board() as board,
            mock.patch.dict(os.environ, {"SWARM_EXECUTION_ID": parent}),
            mock.patch.object(core, "prepare_agent", side_effect=prepared),
        ):
            with self.assertRaisesRegex(core.SwarmError, "coordinator.*stopping"):
                core.cmd_launch(board, self.launch_args("--task", "T1", "--as", "ann"))
            self.assertIsNone(board.agent("worker")["pid"])
            self.assertEqual(board.task("T1")["assignee"], "worker")
            self.assertEqual(board.db.execute("SELECT count(*) FROM events WHERE kind='launched'").fetchone()[0], 0)


    def test_ec307_interactive_process_creation_failure_preserves_the_claim(self):
        self.join("ann")
        original = core.OwnedProcess

        def denied(*args, **kwargs):
            if kwargs.get("interactive"):
                raise OSError("controlled executable creation refusal")
            return original(*args, **kwargs)

        with self.board() as board, mock.patch.object(core, "OwnedProcess", side_effect=denied):
            with self.assertRaisesRegex(core.SwarmError, "Work was retained.*whoami"):
                core.cmd_launch(board, self.launch_args("--task", "T1"))
            self.assertEqual(board.task("T1")["state"], "claimed")
            self.assertEqual(board.agent("worker")["state"], "busy")
            execution = board.db.execute("SELECT * FROM executions WHERE agent='worker'").fetchone()
            self.assertEqual(execution["state"], "unknown")
            self.assertIsNone(execution["child_pid"])
            self.assertEqual(board.agent("worker")["pid"], os.getpid())
            self.assertTrue(Path(board.task("T1")["worktree"]).is_dir())


    def test_ec309_refused_sqlite_commit_rolls_back_and_releases_the_writer(self):
        self.join("ann")

        def deny_commit(action, arg1, arg2, database, trigger):
            return (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT"
                else sqlite3.SQLITE_OK
            )

        with self.board() as board:
            before = dict(board.task("T1"))
            board.db.set_authorizer(deny_commit)
            try:
                with self.assertRaises(sqlite3.DatabaseError):
                    with board.tx():
                        board.update_task("T1", title="This uncommitted edit must roll back.")
                        board.event("controlled_uncommitted_event", "ann", "T1", "This event must roll back too.")
                self.assertFalse(board.db.in_transaction)
                other = self.db()
                try:
                    other.execute("PRAGMA busy_timeout=0")
                    other.execute("BEGIN IMMEDIATE")
                    other.execute("ROLLBACK")
                finally:
                    other.close()
                self.assertEqual(dict(board.task("T1")), before)
                self.assertIsNone(board.db.execute("SELECT 1 FROM events WHERE kind='controlled_uncommitted_event'").fetchone())
            finally:
                board.db.set_authorizer(None)

    def test_ec344_default_launch_retains_an_execution_and_reliable_inbox(self):
        self.join("ann")
        with self.board() as board:
            core.cmd_launch(board, self.launch_args("--task", "T1"))
            row = board.db.execute("SELECT * FROM executions WHERE agent='worker'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["state"], "exited")
            self.assertIsNotNone(row["child_pid"])
            self.assertEqual(board.task("T1")["state"], "open")
            self.assertTrue((board.dir / "inboxes" / (row["id"] + ".json")).is_file())

    def test_ec304_ec344_retired_launch_options_are_refused_before_registration(self):
        for option in ("--no-task", "--supervised"):
            with self.subTest(option=option):
                self.assertIn("unrecognized arguments", self.sw("launch", "fake", "--name", "worker", option, ok=False))
        self.assertNotIn("worker", self.sw("agents"))

    def test_ec303_late_finalization_preserves_a_replacement_process_and_assignment(self):
        self.join("ann")
        original, owned = core.OwnedProcess, []

        def create(*args, **kwargs):
            process = original(*args, **kwargs)
            if kwargs.get("interactive"):
                owned.append(process)
            return process

        replacement = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            with self.board() as board, mock.patch.object(core, "OwnedProcess", side_effect=create):
                core.cmd_launch(board, self.launch_args("--task", "T1"))
                row = board.db.execute("SELECT * FROM executions WHERE agent='worker'").fetchone()
                self.sw("join", "--kind", "fake", "--as", "worker", "--resume", "--pid", str(replacement.pid))
                self.sw("claim", "T2", "--as", "worker")
                agent, task = dict(board.agent("worker")), dict(board.task("T2"))
                with board.tx():
                    core.finish_execution(board, row, owned[0], 1)
                self.assertEqual(dict(board.agent("worker")), agent)
                self.assertEqual(dict(board.task("T2")), task)
                self.assertIsNone(replacement.poll())
        finally:
            replacement.terminate()
            replacement.wait(timeout=10)

    def test_ec306_exit_settles_the_current_task_of_its_owned_worker(self):
        self.join("ann")
        original, changed = core.OwnedProcess, []

        def create(*args, **kwargs):
            process = original(*args, **kwargs)
            if kwargs.get("interactive"):
                active = process.active

                def observe():
                    running = active()
                    if not running and not changed:
                        _, task = self.replace()
                        tree = Path(task["worktree"])
                        self.sw("plan", "--as", "worker", *fixtures.PLAN, "--set", "scope=docs/", cwd=tree)
                        self.sw("start", "--as", "worker", cwd=tree)
                        (tree / "docs").mkdir(exist_ok=True)
                        (tree / "docs/unfinished.txt").write_text("preserve current work", encoding="utf-8")
                        changed.append((tree, self.task("T2")["epoch"]))
                    return running

                process.active = observe
            return process

        with self.board() as board, mock.patch.object(core, "OwnedProcess", side_effect=create):
            core.cmd_launch(board, self.launch_args("--task", "T1"))
            self.assertEqual(board.agent("worker")["state"], "offline")
            self.assertEqual(board.task("T2")["state"], "orphaned")
            self.assertEqual(board.task("T2")["epoch"], changed[0][1])
            self.assertIsNone(core.current_contract(board, "T2")["active_since"])
            self.assertTrue((changed[0][0] / "docs/unfinished.txt").is_file())
