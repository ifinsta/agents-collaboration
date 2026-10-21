"""Reasoned contracts: real CLI/storage/Git checks, with clocks advanced through persisted timestamps."""

from __future__ import annotations

import json
import os
import sqlite3
import unittest
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from unittest import mock

import test_swarm as fixtures

core = fixtures.swarm_module


class ContractCase(fixtures.SwarmCase):
    @contextmanager
    def database(self, path=None):
        db = sqlite3.connect(path) if path else self.db()
        try:
            with db:
                yield db
        finally:
            db.close()


class Contracts(ContractCase):
    def sql(self, query, args=()):
        with self.database() as db:
            db.execute(query, args)

    def contract(self):
        with self.database() as db:
            db.row_factory = sqlite3.Row
            return db.execute("SELECT * FROM task_contracts WHERE task='T1' ORDER BY id DESC LIMIT 1").fetchone()

    def offer(self, *options):
        self.join("ann")
        self.sw("contract", "offer", "T1", "ann", "--as", "human", *options)

    def activate(self, start=True):
        self.offer()
        self.sw("contract", "accept", "T1", "--as", "ann")
        self.sw("claim", "T1", "--as", "ann")
        wt = Path(self.task("T1")["worktree"])
        self.sw("plan", "--as", "ann", *fixtures.PLAN, cwd=wt)
        if start:
            self.sw("start", "--as", "ann", cwd=wt)
        return wt

    def expire(self):
        terms = json.loads(self.contract()["terms"])
        terms["deadline_at"] = "2020-01-01T00:00:00+00:00"
        self.sql("UPDATE task_contracts SET terms=?", (json.dumps(terms),))

    def test_ec201_migration_is_idempotent_and_preserves_legacy_goals(self):
        self.sw("status")
        self.sql("INSERT INTO goals(id,title,state) VALUES('old','existing goal','active')")
        self.sql("UPDATE tasks SET goal='old' WHERE id='T1'")
        self.sql("UPDATE meta SET value='1' WHERE key='schema_version'")
        self.sw("status")
        self.sw("status")
        with self.database() as db:
            self.assertEqual(
                db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], str(core.SCHEMA_VERSION)
            )
            self.assertEqual(db.execute("SELECT workflow_version FROM goals WHERE id='old'").fetchone()[0], 1)
        self.join("ann")
        self.assertIn("Architecture", self.sw("claim", "T1", "--as", "ann", ok=False))
        self.architecture("old")
        self.sw("claim", "T1", "--as", "ann")
        self.assertEqual(self.contract()["state"], "active")

    def test_ec201_future_schema_is_refused_before_upgrade(self):
        self.sw("status")
        self.sql("UPDATE meta SET value='999' WHERE key='schema_version'")
        self.sql("DROP TABLE checkpoints")
        self.assertIn("newer hivewire", self.sw("status", ok=False))
        with self.database() as db:
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "999")
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='checkpoints'").fetchone())

    def test_ec204_offer_accept_and_one_counter_keep_the_original_decision_deadline(self):
        self.offer()
        self.assertIn("accept the offer", self.sw("claim", "T1", "--as", "ann", ok=False))
        self.join("bob")
        self.assertIn("Only offered owner", self.sw("contract", "accept", "T1", "--as", "bob", ok=False))
        decision = self.contract()["decision_at"]
        self.sw(
            "contract", "counter", "T1", "--as", "ann", "--reason", "The fixture requires a longer validation window."
        )
        self.sw(
            "contract",
            "decide",
            "T1",
            "--active-time-min",
            "35",
            "--reason",
            "Allow five more minutes to verify the fixture.",
            "--as",
            "human",
        )
        self.assertEqual(self.contract()["decision_at"], decision)
        self.assertIn(
            "Only one counter",
            self.sw(
                "contract",
                "counter",
                "T1",
                "--as",
                "ann",
                "--reason",
                "Request yet another round without new fixture evidence.",
                ok=False,
            ),
        )
        self.sw("contract", "accept", "T1", "--as", "ann")
        self.sw("claim", "T1", "--as", "ann")
        self.assertEqual(self.contract()["state"], "active")
        self.assertEqual(self.contract()["epoch"], self.task("T1")["epoch"])

    def test_ec204_decision_expiry_is_durable_when_claim_is_refused(self):
        self.offer()
        self.sql("UPDATE task_contracts SET decision_at='2020-01-01T00:00:00+00:00'")
        self.sw("claim", "T1", "--as", "ann", ok=False)
        self.assertEqual(self.contract()["state"], "expired")
        self.assertIn("Contract expired", self.sw("inbox", "--as", "ann"))

    def test_ec204_replaced_offer_has_a_new_epoch_and_old_grace_does_not_escalate(self):
        self.offer()
        old_epoch = self.contract()["epoch"]
        self.sql("UPDATE task_contracts SET decision_at='2020-01-01T00:00:00+00:00'")
        self.sw("status")
        self.sw("contract", "offer", "T1", "ann", "--as", "human")
        self.assertGreater(self.contract()["epoch"], old_epoch)
        self.sql("UPDATE task_contracts SET grace_until='2020-01-01T00:00:00+00:00' WHERE state='expired'")
        self.sw("status")
        with self.database() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM events WHERE kind='contract_recovery_required'").fetchone()[0], 0
            )
        self.assertIn(
            "Stale offer epoch", self.sw("contract", "accept", "T1", "--as", "ann", "--epoch", str(old_epoch), ok=False)
        )
        self.sw("contract", "accept", "T1", "--as", "ann", "--epoch", str(self.contract()["epoch"]))

    def test_ec205_stale_leave_cannot_release_the_current_epoch(self):
        wt = self.activate()
        epoch = self.task("T1")["epoch"]
        self.expire()
        self.sw("status")
        self.assertIn(
            "Stale epoch",
            self.sw(
                "leave",
                "--as",
                "ann",
                "--epoch",
                str(epoch),
                "--release",
                "An obsolete client is attempting a handoff.",
                ok=False,
            ),
        )
        self.assertEqual(self.task("T1")["assignee"], "ann")
        self.assertEqual(self.task("T1")["state"], "expired")
        self.assertTrue(wt.exists())

    def test_ec202_scope_exception_cannot_widen_a_contract(self):
        wt = self.activate()
        (wt / "outside.txt").write_text("outside the agreed scope\n", encoding="utf-8")
        self.sw("step", "1", "--as", "ann", "--evidence", "Wrote a file that is outside the contracted scope")
        self.git("add", ".", cwd=wt)
        self.git("commit", "-qm", "attempt a scope exception", cwd=wt)
        self.sw("step", "2", "--as", "ann", "--evidence", "Committed the file for verification")
        self.assertIn(
            "outside the approved scope",
            self.sw(
                "submit",
                "--as",
                "ann",
                "--evidence",
                "The command completed but the scope is wrong",
                "--out-of-scope-reason",
                "Attempting to widen the accepted contract",
                ok=False,
            ),
        )

    def test_ec205_expiry_fences_work_and_preserves_dirty_tree_through_restart(self):
        wt = self.activate()
        (wt / "unfinished.txt").write_text("valuable uncommitted work\n", encoding="utf-8")
        epoch = self.task("T1")["epoch"]
        target = self.git("rev-parse", "main")
        self.expire()
        self.assertIn(
            "Contract for T1",
            self.sw("step", "1", "--as", "ann", "--evidence", "file written but not verified", ok=False),
        )
        self.assertEqual(self.task("T1")["state"], "expired")
        self.assertEqual(self.task("T1")["epoch"], epoch + 1)
        self.sw("status")  # another process reopens the board
        self.assertTrue((wt / "unfinished.txt").exists())
        self.assertEqual(self.git("rev-parse", "main"), target)
        self.assertIn(
            "Stale epoch",
            self.sw(
                "checkpoint",
                "--as",
                "ann",
                "--epoch",
                str(epoch),
                "--note",
                "File written but verification is incomplete",
                "--next",
                "Run the fixture test before submitting",
                ok=False,
            ),
        )
        self.sw(
            "checkpoint",
            "--as",
            "ann",
            "--epoch",
            str(epoch + 1),
            "--note",
            "File written but verification is incomplete",
            "--next",
            "Run the fixture test before submitting",
        )
        self.assertIn("unfinished.txt", self.sw("explain", "T1"))
        self.sw("release", "--as", "ann", "Checkpoint retained; verify the fixture before continuing.")
        self.assertTrue(wt.exists())
        self.assertTrue((wt / "unfinished.txt").exists())
        self.assertEqual(self.task("T1")["state"], "open")

    def test_ec206_blocked_time_does_not_consume_active_time_but_wall_deadline_still_applies(self):
        self.activate()
        self.sql("UPDATE task_contracts SET active_since=?", (core.iso(core.utcnow() - timedelta(minutes=2)),))
        self.sw("block", "--as", "ann", "Waiting for the fixture owner to supply input")
        before = self.contract()["active_seconds"]
        self.sql("UPDATE task_contracts SET blocked_at=?", (core.iso(core.utcnow() - timedelta(minutes=10)),))
        self.sw("start", "--as", "ann")
        c = self.contract()
        self.assertAlmostEqual(c["active_seconds"], before, delta=1)
        self.assertGreaterEqual(c["blocked_seconds"], 600)
        self.expire()
        self.sw("start", "--as", "ann", ok=False)
        self.assertEqual(self.contract()["state"], "expired")

    def test_ec206_active_time_and_deliberation_limits_are_enforced(self):
        self.activate(start=False)
        self.sql("UPDATE task_contracts SET deliberation_at='2020-01-01T00:00:00+00:00'")
        self.sw("start", "--as", "ann", ok=False)
        self.assertEqual(self.task("T1")["failure"], "deliberation limit elapsed")
        self.sw(
            "contract",
            "extend",
            "T1",
            "--minutes",
            "5",
            "--reason",
            "The API decision is now settled; resume the bounded implementation.",
            "--as",
            "human",
        )
        self.sw("start", "--as", "ann")
        self.sql("UPDATE task_contracts SET active_seconds=999999")
        self.sw("step", "1", "--as", "ann", "--evidence", "Unverified fixture still in progress", ok=False)
        self.assertEqual(self.task("T1")["failure"], "active time limit elapsed")
        self.assertIn(
            "One justified extension",
            self.sw(
                "contract",
                "extend",
                "T1",
                "--minutes",
                "5",
                "--reason",
                "Requesting another extension after the first has been consumed.",
                "--as",
                "human",
                ok=False,
            ),
        )

    def test_ec207_checkpoint_due_and_grace_escalation_are_idempotent(self):
        self.activate()
        self.sql("UPDATE task_contracts SET checkpoint_at='2020-01-01T00:00:00+00:00'")
        self.sw("status")
        self.sw("status")
        self.assertIn("(DUE)", self.sw("explain", "T1"))
        self.expire()
        self.sw("status")
        self.sql("UPDATE task_contracts SET grace_until='2020-01-01T00:00:00+00:00'")
        self.sw("status")
        self.sw("status")
        with self.database() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM messages WHERE body LIKE 'Checkpoint due:%'").fetchone()[0], 1
            )
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE kind='contract_expired'").fetchone()[0], 1)
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM events WHERE kind='contract_recovery_required'").fetchone()[0], 1
            )

    def test_ec207_due_checkpoint_blocks_new_work_until_a_fenced_snapshot(self):
        self.activate()
        self.sql("UPDATE task_contracts SET checkpoint_at='2020-01-01T00:00:00+00:00'")
        self.assertIn(
            "Checkpoint due", self.sw("step", "1", "--as", "ann", "--evidence", "Recorded fixture evidence", ok=False)
        )
        self.sw(
            "checkpoint",
            "--as",
            "ann",
            "--epoch",
            str(self.task("T1")["epoch"]),
            "--note",
            "The fixture has been investigated and remains local",
            "--next",
            "Record the evidence and commit the fixture",
        )
        self.sw("step", "1", "--as", "ann", "--evidence", "Recorded fixture evidence")

    def test_ec210_review_reserve_stops_new_implementation(self):
        self.activate()
        terms = json.loads(self.contract()["terms"])
        terms["deadline_at"] = core.iso(core.utcnow() + timedelta(minutes=4))
        self.sql("UPDATE task_contracts SET terms=?", (json.dumps(terms),))
        self.assertIn(
            "Review reserve reached",
            self.sw(
                "step", "1", "--as", "ann", "--evidence", "The fixture is incomplete and needs a handoff", ok=False
            ),
        )
        self.assertEqual(self.contract()["state"], "active")
        self.sw(
            "checkpoint",
            "--as",
            "ann",
            "--epoch",
            str(self.task("T1")["epoch"]),
            "--note",
            "The fixture is incomplete and needs a handoff",
            "--next",
            "Review the fixture and propose a smaller follow-up",
        )

    def test_ec211_crash_during_migration_rolls_back_schema_and_can_be_retried(self):
        self.sw("status")
        self.sql("UPDATE meta SET value='1' WHERE key='schema_version'")
        self.sql("ALTER TABLE goals DROP COLUMN architecture_approval")
        self.sw("status", ok=False, env={"SWARM_FAILPOINT": "during_migration"})
        with self.database() as db:
            self.assertNotIn("architecture_approval", {r[1] for r in db.execute("PRAGMA table_info(goals)")})
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "1")
        self.sw("status")
        with self.database() as db:
            self.assertIn("architecture_approval", {r[1] for r in db.execute("PRAGMA table_info(goals)")})

    def test_ec208_expiry_during_gate_never_advances_target(self):
        self.offer()
        self.sw("contract", "accept", "T1", "--as", "ann")
        self.to_ready("ann", "T1")
        original = self.git("rev-parse", "main")
        sw = core.Swarm(self.root)
        old_cwd = Path.cwd()

        def expire_in_gate(*args, **kwargs):
            self.expire()
            return None

        try:
            with mock.patch.object(core, "gate_run", side_effect=expire_in_gate):
                with self.assertRaisesRegex(core.SwarmError, "absolute deadline"):
                    core.cmd_merge(sw, core.build_parser().parse_args(["merge", "--as", "ann"]))
            self.assertEqual(self.git("rev-parse", "main"), original)
            self.assertIsNone(sw.meta("merge_lock"))
        finally:
            sw.db.close()
            os.chdir(old_cwd)


