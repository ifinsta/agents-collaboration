"""Usage reservations, honest evidence and recovery against disposable Git repositories."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest import mock

from test_hardening import HardeningCase, core
from test_verification import VerificationCase
import test_swarm as fixtures


class Budgets(HardeningCase):
    def test_ec321_native_claude_and_codex_reports_keep_hashes_and_count_cache_once(self):
        self.activate("--token-limit", "100", "--cost-limit", "1")
        claude = self.reserve("claude", "--tokens", "40", "--cost", "0.1")["result"]["run"]
        source = Path(self.tmp.name) / "native.json"
        source.write_text(json.dumps({"type": "result", "usage": {"input_tokens": 20, "output_tokens": 3,
            "cache_creation_input_tokens": 4, "cache_read_input_tokens": 5}, "total_cost_usd": 0.01}), encoding="utf-8")
        result = self.json_command("usage", "report", claude["id"], "--as", "ann", "--source", str(source), "--format", "claude", "--json")["result"]["run"]
        self.assertEqual(result["reported_tokens"], 32)
        self.assertEqual(result["reported_micros"], 10000)
        self.assertEqual(result["source_hash"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(result["source_data"]["format"], "claude")
        codex = self.reserve("codex", "--tokens", "20", "--cost", "0")["result"]["run"]
        source.write_text(json.dumps({"type": "thread.started"}) + "\n" + json.dumps({"type": "turn.completed",
            "usage": {"input_tokens": 10, "cached_input_tokens": 9, "output_tokens": 2}}), encoding="utf-8")
        result = self.json_command("usage", "report", codex["id"], "--as", "ann", "--source", str(source), "--format", "codex", "--json")["result"]["run"]
        self.assertEqual(result["reported_tokens"], 12)
        self.assertIsNone(result["reported_micros"])
        self.assertEqual(result["state"], "closed")

    def test_ec321_incomplete_or_invalid_native_reports_cannot_fabricate_zero_or_settle(self):
        self.activate("--token-limit", "100", "--cost-limit", "1")
        run = self.reserve("native", "--tokens", "100", "--cost", "1")["result"]["run"]
        source = Path(self.tmp.name) / "native.json"
        for counters in ({"input_tokens": True, "output_tokens": 2}, {"input_tokens": "5", "output_tokens": 2}, {"input_tokens": -1}):
            source.write_text(json.dumps({"type": "result", "usage": counters}), encoding="utf-8")
            error = self.json_command("usage", "report", run["id"], "--as", "ann", "--source", str(source), "--format", "claude", "--json", ok=False)
            self.assertIn("counters", error["error"]["message"])
        source.write_text(json.dumps({"type": "result", "usage": {"input_tokens": 5}}), encoding="utf-8")
        result = self.json_command("usage", "report", run["id"], "--as", "ann", "--source", str(source), "--format", "claude", "--json")["result"]["run"]
        self.assertEqual(result["state"], "unknown")
        self.assertIsNone(result["reported_tokens"])
        self.assertIsNone(result["reported_micros"])

    def activate(self, *limits, start=False):
        self.join("ann")
        self.sw("contract", "offer", "T1", "ann", "--as", "human", *limits)
        self.sw("contract", "accept", "T1", "--as", "ann")
        self.sw("claim", "T1", "--as", "ann")
        if start:
            self.sw("plan", "--as", "ann", *fixtures.PLAN)
            self.sw("start", "--as", "ann")
        return Path(self.task("T1")["worktree"])

    def reserve(self, key="window", *amounts, ok=True, env=None):
        return self.json_command(
            "usage", "reserve", "T1", "--as", "ann", "--key", key, *amounts, "--json", ok=ok, env=env
        )

    def ledger(self):
        return self.json_command("usage", "show", "T1", "--json")["result"]

    def report(self, ident, data, ok=True, env=None):
        source = Path(self.tmp.name) / "usage.json"
        source.write_text(json.dumps(data), encoding="utf-8")
        return self.json_command(
            "usage", "report", ident, "--source", str(source), "--as", "ann", "--json", ok=ok, env=env
        )

    def test_ec263_schema_seven_upgrade_rolls_back_and_keeps_legacy_terms(self):
        self.activate()
        with self.board() as sw, sw.tx():
            c = core.current_contract(sw, "T1")
            terms = json.loads(c["terms"])
            terms.pop("budget")
            sw.db.execute("UPDATE task_contracts SET terms=?", (json.dumps(terms),))
            sw.db.execute("DROP TABLE usage_runs")
            sw.set_meta("schema_version", "7")
        self.sw("status", ok=False, env={"SWARM_FAILPOINT": "during_migration"})
        db = self.db()
        try:
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "7")
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='usage_runs'").fetchone())
        finally:
            db.close()
        usage = self.ledger()["usage"]
        self.assertIsNone(usage["budget"]["tokens"])
        self.assertIsNone(usage["reported_cost_micros"])
        self.assertEqual(self.ledger()["runs"], [])

    def test_ec264_policy_is_bounded_and_new_limits_require_human_authority(self):
        self.join("ann")
        denied = self.sw("contract", "offer", "T1", "ann", "--as", "ann", "--token-limit", "100", ok=False)
        self.assertIn("Humans own budget increases", denied)
        for flag, value in (
            ("--cost-limit", "NaN"),
            ("--tool-time-min", "nan"),
            ("--currency", "usd"),
            ("--token-limit", "0"),
        ):
            with self.subTest(flag=flag):
                self.sw("contract", "offer", "T1", "ann", flag, value, "--as", "human", ok=False)
        self.sw("contract", "offer", "T1", "ann", "--cost-limit", "0.1000009", "--as", "human")
        with self.board() as sw:
            self.assertEqual(core.contract_budget(core.current_contract(sw, "T1"))["cost_micros"], 100000)

    def test_ec265_reservations_hold_allowance_and_retry_without_double_debit(self):
        self.activate("--token-limit", "100", "--cost-limit", "0.5")
        first = self.reserve("one", "--tokens", "60", "--cost", "0.3")["result"]["run"]
        replay = self.reserve("one", "--tokens", "60", "--cost", "0.3")["result"]["run"]
        self.assertEqual(first["id"], replay["id"])
        page = self.json_command("usage", "show", "T1", "--limit", "1", "--json")["result"]
        self.assertEqual(page["runs"][0]["id"], first["id"])
        self.assertEqual(
            self.json_command("usage", "show", "T1", "--after", str(page["next_cursor"]), "--json")["result"]["runs"],
            [],
        )
        self.json_command("usage", "show", "T1", "--limit", "201", "--json", ok=False)
        self.reserve("two", "--tokens", "50", "--cost", "0.2", ok=False)
        self.reserve("one", "--tokens", "40", "--cost", "0.2", ok=False)
        usage = self.ledger()["usage"]
        self.assertEqual(usage["reserved"]["tokens"], 60)
        self.assertEqual(usage["remaining"]["cost_micros"], 200000)
        self.assertIsNone(usage["reported_tokens"])
        self.assertEqual(len(self.ledger()["runs"]), 1)

    def test_ec266_numeric_reports_are_hashed_minimized_and_missing_cost_is_unknown(self):
        self.activate("--token-limit", "100", "--cost-limit", "0.5")
        ident = self.reserve()["result"]["run"]["id"]
        first = {"tokens": 20, "prompt": "private prompt must not enter ledger"}
        row = self.report(ident, first)["result"]["run"]
        self.assertEqual(row["state"], "unknown")
        self.assertIsNone(row["reported_micros"])
        self.assertEqual(row["source_hash"], hashlib.sha256(json.dumps(first).encode()).hexdigest())
        self.assertNotIn("private prompt", json.dumps(self.ledger()))
        self.report(ident, {"tokens": 19, "cost": "0.1", "currency": "USD"}, ok=False)
        self.report(ident, {"tokens": 21, "cost": "0.1", "currency": "EUR"}, ok=False)
        final = {"tokens": 21, "cost": "0.1000001", "currency": "USD"}
        row = self.report(ident, final)["result"]["run"]
        self.assertEqual(row["reported_micros"], 100001)
        self.assertEqual(row["state"], "closed")
        self.assertEqual(self.report(ident, final)["result"]["run"]["source_hash"], row["source_hash"])
        self.report(ident, {"tokens": 22, "cost": "0.2", "currency": "USD"}, ok=False)

    def test_ec267_actual_overrun_fences_work_and_time_alone_cannot_reopen_it(self):
        wt = self.activate("--token-limit", "100")
        ident = self.reserve()["result"]["run"]["id"]
        self.sw("plan", "--as", "ann", *fixtures.PLAN)
        self.sw("start", "--as", "ann")
        (wt / "unfinished.txt").write_text("retained", encoding="utf-8")
        epoch = self.task("T1")["epoch"]
        self.report(ident, {"tokens": 120})
        self.assertEqual(self.task("T1")["state"], "expired")
        self.assertGreater(self.task("T1")["epoch"], epoch)
        self.assertEqual(self.reserve()["result"]["run"]["id"], ident)
        self.assertEqual(self.ledger()["usage"]["policy_debit"]["tokens"], 120)
        self.sw("start", "--as", "ann", ok=False)
        self.sw(
            "contract",
            "extend",
            "T1",
            "--minutes",
            "5",
            "--reason",
            "Time does not authorize additional token consumption.",
            "--as",
            "human",
            ok=False,
        )
        self.sw("record", "T1", "--commit", "HEAD", ok=False)
        self.sw(
            "contract",
            "extend",
            "T1",
            "--minutes",
            "5",
            "--token-limit",
            "200",
            "--reason",
            "Human approves a bounded recovery allowance after actual overrun.",
            "--as",
            "human",
        )
        usage = self.ledger()["usage"]
        self.assertEqual(usage["remaining"]["tokens"], 80)
        self.assertEqual((wt / "unfinished.txt").read_text(encoding="utf-8"), "retained")
        with self.board() as sw:
            c = core.current_contract(sw, "T1")
            self.assertEqual(c["extension_count"], 1)
            self.assertEqual(len(json.loads(c["terms"])["budget_history"]), 1)

    def test_ec268_human_settlement_charges_reservation_without_inventing_actuals(self):
        self.activate("--token-limit", "100", "--cost-limit", "0.5")
        ident = self.reserve("one", "--tokens", "60", "--cost", "0.3")["result"]["run"]["id"]
        args = (
            "usage",
            "reconcile",
            ident,
            "--confirm-stopped",
            "--charge-reserved",
            "--reason",
            "The external process has stopped; exact provider usage is unavailable.",
        )
        self.sw(*args, "--as", "ann", ok=False)
        self.sw(*args)
        self.sw(*args)
        usage = self.ledger()["usage"]
        self.assertEqual(usage["policy_debit"]["tokens"], 60)
        self.assertIsNone(usage["reported_tokens"])
        self.assertIsNone(usage["reported_cost_micros"])
        self.assertIsNone(usage["observed_tool_seconds"])
        self.report(ident, {"tokens": 5, "cost": "0.01", "currency": "USD"})
        self.assertEqual(self.ledger()["usage"]["policy_debit"]["tokens"], 60)

    def test_ec269_owned_command_failure_is_measured_and_retry_never_launches_twice(self):
        wt = self.activate("--tool-time-min", "1", start=True)
        command = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('evidence.txt').write_text('once'); raise SystemExit(3)",
        ]
        args = (
            "tool",
            "run",
            "--as",
            "ann",
            "--command",
            json.dumps(command),
            "--timeout-seconds",
            "20",
            "--key",
            "one",
            "--json",
        )
        self.json_command(*args, ok=False)
        row = self.ledger()["runs"][0]
        self.assertEqual(row["state"], "closed")
        self.assertGreater(row["measured_seconds"], 0)
        self.assertEqual(row["source_data"]["exit_code"], 3)
        self.assertTrue(row["source_data"]["group_quiescent"])
        self.assertEqual(self.task("T1")["state"], "in_progress")
        (wt / "evidence.txt").write_text("preserve", encoding="utf-8")
        self.json_command(*args, ok=False)
        self.assertEqual((wt / "evidence.txt").read_text(encoding="utf-8"), "preserve")
        self.assertEqual(len(self.ledger()["runs"]), 1)

    def test_ec270_crashed_reservation_and_report_commits_are_atomic_and_retryable(self):
        self.activate("--token-limit", "100")
        for point, count in (("before_usage_reservation_commit", 0), ("after_usage_reservation_commit", 1)):
            self.sw(
                "usage",
                "reserve",
                "T1",
                "--as",
                "ann",
                "--key",
                "crash",
                "--tokens",
                "50",
                ok=False,
                env={"SWARM_FAILPOINT": point},
            )
            self.assertEqual(len(self.ledger()["runs"]), count)
        ident = self.reserve("crash", "--tokens", "50")["result"]["run"]["id"]
        source = Path(self.tmp.name) / "crash-report.json"
        source.write_text('{"tokens": 20}', encoding="utf-8")
        args = ("usage", "report", ident, "--as", "ann", "--source", str(source))
        self.sw(*args, ok=False, env={"SWARM_FAILPOINT": "before_usage_report_commit"})
        self.assertEqual(self.ledger()["runs"][0]["state"], "reserved")
        self.sw(*args, ok=False, env={"SWARM_FAILPOINT": "after_usage_report_commit"})
        self.assertEqual(self.ledger()["runs"][0]["state"], "closed")
        self.sw(*args)
        self.assertEqual(self.ledger()["usage"]["policy_debit"]["tokens"], 20)

    def test_ec383_a_crashed_tool_supervisor_on_this_host_is_settled_by_the_engine(self):
        self.activate("--tool-time-min", "1", start=True)
        command = [sys.executable, "-c", "pass"]
        self.sw(
            "tool", "run", "--as", "ann", "--command", json.dumps(command), "--timeout-seconds", "10",
            ok=False, env={"SWARM_FAILPOINT": "after_usage_reservation_commit"},
        )
        self.sw("status")
        row = self.ledger()["runs"][0]
        self.assertEqual(row["state"], "charged")
        self.assertIn("engine-verified: supervisor gone", row["detail"])

    def test_ec271_lost_tool_intent_stays_unknown_and_prevents_cleanup_or_reoffer(self):
        wt = self.activate("--tool-time-min", "1", start=True)
        command = [sys.executable, "-c", "from pathlib import Path; Path('must-not-start').touch()"]
        self.sw(
            "tool",
            "run",
            "--as",
            "ann",
            "--command",
            json.dumps(command),
            "--timeout-seconds",
            "10",
            ok=False,
            env={"SWARM_FAILPOINT": "after_usage_reservation_commit"},
        )
        with self.board() as sw, sw.tx():  # a supervisor on another host: its end cannot be proven here (EC-383)
            run = sw.db.execute("SELECT id FROM usage_runs").fetchone()["id"]
            ident = json.loads(sw.meta(f"usage_supervisor:{run}"))
            sw.set_meta(f"usage_supervisor:{run}", json.dumps({**ident, "ns": "another-host/boot"}))
        self.sw("status")
        row = self.ledger()["runs"][0]
        self.assertEqual(row["state"], "unknown")
        self.assertFalse((wt / "must-not-start").exists())
        doctor = self.json_command("doctor", "--json", ok=False)["result"]
        self.assertIn("unknown_usage", {item["code"] for item in doctor["issues"]})
        self.assertTrue(wt.exists())
        with self.board() as sw:
            self.assertIn("usage", core.worktree_activity(sw, sw.task("T1")).lower())
            self.assertIsNone(core.usage_summary(sw, core.current_contract(sw, "T1"))["observed_tool_seconds"])
        self.sw("tool", "run", "--as", "ann", "--command", json.dumps(command), ok=False)
        self.sw("record", "T1", "--commit", "HEAD", ok=False)
        self.sw(
            "usage",
            "reconcile",
            row["id"],
            "--confirm-stopped",
            "--charge-reserved",
            "--reason",
            "The creating supervisor exited before launch; no owned process remains.",
        )
        self.assertEqual(self.ledger()["usage"]["policy_debit"]["tool_seconds"], 10)
        self.assertIsNone(self.ledger()["usage"]["observed_tool_seconds"])

    def test_ec272_pending_usage_blocks_submission_until_report_then_gates_are_metered(self):
        wt = self.activate("--token-limit", "100", "--tool-time-min", "1")
        ident = self.reserve()["result"]["run"]["id"]
        self.sw("plan", "--as", "ann", *fixtures.PLAN)
        self.sw("start", "--as", "ann")
        (wt / "src").mkdir(exist_ok=True)
        (wt / "src" / "file.txt").write_text("complete", encoding="utf-8")
        self.git("add", "src/file.txt", cwd=wt)
        self.git("commit", "-qm", "task", cwd=wt)
        self.sw("step", "1", "--as", "ann", "--evidence", "The source file contains the completed change.")
        self.sw("step", "2", "--as", "ann", "--evidence", "The source change is committed on the task branch.")
        self.assertIn("not settled", self.sw("submit", "--as", "ann", ok=False))
        self.report(ident, {"tokens": 20})
        self.sw(
            "submit", "--as", "ann", "--evidence", "The source change is committed; configured gates verify acceptance."
        )
        self.sw("merge", "--as", "ann")
        self.assertEqual(self.task("T1")["state"], "done")
        tools = [r for r in self.ledger()["runs"] if r["kind"] == "tool"]
        self.assertTrue(tools)
        self.assertTrue(all(r["state"] == "closed" and r["measured_seconds"] > 0 for r in tools))
        self.assertIsNotNone(self.ledger()["usage"]["observed_tool_seconds"])

    def test_ec273_concurrent_reservations_cannot_overdraw_shared_allowance(self):
        self.activate("--token-limit", "100")

        def allocate(key):
            return self.sw("usage", "reserve", "T1", "--as", "ann", "--key", key, "--tokens", "60", ok=None)

        with ThreadPoolExecutor(max_workers=2) as pool:
            outputs = list(pool.map(allocate, ("one", "two")))
        self.assertEqual(sum("Reservation exceeds" in output for output in outputs), 1)
        self.assertEqual(len(self.ledger()["runs"]), 1)
        self.assertEqual(self.ledger()["usage"]["reserved"]["tokens"], 60)

    def test_ec274_owned_timeout_measures_clock_and_preserves_work_without_completion(self):
        wt = self.activate("--tool-time-min", "1", start=True)
        ready = Path(self.tmp.name) / "tool-ready"
        command = [
            sys.executable,
            "-c",
            "from pathlib import Path; import time; Path('unfinished.txt').write_text('retained'); "
            f"Path({str(ready)!r}).touch(); time.sleep(120)",
        ]
        clock = mock.Mock(monotonic=lambda: 60.0 if ready.exists() else 0.0, sleep=time.sleep)
        with self.board() as sw:
            env = sw.env_for(sw.agent("ann"), "T1")
            with mock.patch.object(core, "time", clock):
                with self.assertRaises(core.subprocess.TimeoutExpired) as failure:
                    core.metered_run(sw, command, wt, {**os.environ, **env}, 2)
            self.assertTrue(failure.exception.owned_quiescent)
        row = self.ledger()["runs"][0]
        self.assertEqual(row["state"], "closed")
        self.assertEqual(row["measured_seconds"], 60)
        self.assertEqual(self.task("T1")["state"], "expired")
        self.assertEqual((wt / "unfinished.txt").read_text(encoding="utf-8"), "retained")

    def test_ec275_replacement_offer_keeps_prior_consumption_and_closed_clocks(self):
        self.activate("--token-limit", "100")
        ident = self.reserve()["result"]["run"]["id"]
        self.report(ident, {"tokens": 20})
        with self.board() as sw, sw.tx():
            c = core.current_contract(sw, "T1")
            origin = core.contract_budget(c)["origin"]
            sw.db.execute("UPDATE task_contracts SET active_since=?", (core.iso(core.utcnow() - timedelta(seconds=2)),))
        self.sw("release", "--as", "ann", "Release the unchanged task for another bounded assignment.")
        with self.board() as sw:
            closed = core.current_contract(sw, "T1")
            self.assertIsNone(closed["active_since"])
            self.assertIsNone(closed["blocked_at"])
            self.assertGreater(closed["active_seconds"], 0)
        self.assertIn(
            "existing usage currency",
            self.sw("contract", "offer", "T1", "ann", "--token-limit", "100", "--currency", "EUR", "--as", "human", ok=False),
        )
        self.sw("contract", "offer", "T1", "ann", "--token-limit", "100", "--as", "human")
        usage = self.ledger()["usage"]
        self.assertEqual(usage["budget"]["origin"], origin)
        self.assertEqual(usage["policy_debit"]["tokens"], 20)
        self.assertEqual(usage["remaining"]["tokens"], 80)


class GoalBudgetEvidence(VerificationCase):
    def test_ec276_late_usage_facts_invalidate_an_earlier_goal_receipt(self):
        original_ready = self.to_ready
        runs = []

        def ready_with_settled_usage(*args, **kwargs):
            tree = original_ready(*args, **kwargs)
            row = self.json_command(
                "usage", "reserve", "F-file", "--as", "ann", "--tokens", "20", "--key", "external", "--json"
            )["result"]["run"]
            runs.append(row["id"])
            self.sw(
                "usage",
                "reconcile",
                row["id"],
                "--confirm-stopped",
                "--charge-reserved",
                "--reason",
                "The external operation stopped; consume its full allowance conservatively.",
            )
            return tree

        with mock.patch.object(self, "to_ready", ready_with_settled_usage):
            self.build_goal()
        self.sw("goal", "verify", "GF", "--key", "before-usage-evidence")
        source = Path(self.tmp.name) / "late-usage.json"
        source.write_text('{"tokens": 5}', encoding="utf-8")
        self.sw("usage", "report", runs[0], "--as", "ann", "--source", str(source))
        self.assertIn("goal verify", self.sw("goal", "close", "GF", ok=False))
        self.assertEqual(self.goal()["state"], "active")
        self.sw("goal", "verify", "GF", "--key", "with-usage-evidence")
        self.sw("goal", "close", "GF")
        self.assertEqual(self.goal()["state"], "closed")
