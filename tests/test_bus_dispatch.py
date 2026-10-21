"""Real loopback wakeups and owned adapter hooks preserve durable control authority."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from unittest import mock

import test_bus as bus_tests
import test_processes as processes
from test_hardening import core, fixtures


class Wakeups(bus_tests.BusCase):
    def test_ec337_wake_hints_follow_commit_and_never_rollback(self):
        with self.board() as sw:
            wake = core.BusWake(sw, "bob")
            try:
                with self.assertRaisesRegex(ValueError, "rollback"):
                    with sw.tx():
                        sw.message("ann", "bob", "This message must roll back", kind="status")
                        self.assertFalse(wake.wait(0))
                        raise ValueError("rollback")
                self.assertFalse(wake.wait(0.05))
                self.assertEqual(sw.db.execute("SELECT COUNT(*) FROM messages WHERE body LIKE 'This message%'").fetchone()[0], 0)
                with sw.tx():
                    sw.message("ann", "bob", "This message committed", kind="status")
                    self.assertFalse(wake.wait(0))
                self.assertTrue(wake.wait(1))
            finally:
                wake.close()

    def test_ec338_invalid_hints_and_sender_failure_cannot_lose_committed_messages(self):
        with self.board() as sw:
            wake = core.BusWake(sw, "bob")
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.sendto(b"forged-control-payload", wake.sock.getsockname())
                self.assertFalse(wake.wait(1))
                with mock.patch.object(socket, "socket", side_effect=OSError("loopback unavailable")):
                    with sw.tx():
                        sw.message("ann", "bob", "Preserve the committed message without a hint", kind="status")
                self.assertEqual(sw.db.execute("SELECT COUNT(*) FROM messages WHERE body LIKE 'Preserve the committed%'").fetchone()[0], 1)
                self.assertEqual(len(self.receive()), 1)
            finally:
                wake.close()

    def test_ec339_dispatch_relay_is_durable_and_notifications_do_not_ack(self):
        hook = Path(self.tmp.name) / "hook.py"
        marker = Path(self.tmp.name) / "seen.json"
        hook.write_text("import os,json,pathlib\np=pathlib.Path(os.environ['SWARM_BUS_EVENT_PATH'])\n" + f"pathlib.Path({str(marker)!r}).write_text(p.read_text())\n", encoding="utf-8")
        self.config("[bus]\nmessage_hook = " + json.dumps([sys.executable, str(hook)]))
        with self.board() as sw:
            runtime = core.AdapterInbox(sw, "bob")
            try:
                runtime.refresh()
                self.publish()
                self.assertTrue(runtime.wait(1))
                runtime.refresh(woke=True)
                payload = json.loads(marker.read_text(encoding="utf-8"))
                receipt = payload["deliveries"][0]["receipt"]
                self.assertEqual(json.loads(runtime.path.read_text())["deliveries"], payload["deliveries"])
                self.assertIsNone(sw.db.execute("SELECT acked_at FROM message_recipients WHERE msg=? AND agent='bob'", (receipt["message_id"],)).fetchone()[0])
                self.assertEqual(self.receive(), [])
                self.receipt_command("ack", receipt)
            finally:
                runtime.close()
            self.assertEqual(sw.db.execute("SELECT COUNT(*) FROM bus_listeners").fetchone()[0], 0)

    def test_ec339_hook_timeout_and_fallback_preserve_pending_work(self):
        self.config("[bus]\nhook_timeout_sec = 0.1\nmessage_hook = " + json.dumps([sys.executable, "-c", "import time;time.sleep(60)"]))
        with self.board() as sw:
            with mock.patch.object(socket, "socket", side_effect=OSError("no socket")):
                runtime = core.AdapterInbox(sw, "bob")
            try:
                self.publish()
                runtime.refresh(woke=True)
                self.assertIsNotNone(sw.db.execute("SELECT * FROM events WHERE kind='bus_dispatch_failed'").fetchone())
                self.assertIsNone(sw.db.execute("SELECT acked_at FROM message_recipients WHERE agent='bob'").fetchone()[0])
            finally:
                runtime.close()

    def test_ec340_tool_hook_exposes_authoritative_pause_and_enforcement(self):
        self.sw("claim", "T1", "--as", "bob")
        self.sw("plan", "--as", "bob", *fixtures.PLAN)
        self.sw("start", "--as", "bob")
        self.sw("interrupt", "request", "bob", "--mode", "pause", "--reason", "Review this source boundary at a safe checkpoint")
        view = self.bus("hook", "--stage", "before-tool")
        self.assertTrue(view["blocked"])
        self.assertEqual(view["controls"][0]["state"], "requested")
        done = subprocess.run([sys.executable, str(fixtures.SWARM), "--as", "bob", "bus", "hook", "--enforce", "--json"], cwd=self.root, capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(done.returncode, 2)
        self.assertTrue(json.loads(done.stdout)["result"]["blocked"])
        with self.board() as sw:
            self.assertIsNone(sw.db.execute("SELECT acked_at FROM interrupts").fetchone()[0])

    def test_ec340_resume_notifies_interrupt_hook_even_without_pending_messages(self):
        hook = Path(self.tmp.name) / "control.py"
        marker = Path(self.tmp.name) / "control.jsonl"
        hook.write_text("import os,json,pathlib\np=json.loads(pathlib.Path(os.environ['SWARM_BUS_EVENT_PATH']).read_text())\n" + f"with pathlib.Path({str(marker)!r}).open('a') as f: f.write(json.dumps(p['blocked'])+'\\n')\n", encoding="utf-8")
        self.config("[bus]\ninterrupt_hook = " + json.dumps([sys.executable, str(hook)]))
        with self.board() as sw:
            runtime = core.AdapterInbox(sw, "bob")
            try:
                runtime.refresh()
                self.sw("pause", "Review the source boundary before continuing", "--as", "ann")
                self.assertTrue(runtime.wait(1))
                runtime.refresh(woke=True)
                self.sw("resume", "--as", "ann")
                self.assertTrue(runtime.wait(1))
                runtime.refresh(woke=True)
                self.assertEqual([json.loads(line) for line in marker.read_text().splitlines()], [True, False])
            finally:
                runtime.close()

    def test_ec340_execution_stop_blocks_hook_without_targeted_interrupt(self):
        self.sw("claim", "T1", "--as", "bob")
        with self.board() as sw, sw.tx():
            sw.db.execute("INSERT INTO executions(id,agent,task,epoch,state,supervisor_pid,started_at,heartbeat_at,policy,stop_requested_at) VALUES(?,'bob','T1',1,'stop_requested',?,?,?,?,?)", ("d" * 32, os.getpid(), core.iso(), core.iso(), json.dumps(core.DEFAULTS["spawn"]), core.iso()))
        view = self.bus("hook", "--stage", "before-tool")
        self.assertTrue(view["blocked"])
        self.assertIn("Execution", view["reason"])
        self.assertEqual(view["controls"], [])

    def test_ec339_replaced_supervisor_cannot_create_a_delayed_hook(self):
        marker = Path(self.tmp.name) / "must-not-run"
        self.config("[bus]\nmessage_hook = " + json.dumps([sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"]))
        execution = "f" * 32
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with self.board() as sw:
                with sw.tx():
                    sw.update_agent("bob", pid=os.getpid())
                    sw.db.execute("INSERT INTO executions(id,agent,task,epoch,state,supervisor_pid,started_at,heartbeat_at,policy) VALUES(?,'bob','T1',0,'running',?,?,?,?)", (execution, os.getpid(), core.iso(), core.iso(), json.dumps(core.DEFAULTS["spawn"])))
                runtime = core.AdapterInbox(sw, "bob", execution)
                original = core.run_owned

                def replace(*args, **kwargs):
                    with sw.tx():
                        sw.update_agent("bob", pid=unrelated.pid)
                    return original(*args, **kwargs)

                try:
                    self.publish()
                    with mock.patch.object(core, "run_owned", side_effect=replace):
                        runtime.refresh(woke=True)
                    self.assertFalse(marker.exists())
                    self.assertEqual(sw.agent("bob")["pid"], unrelated.pid)
                    self.assertIsNone(unrelated.poll())
                finally:
                    runtime.close()
        finally:
            unrelated.kill()
            unrelated.wait()

    def test_ec341_listener_migration_rolls_back_without_inventing_deliveries(self):
        with self.board() as sw, sw.tx():
            sw.db.execute("DROP TABLE bus_listeners")
            sw.set_meta("schema_version", "11")
        def fail(point):
            if point == "during_migration":
                raise core.SwarmError("interrupted listener migration")
        with mock.patch.object(core, "failpoint", side_effect=fail):
            with self.assertRaisesRegex(core.SwarmError, "interrupted listener"):
                core.Swarm(self.root)
        db = self.db()
        self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='bus_listeners'").fetchone())
        db.close()
        with self.board() as sw:
            self.assertEqual(sw.meta("schema_version"), "13")
            self.assertEqual(sw.db.execute("SELECT COUNT(*) FROM bus_listeners").fetchone()[0], 0)


class AutomaticAdapter(processes.ProcessCase):
    def test_ec342_supervisor_dispatches_messages_and_interrupts_without_long_poll_wait(self):
        self.configure_worker()
        path = self.root / ".agents/swarm/config.toml"
        hook = Path(self.tmp.name) / "relay.py"
        seen, stopped = Path(self.tmp.name) / "message.json", Path(self.tmp.name) / "interrupt.json"
        hook.write_text("import os,json,pathlib\np=json.loads(pathlib.Path(os.environ['SWARM_BUS_EVENT_PATH']).read_text())\n" + f"pathlib.Path({str(stopped)!r} if p['blocked'] else {str(seen)!r}).write_text(json.dumps(p))\n", encoding="utf-8")
        text = path.read_text(encoding="utf-8").replace("poll_sec = 0.05", "poll_sec = 30")
        text += "\nmessage_hook = " + json.dumps([sys.executable, str(hook)]) + "\ninterrupt_hook = " + json.dumps([sys.executable, str(hook)]) + "\n"
        path.write_text(text, encoding="utf-8")
        try:
            self.sw("spawn", "hold", "--name", "worker", "--task", "T1")
            self.wait_for(lambda: self.ready.exists())
            self.sw("send", "worker", "Review the source fixture before the next task step", "--kind", "review_request", "--as", "ann")
            self.wait_for(lambda: seen.exists(), seconds=10)
            self.assertEqual(json.loads(seen.read_text())["deliveries"][0]["message"]["kind"], "review_request")
            self.sw("interrupt", "request", "worker", "--mode", "pause", "--reason", "Retain unfinished work at a safe checkpoint")
            self.wait_for(lambda: stopped.exists(), seconds=10)
            self.assertNotIn(self.execution()["state"], core.EXECUTION_TERMINAL)
            self.sw("execution", "stop", self.execution()["id"], "--reason", "Finish this owned fixture under its captured stop policy")
            self.wait_for(lambda: self.execution()["state"] in core.EXECUTION_TERMINAL, seconds=10)
            self.assertTrue((Path(self.task("T1")["worktree"]) / "unfinished.txt").exists())
            with self.board() as sw:
                self.assertIsNone(sw.db.execute("SELECT acked_at FROM interrupts").fetchone()[0])
        finally:
            self.cleanup_worker()
