"""Durable messaging and interrupts against real temporary Git repositories."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
from datetime import timedelta, timezone
from pathlib import Path
from unittest import mock

import test_contracts as contracts
import test_swarm as fixtures

core = fixtures.swarm_module


class CommunicationCase(contracts.ContractCase):
    def sql(self, query, args=()):
        with self.database() as db:
            db.execute(query, args)

    def row(self, table, where="1=1", args=()):
        with self.database() as db:
            db.row_factory = fixtures.sqlite3.Row
            return db.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY id DESC LIMIT 1", args).fetchone()

    def setup_worker(self, ready=False, contracted=False):
        self.join("ann")
        self.join("bob")
        if contracted:
            self.sw("contract", "offer", "T1", "bob", "--as", "ann")
            self.sw("contract", "accept", "T1", "--as", "bob")
        if ready:
            return self.to_ready("bob", "T1")
        self.sw("claim", "T1", "--as", "bob")
        wt = Path(self.task("T1")["worktree"])
        self.sw("plan", "--as", "bob", *fixtures.PLAN, cwd=wt)
        self.sw("start", "--as", "bob", cwd=wt)
        (wt / "dirty.txt").write_text("preserve uncommitted work\n", encoding="utf-8")
        return wt

    def request(self, mode="pause", **kwargs):
        return self.sw(
            "interrupt",
            "request",
            "bob",
            "--mode",
            mode,
            "--reason",
            "Stop at a checkpoint while the interface decision is reviewed",
            "--key",
            "control-1",
            **kwargs,
        )

    def cp(self, task="T1", owner="bob", operator=False):
        args = [
            "checkpoint",
            "--as",
            owner,
            "--epoch",
            str(self.task(task)["epoch"]),
            "--note",
            "Local edits and verification remain incomplete",
            "--next",
            "Review the interface fixture before resuming",
        ]
        if operator:
            args += ["--task", task]
        self.sw(*args)
        return self.row("checkpoints")["id"]

    def ack_control(self):
        self.sw(
            "interrupt",
            "ack",
            str(self.row("interrupts")["id"]),
            "--as",
            "bob",
            "--epoch",
            str(self.task("T1")["epoch"]),
        )


class Envelopes(CommunicationCase):
    def test_ec212_normal_typed_messages_redeliver_until_ack_and_offsets_normalize(self):
        self.join("ann")
        self.join("bob")
        end = core.utcnow() + timedelta(minutes=5)
        offset = end.astimezone(timezone(timedelta(hours=3))).isoformat()
        self.sw(
            "send",
            "bob",
            "A typed status update still needs acknowledgement",
            "--as",
            "ann",
            "--kind",
            "status",
            "--expires-at",
            offset,
        )
        message = self.row("messages")
        self.assertEqual(message["expires_at"], core.iso(end))
        first = json.loads(self.sw("inbox", "--as", "bob", "--json"))["result"]["messages"]
        second = json.loads(self.sw("inbox", "--as", "bob", "--json"))["result"]["messages"]
        self.assertEqual(first, second)
        self.assertTrue(first[0]["requires_ack"])
        self.ack_message(message["id"], "bob")
        self.assertEqual(json.loads(self.sw("inbox", "--as", "bob", "--json"))["result"]["messages"], [])

    def test_inbox_by_id_observes_one_addressed_message_without_acknowledging_it(self):
        self.join("ann")
        self.join("bob")
        self.sw("send", "bob", "Review the interface", "--kind", "review_request", "--as", "ann")
        message = self.row("messages")
        observed = json.loads(self.sw("inbox", "--as", "bob", "--id", str(message["id"]), "--json"))["result"]["messages"]
        self.assertEqual([m["message_id"] for m in observed], [message["id"]])
        with self.database() as db:
            db.row_factory = fixtures.sqlite3.Row
            receipt = db.execute("SELECT * FROM message_recipients WHERE msg=? AND agent='bob'", (message["id"],)).fetchone()
        self.assertIsNotNone(receipt["delivered_at"])
        self.assertIsNone(receipt["acked_at"])
        again = json.loads(self.sw("inbox", "--as", "bob", "--json"))["result"]["messages"]
        self.assertEqual([m["message_id"] for m in again], [message["id"]], "a read observation does not acknowledge")
        self.sw("inbox", "--as", "ann", "--id", str(message["id"]), "--json", ok=False)


    def test_ec213_concurrent_retries_commit_one_message(self):
        self.join("ann")
        self.join("bob")
        results = []

        def send():
            result = fixtures.subprocess.run(
                [
                    fixtures.sys.executable,
                    str(fixtures.SWARM),
                    "send",
                    "bob",
                    "One durable retryable decision",
                    "--as",
                    "ann",
                    "--kind",
                    "decision",
                    "--key",
                    "concurrent-key",
                ],
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            results.append((result.returncode, result.stdout + result.stderr))

        threads = [threading.Thread(target=send) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertTrue(all(code == 0 for code, _ in results), results)
        with self.database() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM messages WHERE idempotency_key='concurrent-key'").fetchone()[0], 1
            )

    def test_ec212_crash_before_commit_rolls_back_and_after_commit_retries_exactly_once(self):
        self.join("ann")
        self.join("bob")
        command = [
            "send",
            "bob",
            "Review this critical fixture decision",
            "--as",
            "ann",
            "--priority",
            "critical",
            "--kind",
            "decision",
            "--key",
            "decision-1",
        ]
        self.sw(*command, ok=False, env={"SWARM_FAILPOINT": "before_message_commit"})
        self.assertIsNone(self.row("messages", "idempotency_key='decision-1'"))
        self.sw(*command, ok=False, env={"SWARM_FAILPOINT": "after_message_commit"})
        message = self.row("messages", "idempotency_key='decision-1'")
        self.sw(*command)
        with self.database() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM messages WHERE idempotency_key='decision-1'").fetchone()[0], 1
            )
        self.sw("inbox", "--as", "bob", "--json", ok=False, env={"SWARM_FAILPOINT": "after_inbox_commit"})
        envelope = json.loads(self.sw("inbox", "--as", "bob", "--json"))["result"]["messages"][-1]
        self.assertEqual(envelope["message_id"], message["id"])
        self.assertEqual(envelope["version"], 1)
        self.assertEqual(envelope["kind"], "decision")
        self.assertEqual(envelope["body_ref"], f"sqlite:messages/{message['id']}/body")
        self.ack_message(message["id"], "bob")
        self.ack_message(message["id"], "bob")
        self.assertEqual(json.loads(self.sw("inbox", "--as", "bob", "--json"))["result"]["messages"], [])
        self.assertEqual(len(json.loads(self.sw("inbox", "--as", "bob", "--all", "--json"))["result"]["messages"]), 1)

    def test_ec213_conflicting_keys_replies_cursors_and_per_recipient_broadcast_ack(self):
        self.join("ann")
        self.join("bob")
        self.sw("send", "bob", "Initial interface question", "--as", "ann", "--kind", "question", "--key", "q-1")
        parent = self.row("messages", "idempotency_key='q-1'")
        self.assertIn(
            "different content",
            self.sw(
                "send",
                "bob",
                "Different interface question",
                "--as",
                "ann",
                "--kind",
                "question",
                "--key",
                "q-1",
                ok=False,
            ),
        )
        self.sw(
            "send",
            "ann",
            "The interface should remain synchronous",
            "--as",
            "bob",
            "--reply-to",
            str(parent["id"]),
            "--kind",
            "decision",
        )
        reply = self.row("messages")
        self.assertEqual(reply["thread_id"], parent["thread_id"])
        self.assertGreater(reply["id"], parent["id"])
        replay = json.loads(
            self.sw("inbox", "--as", "ann", "--all", "--after", str(parent["id"]), "--limit", "1", "--json")
        )
        replay = replay["result"]
        self.assertEqual(replay["messages"][0]["message_id"], reply["id"])
        self.assertEqual(replay["next_cursor"], reply["id"])
        self.sw("send", "*", "Critical current-pool warning", "--as", "ann", "--priority", "critical")
        broadcast = self.row("messages")
        self.join("cat")
        self.assertNotIn("current-pool", self.sw("inbox", "--as", "cat", "--all"))
        self.ack_message(broadcast["id"], "bob")
        self.assertEqual(self.row("messages", "id=?", (broadcast["id"],))["ack_state"], "pending")
        self.assertIn("receipt", self.ack_message(broadcast["id"], "cat", ok=False))
        self.ack_message(broadcast["id"])
        self.assertEqual(self.row("messages", "id=?", (broadcast["id"],))["ack_state"], "acked")

    def test_ec214_dead_letter_escalates_once_and_retention_keeps_unresolved_critical_payload(self):
        self.join("ann")
        self.join("bob")
        self.sw(
            "send",
            "bob",
            "Critical fixture approval is still owed",
            "--as",
            "ann",
            "--priority",
            "critical",
            "--key",
            "late-1",
        )
        message = self.row("messages")
        self.sql(
            "UPDATE messages SET expires_at='2020-01-01T00:00:00+00:00',created_at='2020-01-01T00:00:00+00:00' WHERE id=?",
            (message["id"],),
        )
        self.sw("status")
        self.sw("status")
        dead = self.row("messages", "id=?", (message["id"],))
        self.assertEqual(dead["ack_state"], "dead_letter")
        self.assertIsNone(dead["body_pruned_at"])
        with self.database() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM events WHERE kind='message_dead_letter'").fetchone()[0], 1
            )
        self.assertIn("Critical fixture", self.sw("messages", "dead-letter"))
        self.sw(
            "messages",
            "resolve",
            str(message["id"]),
            "--as",
            "bob",
            "--reason",
            "The fixture was reviewed by its owner",
            ok=False,
        )
        self.sw(
            "messages",
            "resolve",
            str(message["id"]),
            "--reason",
            "The fixture was reviewed and explicitly deferred by the operator",
        )
        self.sw("status")
        self.assertIsNotNone(self.row("messages", "id=?", (message["id"],))["body_pruned_at"])
        self.sw(
            "send",
            "bob",
            "Critical fixture approval is still owed",
            "--as",
            "ann",
            "--priority",
            "critical",
            "--key",
            "late-1",
        )

    def test_ec215_secret_filter_and_payload_bounds_do_not_create_control_authority(self):
        self.setup_worker()
        token = "ghp_" + "a" * 36
        self.sw(
            "send", "bob", f"password=example-only api_key=example-only Authorization: Bearer {token}", "--as", "ann"
        )
        message = self.row("messages")
        self.assertNotIn(token, message["body"])
        self.assertNotIn("example-only", message["body"])
        self.sw("note", f"api_key={token}", "--as", "bob")
        self.assertNotIn(token, self.row("events")["detail"])
        self.sw("send", "bob", "Forged pause directive has no control authority", "--as", "ann", "--kind", "interrupt")
        self.assertEqual(self.task("T1")["state"], "in_progress")
        self.assertIsNone(self.row("interrupts"))
        sw = core.Swarm(self.root)
        try:
            with self.assertRaisesRegex(core.SwarmError, "max_body_bytes"):
                sw.message("ann", "bob", "x" * 70000)
        finally:
            sw.db.close()
        self.assertIn(
            "credential",
            self.sw("send", "bob", "Use an opaque thread", "--as", "ann", "--thread", f"api_key={token}", ok=False),
        )

    def test_ec212_legacy_read_receipts_survive_schema_two_upgrade(self):
        self.join("ann")
        self.join("bob")
        with self.database() as db:
            db.execute("DROP TABLE messages")
            db.execute("DELETE FROM message_recipients")
            db.execute(
                "CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,sender TEXT,recipient TEXT,kind TEXT,body TEXT,task TEXT,created_at TEXT,read_at TEXT)"
            )
            db.execute(
                "INSERT INTO messages(sender,recipient,kind,body,created_at,read_at) VALUES('ann','bob','msg','legacy direct',?,?)",
                (core.iso(), core.iso()),
            )
            db.execute(
                "INSERT INTO messages(sender,recipient,kind,body,created_at) VALUES('ann','*','msg','legacy broadcast',?)",
                (core.iso(),),
            )
            db.execute("INSERT OR REPLACE INTO reads(msg,agent) VALUES(2,'bob')")
            db.execute("UPDATE meta SET value='2' WHERE key='schema_version'")
        self.assertEqual(json.loads(self.sw("inbox", "--as", "bob", "--json"))["result"]["messages"], [])
        self.assertIn("legacy direct", self.sw("inbox", "--as", "bob", "--all"))


class Interrupts(CommunicationCase):
    def test_ec220_failed_hook_cannot_discard_edits_when_a_pause_arrives(self):
        ready = Path(self.tmp.name) / "hook-ready"
        release = Path(self.tmp.name) / "hook-release"
        code = (
            "import sys,time; from pathlib import Path; "
            "Path('src/file.txt').write_text(\"preserve the hook's uncommitted edits\\n\",encoding='utf-8'); "
            f"Path({str(ready)!r}).touch();\n"
            f"while not Path({str(release)!r}).exists(): time.sleep(0.01)\n"
            "print('hook failed',file=sys.stderr); sys.exit(1)"
        )
        config = self.root / ".agents" / "swarm" / "config.toml"
        config.write_text(
            config.read_text(encoding="utf-8")
            + "\n[merge]\nmessage_command = "
            + json.dumps([sys.executable, "-c", code])
            + "\n",
            encoding="utf-8",
        )
        self.git("commit", "-qam", "exercise an actual failing message hook")
        wt = self.setup_worker(ready=True)
        sw = core.Swarm(self.root)
        old_cwd = Path.cwd()
        target = self.git("rev-parse", "main")
        stop, errors = threading.Event(), []

        def pause_hook():
            try:
                deadline = time.monotonic() + 30
                while not ready.exists():
                    if stop.wait(0.01):
                        return
                    if time.monotonic() >= deadline:
                        raise AssertionError("The actual message hook did not become ready")
                self.request()
            except BaseException as exc:
                errors.append(exc)
            finally:
                release.touch()

        controller = threading.Thread(target=pause_hook)
        controller.start()
        try:
            core.cmd_merge(sw, core.build_parser().parse_args(["merge", "--as", "bob"]))
            controller.join(30)
            self.assertFalse(controller.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(
                (wt / "src" / "file.txt").read_text(encoding="utf-8"), "preserve the hook's uncommitted edits\n"
            )
            self.assertEqual(self.task("T1")["state"], "interrupted")
            self.assertEqual(self.git("rev-parse", "main"), target)
        finally:
            stop.set()
            release.touch()
            controller.join(30)
            sw.db.close()
            os.chdir(old_cwd)

    def test_ec220_late_gate_failure_cannot_overwrite_a_fenced_pause(self):
        self.setup_worker(ready=True)
        original = self.git("rev-parse", "main")
        sw = core.Swarm(self.root)
        old_cwd = Path.cwd()

        def gate_fails_after_pause(*args, **kwargs):
            self.request()
            return "The fixture gate failed after the pause request"

        try:
            with mock.patch.object(core, "gate_run", side_effect=gate_fails_after_pause):
                core.cmd_merge(sw, core.build_parser().parse_args(["merge", "--as", "bob"]))
            self.assertEqual(self.task("T1")["state"], "interrupted")
            self.assertEqual(self.git("rev-parse", "main"), original)
        finally:
            sw.db.close()
            os.chdir(old_cwd)

    def test_ec220_released_merger_cannot_use_a_different_task_with_the_same_epoch(self):
        self.setup_worker(ready=True)
        original = self.git("rev-parse", "main")
        sw = core.Swarm(self.root)
        old_cwd = Path.cwd()

        def switch_assignment(*args, **kwargs):
            self.sw("release", "--as", "bob", "Hand off the previous task while a gate is still returning")
            self.sw("claim", "T2", "--as", "bob")
            return None

        try:
            with mock.patch.object(core, "gate_run", side_effect=switch_assignment):
                with self.assertRaises(core.SwarmError):
                    core.cmd_merge(sw, core.build_parser().parse_args(["merge", "--as", "bob"]))
            self.assertEqual(self.git("rev-parse", "main"), original)
            self.assertNotEqual(self.task("T1")["state"], "done")
        finally:
            sw.db.close()
            os.chdir(old_cwd)

    def test_ec216_attention_can_be_answered_without_stopping_an_idle_or_working_agent(self):
        self.join("ann")
        self.join("bob")
        self.request("attention")
        r = self.row("interrupts")
        self.sw("interrupt", "ack", str(r["id"]), "--as", "bob")
        self.sw(
            "interrupt", "complete", str(r["id"]), "--as", "bob", "--note", "Ready to discuss the interface decision"
        )
        self.sw("claim", "T1", "--as", "bob")
        self.sw("plan", "--as", "bob", *fixtures.PLAN)
        self.sw("start", "--as", "bob")
        self.sw(
            "interrupt",
            "request",
            "bob",
            "--mode",
            "attention",
            "--reason",
            "Answer the interface question while continuing independent work",
            "--key",
            "attention-2",
        )
        self.sw("step", "1", "--as", "bob", "--evidence", "Inspected the interface fixture while answering")
        self.ack_control()
        r = self.row("interrupts")
        cp = self.cp()
        self.sw(
            "interrupt",
            "complete",
            str(r["id"]),
            "--as",
            "bob",
            "--epoch",
            str(r["epoch"]),
            "--checkpoint",
            str(cp),
            "--note",
            "The interface question has been answered with a checkpoint",
        )
        self.assertEqual(self.task("T1")["state"], "in_progress")

    def test_ec220_pause_during_gate_preserves_the_target(self):
        self.setup_worker(ready=True)
        original = self.git("rev-parse", "main")
        sw = core.Swarm(self.root)
        old_cwd = Path.cwd()

        def gate_then_pause(*args, **kwargs):
            self.request()
            return None

        try:
            with mock.patch.object(core, "gate_run", side_effect=gate_then_pause):
                with self.assertRaisesRegex(core.SwarmError, "Interrupt"):
                    core.cmd_merge(sw, core.build_parser().parse_args(["merge", "--as", "bob"]))
            self.assertEqual(self.git("rev-parse", "main"), original)
        finally:
            sw.db.close()
            os.chdir(old_cwd)

    def test_ec216_targeted_pause_fences_old_epoch_and_preserves_dirty_work_until_resume(self):
        wt = self.setup_worker()
        old_epoch = self.task("T1")["epoch"]
        self.request()
        r = self.row("interrupts")
        epoch = self.task("T1")["epoch"]
        self.assertGreater(epoch, old_epoch)
        control_message = self.row("messages", "correlation_id=?", (f"interrupt:{r['id']}",))
        self.ack_message(control_message["id"], "bob")
        self.assertEqual(self.row("interrupts")["state"], "requested")
        self.sw("claim", "T2", "--as", "ann")  # unrelated work remains available
        self.assertIn(
            "Interrupt", self.sw("step", "1", "--as", "bob", "--evidence", "Attempting work while paused", ok=False)
        )
        self.assertIn(
            "Stale", self.sw("interrupt", "ack", str(r["id"]), "--as", "bob", "--epoch", str(old_epoch), ok=False)
        )
        self.assertIn(
            "checkpoint", self.sw("release", "--as", "bob", "Trying to bypass the checkpoint protocol", ok=False)
        )
        self.ack_control()
        checkpoint = self.cp()
        self.sw(
            "interrupt",
            "complete",
            str(r["id"]),
            "--as",
            "bob",
            "--epoch",
            str(epoch),
            "--checkpoint",
            str(checkpoint),
            "--note",
            "Paused safely with the current edits retained",
        )
        self.assertEqual(self.task("T1")["state"], "interrupted")
        self.sw("interrupt", "resume", str(r["id"]))
        self.sw("interrupt", "resume", str(r["id"]))
        self.assertEqual(self.task("T1")["state"], "planning")
        self.assertGreater(self.task("T1")["epoch"], epoch)
        self.sw("start", "--as", "bob")
        self.assertEqual((wt / "dirty.txt").read_text(encoding="utf-8"), "preserve uncommitted work\n")

    def test_ec217_yield_requires_a_fresh_checkpoint_including_untracked_contents_and_is_replayable(self):
        wt = self.setup_worker()
        old_checkpoint = self.cp()
        self.request("yield")
        r = self.row("interrupts")
        self.ack_control()
        self.assertIn(
            "predates",
            self.sw(
                "interrupt",
                "complete",
                str(r["id"]),
                "--as",
                "bob",
                "--epoch",
                str(r["epoch"]),
                "--checkpoint",
                str(old_checkpoint),
                "--note",
                "An obsolete checkpoint must not complete the interrupt",
                ok=False,
            ),
        )
        checkpoint = self.cp()
        (wt / "dirty.txt").write_text("changed after the snapshot\n", encoding="utf-8")
        args = [
            "interrupt",
            "complete",
            str(r["id"]),
            "--as",
            "bob",
            "--epoch",
            str(r["epoch"]),
            "--checkpoint",
            str(checkpoint),
            "--note",
            "Hand off the fixture for independent continuation",
        ]
        self.assertIn("Work changed", self.sw(*args, ok=False))
        checkpoint = self.cp()
        args[args.index("--checkpoint") + 1] = str(checkpoint)
        self.sw(*args)
        self.sw(*args)
        self.sw(
            "handoff",
            "--as",
            "bob",
            "--checkpoint",
            str(checkpoint),
            "--note",
            "Hand off the fixture for independent continuation",
        )
        self.assertEqual(self.task("T1")["state"], "open")
        self.assertTrue((wt / "dirty.txt").exists())
        self.assertEqual(self.row("messages", "envelope_kind='handoff'")["correlation_id"], f"checkpoint:{checkpoint}")
        self.sw("claim", "T1", "--adopt", "--as", "ann")
        self.assertIn(
            "holds no task",
            self.sw("step", "1", "--as", "bob", "--evidence", "An obsolete worker attempts to continue", ok=False),
        )

    def test_ec218_timeout_escalates_once_and_operator_recovers_without_owner_ack(self):
        wt = self.setup_worker()
        self.request()
        self.sql("UPDATE interrupts SET deadline_at='2020-01-01T00:00:00+00:00'")
        self.sw("status")
        self.sw("status")
        self.assertEqual(self.row("interrupts")["state"], "timed_out")
        with self.database() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE kind='interrupt_timeout'").fetchone()[0], 1)
        checkpoint = self.cp(owner="ann", operator=True)
        self.sw(
            "handoff",
            "--as",
            "ann",
            "--task",
            "T1",
            "--epoch",
            str(self.task("T1")["epoch"]),
            "--checkpoint",
            str(checkpoint),
            "--note",
            "Owner failed to acknowledge; preserve and replan the fixture",
        )
        self.assertTrue(wt.exists())
        self.assertEqual(self.task("T1")["state"], "open")
        self.assertIsNone(self.task("T1")["assignee"])
        self.assertIn("marked offline", self.sw("claim", "T2", "--as", "bob", ok=False))

    def test_ec219_cancel_needs_human_policy_and_never_marks_work_verified(self):
        wt = self.setup_worker()
        self.assertIn("Cancel requires", self.request("cancel", ok=False, env={"SWARM_AS": "ann"}))
        config = self.root / ".agents" / "swarm" / "config.toml"
        config.write_text(
            config.read_text(encoding="utf-8") + '\n[interrupts]\nallow_coordinator_cancel = "false"\n',
            encoding="utf-8",
        )
        self.assertIn("must be bool", self.request("cancel", ok=False, env={"SWARM_AS": "ann"}))
        config.write_text(config.read_text(encoding="utf-8").replace('allow_coordinator_cancel = "false"', 'allow_coordinator_cancel = false'), encoding="utf-8")
        self.request("cancel")
        r = self.row("interrupts")
        self.ack_control()
        checkpoint = self.cp()
        self.sw(
            "interrupt",
            "complete",
            str(r["id"]),
            "--as",
            "bob",
            "--epoch",
            str(r["epoch"]),
            "--checkpoint",
            str(checkpoint),
            "--note",
            "Abort this assignment while preserving its unfinished artifacts",
        )
        self.assertNotEqual(self.task("T1")["state"], "done")
        self.assertIsNone(self.task("T1")["merged_sha"])
        self.assertTrue((wt / "dirty.txt").exists())
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                'allow_coordinator_cancel = false', "allow_coordinator_cancel = true"
            ),
            encoding="utf-8",
        )
        self.sw("claim", "T1", "--adopt", "--as", "bob")
        self.request("cancel", env={"SWARM_AS": "ann"})
        self.assertEqual(self.row("interrupts")["requester"], "ann")

    def test_ec220_pause_during_gate_or_after_intent_never_advances_target(self):
        self.setup_worker(ready=True)
        original = self.git("rev-parse", "main")
        sw = core.Swarm(self.root)
        old_cwd = Path.cwd()
        try:

            def pause_after_intent(name):
                if name == "after_intent":
                    self.request()

            with mock.patch.object(core, "failpoint", side_effect=pause_after_intent):
                with self.assertRaisesRegex(core.SwarmError, "Interrupt"):
                    core.cmd_merge(sw, core.build_parser().parse_args(["merge", "--as", "bob"]))
            self.assertEqual(self.git("rev-parse", "main"), original)
            self.assertEqual(self.task("T1")["state"], "interrupted")
        finally:
            sw.db.close()
            os.chdir(old_cwd)

    def test_ec220_pause_during_rebase_prevents_integration(self):
        self.setup_worker(ready=True)
        original = self.git("rev-parse", "main")
        sw = core.Swarm(self.root)
        old_cwd = Path.cwd()
        real_run = core.run

        def run_then_interrupt(argv, **kwargs):
            result = real_run(argv, **kwargs)
            if argv[:2] == ["git", "rebase"]:
                self.request()
            return result

        try:
            with mock.patch.object(core, "run", side_effect=run_then_interrupt):
                with self.assertRaisesRegex(core.SwarmError, "Interrupt"):
                    core.cmd_merge(sw, core.build_parser().parse_args(["merge", "--as", "bob"]))
            self.assertEqual(self.git("rev-parse", "main"), original)
        finally:
            sw.db.close()
            os.chdir(old_cwd)

    def test_ec221_killed_interrupt_checkpoint_and_handoff_transactions_recover_idempotently(self):
        wt = self.setup_worker()
        self.request(ok=False, env={"SWARM_FAILPOINT": "before_interrupt_commit"})
        self.assertIsNone(self.row("interrupts"))
        self.assertEqual(self.task("T1")["epoch"], 1)
        self.request(ok=False, env={"SWARM_FAILPOINT": "after_interrupt_commit"})
        self.request()
        self.ack_control()
        epoch = str(self.task("T1")["epoch"])
        cp_args = [
            "checkpoint",
            "--as",
            "bob",
            "--epoch",
            epoch,
            "--note",
            "The interface work is partially complete",
            "--next",
            "Review the fixture and finish the acceptance check",
        ]
        self.sw(*cp_args, ok=False, env={"SWARM_FAILPOINT": "before_checkpoint_commit"})
        self.assertIsNone(self.row("checkpoints"))
        self.sw(*cp_args, ok=False, env={"SWARM_FAILPOINT": "after_checkpoint_commit"})
        checkpoint = self.row("checkpoints")["id"]
        args = [
            "handoff",
            "--as",
            "bob",
            "--epoch",
            epoch,
            "--checkpoint",
            str(checkpoint),
            "--note",
            "Preserve this checkpoint and replan the acceptance work",
        ]
        self.sw(*args, ok=False, env={"SWARM_FAILPOINT": "before_handoff_commit"})
        self.assertEqual(self.task("T1")["state"], "interrupted")
        self.sw(*args, ok=False, env={"SWARM_FAILPOINT": "after_handoff_commit"})
        self.sw(*args)
        self.assertEqual(self.task("T1")["state"], "open")
        self.assertTrue((wt / "dirty.txt").exists())

    def test_ec222_contract_extension_cannot_resume_a_targeted_pause(self):
        self.setup_worker(contracted=True)
        self.request()
        terms = json.loads(self.row("task_contracts")["terms"])
        terms["deadline_at"] = "2020-01-01T00:00:00+00:00"
        self.sql("UPDATE task_contracts SET terms=?", (json.dumps(terms),))
        self.sw("status")
        self.sw(
            "contract",
            "extend",
            "T1",
            "--minutes",
            "5",
            "--reason",
            "Allow a bounded recovery window for the retained work",
        )
        self.assertIn("Interrupt", self.sw("start", "--as", "bob", ok=False))
        self.assertEqual(self.task("T1")["state"], "interrupted")
        self.sql("UPDATE interrupts SET deadline_at='2020-01-01T00:00:00+00:00'")
        self.sw("status")
        checkpoint = self.cp(owner="ann", operator=True)
        self.sw(
            "handoff",
            "--as",
            "ann",
            "--task",
            "T1",
            "--epoch",
            str(self.task("T1")["epoch"]),
            "--checkpoint",
            str(checkpoint),
            "--note",
            "Retain the paused assignment for an explicit replacement contract",
        )


if __name__ == "__main__":
    unittest.main()
