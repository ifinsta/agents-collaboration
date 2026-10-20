"""Stage D conformance and recovery checks against disposable real Git repositories."""

from __future__ import annotations

import json
import importlib.util
import os
import random
import sqlite3
import subprocess
import sys
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import test_swarm as fixtures

core = fixtures.swarm_module


class HardeningCase(fixtures.SwarmCase):
    def json_command(self, *argv, ok=True, cwd=None, env=None):
        done = subprocess.run(
            [sys.executable, str(fixtures.SWARM), *argv],
            cwd=cwd or self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            env={**os.environ, **(env or {})},
        )
        self.assertEqual(done.stderr, "")
        data = json.loads(done.stdout)
        self.assertEqual(data["exit_code"], done.returncode)
        self.assertEqual(data["ok"], ok, data)
        self.assertEqual(data["protocol_version"], core.PROTOCOL_VERSION)
        return data

    @contextmanager
    def board(self):
        sw = core.Swarm(self.root)
        try:
            yield sw
        finally:
            sw.db.close()

    def config(self, section):
        path = self.root / ".agents" / "swarm" / "config.toml"
        path.write_text(path.read_text(encoding="utf-8") + "\n" + section + "\n", encoding="utf-8")
        self.git("add", ".agents/swarm/config.toml")
        self.git("commit", "-qm", "configure trial")


class JsonProtocol(HardeningCase):
    def test_ec235_global_json_supports_nested_commands_and_preserves_legacy_payloads(self):
        data = self.json_command("--json", "protocol")
        self.assertIn("event-replay", data["result"]["capabilities"])
        self.join("ann")
        self.join("bob")
        self.sw("send", "ann", "look at the task evidence", "--as", "bob")
        status = self.json_command("status", "--as", "ann", "--json")
        self.assertEqual(status["unread"], 1)
        self.assertNotIn("unread message(s)", status["output"])
        self.assertIsInstance(status["result"]["tasks"][0]["needs"], list)
        self.assertIn("next_action", status["result"]["tasks"][0])
        self.assertEqual(self.json_command("goal", "list", "--json")["command"], "goal")
        inbox = self.json_command("--json", "inbox", "--as", "ann")
        self.assertNotIn("messages", inbox)
        self.assertIn("messages", inbox["result"])
        environment = self.json_command("environment", "--json")
        self.assertNotIn("rules", environment)
        self.assertIn("rules", environment["result"])
        claimed = self.json_command("claim", "T1", "--as", "ann", "--json")
        self.assertEqual(claimed["result"]["task"]["id"], "T1")
        self.assertEqual(claimed["result"]["task"]["epoch"], self.task("T1")["epoch"])

    def test_ec235_argument_errors_help_refusals_and_version_mismatch_have_one_envelope(self):
        error = self.json_command("--json", "does-not-exist", ok=False)
        self.assertEqual(error["error"]["code"], "invalid_arguments")
        self.assertFalse((self.root / ".git" / "swarm").exists())
        self.assertIn("usage:", self.json_command("--json", "--help")["output"])
        mismatch = self.json_command("--json", "--protocol-version", "999", "status", ok=False)
        self.assertIn("Unsupported protocol", mismatch["error"]["message"])
        self.assertFalse((self.root / ".git" / "swarm").exists())
        refusal = self.json_command("claim", "T1", "--json", ok=False)
        self.assertIn("who you are", refusal["error"]["message"])
        self.assertIn("next_action", refusal["error"])
        denied = self.json_command("--json", "--as", "human", "pause", "stop", ok=False, env={"SWARM_AS": "ann"})
        self.assertIn("may not act as the human", denied["error"]["message"])

    def test_ec235_json_never_opens_a_terminal_or_waits_for_interactive_input(self):
        for argv in (("launcher",), ("monitor",), ("dashboard",), ("console",), ("launch", "fake"), ("update",)):
            with self.subTest(argv=argv):
                result = self.json_command(*argv, "--json", ok=False)
                self.assertIn("without prompts", result["error"]["message"])
        self.assertFalse((self.root / ".git" / "swarm").exists())

    def test_ec236_event_replay_is_versioned_ordered_bounded_and_rejects_future_events(self):
        self.join("ann")
        self.sw("claim", "T1", "--as", "ann")
        first = self.json_command("events", "--limit", "1", "--json")["result"]
        second = self.json_command("events", "--after", str(first["next_cursor"]), "--json")["result"]
        events = first["events"] + second["events"]
        self.assertTrue(events)
        self.assertEqual([e["id"] for e in events], sorted({e["id"] for e in events}))
        self.assertTrue(all(e["version"] == 1 for e in events))
        self.assertEqual(
            self.json_command("events", "--after", str(second["next_cursor"]), "--json")["result"]["events"], []
        )
        self.json_command("events", "--limit", "1001", "--json", ok=False)
        with self.board() as sw, sw.tx():
            sw.db.execute("UPDATE events SET version=999 WHERE id=?", (events[0]["id"],))
        self.assertIn("unsupported protocol", self.json_command("events", "--json", ok=False)["error"]["message"])

    def test_ec236_schema_four_event_migration_rolls_back_when_killed_and_is_retryable(self):
        self.join("ann")
        with self.board() as sw, sw.tx():
            sw.db.execute("ALTER TABLE events DROP COLUMN version")
            sw.set_meta("schema_version", "4")
        self.sw("status", ok=False, env={"SWARM_FAILPOINT": "during_migration"})
        db = self.db()
        try:
            self.assertNotIn("version", {r[1] for r in db.execute("PRAGMA table_info(events)")})
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "4")
        finally:
            db.close()
        events = self.json_command("events", "--json")["result"]["events"]
        self.assertTrue(events)
        self.assertTrue(all(e["version"] == 1 for e in events))


