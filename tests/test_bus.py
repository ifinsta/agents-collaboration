"""Bus contract conformance against real SQLite/Git and killed CLI transactions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import timedelta
import hashlib
import io
import json
import subprocess
import sys
from unittest import mock

import test_final_transitions as transitions
from test_hardening import HardeningCase, core, fixtures


class BusCase(HardeningCase):
    def setUp(self):
        super().setUp()
        self.join("ann")
        self.join("bob")

    def command(self, *args, ok=True, who="bob"):
        original = core.Swarm
        output = io.StringIO()
        with redirect_stdout(output), mock.patch.object(core, "Swarm", side_effect=lambda: original(self.root)):
            code = core.main(["--json", "--as", who, *args])
        result = json.loads(output.getvalue())
        self.assertEqual(result["ok"], ok, result)
        self.assertEqual(code, 0 if ok else 2, result)
        return result["result"] if ok else result["error"]

    def bus(self, *args, **kwargs):
        return self.command("bus", *args, **kwargs)

    def publish(self, *, to="bob", key="message-1", **kwargs):
        return self.bus("publish", to, "Inspect the accepted source fixture", "--kind", "decision", "--key", key, who="ann", **kwargs)["message"]

    def receive(self, consumer="bob:boot-1", **kwargs):
        return self.bus("receive", "--consumer", consumer, **kwargs)["deliveries"]

    def receipt_command(self, action, receipt, *extra, **kwargs):
        return self.bus(action, str(receipt["message_id"]), "--consumer", receipt["consumer"], "--token", receipt["token"], *extra, **kwargs)


class Bus(BusCase):
    def test_ec330_envelope_schema_idempotent_publish_and_installed_contract(self):
        schema = self.bus("schema")
        message = self.publish()
        self.assertEqual(message, self.publish())
        self.assertEqual(set(message), set(schema["required"]))
        self.assertEqual(set(message), set(schema["properties"]))
        self.assertEqual(message["version"], schema["properties"]["version"]["const"])
        self.assertIn(message["kind"], schema["properties"]["kind"]["enum"])
        self.bus("publish", "bob", "Conflicting content for the original retry key", "--kind", "decision", "--key", "message-1", who="ann", ok=False)
        manifest = json.loads((fixtures.SWARM.parent / "MANIFEST.json").read_text(encoding="utf-8"))
        for name in ("BUS.md", "BUS.schema.json"):
            self.assertEqual(manifest["files"][name], hashlib.sha256((fixtures.SWARM.parent / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest())

    def test_ec331_concurrent_consumers_get_one_receipt_and_legacy_cannot_ack_it(self):
        message = self.publish()
        self.bus("ack", str(message["message_id"]), "--consumer", "bob:unclaimed", "--token", "not-a-receipt", ok=False)

        def receive(consumer):
            done = subprocess.run([sys.executable, str(fixtures.SWARM), "--json", "--as", "bob", "bus", "receive", "--consumer", consumer], cwd=self.root, capture_output=True, text=True, encoding="utf-8", check=True)
            return json.loads(done.stdout)["result"]["deliveries"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            batches = list(pool.map(receive, ("bob:one", "bob:two")))
        deliveries = [d for batch in batches for d in batch]
        self.assertEqual(len(deliveries), 1)
        receipt = deliveries[0]["receipt"]
        self.assertEqual(receipt["message_id"], message["message_id"])
        self.assertEqual(self.command("inbox")["messages"], [])
        self.assertEqual(len(self.command("inbox", "--all")["messages"]), 1)
        self.command("ack", "--message", str(message["message_id"]), ok=False)
        self.assertTrue(self.receipt_command("ack", receipt)["changed"])
        self.assertFalse(self.receipt_command("ack", receipt)["changed"])
        self.bus("publish", "ann", "Reviewed the accepted source fixture", "--reply-to", str(message["message_id"]))

    def test_ec332_expired_receipts_retry_and_renew_reject_old_consumer_authority(self):
        self.publish()
        first = self.receive()[0]["receipt"]
        with self.board() as sw, sw.tx():
            sw.db.execute("UPDATE message_claims SET lease_until=?", (core.iso(core.utcnow() - timedelta(seconds=1)),))
        self.receipt_command("ack", first, ok=False)
        second = self.receive("bob:boot-2")[0]["receipt"]
        self.assertEqual(second["attempt"], 2)
        self.assertNotEqual(first["token"], second["token"])
        self.receipt_command("ack", first, ok=False)
        self.assertEqual(self.receipt_command("renew", second, "--lease-sec", "300")["outcome"], "renewed")
        self.receipt_command("retry", second, "--reason", "The evidence tool is temporarily unavailable")
        self.receipt_command("ack", second, ok=False)
        third = self.receive()[0]["receipt"]
        self.assertEqual(third["attempt"], 3)
        self.receipt_command("ack", third)
        self.assertEqual(self.receive(), [])

    def test_ec333_expiry_dead_letter_and_broadcast_keep_independent_receipts(self):
        self.publish(to="*")
        bob = self.receive()[0]["receipt"]
        human = self.bus("receive", "--consumer", "operator:one", who="human")["deliveries"][0]["receipt"]
        self.receipt_command("ack", bob)
        self.assertEqual(len(self.bus("receive", "--consumer", "operator:two", who="human")["deliveries"]), 0)
        self.receipt_command("ack", human, who="human")
        self.bus("publish", "bob", "Inspect this critical evidence before continuing", "--priority", "critical", who="ann")
        receipt = self.receive()[0]["receipt"]
        with self.board() as sw, sw.tx():
            sw.db.execute("UPDATE messages SET expires_at=? WHERE id=?", (core.iso(core.utcnow() - timedelta(seconds=1)), receipt["message_id"]))
        self.receipt_command("ack", receipt, ok=False)
        self.assertEqual(self.receive(), [])
        with self.board() as sw:
            self.assertEqual(sw.db.execute("SELECT ack_state FROM messages WHERE id=?", (receipt["message_id"],)).fetchone()[0], "dead_letter")
            self.assertIsNone(sw.db.execute("SELECT acked_at FROM message_recipients WHERE msg=? AND agent='bob'", (receipt["message_id"],)).fetchone()[0])

    def test_ec334_plain_send_uses_reliable_delivery_and_fifo_is_explicit(self):
        plain = self.command("send", "bob", "A reliable default status notification", who="ann")["message"]
        self.assertTrue(plain["requires_ack"])
        first = self.publish()
        second = self.bus("publish", "bob", "A later urgent observation", "--priority", "critical", who="ann")["message"]
        deliveries = self.receive()
        self.assertEqual([d["message"]["message_id"] for d in deliveries], [plain["message_id"], first["message_id"], second["message_id"]])
        self.assertEqual(self.command("inbox")["messages"], [])
        for args in (("--lease-sec", "0"), ("--lease-sec", "301"), ("--limit", "0"), ("--limit", "1001")):
            self.bus("receive", "--consumer", "bob:limits", *args, ok=False)
        self.bus("receive", "--consumer", "contains whitespace", ok=False)
        self.command("--epoch", "-1", "bus", "publish", "bob", "An invalid negative task epoch", who="ann", ok=False)

    def test_ec335_schema10_migration_keeps_existing_mailbox_and_receipts(self):
        message = self.publish()
        with self.board() as sw, sw.tx():
            sw.db.execute("DROP TABLE message_claims")
            sw.set_meta("schema_version", "10")
        with self.board() as sw:
            self.assertEqual(sw.meta("schema_version"), str(core.SCHEMA_VERSION))
            self.assertEqual(sw.db.execute("SELECT COUNT(*) FROM message_claims").fetchone()[0], 0)
        self.assertEqual(self.receive()[0]["message"]["message_id"], message["message_id"])


class BusCrashes(BusCase):
    paused = transitions.FinalTransitions.paused
    kill = transitions.FinalTransitions.kill

    def test_ec336_receive_and_ack_crashes_recover_committed_receipts_only(self):
        self.publish()
        receive = ["--json", "--as", "bob", "bus", "receive", "--consumer", "bob:crash"]
        with self.paused("before_cmd_bus_commit", *receive) as child:
            self.kill(child)
        with self.board() as sw:
            self.assertEqual(sw.db.execute("SELECT COUNT(*) FROM message_claims").fetchone()[0], 0)
        with self.paused("after_cmd_bus_commit", *receive) as child:
            self.kill(child)
        self.assertEqual(self.receive(), [])
        with self.board() as sw, sw.tx():
            sw.db.execute("UPDATE message_claims SET lease_until=?", (core.iso(core.utcnow() - timedelta(seconds=1)),))
        receipt = self.receive()[0]["receipt"]
        ack = ["--json", "--as", "bob", "bus", "ack", str(receipt["message_id"]), "--consumer", receipt["consumer"], "--token", receipt["token"]]
        with self.paused("before_cmd_bus_commit", *ack) as child:
            self.kill(child)
        with self.board() as sw:
            self.assertIsNone(sw.db.execute("SELECT acked_at FROM message_recipients WHERE msg=? AND agent='bob'", (receipt["message_id"],)).fetchone()[0])
        with self.paused("after_cmd_bus_commit", *ack) as child:
            self.kill(child)
        self.assertFalse(self.receipt_command("ack", receipt)["changed"])
