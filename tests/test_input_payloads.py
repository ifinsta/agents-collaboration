"""Bounded operator inputs and typed lifecycle results against actual temporary boards."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from unittest import mock

from test_hardening import HardeningCase, core, fixtures


class InputAndPayloads(HardeningCase):
    def test_ec325_native_send_environment_and_lock_receipts_require_no_prose_parsing(self):
        self.join("ann")
        self.join("bob")
        args = ["send", "bob", "Inspect the versioned interface before implementation", "--as", "ann", "--key", "receipt-1", "--json"]
        sent = self.json_command(*args)["result"]["message"]
        self.assertIsInstance(sent["message_id"], int)
        self.assertEqual(self.json_command(*args)["result"]["message"]["message_id"], sent["message_id"])
        inbox = self.json_command("inbox", "--as", "bob", "--json")["result"]
        self.assertIn(sent["message_id"], [m["message_id"] for m in inbox["messages"]])
        environment = self.json_command("env", "--as", "ann", "--json")["result"]["environment"]
        self.assertEqual(environment["SWARM_AS"], "ann")
        self.assertEqual(environment["SWARM_SLOT"], "1")
        claimed = self.json_command("claim", "T5", "--as", "ann", "--json")["result"]
        self.assertEqual([(r["name"], r["agent"]) for r in claimed["locks"]], [("config", "ann")])

    def test_ec324_configuration_shape_and_file_limits_refuse_without_losing_board_state(self):
        self.join("ann")
        self.sw("claim", "T1", "--as", "ann")
        before = dict(self.task("T1"))
        path = self.root / ".agents/swarm/config.toml"
        original = path.read_bytes()
        try:
            for invalid in (b'project = "invalid"', b'[swarm]\nmax_agents = true', b'[gates]\ntimeout_min = nan', b'#' * (1024 * 1024 + 1)):
                path.write_bytes(invalid)
                result = self.json_command("status", "--json", ok=False)
                self.assertEqual(result["error"]["code"], "command_refused")
                self.assertIn("retry", result["error"]["message"])
                self.assertEqual(dict(self.task("T1")), before)
        finally:
            path.write_bytes(original)
        self.json_command("status", "--json")
        backlog = self.root / "backlog.md"
        saved = backlog.read_bytes()
        try:
            backlog.write_bytes(b"#" * (1024 * 1024 + 1))
            self.assertIn("exceeds", self.sw("sync", ok=False))
            self.assertEqual(dict(self.task("T1")), before)
        finally:
            backlog.write_bytes(saved)

    def test_ec324_embedded_oversized_cli_and_unbounded_log_requests_have_repair_refusals(self):
        output = io.StringIO()
        with redirect_stdout(output), mock.patch.object(core, "Swarm", side_effect=AssertionError("oversized input opened a board")):
            self.assertEqual(core.main(["--json", "pause", "x" * 65537]), 2)
        self.assertIn("64 KiB", json.loads(output.getvalue())["error"]["message"])
        self.join("ann")
        for limit in ("-1", "0", "1001"):
            self.assertIn("--limit", self.json_command("log", "--limit", limit, "--json", ok=False)["error"]["message"])

    def test_ec325_lifecycle_payloads_expose_questions_and_the_released_subject(self):
        self.join("ann")
        self.json_command("claim", "T1", "--as", "ann", "--json")
        plan = self.json_command("plan", "--as", "ann", *fixtures.PLAN, "--json")["result"]
        self.assertIsInstance(plan["task"]["plan"], dict)
        question = self.json_command("ask", "Which response contract should this implementation use?", "--critical", "--to", "human", "--as", "ann", "--json")["result"]["questions"][-1]
        answered = self.json_command("answer", str(question["id"]), "Use the documented versioned response contract", "--json")["result"]["question"]
        self.assertEqual(answered["task"], "T1")
        self.assertEqual(answered["answer"], "Use the documented versioned response contract")
        listed = self.json_command("questions", "--task", "T1", "--all", "--json")["result"]["questions"]
        self.assertEqual(listed[-1], answered)
        self.json_command("ask", "Which follow-up check should the successor run?", "--to", "human", "--as", "ann", "--json")
        page = self.json_command("questions", "--task", "T1", "--all", "--limit", "1", "--json")["result"]
        following = self.json_command("questions", "--task", "T1", "--all", "--limit", "1", "--after", str(page["next_cursor"]), "--json")["result"]
        self.assertEqual(page["questions"][0]["id"], question["id"])
        self.assertGreater(following["questions"][0]["id"], question["id"])
        self.json_command("questions", "--limit", "0", "--json", ok=False)
        result = self.json_command("release", "--as", "ann", "Retain implementation and answered questions for a bounded successor", "--json")["result"]
        self.assertEqual(result["task"]["id"], "T1")
        self.assertEqual(result["task"]["state"], "open")
        self.assertIsNone(result["agent"]["task"])
