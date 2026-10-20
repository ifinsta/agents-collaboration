"""Acting from the dashboard as the human, and the inbox steward.

Actions run the real `hivewire` command in the board's repository, so these tests check both the HTTP guards and that
the board changed the way the CLI would change it. Nothing here starts a real agent CLI.
"""

from __future__ import annotations

import http.client
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta

from test_web_dashboard import WebCase, core, fixtures

import swarm_web  # noqa: E402  (the fixtures put the skill directory on sys.path)


class ActionCase(WebCase):
    def setUp(self):
        super().setUp()
        with self.board() as sw:
            self.entry = swarm_web.register(sw, "python hivewire.py", str(fixtures.SWARM.with_name("hivewire.py")))

    def act(self, body, *, origin=True, token=True, ctype="application/json", raw=None, board=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=180)
        headers = {"Host": f"127.0.0.1:{self.port}", "Content-Type": ctype}
        if origin:
            headers["Origin"] = origin if isinstance(origin, str) else f"http://127.0.0.1:{self.port}"
        if token:
            headers["X-Swarm-Token"] = self.server.token
        data = raw if raw is not None else json.dumps(body).encode("utf-8")
        try:
            conn.request("POST", "/api/act" + (f"?b={board}" if board else ""), body=data, headers=headers)
            response = conn.getresponse()
            payload = response.read()
            return response.status, json.loads(payload) if payload else {}
        finally:
            conn.close()

    def ok(self, body):
        status, result = self.act(body)
        self.assertEqual(status, 200, result)
        self.assertTrue(result["ok"], result)
        return result

    def db(self):
        con = sqlite3.connect(self.root / ".git" / "swarm" / "swarm.db")
        con.row_factory = sqlite3.Row
        return closing(con)

    def ask_human(self, text="Should /ready fail while the cache is cold?"):
        self.sw("--as", "bob", "claim", "T2")
        self.sw("--as", "bob", "ask", text, "--to", "human", "--critical")
        with self.db() as con:
            return con.execute("SELECT id FROM questions ORDER BY id DESC LIMIT 1").fetchone()[0]


class Guards(ActionCase):
    def test_an_action_needs_the_pages_origin_the_token_json_and_a_known_action(self):
        body = {"action": "steward"}
        self.assertEqual(self.act(body, origin=False)[0], 403, "no Origin: not the dashboard's page")
        self.assertEqual(self.act(body, origin="http://evil.example")[0], 403)
        self.assertEqual(self.act(body, origin=f"http://127.0.0.1:{self.port + 1}")[0], 403)
        self.assertEqual(self.act(body, token=False)[0], 403)
        self.assertEqual(self.act(body, ctype="text/plain")[0], 415)
        self.assertEqual(self.act(None, raw=b"{not json")[0], 400)
        self.assertEqual(self.act(None, raw=b"[1, 2]")[0], 400)
        self.assertEqual(self.act(None, raw=json.dumps({"action": "x", "pad": "a" * 20000}).encode())[0], 413)
        self.assertEqual(self.act({"action": "rm -rf"})[0], 400)
        self.assertEqual(self.act(body, board="deadbeef")[0], 404)

    def test_a_read_only_dashboard_and_an_old_registration_cannot_act(self):
        self.server.actions = False
        self.assertEqual(self.act({"action": "steward"})[0], 403)
        self.assertFalse(self.api("/api/overview")["actions"])
        self.server.actions = True
        self.assertTrue(self.api("/api/overview")["actions"])
        with self.board() as sw:
            swarm_web.register(sw, "python hivewire.py", None)  # registered by a swarm that knew no launcher
        self.assertEqual(self.act({"action": "steward"})[0], 409)
        self.assertFalse(self.api("/api/overview")["actions"])

    def test_inputs_are_checked_before_any_command_runs(self):
        for body in (
            {"action": "answer", "question": "1", "text": "yes"},
            {"action": "answer", "question": 1, "text": "   "},
            {"action": "answer", "question": 1, "text": "x" * 4001},
            {"action": "waive", "question": 0, "text": "no"},
            {"action": "send", "to": "../ann", "text": "hi"},
            {"action": "send", "to": "ann", "text": "hi", "kind": "interrupt"},
            {"action": "approve", "goal": "--approve"},
            {"action": "ack", "message": True},
            {"action": "start_reviewer", "cli": "bash", "name": "reviewer"},
            {"action": "start_reviewer", "cli": "claude", "name": "Not A Name"},
        ):
            status, result = self.act(body)
            self.assertEqual(status, 400, (body, result))
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM messages WHERE sender='human'").fetchone()[0], 0)