class VerifiedIntegration(HardeningCase):
    def test_ec237_final_commit_and_hook_edits_are_checked_and_evidence_survives_cleanup(self):
        hook = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('src/file.txt').write_text('hook edit'); print('verified merge')",
        ]
        self.config("[merge]\nmessage_command = " + json.dumps(hook))
        self.join("ann")
        self.to_ready("ann", "T1")
        result = self.json_command("merge", "--as", "ann", "--json")["result"]
        self.assertEqual(result["task"]["state"], "done")
        t = self.task("T1")
        self.assertFalse(Path(t["worktree"]).exists())
        proof = json.loads(t["integration_evidence"])["verification"]
        self.assertEqual(proof["commit"], t["merged_sha"])
        self.assertEqual(proof["tree"], self.git("rev-parse", "main^{tree}").strip())
        self.assertEqual(proof["status"], "passed")
        self.assertEqual(len(proof["checks"]), 1)
        self.assertEqual(proof["checks"][0]["exit_code"], 0)
        self.assertGreaterEqual(proof["checks"][0]["elapsed_seconds"], 0)
        self.assertEqual((self.root / "src" / "file.txt").read_text(), "hook edit")

    def test_ec237_hook_cannot_land_a_final_tree_that_fails_checks(self):
        hook = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('src/file.txt').write_text('bad'); print('hook merge')",
        ]
        self.config("[merge]\nmessage_command = " + json.dumps(hook))
        cfg = self.root / ".agents" / "swarm" / "config.toml"
        check = "import pathlib,sys; sys.exit(pathlib.Path('src/file.txt').read_text() == 'bad')"
        text = cfg.read_text(encoding="utf-8")
        old = next(line for line in text.splitlines() if line.startswith("commands = "))
        cfg.write_text(text.replace(old, "commands = " + json.dumps([[sys.executable, "-c", check]])), encoding="utf-8")
        self.git("commit", "-qam", "check final tree")
        self.join("ann")
        wt = self.to_ready("ann", "T1")
        before = self.git("rev-parse", "main")
        outcome = self.json_command("merge", "--as", "ann", "--json", ok=False)
        self.assertEqual(outcome["result"]["task"]["state"], "gates_failed")
        self.assertEqual(self.git("rev-parse", "main"), before)
        self.assertEqual((wt / "src" / "file.txt").read_text(), "bad")

    def test_ec238_gate_modifications_and_hook_scope_expansion_preserve_edits_without_landing(self):
        self.join("ann")
        wt = self.to_ready("ann", "T1")
        target = self.git("rev-parse", "main")
        previous = Path.cwd()
        try:
            with self.board() as sw:

                def dirty_gate(*args, **kwargs):
                    (wt / "src" / "file.txt").write_text("gate edit", encoding="utf-8")
                    return None

                with mock.patch.object(core, "gate_run", side_effect=dirty_gate):
                    with self.assertRaisesRegex(core.SwarmError, "Tracked files changed"):
                        core.cmd_merge(sw, core.argparse.Namespace(as_="ann"))
                self.assertEqual((wt / "src" / "file.txt").read_text(), "gate edit")
                self.assertEqual(self.git("rev-parse", "main"), target)
                self.git("add", "src/file.txt", cwd=wt)
                self.git("commit", "-qm", "retain gate edit", cwd=wt)
                self.sw("submit", "--as", "ann", "--evidence", "inspect retained edits", cwd=wt)
                sw.config["merge"]["message_command"] = [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('config/settings.txt').write_text('outside scope')",
                ]
                with self.assertRaisesRegex(core.SwarmError, "outside the approved scope"):
                    core.cmd_merge(sw, core.argparse.Namespace(as_="ann"))
                self.assertEqual((wt / "config" / "settings.txt").read_text(), "outside scope")
                self.assertEqual(self.git("rev-parse", "main"), target)
        finally:
            os.chdir(previous)

    def test_ec238_late_edit_after_intent_cannot_ride_along_with_verified_commit(self):
        self.join("ann")
        wt = self.to_ready("ann", "T1")
        before = self.git("rev-parse", "main")
        previous = Path.cwd()
        try:
            with self.board() as sw:

                def edit_after_intent(name):
                    if name == "after_intent":
                        (wt / "src" / "file.txt").write_text("late work", encoding="utf-8")

                with mock.patch.object(core, "failpoint", side_effect=edit_after_intent):
                    with self.assertRaisesRegex(core.SwarmError, "Tracked files changed"):
                        core.cmd_merge(sw, core.argparse.Namespace(as_="ann"))
        finally:
            os.chdir(previous)
        self.assertEqual(self.git("rev-parse", "main"), before)
        self.assertEqual((wt / "src" / "file.txt").read_text(), "late work")

    def test_ec239_cleanup_preserves_a_clean_branch_with_new_unmerged_commits(self):
        self.config("[merge]\ncleanup = false")
        self.join("ann")
        wt = self.to_ready("ann", "T1")
        self.sw("merge", "--as", "ann")
        (wt / "src" / "file.txt").write_text("new work after merge", encoding="utf-8")
        self.git("commit", "-qam", "unmerged work", cwd=wt)
        with self.board() as sw, sw.tx():
            sw.update_task("T1", cleanup_pending=1)
        data = self.json_command("doctor", "--fix", "--json")["result"]
        self.assertIn("unmerged commits", data["repairs"][0]["result"])
        self.assertEqual(self.task("T1")["cleanup_pending"], 1)
        self.assertTrue(wt.exists())
        self.assertTrue(self.git("branch", "--list", "swarm/T1").strip())


