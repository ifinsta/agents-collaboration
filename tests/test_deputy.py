"""Deterministic scout, durable attention and bounded deputy delegation."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import unittest
from datetime import timedelta
from pathlib import Path

import test_swarm as fixtures

core = fixtures.swarm_module


class DeputyCase(fixtures.SwarmCase):
    def sql(self, query, args=()):
        con = self.db()
        try:
            con.execute(query, args)
            con.commit()
        finally:
            con.close()

    def rows(self, query, args=()):
        con = self.db()
        con.row_factory = fixtures.sqlite3.Row
        try:
            return con.execute(query, args).fetchall()
        finally:
            con.close()

    def one(self, query, args=()):
        rows = self.rows(query, args)
        return rows[0] if rows else None

    def j(self, *args, **kwargs):
        return json.loads(self.sw(*args, "--json", **kwargs))["result"]

    def fail(self, *args, **kwargs):
        out = self.sw(*args, "--json", ok=False, **kwargs)
        try:
            return json.loads(out)["error"]["message"]
        except (ValueError, KeyError):
            return out

    def seed_urgent_signals(self):
        self.join("ann")
        self.join("bob")
        self.sw(
            "send",
            "bob",
            "The interface decision is blocking the release and needs an owner",
            "--as",
            "ann",
            "--priority",
            "critical",
            "--kind",
            "warning",
        )
        old = core.iso(core.utcnow() - timedelta(hours=1))
        self.sql("UPDATE messages SET created_at=? WHERE id=(SELECT MAX(id) FROM messages)", (old,))
        self.sql("UPDATE tasks SET state='gates_failed',epoch=3 WHERE id='T2'")

    def items(self, **kwargs):
        args = ["attention", "list"]
        for key, value in kwargs.items():
            flag = "--" + key.replace("_", "-")
            args += [flag] if value is True else [flag, str(value)]
        return self.j(*args)["items"]

    def activate(self, agent="bob", scope="*", caps="attention.claim,attention.report,attention.escalate", issuer="ann"):
        return self.j(
            "deputy", "activate", agent, "--scope", scope, "--capabilities", caps, "--minutes", "10", "--as", issuer
        )


class ScanAndDedupe(DeputyCase):
    def test_ec300_scan_is_deterministic_and_deduplicates(self):
        self.seed_urgent_signals()
        first = self.j("deputy", "scan", "--once")
        second = self.j("deputy", "scan", "--once")
        self.assertEqual(second["created_count"], 0)
        self.assertGreaterEqual(first["created_count"] + second["existing_count"], 2)
        self.assertEqual(self.rows("SELECT dedupe_key,COUNT(*) AS n FROM attention_items GROUP BY dedupe_key HAVING n>1"), [])
        items = self.items()
        message = next(i for i in items if i["kind"] == "message")
        task = next(i for i in items if i["kind"] == "task" and i["subject_ref"] == "task:T2")
        self.assertEqual(message["severity"], "P1")
        self.assertEqual(task["severity"], "P1")
        self.assertIn("not evidence of misconduct", self.j("deputy", "scan", "--once")["notice"])

    def test_ec301_critical_message_and_stuck_task_are_detected_once(self):
        self.seed_urgent_signals()
        items = self.items(severity="P1")
        self.assertEqual(len([i for i in items if i["kind"] == "message"]), 1)
        self.assertEqual(len([i for i in items if i["subject_ref"] == "task:T2"]), 1)
        self.assertTrue(all(i["severity"] == "P1" for i in items))

    def test_ec314_unowned_overdue_p1_gets_one_visible_reminder_and_stays_claimable(self):
        self.seed_urgent_signals()
        self.j("deputy", "scan", "--once")
        item = self.items(kind="message")[0]
        past = core.iso(core.utcnow() - timedelta(minutes=30))
        self.sql("UPDATE attention_items SET due_at=? WHERE id=?", (past, item["id"]))
        self.j("deputy", "status")
        history = self.rows(
            "SELECT * FROM attention_history WHERE attention=? AND note LIKE 'SLA reminder%'", (item["id"],)
        )
        self.assertEqual(len(history), 1, "the sweep sends the reminder even before an explicit scan")
        self.assertEqual((history[0]["old_status"], history[0]["new_status"]), ("new", "new"))
        self.assertIn("not an allegation", history[0]["note"])
        message = self.one("SELECT * FROM messages WHERE idempotency_key LIKE ?", (f"attention:remind:{item['id']}:%",))
        self.assertEqual(message["sender"], "swarm")
        self.assertIn("assigns no blame", message["body"])
        self.assertEqual(self.one("SELECT COUNT(*) AS n FROM events WHERE kind='attention_reminded'")["n"], 1)
        self.assertEqual(self.j("deputy", "scan", "--once")["reminded_count"], 0, "an item is reminded once")
        self.assertEqual(self.items(kind="message")[0]["status"], "new", "a reminder is not a claim")
        task = next(i for i in self.items(kind="task") if i["subject_ref"] == "task:T2")
        self.assertIsNone(task["due_at"])
        self.sql(
            "UPDATE attention_items SET detected_at=? WHERE id=?",
            (core.iso(core.utcnow() - timedelta(minutes=31)), task["id"]),
        )
        self.j("deputy", "status")
        task_history = self.rows(
            "SELECT * FROM attention_history WHERE attention=? AND note LIKE 'SLA reminder%'", (task["id"],)
        )
        self.assertEqual(len(task_history), 1, "an item without a due_at is reminded once it is past the queue SLA")
        self.assertIn("queue SLA", task_history[0]["note"])
        self.assertEqual(
            self.one(
                "SELECT COUNT(*) AS n FROM messages WHERE idempotency_key LIKE ?",
                (f"attention:remind:{task['id']}:%",),
            )["n"],
            1,
        )
        self.assertEqual(self.j("deputy", "scan", "--once")["reminded_count"], 0, "the queue-SLA reminder is once only")
        task = next(i for i in self.items(kind="task") if i["subject_ref"] == "task:T2")
        self.assertEqual((task["status"], task["owner"]), ("new", None))
        self.activate(scope="message:*")
        self.assertEqual(self.j("attention", "claim", str(item["id"]), "--as", "bob")["item"]["owner"], "bob")

    def test_ec318_inconsistent_review_reservation_is_a_bounded_conflict_signal(self):
        self.join("ann")
        self.join("bob")
        self.sql("UPDATE agents SET reviewing=99 WHERE name='ann'")
        self.j("deputy", "scan", "--once")
        item = next(i for i in self.items(kind="incident") if i["subject_ref"] == "incident:99")
        self.assertEqual(item["severity"], "P2")
        self.assertIn("inconsistent review reservation", item["summary"])
        self.assertIn("without inferring misconduct", item["summary"])


class Delegation(DeputyCase):
    def test_ec302_worker_without_delegation_cannot_claim(self):
        self.seed_urgent_signals()
        item = self.items(kind="message")[0]
        self.assertIn("no active deputy delegation", self.fail("attention", "claim", str(item["id"]), "--as", "bob"))

    def test_ec303_deputy_cannot_use_coordinator_only_operations(self):
        self.seed_urgent_signals()
        self.activate(scope="message:*")
        self.assertIn("Only the coordinator", self.fail("pause", "stop work", "--as", "bob"))
        item = self.items(kind="message")[0]
        self.j("attention", "claim", str(item["id"]), "--as", "bob")
        self.assertIn(
            "Only the coordinator",
            self.fail(
                "attention",
                "resolve",
                str(item["id"]),
                "--as",
                "bob",
                "--disposition",
                "resolved",
                "--reason",
                "The deputy must not resolve its own finding",
            ),
        )

    def test_ec304_scope_is_exact_and_a_scope_violation_revokes(self):
        self.seed_urgent_signals()
        self.activate(scope="message:*")
        task_item = next(i for i in self.items() if i["kind"] == "task")
        self.assertIn("outside", self.fail("attention", "claim", str(task_item["id"]), "--as", "bob"))
        self.assertIsNone(self.j("deputy", "status")["deputy"])
        # The revoked lease cannot be used even for subjects that matched it.
        message_item = next(i for i in self.items() if i["kind"] == "message")
        self.assertIn("no active deputy delegation", self.fail("attention", "claim", str(message_item["id"]), "--as", "bob"))

    def test_ec305_policy_edit_fences_a_live_delegation(self):
        self.seed_urgent_signals()
        self.activate(scope="message:*")
        item = self.items(kind="message")[0]
        self.j("attention", "claim", str(item["id"]), "--as", "bob")
        with open(self.root / ".agents" / "swarm" / "config.toml", "a", encoding="utf-8") as handle:
            handle.write("\n# policy changed while the deputy held a lease\n")
        self.assertIn(
            "no active deputy delegation",
            self.fail(
                "attention",
                "report",
                str(item["id"]),
                "--as",
                "bob",
                "--finding",
                "The critical message is still waiting for a decision",
                "--evidence",
                "sqlite:messages/1",
                "--recommend",
                "The coordinator should answer or assign the decision",
            ),
        )
        self.assertIn("policy changed", self.one("SELECT reason FROM deputy_delegations ORDER BY id DESC LIMIT 1")["reason"])
        self.assertIsNone(self.j("deputy", "status")["deputy"])

    def test_ec306_coordinator_term_change_revokes_the_lease(self):
        self.join("ann")
        self.join("bob")
        self.join("cat")
        self.sw("deputy", "scan", "--once")
        self.activate(scope="*")
        self.sw("leave", "--as", "ann")
        status = self.j("deputy", "status")
        self.assertEqual(status["coordinator"], "bob")
        self.assertIsNone(status["deputy"])
        self.assertIn(
            "coordination term changed",
            self.one("SELECT reason FROM deputy_delegations ORDER BY id DESC LIMIT 1")["reason"],
        )

    def test_ec307_report_requires_evidence_and_creates_a_bounded_recommendation(self):
        self.seed_urgent_signals()
        self.activate(scope="message:*")
        item = self.items(kind="message")[0]
        self.j("attention", "claim", str(item["id"]), "--as", "bob")
        investigating = self.j(
            "attention",
            "investigate",
            str(item["id"]),
            "--as",
            "bob",
            "--note",
            "Reading the message receipt and the task history before proposing an action",
        )
        self.assertEqual(investigating["item"]["status"], "investigating")
        self.assertIn(
            "evidence",
            self.fail(
                "attention",
                "report",
                str(item["id"]),
                "--as",
                "bob",
                "--finding",
                "The critical message has waited too long for an owner",
                "--recommend",
                "The coordinator should answer it or delegate the decision",
            ),
        )
        reported = self.j(
            "attention",
            "report",
            str(item["id"]),
            "--as",
            "bob",
            "--finding",
            "The critical message has waited an hour for a decision owner",
            "--evidence",
            "sqlite:messages/1",
            "--recommend",
            "The coordinator should answer it or assign a decision owner now",
        )
        self.assertEqual(reported["item"]["status"], "proposed_action")
        self.assertEqual(reported["item"]["decision_owner"], "ann")
        history = self.rows("SELECT * FROM attention_history WHERE attention=? ORDER BY id", (item["id"],))
        inbox = self.one("SELECT * FROM messages WHERE sender='bob' AND recipient='ann' ORDER BY id DESC LIMIT 1")
        self.assertGreaterEqual(len(history), 3)
        self.assertIn("Evidence:", inbox["body"])
        self.assertIn("grants no authority", inbox["body"])
        decided = self.j(
            "attention",
            "resolve",
            str(item["id"]),
            "--as",
            "ann",
            "--disposition",
            "resolved",
            "--reason",
            "The coordinator answers the decision and assigns an owner",
        )
        self.assertEqual((decided["item"]["status"], decided["item"]["disposition"]), ("resolved", "resolved"))
        self.assertEqual(decided["item"]["owner"], None)

    def test_ec316_scoped_deputy_may_propose_an_incident_but_cannot_adjudicate_it(self):
        self.seed_urgent_signals()
        self.sw("claim", "T1", "--as", "bob")
        self.sw("--as", "cat", "join", "--kind", "claude")
        self.activate(agent="cat", scope="task:T1", caps="incident.propose")
        self.sw(
            "incident",
            "open",
            "T1",
            "--signal",
            "The submitted diff may contradict the checkpoint evidence and needs independent review",
            "--subject",
            "bob",
            "--as",
            "cat",
        )
        incident = self.one("SELECT * FROM incidents ORDER BY id DESC LIMIT 1")
        self.assertEqual(incident["opened_by"], "cat")
        reviewer = self.one("SELECT reviewer FROM incident_reviews WHERE incident=?", (incident["id"],))["reviewer"]
        self.assertNotEqual(reviewer, "cat", "the deputy must not review its own proposal")
        self.assertIn(
            "Only the coordinator",
            self.fail(
                "incident",
                "resolve",
                str(incident["id"]),
                "--revision",
                "1",
                "--reason",
                "The deputy must not adjudicate the incident it proposed",
                "--outcome",
                "upheld",
                "--as",
                "cat",
            ),
        )

    def test_ec317_scoped_deputy_may_request_attention_but_not_cancel(self):
        self.seed_urgent_signals()
        self.sw("claim", "T1", "--as", "bob")
        self.sw("--as", "cat", "join", "--kind", "claude")
        self.activate(agent="cat", scope="agent:bob", caps="interrupt.request")
        self.sw(
            "interrupt",
            "request",
            "bob",
            "--mode",
            "attention",
            "--reason",
            "Ask for a short status check before the release decision",
            "--deadline-min",
            "5",
            "--as",
            "cat",
        )
        interrupt = self.one("SELECT * FROM interrupts ORDER BY id DESC LIMIT 1")
        self.assertEqual((interrupt["requester"], interrupt["target"], interrupt["mode"]), ("cat", "bob", "attention"))
        self.assertIn(
            "not cancellation",
            self.fail(
                "interrupt",
                "request",
                "bob",
                "--mode",
                "cancel",
                "--reason",
                "A deputy must not cancel another agent's work",
                "--deadline-min",
                "5",
                "--as",
                "cat",
            ),
        )
        self.assertIn(
            "outside",
            self.fail(
                "interrupt",
                "request",
                "ann",
                "--mode",
                "attention",
                "--reason",
                "This target is outside the delegated scope",
                "--deadline-min",
                "5",
                "--as",
                "cat",
            ),
        )
        self.assertIsNone(self.j("deputy", "status")["deputy"], "a scope violation revokes the lease")


class LeasesAndRecovery(DeputyCase):
    def test_ec308_concurrent_claims_have_one_owner(self):
        self.seed_urgent_signals()
        self.activate(scope="message:*")
        item = self.items(kind="message")[0]
        outputs = []

        def go(who):
            done = subprocess.run(
                [sys.executable, str(fixtures.SWARM), "--as", who, "attention", "claim", str(item["id"])],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=False,
            )
            outputs.append(done.returncode)

        threads = [threading.Thread(target=go, args=(who,)) for who in ("ann", "bob")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(outputs).count(0), 1, outputs)
        self.assertIn(self.one("SELECT owner FROM attention_items WHERE id=?", (item["id"],))["owner"], ("ann", "bob"))

    def test_ec309_expired_lease_preserves_evidence_and_allows_recovery(self):
        self.seed_urgent_signals()
        self.activate(scope="message:*")
        item = self.items(kind="message")[0]
        self.j("attention", "claim", str(item["id"]), "--as", "bob", "--lease-sec", "1")
        time.sleep(1.2)
        recovered = self.j("attention", "claim", str(item["id"]), "--as", "ann")
        self.assertEqual(recovered["item"]["owner"], "ann")
        self.assertIn(
            "does not hold",
            self.fail(
                "attention",
                "report",
                str(item["id"]),
                "--as",
                "bob",
                "--finding",
                "A stale owner must not report against the recovered item",
                "--evidence",
                "sqlite:messages/1",
                "--recommend",
                "The new owner should continue the investigation",
            ),
        )
        notes = [r["note"] for r in self.rows("SELECT note FROM attention_history WHERE attention=?", (item["id"],))]
        self.assertTrue(any("evidence preserved" in note for note in notes), notes)

    def test_ec310_crash_between_scan_and_claim_is_idempotent(self):
        self.seed_urgent_signals()
        before = len(self.items(all=True))
        self.sql("UPDATE attention_items SET status='claimed',owner='bob',lease_until=?", ((core.iso(core.utcnow() - timedelta(seconds=1))),))
        self.j("deputy", "scan", "--once")
        after = self.items(all=True)
        self.assertEqual(len(after), before)
        self.assertTrue(all(i["owner"] is None or i["status"] != "claimed" for i in after))


class Activation(DeputyCase):
    max_agents = 4

    def test_ec311_productive_agent_and_second_lease_are_refused(self):
        self.join("ann")
        self.join("bob")
        self.join("cat")
        self.join("dan")
        self.sw("claim", "T1", "--as", "bob")
        self.assertIn("productive", self.fail("deputy", "activate", "bob", "--scope", "*", "--as", "ann"))
        self.activate(agent="cat")
        self.assertIn("single active deputy", self.fail("deputy", "activate", "dan", "--scope", "*", "--as", "ann"))
        self.assertIn("Only the coordinator", self.fail("deputy", "nominate", "dan", "--as", "bob"))

    def test_ec312_minimum_active_time_and_cooldown_protect_throughput(self):
        self.join("ann")
        self.join("bob")
        self.join("cat")
        self.activate(agent="bob")
        self.assertIn(
            "Minimum deputy active time",
            self.fail("deputy", "release", "--reason", "Demand fell and the deputy should return to the pool", "--as", "bob"),
        )
        self.j("deputy", "release", "--reason", "Coordinator ends the bounded shift and returns the agent", "--as", "ann")
        self.assertIn(
            "cooldown",
            self.fail("deputy", "activate", "cat", "--scope", "*", "--as", "ann"),
        )
        forced = self.j("deputy", "activate", "cat", "--scope", "*", "--as", "human", "--force")
        self.assertEqual(forced["activated"], "cat")

    def test_ec315_worker_role_change_ends_the_lease_and_releases_open_claims(self):
        self.seed_urgent_signals()
        item = self.items(kind="message")[0]
        self.activate(agent="bob", scope="message:*")
        self.j("attention", "claim", str(item["id"]), "--as", "bob")
        self.sw("claim", "T1", "--as", "bob")
        status = self.j("deputy", "status")
        self.assertIsNone(status["deputy"])
        lease = self.one("SELECT * FROM deputy_delegations ORDER BY id DESC LIMIT 1")
        self.assertIn("became productive", lease["reason"])
        released = self.one("SELECT * FROM attention_items WHERE id=?", (item["id"],))
        self.assertEqual((released["status"], released["owner"], released["lease_until"]), ("new", None, None))
        self.assertIn(
            "evidence preserved",
            self.one("SELECT note FROM attention_history WHERE attention=? ORDER BY id DESC LIMIT 1", (item["id"],))[
                "note"
            ],
        )
        self.assertIn("no active deputy delegation", self.fail("attention", "claim", str(item["id"]), "--as", "bob"))

    def test_ec313_all_busy_keeps_scouting_and_escalates_without_a_sixth_slot(self):
        self.seed_urgent_signals()
        self.sw("--as", "cat", "join", "--kind", "claude")
        self.sw("claim", "T1", "--as", "bob")
        self.sw("claim", "T5", "--as", "cat")
        # Both implementers are productive; only the coordinator is idle.
        status = self.j("deputy", "status")
        self.assertTrue(status["candidate"]["eligible"], status)
        self.assertNotIn("bob", status["available"])
        self.assertNotIn("cat", status["available"])
        leases = self.one("SELECT COUNT(*) FROM deputy_delegations WHERE state='active'")[0]
        notice = self.one(
            "SELECT COUNT(*) FROM messages WHERE sender='swarm' AND idempotency_key LIKE 'deputy:capacity:%'"
        )[0]
        self.assertEqual(leases, 0)
        self.assertEqual(notice, 1)


if __name__ == "__main__":
    unittest.main()
