"""Bounded headless output with real subprocesses and temporary Git worktrees."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

from test_processes import ProcessCase, core


class ExecutionOutput(ProcessCase):
    def cleanup_worker(self):
        row = self.execution()
        if row and row["state"] == "unknown":
            if hasattr(self, "release"):
                self.release.write_text("exit", encoding="utf-8")
        else:
            super().cleanup_worker()
        if hasattr(self, "ready") and self.ready.exists() and self.ready.read_text().isdigit():
            self.wait_for(lambda: not self.running(int(self.ready.read_text())))

    def worker(self, code, policy="terminate", cap=2048):
        self.configure_worker(policy, code=code.replace("{", "{{").replace("}", "}}"))
        path = self.root / ".agents" / "swarm" / "config.toml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("[spawn]\n", f"[spawn]\nmax_output_bytes = {cap}\n"),
            encoding="utf-8",
        )
        self.git("commit", "-qam", "bound worker output")

    def spawn(self, env=None, name="worker", task="T1"):
        return self.sw("spawn", "hold", "--name", name, "--task", task, ok=None, env=env)

    def terminal(self):
        return self.wait_for(
            lambda: (
                self.execution() if self.execution() and self.execution()["state"] in core.EXECUTION_TERMINAL else None
            )
        )

    def output(self):
        return json.loads(self.execution()["output"])

    def noisy(self, *, descendants=False, finite=False):
        code = self.holding_program(descendants=descendants)
        head, loop = code.rsplit("\nwhile ", 1)
        if descendants:
            head += f"\nwhile not Path({str(self.child_pid)!r}).exists(): time.sleep(0.01)\n"
        if finite:
            return head + "os.write(1, b'x' * 200000);\nwhile " + loop
        return head + "\nwhile True: os.write(1, b'x' * 8192); time.sleep(0.001)"

    def test_ec277_schema_eight_migration_is_atomic_and_old_logs_are_not_invented(self):
        self.join("ann")
        with self.board() as sw, sw.tx():
            sw.db.execute("INSERT INTO executions(id,agent,task,state) VALUES('old','ann','T1','exited')")
            sw.db.execute("ALTER TABLE executions DROP COLUMN output")
            sw.set_meta("schema_version", "8")
        self.sw("status", ok=False, env={"SWARM_FAILPOINT": "during_migration"})
        db = self.db()
        try:
            self.assertNotIn("output", {r[1] for r in db.execute("PRAGMA table_info(executions)")})
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "8")
        finally:
            db.close()
        result = self.json_command("status", "--json")["result"]
        self.assertIsNone(result["executions"][0]["output"])
        self.assertEqual(result["executions"][0]["state"], "exited")
        self.assertIsNone(self.json_command("execution", "show", "old", "--json")["result"]["output"])

    def test_ec278_output_limit_rejects_quoted_booleans_and_unbounded_values(self):
        self.join("ann")
        path = self.root / ".agents" / "swarm" / "config.toml"
        original = path.read_text(encoding="utf-8")
        for value in ('"2048"', "true", "-1", "nan", "1023", "268435457"):
            with self.subTest(value=value):
                path.write_text(original + f"\n[spawn]\nmax_output_bytes = {value}\n", encoding="utf-8")
                self.assertIn("max_output_bytes", self.sw("status", ok=False))

    def test_ec279_stdout_and_stderr_are_retained_with_exact_hash_and_no_false_completion(self):
        payload = "worker evidence: ✓\n".encode()
        code = "import os; from pathlib import Path; Path('unfinished.txt').write_text('retained'); "
        code += f"os.write(1, {payload!r}); os.write(2, b'diagnostic\\n')"
        self.worker(code)
        previous = self.root / ".git" / "swarm" / "logs" / "worker.log"
        previous.write_bytes(b"previous execution evidence")
        try:
            self.spawn()
            row = self.terminal()
            output = self.output()
            expected = payload + b"diagnostic\n"
            self.assertEqual(Path(output["path"]).read_bytes(), expected)
            self.assertEqual(Path(output["path"]).name, row["id"] + ".log")
            self.assertEqual(previous.read_bytes(), b"previous execution evidence")
            self.assertEqual(output["observed_sha256"], hashlib.sha256(expected).hexdigest())
            self.assertEqual(output["bytes_observed"], len(expected))
            self.assertEqual(output["bytes_retained"], len(expected))
            self.assertTrue(output["stream_complete"])
            self.assertFalse(output["truncated"])
            self.assertEqual(row["state"], "exited")
            self.assertEqual(self.task("T1")["state"], "orphaned")
            result = self.json_command("execution", "show", row["id"], "--json")["result"]
            self.assertEqual(result["output"], output)
            self.assertEqual(self.json_command("status", "--json")["result"]["executions"][0]["output"], output)
        finally:
            self.cleanup_worker()

    def test_ec280_excess_output_terminates_only_owned_descendants_and_retains_work(self):
        self.worker(self.noisy(descendants=True))
        unrelated = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        try:
            self.spawn()
            row = self.terminal()
            output = self.output()
            self.assertTrue(output["truncated"])
            self.assertTrue(output["stream_complete"])
            self.assertEqual(output["bytes_retained"], 2048)
            self.assertGreater(output["bytes_observed"], 2048)
            self.assertEqual(Path(output["path"]).read_bytes(), b"x" * 2048)
            self.assertEqual(output["observed_sha256"], hashlib.sha256(b"x" * output["bytes_observed"]).hexdigest())
            self.assertEqual(row["state"], "failed")
            self.assertIn("output exceeded", row["stop_reason"])
            self.wait_for(lambda: not self.running(int(self.child_pid.read_text())))
            self.assertIsNone(unrelated.poll())
            self.assertTrue(self.work_ready(self.task("T1")["worktree"]))
            self.assertNotEqual(self.task("T1")["state"], "done")
            doctor = self.json_command("doctor", "--json")["result"]
            self.assertIn("execution_output_limited", {issue["code"] for issue in doctor["issues"]})
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=10)
            self.cleanup_worker()

    def test_ec281_cooperative_overflow_caps_storage_without_signalling_and_policy_is_frozen(self):
        self.worker(self.noisy(finite=True), policy="cooperative")
        try:
            self.spawn()
            self.wait_for(lambda: self.execution() and self.execution()["stop_requested_at"])
            row = self.execution()
            self.assertTrue(self.running(int(self.ready.read_text())))
            self.assertIsNone(row["signal_at"])
            self.assertIsNone(row["terminate_at"])
            self.assertEqual(self.task("T1")["state"], "interrupted")
            self.assertEqual(Path(self.output()["path"]).stat().st_size, 2048)
            path = self.root / ".agents" / "swarm" / "config.toml"
            path.write_text(
                path.read_text(encoding="utf-8").replace("max_output_bytes = 2048", "max_output_bytes = 65536"),
                encoding="utf-8",
            )
            self.sw("status")
            self.assertEqual(json.loads(self.execution()["policy"])["max_output_bytes"], 2048)
            self.assertIn("stopping", self.sw("start", "--as", "worker", ok=False))
            self.release.write_text("exit", encoding="utf-8")
            self.assertEqual(self.terminal()["state"], "failed")
            self.assertEqual(self.execution()["exit_code"], 0)
            self.assertTrue(self.output()["stream_complete"])
        finally:
            self.cleanup_worker()

    def test_ec282_a_still_open_output_stream_stays_unknown_after_owned_group_exit(self):
        self.join("ann")
        self.sw("claim", "T1", "--as", "ann")
        tree = Path(self.task("T1")["worktree"])
        command = [sys.executable, "-c", "from pathlib import Path; Path('unfinished.txt').write_text('retained')"]
        with self.board() as sw, core.BoundedExecutionOutput(self.root / "capture.log", 2048) as capture:
            holder = os.dup(capture.fileno())
            owned = None
            try:
                owned = core.OwnedProcess(command, tree, dict(os.environ), capture)
                capture.seal_writer()
                self.wait_for(lambda: not owned.active())
                self.assertFalse(capture.done.is_set())
                with sw.tx():
                    sw.db.execute(
                        "INSERT INTO executions(id,agent,task,state,supervisor_pid,child_pid) VALUES('stream','ann','T1','running',?,?)",
                        (os.getpid(), owned.pid),
                    )
                with self.assertRaisesRegex(core.SwarmError, "output stream is still open"):
                    core.observe_execution_output(sw, "stream", capture, False)
                row = core.execution_row(sw, "stream")
                self.assertEqual(row["state"], "unknown")
                self.assertFalse(json.loads(row["output"])["stream_complete"])
                self.assertIn("unknown", core.worktree_activity(sw, sw.task("T1")))
                self.assertTrue((tree / "unfinished.txt").exists())
            finally:
                os.close(holder)
                if owned:
                    if not getattr(owned, "finished", False):
                        owned.kill()
                    owned.close()
            self.assertTrue(capture.done.wait(timeout=10))

    def test_ec283_supervisor_crash_never_invents_a_complete_output_stream(self):
        self.worker(self.holding_program(), policy="cooperative")
        try:
            self.spawn(env={"SWARM_FAILPOINT": "after_execution_started"})
            self.wait_for(lambda: self.ready.exists())
            self.sw("status")
            self.wait_for(lambda: self.sw("status") and self.execution()["state"] == "unknown")
            self.assertFalse(self.output()["stream_complete"])
            self.assertLessEqual(Path(self.output()["path"]).stat().st_size, 2048)
            self.assertTrue(self.work_ready(self.task("T1")["worktree"]))
        finally:
            self.cleanup_worker()

    def test_ec284_capture_write_failure_is_evidence_failure_and_memory_stays_bounded(self):
        self.join("ann")
        with core.BoundedExecutionOutput(self.root / "capture.log", 2048) as capture:
            with mock.patch.object(capture.file, "write", side_effect=OSError("controlled storage full")):
                capture.writer.write(b"x" * 100)
                capture.seal_writer()
                self.assertTrue(capture.done.wait(timeout=10))
            output = capture.snapshot(tail=True)
            self.assertEqual(output["bytes_observed"], 100)
            self.assertEqual(output["bytes_retained"], 0)
            self.assertFalse(output["stream_complete"])
            self.assertIn("controlled storage full", output["error"])
            self.assertIn("capture failed", core.execution_output_problem(output))
            self.assertLessEqual(len(capture.tail), 2000)

    def test_ec285_execution_finish_crashes_preserve_output_without_fabricating_completion(self):
        code = "import os; from pathlib import Path; Path('unfinished.txt').write_text('retained'); os.write(1,b'evidence')"
        self.worker(code)
        for when, name, task in (("before", "worker", "T1"), ("after", "other", "T2")):
            with self.subTest(when=when):
                self.spawn(env={"SWARM_FAILPOINT": f"{when}_execution_finish_commit"}, name=name, task=task)

                def finished():
                    self.sw("status")
                    row = self.execution()
                    return row if row["state"] in ("unknown", "exited") else None

                row = self.wait_for(finished)
                self.assertEqual(row["state"], "unknown" if when == "before" else "exited")
                output = self.output()
                self.assertTrue(output["stream_complete"])
                self.assertEqual(Path(output["path"]).read_bytes(), b"evidence")
                self.assertEqual(output["observed_sha256"], hashlib.sha256(b"evidence").hexdigest())
                self.assertNotEqual(self.task(task)["state"], "done")
                self.assertTrue((Path(self.task(task)["worktree"]) / "unfinished.txt").exists())
                with self.board() as sw:
                    events = sw.db.execute(
                        "SELECT count(*) FROM events WHERE kind='execution_exited' AND task=?", (task,)
                    ).fetchone()[0]
                self.assertEqual(events, 0 if when == "before" else 1)
                if when == "before":
                    self.assertFalse(self.running(row["child_pid"]))
                    self.assertIn("live/uncertain", self.spawn(name=name, task=task))
                    self.sw(
                        "execution",
                        "reconcile",
                        row["id"],
                        "--confirm-stopped",
                        "--reason",
                        "The fixture group exited before its supervisor died; preserve incomplete control evidence.",
                    )
