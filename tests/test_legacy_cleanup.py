"""Current writes use one delivery, execution and verification contract."""

from __future__ import annotations

import json

from test_hardening import HardeningCase, core


class LegacyCleanup(HardeningCase):
    def test_ec344_replies_and_observation_never_acknowledge_a_delivery(self):
        self.join("ann")
        self.join("bob")
        message = self.json_command("send", "bob", "Review the current interface", "--as", "ann", "--json")["result"]["message"]
        self.assertEqual(message["kind"], "status")
        self.assertTrue(message["requires_ack"])
        self.sw("inbox", "--as", "bob")
        self.sw("send", "ann", "The interface review is still in progress", "--reply-to", str(message["message_id"]), "--as", "bob")
        with self.board() as board:
            self.assertIsNone(board.db.execute("SELECT acked_at FROM message_recipients WHERE msg=? AND agent='bob'", (message["message_id"],)).fetchone()[0])
            for kind in core.HISTORICAL_MESSAGE_KINDS:
                with self.subTest(kind=kind), self.assertRaisesRegex(core.SwarmError, "Unsupported message kind"):
                    board.message("ann", "bob", "An obsolete producer must upgrade", kind=kind)
        self.ack_message(message["message_id"], "bob")
        self.assertNotIn("Review the current interface", self.sw("inbox", "--as", "bob"))

    def test_ec344_all_fresh_claims_have_contracts_and_old_active_work_requires_recovery(self):
        self.join("ann")
        self.sw("claim", "T1", "--as", "ann")
        with self.board() as board, board.tx():
            contract = core.current_contract(board, "T1")
            self.assertEqual(contract["state"], "active")
            self.assertEqual(contract["epoch"], board.task("T1")["epoch"])
            self.assertEqual(json.loads(contract["terms"])["scope"], "src/")
            board.db.execute("DELETE FROM task_contracts WHERE task='T1'")
        self.assertIn("no contract", self.sw("start", "--as", "ann", ok=False))
        self.sw("checkpoint", "--as", "ann", "--epoch", str(self.task("T1")["epoch"]), "--note", "Preserve the older assignment before upgrading", "--next", "Release and reclaim under current contract terms")
        self.sw("release", "--as", "ann", "Preserve the older assignment and accept current terms on reclaim.")
        self.sw("claim", "T1", "--as", "ann")

    def test_ec344_retired_budget_setting_refuses_silent_loss_of_limits(self):
        config = self.root / ".agents/swarm/config.toml"
        config.write_text(config.read_text(encoding="utf-8").replace("[swarm]", "[swarm]\ntask_budget_min = 15"), encoding="utf-8")
        self.assertIn("Use [contracts] active_time_min", self.sw("status", ok=False))

    def test_ec344_integration_without_executable_gates_preserves_work(self):
        self.join("ann")
        worktree = self.to_ready("ann", "T1")
        target = self.git("rev-parse", "main")
        config = self.root / ".agents/swarm/config.toml"
        config.write_text("\n".join("commands = []" if line.startswith("commands =") else line for line in config.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8")
        self.assertIn("Integration requires configured verification gates", self.sw("merge", "--as", "ann", ok=False))
        self.assertEqual(self.git("rev-parse", "main"), target)
        self.assertTrue((worktree / "src/file.txt").is_file())
        self.assertEqual(self.task("T1")["state"], "ready_to_merge")

    def test_ec344_protocol_two_has_one_result_location_and_refuses_version_one(self):
        self.assertEqual(core.PROTOCOL_VERSION, 2)
        self.assertIn("Unsupported protocol version 1", self.json_command("--protocol-version", "1", "protocol", "--json", ok=False)["error"]["message"])
        self.assertFalse((self.root / ".git/swarm").exists())
        for command, field in (("environment", "rules"), ("inbox", "messages")):
            with self.subTest(command=command):
                result = self.json_command(command, "--json")
                self.assertIn(field, result["result"])
                self.assertNotIn(field, result)

    def test_ec344_reclaim_carries_deadline_scope_and_remaining_allowances(self):
        self.join("ann")
        self.sw("claim", "T1", "--as", "ann")
        with self.board() as board, board.tx():
            original = core.current_contract(board, "T1")
            terms = json.loads(original["terms"])
            board.db.execute("UPDATE task_contracts SET active_seconds=60 WHERE id=?", (original["id"],))
        self.sw("release", "--as", "ann", "Preserve the remaining allowance for the next task owner.")
        self.sw("claim", "T1", "--as", "ann")
        with self.board() as board:
            current = core.current_contract(board, "T1")
            retained = json.loads(current["terms"])
            self.assertEqual(retained["deadline_at"], terms["deadline_at"])
            self.assertEqual(retained["scope"], terms["scope"])
            self.assertEqual(retained["budget"]["origin"], terms["budget"]["origin"])
            self.assertAlmostEqual(retained["active_time_min"], terms["active_time_min"] - 1, places=2)
