"""Completion requires observed checks against immutable Git source, not prose."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from unittest import mock

from test_hardening import HardeningCase
import test_swarm as fixtures

core = fixtures.swarm_module


class VerificationCase(HardeningCase):
    def receipt(self):
        with self.board() as sw:
            return sw.db.execute("SELECT * FROM verification_runs ORDER BY rowid DESC LIMIT 1").fetchone()

    def goal(self):
        with self.board() as sw:
            return sw.db.execute("SELECT * FROM goals WHERE id='GF'").fetchone()

    def define_check(self, code=None):
        code = (
            code
            or "from pathlib import Path; assert Path('src/file.txt').read_text(encoding='utf-8') == 'x\\n'; print('checked source fixture')"
        )
        argv = [sys.executable, "-c", code.replace("'x\\n'", repr("x\n"))]
        self.sw("goal", "check", "GF", "1", "--command", json.dumps(argv))
        return argv

    def build_goal(self, *, code=None, owed=None):
        self.join("ann")
        self.sw("goal", "new", "GF", "Land the reviewed fixture output")
        fixtures.Goals.answer_all(self, "GF")
        self.sw(
            "goal",
            "outcome",
            "GF",
            "The source file contains the reviewed fixture output",
            "--check",
            "Run the source fixture assertion against the landed commit",
        )
        self.sw(
            "goal",
            "task",
            "GF",
            "F-file",
            "Write the fixture source",
            "--serves",
            "1",
            "--scope",
            "src/",
            "--done-when",
            "The committed source fixture assertion passes",
        )
        self.define_check(code)
        self.architecture("GF")
        self.sw("goal", "commit", "GF")
        tree = self.to_ready("ann", "F-file")
        if owed:
            self.sw("submit", "--as", "ann", "--evidence", "The local fixture gate passed", "--owed", owed, cwd=tree)
        self.sw("merge", "--as", "ann")
        return self.git("rev-parse", "main").strip()

    def killed(self, argv, point):
        done = subprocess.run(
            [sys.executable, str(fixtures.SWARM), *argv],
            cwd=self.root,
            env={**os.environ, "SWARM_FAILPOINT": point},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(done.returncode, 97, done.stdout + done.stderr)


class Receipts(VerificationCase):
    def test_ec254_schema_six_migration_is_atomic_and_preserves_existing_state(self):
        self.sw("status")
        with self.board() as sw, sw.tx():
            sw.db.execute("DROP TABLE verification_runs")
            sw.db.execute("ALTER TABLE goals DROP COLUMN closure")
            sw.db.execute("INSERT INTO goals(id,title,state) VALUES('old','Legacy closure','closed')")
            sw.set_meta("schema_version", "6")
        self.killed(["status"], "during_migration")
        db = self.db()
        try:
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "6")
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='verification_runs'").fetchone())
            self.assertNotIn("closure", [r[1] for r in db.execute("PRAGMA table_info(goals)")])
        finally:
            db.close()
        self.sw("status")
        self.sw("status")
        with self.board() as sw:
            self.assertEqual(sw.meta("schema_version"), str(core.SCHEMA_VERSION))
            row = sw.db.execute("SELECT * FROM goals WHERE id='old'").fetchone()
            self.assertEqual(row["state"], "closed")
            self.assertIsNone(row["closure"])
        issues = self.json_command("doctor", "--json")["result"]["issues"]
        self.assertIn("unverified_goal_closure", {i["code"] for i in issues})

    def test_ec255_external_record_requires_actual_gates_and_preserves_failed_work(self):
        self.join("ann")
        self.sw("contract", "offer", "T1", "ann", "--as", "human")
        self.sw("contract", "accept", "T1", "--as", "ann")
        self.sw("claim", "T1", "--as", "ann")
        tree = Path(self.task("T1")["worktree"])
        self.sw("plan", "--as", "ann", *fixtures.PLAN, cwd=tree)
        self.sw("start", "--as", "ann", cwd=tree)
        # Board timestamps have second resolution. Advance the persisted running
        # clock deterministically instead of depending on process startup speed.
        with self.board() as sw, sw.tx():
            sw.db.execute(
                "UPDATE task_contracts SET active_since=? WHERE task='T1'",
                (core.iso(core.utcnow() - timedelta(seconds=2)),),
            )
        self.sw("block", "Waiting on the external fixture integration", "--as", "ann")
        with self.board() as sw, sw.tx():
            sw.db.execute(
                "UPDATE task_contracts SET blocked_at=? WHERE task='T1'",
                (core.iso(core.utcnow() - timedelta(seconds=2)),),
            )
        (tree / "unfinished.txt").write_text("preserve this unfinished fixture", encoding="utf-8")
        (self.root / "FAIL").write_text("Fail acceptance", encoding="utf-8")
        self.git("add", "FAIL")
        self.git("commit", "-qm", "land failing acceptance")
        bad = self.git("rev-parse", "main").strip()
        self.assertIn("not recorded", self.sw("record", "T1", "--commit", bad, ok=False))
        row = self.receipt()
        self.assertEqual(row["state"], "failed")
        self.assertEqual(json.loads(row["results"])[0]["exit_code"], 1)
        self.assertNotEqual(self.task("T1")["state"], "done")
        self.assertEqual((tree / "unfinished.txt").read_text(), "preserve this unfinished fixture")
        self.assertTrue((Path(row["worktree"]) / "FAIL").exists())
        self.git("rm", "FAIL")
        self.git("commit", "-qm", "repair acceptance")
        good = self.git("rev-parse", "main").strip()
        self.sw("record", "T1", "--commit", good, "--key", "record-fixed")
        proof = json.loads(self.task("T1")["integration_evidence"])
        self.assertEqual(proof["verification"]["status"], "passed")
        self.assertEqual(proof["verification"]["commit"], good)
        self.assertEqual(self.receipt()["state"], "passed")
        self.sw("record", "T1", "--commit", good, "--key", "record-fixed")
        with self.board() as sw:
            contract = core.current_contract(sw, "T1")
            self.assertEqual(contract["state"], "closed")
            self.assertIsNone(contract["active_since"])
            self.assertIsNone(contract["blocked_at"])
            self.assertGreater(contract["active_seconds"], 0)
            self.assertGreater(contract["blocked_seconds"], 0)
            self.assertEqual(
                sw.db.execute("SELECT count(*) FROM events WHERE kind='recorded_done' AND task='T1'").fetchone()[0], 1
            )
        self.assertEqual((tree / "unfinished.txt").read_text(), "preserve this unfinished fixture")

    def test_ec255_empty_gate_configuration_cannot_verify_external_completion(self):
        path = self.root / ".agents" / "swarm" / "config.toml"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text(
            "\n".join("commands = []" if line.startswith("commands =") else line for line in lines) + "\n",
            encoding="utf-8",
        )
        sha = self.git("rev-parse", "main").strip()
        self.assertIn("empty check set", self.sw("record", "T1", "--commit", sha, ok=False))
        self.assertEqual(self.task("T1")["state"], "open")
        self.assertIsNone(self.receipt())

    def test_ec256_closure_needs_observed_outcomes_and_preserves_human_checkout_dirt(self):
        sha = self.build_goal()
        self.assertIn(
            "goal verify",
            self.sw("goal", "close", "GF", "--evidence", "1=The agent claims that all checks passed", ok=False),
        )
        human = self.root / "src" / "file.txt"
        human.write_text("human uncommitted work", encoding="utf-8")
        data = self.json_command("goal", "verify", "GF", "--key", "verified-goal", "--json")["result"]["verification"]
        self.assertEqual(data["state"], "passed", data)
        self.assertEqual(data["commit_sha"], sha)
        self.assertEqual(data["platform"], core.current_os())
        self.assertEqual([r["outcome"] for r in data["results"]], [None, 1])
        self.assertIn("checked source fixture", data["results"][-1]["output"])
        self.assertEqual((Path(data["worktree"]) / "src" / "file.txt").read_text(), "x\n")
        self.sw("goal", "close", "GF")
        self.sw("goal", "close", "GF")
        self.sw("goal", "verify", "GF", "--key", "verified-goal")
        goal = self.json_command("goal", "show", "GF", "--json")["result"]["goal"]
        self.assertEqual(goal["closure"]["receipt"], data["id"])
        self.assertEqual(goal["closure"]["status"], "verified_outcomes")
        self.assertEqual(human.read_text(), "human uncommitted work")
        self.assertIn(
            "closed", self.sw("goal", "ask", "GF", "Changing a closed goal must preserve its original proof", ok=False)
        )
        self.assertIn("closed", self.sw("goal", "commit", "GF", ok=False))
        with self.board() as sw:
            self.assertEqual(sw.db.execute("SELECT count(*) FROM events WHERE kind='goal_closed'").fetchone()[0], 1)

    def test_ec256_empty_uncommitted_and_fabricated_done_goals_cannot_close(self):
        self.sw("goal", "new", "GF", "An empty goal is unfinished")
        self.assertIn("uncommitted or empty", self.sw("goal", "close", "GF", ok=False))
        self.assertEqual(self.goal()["state"], "interrogating")
        fixtures.Goals.answer_all(self, "GF")
        self.sw(
            "goal",
            "outcome",
            "GF",
            "The source fixture has a committed result",
            "--check",
            "Check that the fixture exists on the target",
        )
        self.sw(
            "goal",
            "task",
            "GF",
            "F-file",
            "Produce the fixture",
            "--serves",
            "1",
            "--done-when",
            "The fixture exists on the target",
        )
        self.define_check()
        self.architecture("GF")
        self.sw("goal", "commit", "GF")
        with self.board() as sw, sw.tx():
            sw.update_task("F-file", state="done")
        self.assertIn(
            "no landed completion",
            self.sw("goal", "close", "GF", "--evidence", "1=A forged claim of completed checks", ok=False),
        )
        self.assertEqual(self.goal()["state"], "active")

    def test_ec257_changed_target_policy_or_check_revision_invalidates_receipts(self):
        self.build_goal()
        self.sw("goal", "verify", "GF", "--key", "first")
        first = self.receipt()
        self.git("commit", "--allow-empty", "-qm", "target advanced")
        self.assertIn("goal verify", self.sw("goal", "close", "GF", ok=False))
        self.assertIn("different source", self.sw("goal", "verify", "GF", "--key", "first", ok=False))
        self.sw("goal", "verify", "GF", "--key", "new-target")
        config = self.root / ".agents" / "swarm" / "config.toml"
        config.write_text(config.read_text(encoding="utf-8") + "\n# policy revision\n", encoding="utf-8")
        self.assertIn("goal verify", self.sw("goal", "close", "GF", ok=False))
        self.define_check(
            "from pathlib import Path; assert Path('src/file.txt').read_text() == 'x\\n'; print('revised check')"
        )
        self.assertIn("approval", self.sw("goal", "verify", "GF", ok=False))
        self.sw("goal", "architecture", "GF", "--approve")
        self.assertIn("goal verify", self.sw("goal", "close", "GF", ok=False))
        self.sw("goal", "verify", "GF", "--key", "reapproved")
        self.sw("goal", "close", "GF")
        self.assertNotEqual(json.loads(self.goal()["closure"])["receipt"], first["id"])

    def test_ec257_check_definitions_reject_invalid_shapes_secrets_and_unprivileged_edits(self):
        self.build_goal()
        revision = self.goal()["revision"]
        for commands in (
            "[]",
            '"python check.py"',
            "[1]",
            '[""]',
            '["python","\\u0000"]',
            '["python","password=example-credential"]',
        ):
            self.sw("goal", "check", "GF", "1", "--command", commands, ok=False)
            self.assertEqual(self.goal()["revision"], revision)
        self.join("bob")
        self.sw(
            "goal", "check", "GF", "1", "--command", json.dumps([sys.executable, "--version"]), "--as", "bob", ok=False
        )
        self.assertEqual(self.goal()["revision"], revision)

        with self.board() as sw, sw.tx():
            sw.db.execute(
                "INSERT INTO executions(id,agent,task,state,started_at,heartbeat_at) VALUES(?,?,'F-file','unknown',?,?)",
                ("f" * 32, "ann", core.iso(), core.iso()),
            )
        self.assertIn("Execution", self.sw("goal", "verify", "GF", "--as", "ann", ok=False))
        self.assertIsNone(self.receipt())

    def test_ec259_a_later_failed_run_cannot_be_hidden_by_an_older_passed_receipt(self):
        flag = Path(self.tmp.name) / "external-state.txt"
        flag.write_text("go", encoding="utf-8")
        self.build_goal(code=f"from pathlib import Path; assert Path({str(flag)!r}).read_text() == 'go'")
        self.sw("goal", "verify", "GF", "--key", "available")
        flag.write_text("stop", encoding="utf-8")
        self.sw("goal", "verify", "GF", "--key", "unavailable", ok=False)
        self.assertIn("goal verify", self.sw("goal", "close", "GF", ok=False))
        self.assertEqual(self.goal()["state"], "active")

    def test_ec257_check_definition_crashes_preserve_approval_or_commit_exactly_once(self):
        self.build_goal()
        before = self.goal()["revision"]
        original = json.loads(self.goal()["outcomes"])[0]["commands"]
        argv = [sys.executable, "-c", "print('a newly defined check')"]
        command = ["goal", "check", "GF", "1", "--command", json.dumps(argv)]
        self.killed(command, "before_goal_check_commit")
        self.assertEqual(self.goal()["revision"], before)
        self.assertEqual(json.loads(self.goal()["outcomes"])[0]["commands"], original)
        self.assertIsNotNone(self.goal()["architecture_approval"])
        self.killed(command, "after_goal_check_commit")
        self.assertEqual(self.goal()["revision"], before + 1)
        self.assertIsNone(self.goal()["architecture_approval"])
        self.sw(*command)
        self.assertEqual(self.goal()["revision"], before + 1)
        with self.board() as sw:
            self.assertEqual(
                sw.db.execute("SELECT count(*) FROM events WHERE kind='goal_check_defined'").fetchone()[0], 2
            )

    def test_ec258_owed_checks_need_a_passed_receipt_and_separate_human_resolution(self):
        owed = "Repeat the fixture gate on this machine before closing"
        self.build_goal(owed=owed)
        self.assertIn("owed checks", self.sw("goal", "verify", "GF", ok=False))
        self.sw("verify", "F-file", "--key", "owed-run")
        receipt = self.receipt()
        args = [
            "verification",
            "resolve-owed",
            "F-file",
            "--receipt",
            receipt["id"],
            "--reason",
            "Observed the repeated fixture gate on the required machine",
        ]
        self.assertIn("human", self.sw(*args, "--as", "ann", ok=False))
        self.assertIn("human attestation", self.sw(*args))
        proof = json.loads(self.task("F-file")["integration_evidence"])
        self.assertEqual(proof["owed_resolutions"][0]["owed"], owed)
        self.assertEqual(proof["owed_resolutions"][0]["origin"], "human_attestation")
        self.assertEqual(json.loads(self.task("F-file")["submit"])["owed"], "")
        self.sw("goal", "verify", "GF")
        self.sw("goal", "close", "GF")

    def test_ec259_zero_exit_after_tracked_edits_is_not_a_verified_result(self):
        self.build_goal(code="from pathlib import Path; Path('src/file.txt').write_text('uncommitted check edit')")
        self.sw("goal", "verify", "GF", ok=False)
        row = self.receipt()
        self.assertEqual(row["state"], "failed")
        self.assertEqual(json.loads(row["results"])[-1]["exit_code"], 0)
        self.assertEqual((Path(row["worktree"]) / "src/file.txt").read_text(), "uncommitted check edit")
        self.assertIn("goal verify", self.sw("goal", "close", "GF", ok=False))
        self.assertEqual((self.root / "src/file.txt").read_text(), "x\n")

    def test_ec259_target_move_during_checks_cannot_produce_a_current_goal_receipt(self):
        self.build_goal()
        real_gate = core.run_gate
        moved = []

        def gate(*args, **kwargs):
            result = real_gate(*args, **kwargs)
            if not moved:
                self.git("commit", "--allow-empty", "-qm", "advance target during check")
                moved.append(True)
            return result

        with self.board() as sw, mock.patch.object(core, "run_gate", side_effect=gate):
            args = core.build_parser().parse_args(["goal", "verify", "GF"])
            core.cmd_goal_verify(sw, args)
        self.assertEqual(self.receipt()["state"], "failed")
        self.assertIn("target changed", self.receipt()["detail"])
        self.assertEqual(self.goal()["state"], "active")

    def test_ec260_verifier_crashes_preserve_results_and_unknown_never_restarts_blindly(self):
        self.build_goal()
        for point in (
            "after_verification_intent",
            "before_verification_result_commit",
            "after_verification_result_commit",
            "before_verification_commit",
            "after_verification_commit",
        ):
            key = "kill-" + point
            self.killed(["goal", "verify", "GF", "--key", key], point)
            row = self.receipt()
            if point == "after_verification_commit":
                self.assertEqual(row["state"], "passed")
                self.sw("goal", "verify", "GF", "--key", key)
                self.assertEqual(self.receipt()["id"], row["id"])
            else:
                self.sw("status")
                self.assertEqual(self.receipt()["state"], "unknown")
                if point == "after_verification_intent":
                    issues = self.json_command("doctor", "--json", ok=False)["result"]["issues"]
                    self.assertIn("verification_supervision_lost", {i["code"] for i in issues})
                self.assertIn("uncertain", self.sw("goal", "verify", "GF", "--key", key + "-fresh", ok=False))
                if point == "after_verification_result_commit":
                    self.assertTrue(json.loads(row["results"]))
                self.sw(
                    "verification",
                    "reconcile",
                    row["id"],
                    "--confirm-stopped",
                    "--reason",
                    "The killed fixture verifier and its completed command group have stopped",
                )
                self.assertEqual(self.receipt()["state"], "abandoned")
        with self.board() as sw:
            self.assertEqual(
                sw.db.execute("SELECT count(*) FROM events WHERE kind='verification_passed'").fetchone()[0], 1
            )

    def test_ec260_reconciliation_fences_a_late_verifier_completion(self):
        self.build_goal()
        real_verify = core.verify_worktree_commit
        reconciled = []

        def verify(path, sha):
            real_verify(path, sha)
            if not reconciled:
                reconciled.append(True)
                with self.board() as other, other.tx():
                    other.db.execute("UPDATE verification_runs SET heartbeat_at='2020-01-01T00:00:00+00:00'")
                self.sw("status")
                self.sw(
                    "verification",
                    "reconcile",
                    self.receipt()["id"],
                    "--confirm-stopped",
                    "--reason",
                    "The fixture command group completed; abandon its uncertain verifier",
                )

        with self.board() as sw, mock.patch.object(core, "verify_worktree_commit", side_effect=verify):
            args = core.build_parser().parse_args(["goal", "verify", "GF"])
            core.cmd_goal_verify(sw, args)
            self.assertEqual(args.exit_code, 1)
            self.assertEqual(
                sw.db.execute("SELECT count(*) FROM events WHERE kind='verification_passed'").fetchone()[0], 0
            )
        self.assertEqual(self.receipt()["state"], "abandoned")
        self.assertIn("Human attestation", self.receipt()["detail"])
        self.assertEqual(self.goal()["state"], "active")

    def test_ec261_killed_external_completion_is_atomic_and_retry_is_exactly_once(self):
        sha = self.git("rev-parse", "main").strip()
        for task, point in (("T1", "before_record_commit"), ("T2", "after_record_commit")):
            self.killed(["record", task, "--commit", sha, "--key", task], point)
            self.assertEqual(self.task(task)["state"], "open" if point.startswith("before") else "done")
            self.sw("record", task, "--commit", sha, "--key", task)
            self.assertEqual(self.task(task)["state"], "done")
            with self.board() as sw:
                self.assertEqual(
                    sw.db.execute(
                        "SELECT count(*) FROM events WHERE kind='recorded_done' AND task=?", (task,)
                    ).fetchone()[0],
                    1,
                )

    def test_ec262_goal_close_crash_keeps_receipt_and_retries_without_duplicate_success(self):
        self.build_goal()
        self.sw("goal", "verify", "GF")
        receipt = self.receipt()["id"]
        self.killed(["goal", "close", "GF"], "before_goal_close_commit")
        self.assertEqual(self.goal()["state"], "active")
        self.assertIsNone(self.goal()["closure"])
        self.killed(["goal", "close", "GF"], "after_goal_close_commit")
        self.assertEqual(self.goal()["state"], "closed")
        self.sw("goal", "close", "GF")
        self.assertEqual(json.loads(self.goal()["closure"])["receipt"], receipt)
        with self.board() as sw:
            self.assertEqual(sw.db.execute("SELECT count(*) FROM events WHERE kind='goal_closed'").fetchone()[0], 1)