class DoctorAndStorage(HardeningCase):
    def test_ec241_seeded_claim_release_model_preserves_single_ownership_and_stale_epoch_fences(self):
        workers = ("ann", "bob", "cat")
        for who in workers:
            self.join(who)
        model = {"T1": None, "T2": None}
        rng = random.Random(241)
        for _ in range(16):
            who, tid = rng.choice(workers), rng.choice(tuple(model))
            if model[tid] == who:
                self.json_command(
                    "release", "Return this preserved task for another worker to continue", "--as", who, "--json"
                )
                model[tid] = None
            else:
                allowed = model[tid] is None and who not in model.values()
                self.json_command("claim", tid, "--as", who, "--json", ok=allowed)
                if allowed:
                    model[tid] = who
            with self.board() as sw:
                for task_id, owner in model.items():
                    task = sw.task(task_id)
                    self.assertEqual(task["assignee"] if task["state"] in core.HELD else None, owner)
                    if owner:
                        self.assertEqual(sw.agent(owner)["task"], task_id)
                        self.assertTrue(Path(task["worktree"]).exists())
                        self.assertGreater(task["epoch"], 0)
                        self.json_command(
                            "release",
                            "This stale command must preserve the current assignment",
                            "--as",
                            owner,
                            "--epoch",
                            str(task["epoch"] - 1),
                            "--json",
                            ok=False,
                        )
                self.assertEqual(len([o for o in model.values() if o]), len({o for o in model.values() if o}))

    def test_ec240_doctor_reports_ownership_evidence_and_owed_checks_with_safe_hints(self):
        self.join("ann")
        self.to_ready("ann", "T1")
        self.sw("submit", "--as", "ann", "--evidence", "Windows gate", "--owed", "Linux check unavailable")
        with self.board() as sw, sw.tx():
            sw.update_agent("ann", task=None)
        result = self.json_command("doctor", "--json", ok=False)["result"]
        self.assertFalse(result["healthy"])
        by_code = {i["code"]: i for i in result["issues"]}
        self.assertIn("ownership_drift", by_code)
        self.assertIn("Linux check unavailable", by_code["owed_checks"]["message"])
        self.assertTrue(all(i["next_action"] for i in result["issues"]))
        self.assertTrue(Path(self.task("T1")["worktree"]).exists())

    def test_ec240_doctor_cleanup_preview_retains_files_then_applies_idempotently(self):
        self.config("[merge]\ncleanup = false")
        self.join("ann")
        wt = self.to_ready("ann", "T1")
        self.sw("merge", "--as", "ann")
        with self.board() as sw, sw.tx():
            sw.update_task("T1", cleanup_pending=1)
        preview = self.json_command("doctor", "--fix", "--dry-run", "--json")["result"]
        self.assertTrue(preview["dry_run"])
        self.assertTrue(wt.exists())
        self.assertEqual(self.task("T1")["cleanup_pending"], 1)
        self.json_command("doctor", "--fix", "--json")
        self.assertFalse(wt.exists())
        self.assertEqual(self.json_command("doctor", "--fix", "--json")["result"]["repairs"], [])

    def test_ec240_doctor_reports_missing_source_pins_without_inventing_evidence(self):
        self.join("ann")
        sha = self.git("rev-parse", "main").strip()
        self.sw(
            "memory",
            "propose",
            "Keep a committed acceptance fixture",
            "--as",
            "ann",
            "--applicability",
            "local fixture work",
            "--event",
            "1",
            "--commit",
            sha,
        )
        self.git("update-ref", "-d", f"refs/swarm/evidence/{sha}")
        result = self.json_command("doctor", "--json", ok=False)["result"]
        self.assertIn("missing_evidence_pin", {i["code"] for i in result["issues"]})
        self.assertFalse(self.git("for-each-ref", "refs/swarm/evidence/", "--format=%(refname)").strip())

    def test_ec241_busy_writer_waits_for_atomic_commit_and_rollback_drops_partial_event(self):
        self.join("ann")
        with self.board() as sw, self.board() as competing:
            before = sw.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            with self.assertRaisesRegex(RuntimeError, "rollback"):
                with sw.tx():
                    sw.event("partial", "ann", "T1", "must not survive")
                    sw.update_task("T1", state="broken")
                    raise RuntimeError("rollback")
            self.assertEqual(sw.task("T1")["state"], "open")
            self.assertEqual(sw.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], before)
            competing.db.execute("PRAGMA busy_timeout=0")
            sw.db.execute("BEGIN IMMEDIATE")
            try:
                with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                    with competing.tx():
                        competing.event("must_not_commit", "ann", "T1")
            finally:
                sw.db.execute("ROLLBACK")
            with competing.tx():
                competing.event("retry_after_busy", "ann", "T1")
            self.assertEqual(sw.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], before + 1)

    def test_ec241_concurrent_takeovers_leave_one_owner_and_fence_the_old_worker(self):
        self.join("ann")
        self.sw("claim", "T1", "--as", "ann")
        old_epoch = self.task("T1")["epoch"]
        self.join("bob")
        self.join("cat")
        with self.board() as sw, sw.tx():
            sw.update_agent("ann", state="offline", offline_at="2020-01-01T00:00:00+00:00")
            sw.update_task("T1", state="orphaned")
        results = []

        def takeover(who):
            done = subprocess.run(
                [sys.executable, str(fixtures.SWARM), "claim", "T1", "--as", who, "--take-over", "--json"],
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            results.append(json.loads(done.stdout))

        threads = [threading.Thread(target=takeover, args=(who,)) for who in ("bob", "cat")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(r["ok"] for r in results), 1, results)
        t = self.task("T1")
        self.assertGreater(t["epoch"], old_epoch)
        self.assertIn(t["assignee"], ("bob", "cat"))
        stale = self.json_command("start", "--as", "ann", "--epoch", str(old_epoch), "--json", ok=False)
        self.assertIsNotNone(stale["error"])
        self.assertTrue(Path(t["worktree"]).exists())


class WorkforceBenchmark(HardeningCase):
    def test_ec242_untracked_runner_helpers_cannot_change_the_acceptance_environment(self):
        script = fixtures.SWARM.parents[2] / "scripts" / "workforce_bench.py"
        spec = importlib.util.spec_from_file_location("workforce_bench_for_test", script)
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)
        trial = bench.Trial(Path(self.tmp.name) / "trial", "solo", None, 300)
        trial.setup()
        code = bench.CODE
        for task in bench.TASKS.values():
            code = code.replace(task["stub"], task["solution"])
        (trial.repo / "durations.py").write_text(code, encoding="utf-8")
        trial.git("add", "durations.py")
        trial.git("commit", "-qm", "correct workload")
        self.assertTrue(trial.check(trial.repo))
        (trial.repo / "sitecustomize.py").write_text("# unexpected runner helper\n", encoding="utf-8")
        self.assertFalse(trial.check(trial.repo))

    def test_ec242_fresh_installs_compare_three_real_workflows_without_fabricating_cost(self):
        output = Path(self.tmp.name) / "trial"
        script = fixtures.SWARM.parents[2] / "scripts" / "workforce_bench.py"
        done = subprocess.run(
            [sys.executable, str(script), "--output", str(output), "--fault", "after_target_moved"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
        self.assertEqual({r["mode"] for r in report["results"]}, {"solo", "uncoordinated", "coordinated"})
        for row in report["results"]:
            self.assertEqual(row["verified_completion"], 2)
            self.assertTrue(row["full_acceptance"])
            self.assertIsNone(row["usage"]["cost"])
            self.assertEqual(row["usage"]["human_interventions"], 0)
            self.assertEqual(row["runner"], "scripted-mechanics-only")
            self.assertTrue(row["owed"])
            self.assertTrue((output / row["mode"] / "check-1.log").exists())
            if row["mode"] == "coordinated":
                self.assertEqual(row["fault"]["process_exit_code"], 97)
                self.assertEqual(row["fault"]["recovered_state"], "done")
                self.assertEqual(row["fault"]["completion_events"], 1)
                self.assertTrue(row["fault"]["retained_check_proof"])

    def test_ec242_runner_claims_cannot_replace_fixed_acceptance_checks(self):
        output = Path(self.tmp.name) / "trial"
        runner = Path(self.tmp.name) / "runner.json"
        runner.write_text(
            json.dumps([sys.executable, "-c", "from pathlib import Path; Path('test_duration.py').write_text('')"]),
            encoding="utf-8",
        )
        script = fixtures.SWARM.parents[2] / "scripts" / "workforce_bench.py"
        done = subprocess.run(
            [sys.executable, str(script), "--output", str(output), "--mode", "solo", "--runner", str(runner)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        result = json.loads((output / "comparison.json").read_text(encoding="utf-8"))["results"][0]
        self.assertFalse(result["full_acceptance"])
        self.assertEqual(result["verified_completion"], 0)
        self.assertIsNone(result["usage"]["cost"])
        self.assertIsNone(result["usage"]["human_interventions"])
        noisy_output = Path(self.tmp.name) / "noisy-trial"
        runner.write_text(
            json.dumps([sys.executable, "-c", "print('x' * 2000000); import time; time.sleep(30)"]), encoding="utf-8"
        )
        done = subprocess.run(
            [sys.executable, str(script), "--output", str(noisy_output), "--mode", "solo", "--runner", str(runner)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        noisy = json.loads((noisy_output / "comparison.json").read_text(encoding="utf-8"))["results"][0]
        self.assertEqual(noisy["verified_completion"], 0)
        self.assertTrue(all("output exceeded" in r["failure"] for r in noisy["attempts"]))
        self.assertTrue((noisy_output / "solo" / "T1-1-runner.log").exists())


if __name__ == "__main__":
    unittest.main()
