"""Proposal-driven integrity and liveness checks against real temporary Git repositories.

Covers the accepted parts of docs/proposals/identity-scope-offers.md and
docs/proposals/merge-liveness.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import unittest
from datetime import timedelta
from pathlib import Path

import test_contracts as contracts
import test_swarm as fixtures

core = fixtures.swarm_module
SWARM = fixtures.SWARM
PLAN = fixtures.PLAN


class ProposalCase(contracts.ContractCase):
    def contract(self, tid="T1"):
        with self.database() as db:
            db.row_factory = fixtures.sqlite3.Row
            return dict(db.execute("SELECT * FROM task_contracts WHERE task=? ORDER BY id DESC LIMIT 1", (tid,)).fetchone())

    def set_terms(self, **values):
        terms = json.loads(self.contract()["terms"])
        terms.update(values)
        with self.database() as db:
            db.execute("UPDATE task_contracts SET terms=? WHERE task='T1'", (json.dumps(terms),))

    def set_deadline(self, when):
        self.set_terms(deadline_at=core.iso(when))

    def set_queue(self, agent="ann", task="T2"):
        with self.database() as db:
            db.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('merge_lock',?)",
                (json.dumps({"agent": agent, "task": task, "at": core.iso()}),),
            )

    def activate_with_contract(self, name="bob"):
        self.join("ann")
        self.join(name)
        self.sw("contract", "offer", "T1", name, "--as", "ann")
        self.sw("contract", "accept", "T1", "--as", name)
        self.sw("claim", "T1", "--as", name)
        wt = Path(self.task("T1")["worktree"])
        self.sw("plan", "--as", name, *PLAN, cwd=wt)
        self.sw("start", "--as", name, cwd=wt)
        return wt


class SenderIdentity(ProposalCase):
    def messages(self):
        with self.database() as db:
            db.row_factory = fixtures.sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM messages ORDER BY id")]

    def test_ec367_send_refuses_missing_identity_and_writes_nothing(self):
        self.join("ann")
        self.join("bob")
        out = self.sw("send", "bob", "unauthenticated acknowledgement", ok=False)
        self.assertIn("Say who you are", out)
        self.assertEqual(self.messages(), [])

        out = self.sw("send", "bob", "explicit operator message", "--as", "human")
        self.assertIn("as human -> bob", out)
        self.assertEqual(self.messages()[-1]["sender"], "human")

    def test_ec367_env_identity_is_used_but_explicit_as_wins(self):
        self.join("ann")
        self.join("bob")
        out = self.sw("send", "bob", "from the environment", env={"SWARM_AS": "ann"})
        self.assertIn("as ann -> bob", out)
        self.assertEqual(self.messages()[-1]["sender"], "ann")

        out = self.sw("send", "bob", "explicit sender wins", "--as", "bob", env={"SWARM_AS": "ann"})
        self.assertIn("as bob -> bob", out)
        self.assertEqual(self.messages()[-1]["sender"], "bob")

    def test_ec367_authority_commands_refuse_a_missing_identity(self):
        self.join("ann")
        out = self.sw("contract", "offer", "T1", "ann", ok=False)
        self.assertIn("Say who you are", out)
        with self.database() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM task_contracts").fetchone()[0], 0)
        self.sw("contract", "offer", "T1", "ann", "--as", "human")

        out = self.sw(
            "incident", "resolve", "1", "--reason", "Routing the frozen snapshot to the operator",
            "--revision", "1", "--outcome", "escalated", ok=False,
        )
        self.assertIn("Say who you are", out)


class AdditiveScope(ProposalCase):
    def test_ec368_scope_add_is_coordinator_only_audited_and_preserves_assignment(self):
        wt = self.activate_with_contract()
        before_task, before_contract = self.task("T1"), self.contract()
        reason = "The closure record belongs to this task"

        out = self.sw(
            "contract", "scope", "add", "T1",
            "--path", "docs/closure.txt", "--reason", reason, "--as", "bob", ok=False,
        )
        self.assertIn("Only the coordinator", out)

        out = self.sw(
            "contract", "scope", "add", "T1",
            "--path", "docs/closure.txt", "--reason", reason, "--as", "ann",
        )
        self.assertIn("scope extended", out)
        after_task, after_contract = self.task("T1"), self.contract()
        self.assertEqual(before_task["epoch"], after_task["epoch"])
        self.assertEqual(before_task["ord"], after_task["ord"])
        self.assertEqual(before_task["assignee"], after_task["assignee"])
        self.assertEqual(before_contract["epoch"], after_contract["epoch"])
        terms = json.loads(after_contract["terms"])
        self.assertEqual(terms["scope_additions"], ["docs/closure.txt"])
        self.assertEqual(terms["scope_history"][-1]["by"], "ann")
        self.assertIn("closure record", terms["scope_history"][-1]["reason"])

        explain = self.sw("explain", "T1")
        self.assertIn("docs/closure.txt", explain)
        self.assertIn("closure record", explain)
        with self.database() as db:
            self.assertIsNotNone(
                db.execute("SELECT 1 FROM events WHERE kind='contract_scope_extended' AND task='T1'").fetchone()
            )

        # Repeating the same extension is a no-op, not a second audit entry.
        self.sw("contract", "scope", "add", "T1", "--path", "docs/closure.txt", "--reason", reason, "--as", "ann")
        self.assertEqual(len(json.loads(self.contract()["terms"])["scope_history"]), 1)

    def test_ec369_extended_scope_is_checked_at_submit(self):
        wt = self.activate_with_contract()
        self.sw(
            "contract", "scope", "add", "T1",
            "--path", "docs/closure.txt", "--reason", "The closure record belongs to this task", "--as", "ann",
        )
        (wt / "outside.txt").write_text("not approved\n", encoding="utf-8")
        (wt / "docs").mkdir(exist_ok=True)
        (wt / "docs" / "closure.txt").write_text("approved by extension\n", encoding="utf-8")
        self.git("add", ".", cwd=wt)
        self.git("commit", "-qm", "attempt with an unapproved file", cwd=wt)
        self.sw("step", "1", "--as", "bob", "--evidence", "wrote both files", cwd=wt)
        self.sw("step", "2", "--as", "bob", "--evidence", "committed both files", cwd=wt)

        out = self.sw(
            "submit", "--as", "bob", "--evidence", "gates pass locally",
            "--out-of-scope-reason", "the closure record is required", cwd=wt, ok=False,
        )
        self.assertIn("outside the approved scope", out)

        (wt / "outside.txt").unlink()
        self.git("add", "-A", cwd=wt)
        self.git("commit", "-qm", "keep only the approved extension", cwd=wt)
        out = self.sw("submit", "--as", "bob", "--evidence", "gates pass locally", cwd=wt)
        self.assertIn("ready to merge", out)

    def test_ec369_scope_add_rejects_paths_that_escape_the_repository(self):
        self.activate_with_contract()
        for path in ("../outside", "/absolute/file", "C:/windows/file"):
            out = self.sw(
                "contract", "scope", "add", "T1", "--path", path,
                "--reason", "A path must stay inside the repository", "--as", "ann", ok=False,
            )
            self.assertIn("must", out)


class QueueLiveness(ProposalCase):
    def ready_task(self):
        self.join("ann")
        self.join("bob")
        self.sw("contract", "offer", "T1", "bob", "--as", "ann")
        self.sw("contract", "accept", "T1", "--as", "bob")
        self.to_ready("bob", "T1")
        self.assertEqual(self.task("T1")["state"], "ready_to_merge")
        return Path(self.task("T1")["worktree"])

    def test_ec370_ready_task_behind_busy_queue_gets_one_bounded_grace(self):
        self.ready_task()
        self.set_deadline(core.utcnow() - timedelta(minutes=5))
        self.set_queue()
        self.sw("status")

        self.assertEqual(self.task("T1")["state"], "ready_to_merge")
        c = self.contract()
        terms = json.loads(c["terms"])
        self.assertIn("merge_queue", terms["queue_grace"]["kind"])
        self.assertEqual(c["extension_count"], 0)  # the manual extension remains available
        why = json.loads(self.sw("why", "T1", "--json"))["result"]
        self.assertIn("merge_queue", [b["kind"] for b in why["blockers"]])

        # The grace is bounded: a second sweep with the deadline still past expires the task.
        self.set_deadline(core.utcnow() - timedelta(minutes=5))
        self.sw("status")
        self.assertEqual(self.task("T1")["state"], "expired")
        self.assertIn("Contract expired", self.sw("inbox", "--as", "bob"))

    def test_ec370_submit_extends_once_when_the_queue_is_already_busy(self):
        self.join("ann")
        self.join("bob")
        self.sw("contract", "offer", "T1", "bob", "--as", "ann")
        self.sw("contract", "accept", "T1", "--as", "bob")
        self.sw("--as", "bob", "claim", "T1")
        wt = Path(self.task("T1")["worktree"])
        self.sw("--as", "bob", "plan", *PLAN, cwd=wt)
        self.sw("--as", "bob", "start", cwd=wt)
        (wt / "src").mkdir(exist_ok=True)
        (wt / "src/file.txt").write_text("x\n")
        self.sw("--as", "bob", "step", "1", "--evidence", "wrote src/file.txt", cwd=wt)
        self.git("add", ".", cwd=wt)
        self.git("commit", "-qm", "work", cwd=wt)
        self.sw("--as", "bob", "step", "2", "--evidence", "committed the work", cwd=wt)

        self.set_deadline(core.utcnow() + timedelta(minutes=5))
        self.set_queue()
        self.sw("submit", "--as", "bob", "--evidence", "gates pass locally", cwd=wt)
        terms = json.loads(self.contract()["terms"])
        self.assertEqual(terms["queue_grace"]["kind"], "merge_queue")
        self.assertGreater(core.parse(terms["deadline_at"]), core.utcnow() + timedelta(minutes=100))

    def test_ec371_queue_time_does_not_consume_the_active_budget(self):
        self.ready_task()
        self.set_terms(active_time_min=0.01)
        with self.database() as db:
            db.execute("UPDATE task_contracts SET active_seconds=0, active_since=NULL WHERE task='T1'")
        before = self.contract()["active_seconds"]
        time.sleep(1.2)
        self.sw("status")
        after = self.contract()
        self.assertEqual(float(after["active_seconds"]), float(before))
        self.assertIsNone(after["active_since"])
        self.assertEqual(self.task("T1")["state"], "ready_to_merge")

    def test_ec372_why_composes_the_enforced_blocker_and_next_action(self):
        out = self.sw("why", "T3")
        self.assertIn("unmet dependencies: T1", out)
        self.assertIn("next:", out)
        data = json.loads(self.sw("why", "T3", "--json"))["result"]
        self.assertEqual(data["task"], "T3")
        self.assertEqual(data["blockers"][0]["kind"], "dependency")
        self.assertTrue(data["next_action"])


class InboxWait(ProposalCase):
    def test_ec373_wait_streams_one_json_line_per_message_and_exits_on_timeout(self):
        self.join("ann")
        self.join("bob")
        proc = subprocess.Popen(
            [sys.executable, str(SWARM), "inbox", "--as", "bob", "--wait", "--json", "--timeout", "2"],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            time.sleep(0.7)
            self.sw("send", "bob", "streamed reply", "--as", "ann")
            line = proc.stdout.readline()
            self.assertTrue(line.strip(), "the wait stream did not emit the message")
            envelope = json.loads(line)
            self.assertEqual(envelope["sender"], "ann")
            self.assertEqual(envelope["body"], "streamed reply")
            rest, err = proc.communicate(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(rest.strip(), "", "the stream must not append a footer or final document")
        self.assertEqual(err.strip(), "")

    def test_ec373_wait_with_no_messages_exits_zero_with_no_output(self):
        self.join("bob")
        started = time.monotonic()
        out = self.sw("inbox", "--as", "bob", "--wait", "--timeout", "0.3")
        self.assertEqual(out.strip(), "")
        self.assertGreaterEqual(time.monotonic() - started, 0.3)


if __name__ == "__main__":
    unittest.main()
