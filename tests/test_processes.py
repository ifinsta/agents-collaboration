"""Owned process groups, explicit timeout policy and artifact-preserving recovery."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

import test_contracts as contracts
import test_swarm as fixtures
from test_hardening import HardeningCase

core = fixtures.swarm_module


class ProcessCase(HardeningCase):
    def wait_for(self, probe, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            result = probe()
            if result:
                return result
            time.sleep(0.05)
        self.fail("timed out waiting for owned process state")

    def running(self, pid):
        if os.name == "nt":
            return core.pid_alive(pid)
        result = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True, check=False)
        return bool(result.stdout.strip()) and not result.stdout.strip().startswith("Z")

    def execution(self):
        with self.board() as sw:
            return sw.db.execute("SELECT * FROM executions ORDER BY started_at DESC,id DESC LIMIT 1").fetchone()

    def work_ready(self, tree):
        file = Path(tree) / "unfinished.txt"
        return self.ready.exists() and file.exists() and file.read_text() == "preserve unfinished work"

    def holding_program(self, *, descendants=False, parent_exits=False):
        self.release = Path(self.tmp.name) / "release"
        self.child_pid = Path(self.tmp.name) / "child.pid"
        self.ready = Path(self.tmp.name) / "ready"
        loop = f"\nwhile not Path({str(self.release)!r}).exists(): time.sleep(0.05)"
        if descendants:
            child = (
                "import os,time; from pathlib import Path; "
                + f"Path({str(self.child_pid)!r}).write_text(str(os.getpid()))"
                + loop
            )
            code = "import os,sys,time,subprocess; from pathlib import Path; "
            code += f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
        else:
            code = "import os,time; from pathlib import Path; "
        code += f"Path({str(self.ready)!r}).write_text(str(os.getpid())); "
        code += "Path('unfinished.txt').write_text('preserve unfinished work'); "
        code += "os._exit(0)" if parent_exits else loop
        return code

    def configure_worker(self, action="terminate", *, code=None):
        code = code or self.holding_program()
        self.config(
            "[spawn]\ntimeout_action = "
            + json.dumps(action)
            + "\ngrace_sec = 0\nsignal_grace_sec = 0.05\npoll_sec = 0.05\n"
            + "[adapters.hold]\nversion = "
            + json.dumps([sys.executable, "--version"])
            + "\nauth = []\nrun = "
            + json.dumps([sys.executable, "-c", code])
            + "\nmodel = []\nunattended = []\nverified = true"
        )
        self.join("ann")

    def cleanup_worker(self):
        if hasattr(self, "release"):
            self.release.write_text("exit", encoding="utf-8")
        if self.execution() and self.execution()["state"] not in core.EXECUTION_TERMINAL:
            # Only our known fixture execution; let the captured policy and owned supervisor stop it.
            self.sw("execution", "stop", self.execution()["id"], "--reason", "Finish the owned fixture safely", ok=None)
        self.wait_for(
            lambda: not self.execution() or self.execution()["state"] in (*core.EXECUTION_TERMINAL, "unknown")
        )


class OwnedGroups(ProcessCase):
    def test_ec244_owned_termination_removes_descendants_and_leaves_unrelated_process_alive(self):
        code = self.holding_program(descendants=True)
        unrelated = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        owned = None
        try:
            with (self.root / "owned.log").open("wb") as log:
                owned = core.OwnedProcess([sys.executable, "-c", code], self.root, dict(os.environ), log)
                self.wait_for(lambda: self.child_pid.exists() and self.work_ready(self.root))
                child = int(self.child_pid.read_text())
                self.assertTrue(owned.active())
                owned.kill()
                self.wait_for(lambda: not owned.active())
                self.wait_for(lambda: not self.running(child))
                self.assertIsNone(unrelated.poll())
                self.assertTrue((self.root / "unfinished.txt").exists())
        finally:
            if owned:
                if not getattr(owned, "finished", False):
                    owned.kill()
                owned.close()
            unrelated.kill()
            unrelated.wait()

    def test_ec244_descendants_remain_owned_after_the_worker_leader_exits(self):
        code = self.holding_program(descendants=True, parent_exits=True)
        with (self.root / "owned.log").open("wb") as log:
            owned = core.OwnedProcess([sys.executable, "-c", code], self.root, dict(os.environ), log)
            try:
                self.wait_for(self.child_pid.exists)
                pid = int(self.child_pid.read_text())
                self.wait_for(lambda: not self.running(owned.pid))
                self.assertTrue(self.running(pid))
                self.assertTrue(owned.active())
                owned.kill()
                self.wait_for(lambda: not owned.active())
                self.wait_for(lambda: not self.running(pid))
            finally:
                if not getattr(owned, "finished", False):
                    owned.kill()
                owned.close()

    def test_ec245_gate_timeout_terminates_its_owned_group_and_bounds_output_in_memory(self):
        code = self.holding_program(descendants=True)
        clock = mock.Mock(
            monotonic=lambda: 2.0 if self.child_pid.exists() and self.work_ready(self.root) else 0.0, sleep=time.sleep
        )
        with mock.patch.object(core, "time", clock):
            result, _ = core.run_gate([sys.executable, "-c", code], self.root, dict(os.environ), 1, None, 0.1)
        self.assertIsNone(result)
        pid = int(self.child_pid.read_text())
        self.wait_for(lambda: not self.running(pid))
        self.assertTrue((self.root / "unfinished.txt").exists())
        result, output = core.run_gate(
            [sys.executable, "-c", "print('x' * 100000)"], self.root, dict(os.environ), 30, None, 1
        )
        self.assertEqual(result, 0)
        self.assertLessEqual(len(output.encode("utf-8")), 2000)
        with self.assertRaisesRegex(core.SwarmError, "output exceeded"):
            core.run_owned([sys.executable, "-c", "print('x' * 2000000)"], self.root, dict(os.environ), 30)
        streams = core.run(
            [sys.executable, "-c", "import sys; print('message'); print('diagnostic',file=sys.stderr)"],
            cwd=self.root,
            owned=True,
        )
        self.assertEqual(streams.stdout.strip(), "message")
        self.assertEqual(streams.stderr.strip(), "diagnostic")

    def test_ec245_raising_keepalive_cleans_up_the_gate_children_before_propagating_refusal(self):
        code = self.holding_program(descendants=True)

        def refused():
            if self.child_pid.exists() and self.work_ready(self.root):
                raise core.SwarmError("controlled permission refusal")

        with self.assertRaisesRegex(core.SwarmError, "controlled permission refusal"):
            core.run_gate([sys.executable, "-c", code], self.root, dict(os.environ), 30, refused, 0.01)
        pid = int(self.child_pid.read_text())
        self.wait_for(lambda: not self.running(pid))
        self.assertTrue((self.root / "unfinished.txt").exists())


class Supervision(ProcessCase):
    def test_ec243_schema_five_upgrade_keeps_prior_records_and_rolls_back_killed_execution_migration(self):
        self.join("ann")
        with self.board() as sw, sw.tx():
            sw.db.execute("DROP TABLE executions")
            sw.set_meta("schema_version", "5")
        self.sw("status", ok=False, env={"SWARM_FAILPOINT": "during_migration"})
        db = self.db()
        try:
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='executions'").fetchone())
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "5")
        finally:
            db.close()
        result = self.json_command("status", "--json")["result"]
        self.assertEqual(result["executions"], [])
        self.assertIn("ann", {a["name"] for a in result["agents"]})

    def test_ec246_expired_live_contract_fences_then_terminates_only_the_owned_group(self):
        self.configure_worker(code=self.holding_program(descendants=True))
        contracts.Architecture.build_goal(self)
        self.architecture("GL")
        self.sw("goal", "commit", "GL")
        try:
            self.sw("spawn", "hold", "--name", "bob", "--task", "H-api")
            self.wait_for(lambda: self.child_pid.exists() and self.work_ready(self.task("H-api")["worktree"]))
            before = self.task("H-api")["epoch"]
            with self.board() as sw, sw.tx():
                contract = core.current_contract(sw, "H-api")
                terms = json.loads(contract["terms"])
                terms.update(deadline_at="2020-01-01T00:00:00+00:00", grace_min=0.001)
                sw.db.execute("UPDATE task_contracts SET terms=? WHERE id=?", (json.dumps(terms), contract["id"]))
            row = self.wait_for(lambda: (r := self.execution()) and r["state"] == "terminated" and r)
            task = self.task("H-api")
            self.assertEqual(task["state"], "expired")
            self.assertGreater(task["epoch"], before)
            self.assertTrue(Path(task["worktree"]).is_dir())
            self.assertEqual((Path(task["worktree"]) / "unfinished.txt").read_text(), "preserve unfinished work")
            self.assertTrue(row["signal_at"])
            self.wait_for(lambda: not self.running(int(self.child_pid.read_text())))
            self.assertNotEqual(task["state"], "done")
        finally:
            self.cleanup_worker()

    def test_ec247_cooperative_policy_never_signals_after_grace_and_stop_preview_is_read_only(self):
        self.configure_worker("cooperative")
        contracts.Architecture.build_goal(self)
        self.architecture("GL")
        self.sw("goal", "commit", "GL")
        try:
            self.sw("spawn", "hold", "--name", "bob", "--task", "H-api")
            self.wait_for(self.ready.exists)
            wt = Path(self.task("H-api")["worktree"])
            self.sw("plan", "--as", "bob", *fixtures.PLAN, cwd=wt)
            self.sw("start", "--as", "bob", cwd=wt)
            with self.board() as sw, sw.tx():
                sw.db.execute(
                    "UPDATE task_contracts SET active_since=? WHERE task='H-api'",
                    (core.iso(core.utcnow() - timedelta(seconds=10)),),
                )
            execution = self.execution()["id"]
            self.sw("execution", "stop", execution, "--reason", "Checkpoint the current fixture", "--dry-run")
            self.assertIsNone(self.execution()["stop_requested_at"])
            self.sw("execution", "stop", execution, "--reason", "Checkpoint the current fixture")
            first = self.execution()["heartbeat_at"]
            row = self.wait_for(lambda: (r := self.execution()) and r["heartbeat_at"] != first and r)
            self.assertEqual(row["state"], "stop_requested")
            self.assertIsNone(row["signal_at"])
            with self.board() as sw:
                contract = core.current_contract(sw, "H-api")
                self.assertIsNone(contract["active_since"])
                self.assertIsNotNone(contract["blocked_at"])
                self.assertGreaterEqual(contract["active_seconds"], 10)
                self.assertEqual(contract["epoch"], self.task("H-api")["epoch"])
            self.assertTrue(self.running(int(self.ready.read_text())))
            self.assertIn(
                "execution_stopping", {i["code"] for i in self.json_command("doctor", "--json")["result"]["issues"]}
            )
            self.release.write_text("done", encoding="utf-8")
            self.wait_for(lambda: self.execution()["state"] == "exited")
        finally:
            self.cleanup_worker()

    def test_ec246_timed_out_targeted_pause_terminates_owned_execution_without_forging_ack(self):
        self.configure_worker()
        try:
            self.sw("spawn", "hold", "--name", "bob", "--task", "T1")
            self.wait_for(self.ready.exists)
            self.sw(
                "interrupt",
                "request",
                "bob",
                "--mode",
                "pause",
                "--reason",
                "Checkpoint this fixture before doing any more work",
            )
            with self.board() as sw, sw.tx():
                sw.db.execute("UPDATE interrupts SET deadline_at='2020-01-01T00:00:00+00:00'")
            row = self.wait_for(lambda: (r := self.execution()) and r["state"] == "terminated" and r)
            self.assertIn("interrupt", row["stop_reason"])
            self.assertTrue(Path(self.task("T1")["worktree"]).exists())
            with self.board() as sw:
                control = sw.db.execute("SELECT * FROM interrupts").fetchone()
                self.assertEqual(control["state"], "timed_out")
                self.assertIsNone(control["acked_at"])
            self.assertEqual(self.task("T1")["state"], "interrupted")
        finally:
            self.cleanup_worker()

    def test_ec248_registry_pids_never_grant_authority_to_signal_unrelated_processes(self):
        self.join("ann")
        unrelated = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        execution = "a" * 32
        try:
            with self.board() as sw, sw.tx():
                sw.db.execute(
                    "INSERT INTO executions(id,agent,task,epoch,state,supervisor_pid,child_pid,started_at,heartbeat_at,policy) VALUES(?,?,?,0,'running',?,?,?,?,?)",
                    (
                        execution,
                        "ann",
                        "T1",
                        os.getpid(),
                        unrelated.pid,
                        core.iso(),
                        core.iso(),
                        json.dumps(sw.config["spawn"]),
                    ),
                )
            self.sw("execution", "stop", execution, "--reason", "Request a controlled fixture stop")
            self.sw("status")
            self.assertIsNone(unrelated.poll())
            self.assertIsNone(self.execution()["signal_at"])
            self.assertIn("pid", self.sw("execution", "show", execution))
            with self.board() as sw, sw.tx():
                sw.db.execute("UPDATE executions SET heartbeat_at='2020-01-01T00:00:00+00:00'")
            self.sw("status")
            self.assertEqual(self.execution()["state"], "unknown")
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.kill()
            unrelated.wait()

    def test_ec249_supervisor_crash_is_unknown_never_success_and_preserves_even_untouched_work(self):
        self.configure_worker()
        self.sw(
            "spawn",
            "hold",
            "--name",
            "bob",
            "--task",
            "T1",
            ok=None,
            env={"SWARM_FAILPOINT": "after_execution_started"},
        )
        row = self.execution()
        self.wait_for(lambda: not self.running(row["supervisor_pid"]))
        self.wait_for(lambda: not self.running(row["child_pid"]))
        with self.board() as sw, sw.tx():
            sw.db.execute("UPDATE executions SET heartbeat_at='2020-01-01T00:00:00+00:00'")
        self.sw("status")
        self.assertEqual(self.execution()["state"], "unknown")
        self.assertTrue(Path(self.task("T1")["worktree"]).exists())
        self.assertIn(
            "execution_supervision_lost",
            {i["code"] for i in self.json_command("doctor", "--json", ok=False)["result"]["issues"]},
        )
        self.sw("join", "--as", "bob", "--kind", "hold", "--resume")
        self.assertIn("Execution", self.sw("plan", "--as", "bob", *fixtures.PLAN, ok=False))
        self.sw("release", "Preserve this fixture while confirming the old group stopped", "--task", "T1")
        self.assertIn("execution", self.sw("claim", "T1", "--as", "ann", ok=False))
        self.sw(
            "execution",
            "reconcile",
            row["id"],
            "--reason",
            "The fixture process group is no longer running",
            "--confirm-stopped",
        )
        self.assertEqual(self.execution()["state"], "reconciled")
        self.assertIn("Human attestation", self.execution()["detail"])

    def test_ec249_crash_after_execution_intent_keeps_the_task_recoverable_without_launching(self):
        self.configure_worker()
        self.sw(
            "spawn",
            "hold",
            "--name",
            "bob",
            "--task",
            "T1",
            ok=False,
            env={"SWARM_FAILPOINT": "after_execution_intent"},
        )
        self.assertFalse(self.ready.exists())
        row = self.execution()
        self.assertIsNone(row["supervisor_pid"])
        with self.board() as sw, sw.tx():
            sw.db.execute("UPDATE executions SET started_at='2020-01-01T00:00:00+00:00'")
        self.sw("status")
        self.assertEqual(self.execution()["state"], "unknown")
        self.assertTrue(Path(self.task("T1")["worktree"]).exists())

    def test_ec249_startup_without_an_acknowledged_group_never_reports_ready(self):
        self.join("ann")
        real_popen = core.subprocess.Popen
        pending = mock.Mock(pid=os.getpid(), stdin=io.BytesIO())
        pending.poll.return_value = None
        awaiting_supervisor = [False]

        def hold_only_supervisor(argv, *args, **kwargs):
            if len(argv) > 2 and argv[2] == "__supervise":
                awaiting_supervisor[0] = True
                return pending
            return real_popen(argv, *args, **kwargs)

        args = core.build_parser().parse_args(["spawn", "fake", "--name", "bob", "--task", "T1"])
        with self.board() as sw:
            sw.config["spawn"]["startup_sec"] = 1
            ticks = iter([0, 2])
            clock = mock.Mock(monotonic=lambda: next(ticks, 2) if awaiting_supervisor[0] else time.monotonic(), sleep=time.sleep)
            with (
                mock.patch.object(core.subprocess, "Popen", side_effect=hold_only_supervisor),
                mock.patch.object(core, "time", clock),
            ):
                with self.assertRaisesRegex(core.SwarmError, "no confirmed ready state"):
                    core.cmd_spawn(sw, args)
            row = sw.db.execute("SELECT * FROM executions").fetchone()
            self.assertEqual(row["state"], "starting")
            self.assertIsNone(row["child_pid"])
            self.assertTrue(Path(sw.task("T1")["worktree"]).exists())

            def deny_only_supervisor(argv, *args, **kwargs):
                if len(argv) > 2 and argv[2] == "__supervise":
                    raise PermissionError("host forbids independent startup")
                return real_popen(argv, *args, **kwargs)

            other = core.build_parser().parse_args(["spawn", "fake", "--name", "cat", "--task", "T2"])
            with mock.patch.object(core.subprocess, "Popen", side_effect=deny_only_supervisor):
                with self.assertRaisesRegex(core.SwarmError, "No fallback was attempted"):
                    core.cmd_spawn(sw, other)
            failed = sw.db.execute("SELECT * FROM executions WHERE agent='cat'").fetchone()
            self.assertEqual(failed["state"], "failed")
            self.assertIsNone(failed["child_pid"])
            self.assertTrue(Path(sw.task("T2")["worktree"]).exists())

    def test_ec249_missing_or_stale_parent_context_refuses_spawn_before_allocating_a_worker(self):
        self.join("ann")
        with self.board() as sw, sw.tx():
            sw.db.execute(
                "INSERT INTO executions(id,agent,task,epoch,state,supervisor_pid,started_at,heartbeat_at,policy) VALUES(?,?,?,0,'running',?,?,?,?)",
                ("b" * 32, "ann", "T1", os.getpid(), core.iso(), core.iso(), json.dumps(sw.config["spawn"])),
            )
        for context in ("", "c" * 32):
            result = self.json_command(
                "spawn",
                "fake",
                "--name",
                "bob",
                "--task",
                "T1",
                "--as",
                "ann",
                "--json",
                ok=False,
                env={"SWARM_EXECUTION_ID": context},
            )
            self.assertIn("SWARM_EXECUTION_ID", result["error"]["message"])
            with self.board() as sw:
                self.assertIsNone(sw.agent("bob"))
                self.assertEqual(sw.task("T1")["state"], "open")

    def test_ec249_stopping_a_spawned_coordinator_does_not_stop_its_independent_worker(self):
        ann_release, bob_release = Path(self.tmp.name) / "ann.release", Path(self.tmp.name) / "bob.release"
        ann_ready, bob_ready = Path(self.tmp.name) / "ann.ready", Path(self.tmp.name) / "bob.ready"
        bob_code = (
            "import os,time; from pathlib import Path; " + f"Path({str(bob_ready)!r}).write_text(str(os.getpid())); "
        )
        bob_code += "Path('unfinished.txt').write_text('independent worker work'); "
        bob_code += f"\nwhile not Path({str(bob_release)!r}).exists(): time.sleep(0.05)"
        ann_code = "import os,sys,time,subprocess; from pathlib import Path; "
        ann_code += f"subprocess.run([sys.executable,{str(fixtures.SWARM)!r},'spawn','hold','--name','bob','--task','T2'],check=True); "
        ann_code += f"Path({str(ann_ready)!r}).write_text(str(os.getpid())); Path('unfinished.txt').write_text('coordinator work'); "
        ann_code += f"\nwhile not Path({str(ann_release)!r}).exists(): time.sleep(0.05)"
        config = '[spawn]\ntimeout_action = "terminate"\ngrace_sec = 0\nsignal_grace_sec = 0.05\npoll_sec = 0.05\n'
        for kind, code in (("controller", ann_code), ("hold", bob_code)):
            config += f"[adapters.{kind}]\nversion = " + json.dumps([sys.executable, "--version"])
            config += "\nauth = []\nrun = " + json.dumps([sys.executable, "-c", code])
            config += "\nmodel = []\nunattended = []\nverified = true\n"
        self.config(config)

        def records(sweep=False):
            with self.board() as sw:
                if sweep:
                    with sw.tx():
                        sw.sweep()
                return {r["agent"]: r for r in sw.db.execute("SELECT * FROM executions")}

        try:
            self.sw("spawn", "controller", "--name", "ann", "--task", "T1")
            self.wait_for(lambda: ann_ready.exists() and bob_ready.exists())
            ids = records()
            self.sw("execution", "stop", ids["ann"]["id"], "--reason", "Stop only the owned coordinator execution")
            self.wait_for(lambda: records()["ann"]["state"] == "terminated")
            self.assertTrue(self.running(ids["bob"]["child_pid"]))
            self.assertTrue(self.running(ids["bob"]["supervisor_pid"]))
            self.assertEqual(records()["bob"]["state"], "running")
            self.assertTrue(Path(self.task("T2")["worktree"]).exists())
        finally:
            ann_release.write_text("exit", encoding="utf-8")
            bob_release.write_text("exit", encoding="utf-8")
            self.sw("status", ok=None)
            self.wait_for(
                lambda: all(r["state"] in (*core.EXECUTION_TERMINAL, "unknown") for r in records(sweep=True).values())
            )

    def test_ec250_spawn_and_gate_policy_reject_quoted_permissions_and_unbounded_limits(self):
        config = self.root / ".agents/swarm/config.toml"
        original = config.read_text(encoding="utf-8")
        for section in (
            '[spawn]\nallow_unattended = "false"',
            '[spawn]\ntimeout_action = "arbitrary"',
            "[spawn]\npoll_sec = nan",
            "[spawn]\ngrace_sec = -1",
            "[spawn]\nmax_turns = true",
        ):
            config.write_text(original + "\n" + section + "\n", encoding="utf-8")
            result = self.json_command("status", "--json", ok=False)
            self.assertIn("config", result["error"]["message"])
        config.write_text(original.replace("[gates]", "[gates]\nretries = -1"), encoding="utf-8")
        self.assertIn("retries", self.json_command("status", "--json", ok=False)["error"]["message"])

    def test_ec250_same_size_and_mtime_policy_changes_do_not_reuse_stale_parsed_config(self):
        self.sw("status")
        config = self.root / ".agents/swarm/config.toml"
        stat = config.stat()
        before = config.read_text(encoding="utf-8")
        after = before.replace("max_agents = 5", "max_agents = 4")
        self.assertEqual(len(before.encode("utf-8")), len(after.encode("utf-8")))
        config.write_text(after, encoding="utf-8")
        os.utime(config, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with self.board() as sw:
            self.assertEqual(sw.config["swarm"]["max_agents"], 4)


if __name__ == "__main__":
    unittest.main()
