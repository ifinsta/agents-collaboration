"""Startup must retain its original task/epoch through brief and process handoff."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_processes import ProcessCase, core


class StartupFences(ProcessCase):
    def replace(self, task="T2", old="T1"):
        self.sw("release", "--task", old, "Preserve this work while replacing the pending startup assignment.")
        self.sw("claim", task, "--as", "worker")
        return dict(self.task(task))

    def test_ec291_preparation_cannot_write_a_brief_for_a_newer_assignment(self):
        self.join("ann")
        original = core.claim
        for requested, newer in (("T1", "T2"), ("", "T1")):
            with self.subTest(requested=requested):
                # Use a fresh registration after each completed scenario.
                if requested == "":
                    self.sw(
                        "release", "--as", "worker", "Retain the prior scenario before another preparation attempt."
                    )
                    self.sw("leave", "--as", "worker")
                    self.sw(
                        "release",
                        "--task",
                        "T1",
                        "Release any original allocation retained from the previous scenario.",
                        ok=None,
                    )
                entered, resume, errors, selected = threading.Event(), threading.Event(), [], []

                def claimed(*args, entered=entered, resume=resume, selected=selected, **kwargs):
                    result = original(*args, **kwargs)
                    selected.append(args[2])
                    entered.set()
                    if not resume.wait(30):
                        raise RuntimeError("fixture preparation control timed out")
                    return result

                def prepare(requested=requested, errors=errors):
                    sw = core.Swarm(self.root)
                    try:
                        core.prepare_agent(sw, "fake", "worker", "", "", requested)
                    except BaseException as exc:
                        errors.append(exc)
                    finally:
                        sw.db.close()

                with mock.patch.object(core, "claim", side_effect=claimed):
                    thread = threading.Thread(target=prepare)
                    thread.start()
                    try:
                        self.assertTrue(entered.wait(30), errors)
                        before = self.replace(newer, old=selected[0])
                        tree = Path(before["worktree"])
                        brief = tree / core.BRIEF_NAME
                        if brief.exists():
                            brief.unlink()
                    finally:
                        resume.set()
                        thread.join(30)
                self.assertFalse(thread.is_alive())
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], core.SwarmError)
                self.assertFalse(brief.exists())
                self.assertEqual(dict(self.task(newer)), before)
                with self.board() as sw:
                    self.assertEqual(sw.agent("worker")["state"], "busy")

    def test_ec294_pid_publication_cannot_overwrite_a_newer_assignment(self):
        marker = Path(self.tmp.name) / "must-not-launch"
        self.configure_worker(code=f"from pathlib import Path; Path({str(marker)!r}).touch()")
        original, created, newer = core.subprocess.Popen, [], []

        def started(argv, *args, **kwargs):
            proc = original(argv, *args, **kwargs)
            if len(argv) > 2 and argv[2] == "__supervise":
                created.append(proc)
                newer.append(self.replace())
            return proc

        args = core.build_parser().parse_args(["spawn", "hold", "--name", "worker", "--task", "T1"])
        try:
            with self.board() as sw, mock.patch.object(core.subprocess, "Popen", side_effect=started):
                with self.assertRaises(core.SwarmError):
                    core.cmd_spawn(sw, args)
                self.assertEqual(sw.agent("worker")["task"], "T2")
                self.assertEqual(sw.agent("worker")["state"], "busy")
                self.assertIsNone(sw.agent("worker")["pid"])
                self.assertEqual(dict(sw.task("T2")), newer[0])
                row = sw.db.execute("SELECT * FROM executions").fetchone()
                self.assertEqual(row["state"], "failed")
                self.assertIsNone(row["child_pid"])
            self.assertFalse(marker.exists())
            self.assertIsNotNone(created[0].poll())
        finally:
            for proc in created:
                if proc.stdin and not proc.stdin.closed:
                    proc.stdin.close()
                if proc.poll() is None:
                    proc.terminate()  # Actual helper handle owned by this fixture, never a registry PID.
                proc.wait(timeout=10)

    def test_ec292_brief_writes_are_serialized_with_ownership(self):
        self.join("ann")
        original = core.write_brief
        observed = []

        def writing(*args):
            db = self.db()
            try:
                db.execute("PRAGMA busy_timeout=0")
                with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                    db.execute("BEGIN IMMEDIATE")
            finally:
                db.close()
            observed.append(args[3]["id"])
            return original(*args)

        with self.board() as sw, mock.patch.object(core, "write_brief", side_effect=writing):
            task = core.prepare_agent(sw, "fake", "worker", "", "", "T1")
        self.assertEqual(observed, ["T1"])
        self.assertTrue((Path(task["worktree"]) / core.BRIEF_NAME).exists())

    def test_ec293_stale_preparation_cannot_create_a_startup_intent(self):
        self.join("ann")
        original = core.prepare_agent

        def prepared(*args):
            result = original(*args)
            self.replace()
            return result

        args = core.build_parser().parse_args(["spawn", "fake", "--name", "worker", "--task", "T1"])
        with self.board() as sw, mock.patch.object(core, "prepare_agent", side_effect=prepared):
            with self.assertRaisesRegex(core.SwarmError, "Assignment changed"):
                core.cmd_spawn(sw, args)
            self.assertEqual(sw.db.execute("SELECT count(*) FROM executions").fetchone()[0], 0)
            self.assertEqual(sw.agent("worker")["task"], "T2")
            self.assertIsNone(sw.agent("worker")["pid"])

    def embedded_startup(self, *, stop=False):
        self.join("ann")
        self.join("worker")
        self.sw("claim", "T1", "--as", "worker")
        marker = Path(self.tmp.name) / "must-not-start"
        execution = "e" * 32
        sw = core.Swarm(self.root)
        task = sw.task("T1")
        packet = {
            "argv": [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"],
            "cwd": task["worktree"],
        }
        with sw.tx():
            sw.update_agent("worker", pid=os.getpid())
            sw.db.execute(
                "INSERT INTO executions(id,agent,task,epoch,state,supervisor_pid,started_at,heartbeat_at,policy) VALUES(?,?,?,?,'starting',?,?,?,?)",
                (
                    execution,
                    "worker",
                    "T1",
                    task["epoch"],
                    os.getpid(),
                    core.iso(),
                    core.iso(),
                    json.dumps(sw.config["spawn"]),
                ),
            )
        original = core.BoundedExecutionOutput
        changed = []

        def opened(*args, **kwargs):
            output = original(*args, **kwargs)
            if stop:
                self.sw(
                    "execution", "stop", execution, "--reason", "Stop this assignment before its worker command starts."
                )
            else:
                changed.append(self.replace())
            return output

        try:
            with (
                mock.patch.object(core, "Swarm", return_value=sw),
                mock.patch.object(core, "BoundedExecutionOutput", side_effect=opened),
                mock.patch.object(
                    core.sys, "stdin", SimpleNamespace(buffer=io.BytesIO((json.dumps(packet) + "\n").encode()))
                ),
            ):
                with self.assertRaises(core.SwarmError):
                    core.supervise_execution(execution)
            self.assertFalse(marker.exists())
            with self.board() as fresh:
                row = core.execution_row(fresh, execution)
                self.assertEqual(row["state"], "failed")
                self.assertIsNone(row["child_pid"])
                self.assertIsNone(fresh.agent("worker")["pid"])
                if not stop:
                    self.assertEqual(dict(fresh.task("T2")), changed[0])
                    self.assertEqual(fresh.agent("worker")["state"], "busy")
        finally:
            sw.db.close()

    def test_ec295_supervisor_rechecks_assignment_before_creating_a_worker(self):
        self.embedded_startup()

    def test_ec296_stop_during_startup_never_launches_a_worker(self):
        self.embedded_startup(stop=True)
        self.assertEqual(self.task("T1")["state"], "interrupted")

    def test_ec297_handoff_commit_crashes_never_invent_worker_start(self):
        marker = Path(self.tmp.name) / "worker-launched"
        code = (
            "from pathlib import Path; Path('unfinished.txt').write_text('retained'); "
            + f"Path({str(marker)!r}).touch()"
        )
        self.configure_worker(code=code)
        for when, name, task in (("before", "worker", "T1"), ("after", "other", "T2")):
            with self.subTest(when=when):
                result = self.sw(
                    "spawn",
                    "hold",
                    "--name",
                    name,
                    "--task",
                    task,
                    ok=None,
                    env={"SWARM_FAILPOINT": f"{when}_execution_handoff_commit"},
                )
                self.assertNotIn("Traceback", result)
                row = self.execution()
                if when == "before":
                    self.assertIsNone(row["supervisor_pid"])
                    self.assertIsNone(row["child_pid"])
                    self.assertFalse(marker.exists())
                    with self.board() as sw, sw.tx():
                        sw.db.execute(
                            "UPDATE executions SET started_at='2020-01-01T00:00:00+00:00' WHERE id=?", (row["id"],)
                        )
                    self.sw("status")
                    self.assertEqual(self.execution()["state"], "unknown")
                else:
                    self.wait_for(lambda: self.execution()["state"] == "exited")
                    self.assertTrue(marker.exists())
                self.assertNotEqual(self.task(task)["state"], "done")
                self.assertTrue(Path(self.task(task)["worktree"]).exists())

    def test_ec298_crash_after_child_creation_before_commit_is_unknown(self):
        self.configure_worker("cooperative")
        try:
            self.sw(
                "spawn",
                "hold",
                "--name",
                "worker",
                "--task",
                "T1",
                ok=None,
                env={"SWARM_FAILPOINT": "before_execution_start_commit"},
            )
            self.wait_for(lambda: self.work_ready(self.task("T1")["worktree"]))
            row = self.execution()
            self.assertIsNone(row["child_pid"])
            self.wait_for(lambda: not core.pid_alive(row["supervisor_pid"]))
            with self.board() as sw, sw.tx():
                sw.db.execute("UPDATE executions SET heartbeat_at='2020-01-01T00:00:00+00:00' WHERE id=?", (row["id"],))
            self.sw("status")
            self.assertEqual(self.execution()["state"], "unknown")
            self.assertNotEqual(self.task("T1")["state"], "done")
            self.assertTrue(Path(self.task("T1")["worktree"]).exists())
        finally:
            self.release.write_text("exit", encoding="utf-8")
            if self.ready.exists():
                self.wait_for(lambda: not self.running(int(self.ready.read_text())))

    def test_ec299_changed_startup_policy_refuses_command_delivery(self):
        self.join("ann")
        original = core.subprocess.Popen
        created = []

        def started(argv, *args, **kwargs):
            proc = original(argv, *args, **kwargs)
            if len(argv) > 2 and argv[2] == "__supervise":
                created.append(proc)
                config = self.root / ".agents" / "swarm" / "config.toml"
                config.write_text(
                    config.read_text(encoding="utf-8") + "\n# Human changed policy during startup\n", encoding="utf-8"
                )
            return proc

        args = core.build_parser().parse_args(["spawn", "fake", "--name", "worker", "--task", "T1"])
        try:
            with self.board() as sw, mock.patch.object(core.subprocess, "Popen", side_effect=started):
                with self.assertRaisesRegex(core.SwarmError, "policy changed"):
                    core.cmd_spawn(sw, args)
                row = sw.db.execute("SELECT * FROM executions").fetchone()
                self.assertEqual(row["state"], "failed")
                self.assertIsNone(row["child_pid"])
                self.assertIsNone(sw.agent("worker")["pid"])
                self.assertEqual(json.loads(row["policy"])["config_digest"], sw.config_stamp)
            self.assertIsNotNone(created[0].poll())
        finally:
            for proc in created:
                if proc.stdin and not proc.stdin.closed:
                    proc.stdin.close()
                if proc.poll() is None:
                    proc.terminate()
                proc.wait(timeout=10)

    def test_ec300_stopping_coordinator_cannot_finish_new_worker_startup(self):
        self.join("ann")
        parent = "b" * 32
        with self.board() as sw, sw.tx():
            sw.db.execute(
                "INSERT INTO executions(id,agent,task,epoch,state,supervisor_pid,started_at,heartbeat_at,policy) VALUES(?,?,?,0,'running',?,?,?,?)",
                (parent, "ann", "T1", os.getpid(), core.iso(), core.iso(), json.dumps(sw.config["spawn"])),
            )
        original_prepare, original_popen = core.prepare_agent, core.subprocess.Popen

        def prepared(*args):
            task = original_prepare(*args)
            self.sw(
                "execution", "stop", parent, "--reason", "Stop the coordinator before its pending worker can start."
            )
            return task

        def no_supervisor(argv, *args, **kwargs):
            if len(argv) > 2 and argv[2] == "__supervise":
                raise AssertionError("The stopped coordinator attempted to start a supervisor")
            return original_popen(argv, *args, **kwargs)

        args = core.build_parser().parse_args(["spawn", "fake", "--name", "worker", "--task", "T1", "--as", "ann"])
        with (
            self.board() as sw,
            mock.patch.dict(os.environ, {"SWARM_EXECUTION_ID": parent}),
            mock.patch.object(core, "prepare_agent", side_effect=prepared),
            mock.patch.object(core.subprocess, "Popen", side_effect=no_supervisor),
        ):
            with self.assertRaisesRegex(core.SwarmError, "coordinator.*stopping"):
                core.cmd_spawn(sw, args)
            self.assertEqual(sw.db.execute("SELECT count(*) FROM executions").fetchone()[0], 1)
            self.assertEqual(core.execution_row(sw, parent)["state"], "stop_requested")
            self.assertIsNone(sw.agent("worker")["pid"])
            self.assertEqual(sw.task("T1")["assignee"], "worker")