class Acting(ActionCase):
    def test_answer_a_question_and_text_that_looks_like_an_option_stays_text(self):
        qid = self.ask_human()
        self.ok({"action": "answer", "question": qid, "text": "--as ann: return 503 while cold"})
        with self.db() as con:
            q = con.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
        self.assertEqual(q["answer"], "--as ann: return 503 while cold")
        self.assertEqual(q["answered_by"], "human")
        status, again = self.act({"action": "answer", "question": qid, "text": "again"})
        self.assertEqual(status, 200)
        self.assertFalse(again["ok"], "the engine refuses a second answer and the page shows why")
        self.assertTrue(again["error"])

    def test_waive_a_question_with_a_reason(self):
        qid = self.ask_human("Which port?")
        self.ok({"action": "waive", "question": qid, "text": "the slot ports decide this"})
        with self.db() as con:
            self.assertEqual(con.execute("SELECT waived FROM questions WHERE id=?", (qid,)).fetchone()[0], 1)

    def test_reply_to_a_message_and_acknowledge_it(self):
        self.sw("--as", "ann", "send", "human", "I lean 503 here", "--kind", "decision")
        with self.db() as con:
            mid = con.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        self.ok({"action": "send", "to": "ann", "kind": "decision", "reply_to": mid, "text": "Agreed: 503 while the cache is cold"})
        thread = self.api(f"/api/message/{mid}")["thread"]
        self.assertEqual([m["sender"] for m in thread], ["ann", "human"])
        self.assertEqual(thread[1]["body"], "Agreed: 503 while the cache is cold")
        human = [r for r in self.api(f"/api/message/{mid}")["recipients"] if r["agent"] == "human"][0]
        self.assertIsNone(human["acked_at"], "a reply does not acknowledge")
        self.ok({"action": "ack", "message": mid})
        human = [r for r in self.api(f"/api/message/{mid}")["recipients"] if r["agent"] == "human"][0]
        self.assertIsNotNone(human["acked_at"])
        status, again = self.act({"action": "ack", "message": mid})
        self.assertFalse(again["ok"])
        self.assertIn("not waiting", again["error"])

    def test_a_message_to_someone_else_cannot_be_acknowledged_by_you(self):
        self.sw("--as", "ann", "send", "bob", "review please", "--kind", "review_request")
        with self.db() as con:
            mid = con.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        status, result = self.act({"action": "ack", "message": mid})
        self.assertFalse(result["ok"])
        bob = [r for r in self.api(f"/api/message/{mid}")["recipients"] if r["agent"] == "bob"][0]
        self.assertIsNone(bob["acked_at"])

    def test_reading_a_message_records_the_observation_without_acknowledging_it(self):
        self.sw("--as", "ann", "send", "human", "Please look at the readiness test", "--kind", "review_request")
        with self.db() as con:
            mid = con.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        self.ok({"action": "read", "message": mid})
        detail = self.api(f"/api/message/{mid}")
        human = [r for r in detail["recipients"] if r["agent"] == "human"][0]
        self.assertIsNotNone(human["read_at"])
        self.assertIsNone(human["acked_at"])
        self.assertEqual(detail["message"]["ack_state"], "pending")
        self.assertEqual(self.api("/api/inbox")["tabs"]["unread"], 0)
        self.sw("--as", "ann", "send", "bob", "Peer only", "--kind", "status")
        with self.db() as con:
            other = con.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        status, result = self.act({"action": "read", "message": other})
        self.assertEqual(status, 200)
        self.assertFalse(result["ok"], "the human cannot observe a message addressed to someone else")

    def test_approve_an_architecture_brief(self):
        self.sw("goal", "new", "health", "Ship a health endpoint")
        self.architecture("health", approve=False)
        self.assertEqual([a["goal"] for a in self.api("/api/decisions")["approvals"]], ["health"])
        self.ok({"action": "approve", "goal": "health"})
        self.assertEqual(self.api("/api/decisions")["approvals"], [])

    def test_the_next_review_task_is_numbered_after_existing_ones(self):
        self.assertEqual(swarm_web.next_review_task(self.entry), "INBOX-1")
        self.sw("add", "INBOX-4", "an older review")
        self.assertEqual(swarm_web.next_review_task(self.entry), "INBOX-5")