class Architecture(ContractCase):
    def build_goal(self):
        self.sw("goal", "new", "GL", "Verify the health endpoint")
        fixtures.Goals.answer_all(self, "GL")
        self.sw(
            "goal",
            "outcome",
            "GL",
            "The endpoint returns a running version",
            "--check",
            "Run the endpoint verification suite",
        )
        self.sw(
            "goal",
            "task",
            "GL",
            "H-api",
            "Implement the endpoint",
            "--serves",
            "1",
            "--scope",
            "src/",
            "--done-when",
            "Run the endpoint verification suite",
        )

    def test_ec202_architecture_is_required_and_approval_tracks_goal_revision(self):
        self.build_goal()
        self.assertIn("architecture brief missing", self.sw("goal", "review", "GL", ok=False))
        self.architecture("GL", approve=False)
        self.assertIn("approval missing", self.sw("goal", "commit", "GL", ok=False))
        self.sw("goal", "architecture", "GL", "--approve")
        self.sw("goal", "review", "GL")
        self.sw(
            "goal",
            "answer",
            "GL",
            "--set",
            "must_not_break=Preserve authentication and production configuration during the endpoint rollout",
        )
        self.assertIn("approval missing or stale", self.sw("goal", "commit", "GL", ok=False))
        self.sw("goal", "architecture", "GL", "--approve")
        self.sw("goal", "commit", "GL")
        self.join("ann")
        self.sw("claim", "H-api", "--as", "ann")
        wt = Path(self.task("H-api")["worktree"])
        self.assertIn(
            "widens contracted scope",
            self.sw("plan", "--as", "ann", *fixtures.PLAN, "--set", "scope=docs/", cwd=wt, ok=False),
        )
        self.sw("plan", "--as", "ann", *fixtures.PLAN, cwd=wt)
        self.assertIn("deadline", self.sw("explain", "H-api"))

    def test_ec203_high_risk_needs_human_and_source_evidence_must_match(self):
        self.build_goal()
        self.join("ann")
        self.architecture("GL", risk="high", approve=False)
        self.assertIn("requires the human", self.sw("goal", "architecture", "GL", "--approve", "--as", "ann", ok=False))
        (self.root / "backlog.md").write_text(
            "Changed source after the architecture was reasoned about\n", encoding="utf-8"
        )
        self.assertIn("evidence changed", self.sw("goal", "architecture", "GL", "--approve", ok=False))
        self.sw("goal", "architecture", "GL", "--evidence", "backlog.md")
        self.sw("goal", "architecture", "GL", "--approve")
        self.sw("goal", "commit", "GL")

    def test_ec201_a_real_version_one_database_upgrades_without_losing_messages(self):
        self.sw("status")
        db_path = self.root / ".git" / "swarm" / "swarm.db"
        self.sql_drop_v2(db_path)
        self.sw("status")
        with self.database(db_path) as db:
            self.assertEqual(db.execute("SELECT body FROM messages").fetchone()[0], "preserve this message")
            self.assertEqual(db.execute("SELECT workflow_version FROM goals").fetchone()[0], 1)

    def sql_drop_v2(self, db_path):
        with self.database(db_path) as db:
            db.execute("DROP TABLE task_contracts")
            db.execute("DROP TABLE checkpoints")
            db.execute("DROP TABLE goals")
            db.execute(
                "CREATE TABLE goals(id TEXT PRIMARY KEY,title TEXT,statement TEXT,state TEXT,answers TEXT DEFAULT '{}',outcomes TEXT DEFAULT '[]',created_by TEXT,created_at TEXT,updated_at TEXT,closed TEXT)"
            )
            db.execute("INSERT INTO goals(id,state) VALUES('old','active')")
            db.execute("INSERT INTO messages(body,recipient,sender) VALUES('preserve this message','human','swarm')")
            db.execute("UPDATE meta SET value='1' WHERE key='schema_version'")

    def test_ec209_crashed_new_goal_owner_can_be_taken_over_with_remaining_contract(self):
        self.build_goal()
        self.architecture("GL")
        self.sw("goal", "commit", "GL")
        self.join("ann")
        self.join("bob")
        self.sw("claim", "H-api", "--as", "ann")
        self.sw("plan", "--as", "ann", *fixtures.PLAN)
        self.sw("start", "--as", "ann")
        with self.database() as db:
            deadline = json.loads(db.execute("SELECT terms FROM task_contracts").fetchone()[0])["deadline_at"]
            db.execute(
                "UPDATE agents SET heartbeat_at='2020-01-01T00:00:00+00:00',offline_at='2020-01-01T00:00:00+00:00',state='offline' WHERE name='ann'"
            )
        self.sw("claim", "H-api", "--take-over", "--as", "bob")
        with self.database() as db:
            owner, terms = db.execute("SELECT owner,terms FROM task_contracts ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(owner, "bob")
            self.assertEqual(json.loads(terms)["deadline_at"], deadline)
        self.sw("join", "--as", "ann", "--kind", "claude", "--resume")
        self.assertIn(
            "holds no task",
            self.sw(
                "step",
                "1",
                "--as",
                "ann",
                "--epoch",
                "1",
                "--evidence",
                "Stale worker should never record this evidence",
                ok=False,
            ),
        )


if __name__ == "__main__":
    unittest.main()