class Steward(ActionCase):
    def age_messages(self, minutes=20):
        old = (datetime.now(UTC) - timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
        with self.db() as con:
            con.execute("UPDATE messages SET created_at=?", (old,))
            con.commit()

    def steward(self):
        with self.board() as sw:
            return swarm_web.steward_pass(sw, remind_after_min=10)

    def test_it_reminds_once_and_never_acknowledges_for_anyone(self):
        self.sw("--as", "ann", "send", "bob", "please review T1", "--kind", "review_request")
        self.age_messages()
        self.assertEqual(self.steward()["reminded"], ["bob"])
        with self.db() as con:
            reminder = con.execute("SELECT * FROM messages WHERE sender='steward'").fetchone()
            original = con.execute("SELECT r.acked_at FROM messages m JOIN message_recipients r ON r.msg=m.id WHERE m.sender='ann'").fetchone()
        self.assertEqual(reminder["recipient"], "bob")
        self.assertIsNotNone(reminder["expires_at"], "a reminder expires instead of piling up")
        self.assertIn("Nobody else can acknowledge", reminder["body"])
        self.assertIsNone(original["acked_at"], "the steward never acknowledges")
        self.assertEqual(self.steward()["reminded"], [], "one reminder per waiting batch")

    def test_fresh_messages_and_the_humans_own_inbox_are_left_alone(self):
        self.sw("--as", "ann", "send", "bob", "just sent", "--kind", "status")
        self.sw("--as", "ann", "send", "human", "for you", "--kind", "decision")
        self.assertEqual(self.steward(), {"reminded": [], "escalated": [], "dead_letters": 0})

    def test_an_offline_recipient_is_escalated_to_the_coordinator(self):
        self.sw("--as", "ann", "send", "bob", "please review T1", "--kind", "review_request")
        self.age_messages()
        with self.db() as con:
            con.execute("UPDATE agents SET state='offline', offline_reason='silent' WHERE name='bob'")
            con.commit()
        self.assertEqual(self.steward()["escalated"], ["bob"])
        with self.db() as con:
            warning = con.execute("SELECT * FROM messages WHERE sender='steward'").fetchone()
        self.assertEqual(warning["recipient"], "ann")
        self.assertEqual(warning["kind"], "warning")

    def test_the_team_canvas_shows_the_steward_and_who_it_reminded(self):
        node = [n for n in self.api("/api/team")["nodes"] if n["id"] == "steward"][0]
        self.assertEqual((node["role"], node["lane"], node["status"]["label"]), ("Steward", 1, "Not started"))
        self.sw("--as", "ann", "send", "bob", "please review T1", "--kind", "review_request")
        self.age_messages()
        self.ok({"action": "steward"})
        team = self.api("/api/team")
        node = [n for n in team["nodes"] if n["id"] == "steward"][0]
        self.assertEqual(node["status"]["label"], "Active")
        self.assertIn(("steward", "steward", "bob"), {(e["kind"], e["from"], e["to"]) for e in team["edges"]})
        self.assertEqual(self.api("/api/overview")["directory"]["steward"]["display"], "Inbox steward")

    def test_the_steward_command_runs_once_and_reports(self):
        done = subprocess.run([sys.executable, str(fixtures.SWARM), "steward", "--once"], cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("reminded nobody", done.stdout)
        refused = subprocess.run([sys.executable, str(fixtures.SWARM), "steward", "--interval", "1"], cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(core.HUMAN, "human")
