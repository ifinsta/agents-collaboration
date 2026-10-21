"""Dead-hand authority: off unless the human arms it, then two independent signatures, exact and single-use."""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from datetime import timedelta
from unittest import mock

from test_hardening import core
from test_oversight import OversightCase

import swarm_deadhand as deadhand

TOKENS = {name: "hwt_" + f"{i:x}" * 32 for i, name in enumerate(("ann", "bob", "cat", "dan", "eve"), start=1)}
REASON = "The frozen review found nothing and the human is away for the day"


class DeadHand(OversightCase):
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
        self.git("commit", "-qm", "configure dead hand")

    def give_tokens(self):
        with self.board() as sw, sw.tx():
            for name, token in TOKENS.items():
                if sw.agent(name):
                    sw.set_meta(f"agent_token:{name}", json.dumps({"hash": deadhand.token_hash(token), "proven": True}))

    def as_(self, name, *args, ok=True):
        return self.sw(*args, "--as", name, env={**os.environ, "SWARM_TOKEN": TOKENS[name]}, ok=ok)

    def waiting_incident(self):
        """An incident whose review is in and whose decision window elapsed, so it needs the human."""
        self.setup_incident()
        self.report()
        self.join("dan")
        self.join("eve")
        self.give_tokens()
        with self.board() as sw, sw.tx():
            sw.db.execute("UPDATE incidents SET state='needs_human' WHERE id=1")
        out = self.as_("ann", "incident", "resolve", "1", "--outcome", "cleared", "--reason", REASON, ok=False)
        self.assertIn("ask the human", out)

    def age_waiting(self, minutes=31):
        with self.board() as sw, sw.tx():
            key = "human_waiting:incident.resolve:1"
            item = json.loads(sw.meta(key))
            item["since"] = core.iso(core.utcnow() - timedelta(minutes=minutes))
            sw.set_meta(key, json.dumps(item))

    def arm(self, hours=4, **kw):
        until = core.iso(core.utcnow() + timedelta(hours=hours))
        with self.board() as sw, mock.patch.object(deadhand, "person_at_terminal"):
            deadhand.cmd_arm(sw, argparse.Namespace(as_=None, until=until, allow=kw.get("allow", ""), deputies=kw.get("deputies", "")))

    def request(self, who="dan", ok=True, outcome="cleared"):
        return self.as_(
            who, "deadhand", "request", "incident.resolve", "1",
            "--arg", f"outcome={outcome}", "--arg", f"reason={REASON}",
            "--reason", "The human is away and the merge waits on this", ok=ok,
        )

    def ticket(self, ident=1):
        with self.board() as sw:
            return dict(sw.db.execute("SELECT * FROM deadhand_tickets WHERE id=?", (ident,)).fetchone())

    def signed(self):
        self.waiting_incident()
        self.age_waiting()
        self.arm()
        self.request()
        deputy = self.ticket()["deputy"]
        self.as_(deputy, "deadhand", "review", "D1", "--verdict", "approve", "--evidence", "Read the frozen brief and the diff hash")
        self.as_("ann", "deadhand", "approve", "D1", "--reason", "The deputy's evidence matches the frozen review")
        return deputy

    def test_ec385_two_independent_signatures_then_one_exact_use(self):
        deputy = self.signed()
        self.assertEqual(deputy, "eve", "the engine skips the coordinator, requester, owner, subject and reviewer")
        self.as_("ann", "incident", "resolve", "1", "--outcome", "cleared", "--reason", REASON, "--deadhand", "D1")
        r = self.row("incidents", "id=1")
        self.assertEqual(r["state"], "resolved")
        self.assertEqual(r["resolved_by"], "ann", "never attributed to the human")
        self.assertIn("dead-hand authority D1: reviewed by eve, approved by ann, armed by the human until", r["resolution"])
        self.assertEqual(self.ticket()["state"], "consumed")

    def test_ec386_refused_unarmed_early_by_the_coordinator_or_outside_the_allowlist(self):
        self.waiting_incident()
        self.assertIn("not armed", self.request(ok=False))
        self.arm()
        self.assertIn("must have waited", self.request(ok=False))
        self.age_waiting()
        self.assertIn("other than the coordinator", self.request(who="ann", ok=False))
        self.arm(allow="usage.reconcile")
        self.assertIn("not delegated", self.request(ok=False))

    def test_ec386_wrong_token_changed_arguments_and_reuse_are_refused(self):
        self.waiting_incident()
        self.age_waiting()
        self.arm()
        self.request()
        out = self.sw("deadhand", "review", "D1", "--verdict", "approve", "--evidence", "Read the frozen brief", "--as", "eve",
                      env={**os.environ, "SWARM_TOKEN": TOKENS["dan"]}, ok=False)
        self.assertIn("join token", out)
        self.as_("eve", "deadhand", "review", "D1", "--verdict", "approve", "--evidence", "Read the frozen brief and diff hash")
        self.assertIn("deputy, the requester", self.as_("dan", "deadhand", "approve", "D1", "--reason", "Looks fine to me too", ok=False)
                      .replace("needs a deputy's approval first, and only the coordinator approves it", "deputy, the requester"))
        self.as_("ann", "deadhand", "approve", "D1", "--reason", "The deputy's evidence matches the frozen review")
        out = self.as_("ann", "incident", "resolve", "1", "--outcome", "cleared", "--reason", REASON + " (edited)", "--deadhand", "D1", ok=False)
        self.assertIn("different arguments", out)
        self.as_("ann", "incident", "resolve", "1", "--outcome", "cleared", "--reason", REASON, "--deadhand", "D1")
        self.assertIn("consumed", self.as_("ann", "usage", "reconcile", "x", "--confirm-stopped", "--charge-reserved",
                                           "--reason", REASON, "--deadhand", "D1", ok=False) + self.ticket()["state"])

    def test_ec386_a_veto_a_disarm_and_a_config_edit_each_stop_a_ticket(self):
        self.signed()
        self.sw("deadhand", "veto", "D1", "--reason", "I am back and will decide this myself")
        out = self.as_("ann", "incident", "resolve", "1", "--outcome", "cleared", "--reason", REASON, "--deadhand", "D1", ok=False)
        self.assertIn("vetoed", out)
        self.arm()
        self.sw("deadhand", "disarm")
        self.assertIn("off", self.sw("deadhand", "status"))
        self.arm()
        self.config("[deadhand]\nwait_min = 45")
        self.assertIn("off", self.sw("deadhand", "status"))

    def test_ec387_a_tokenless_resume_voids_signatures_and_eligibility(self):
        self.waiting_incident()
        self.age_waiting()
        self.arm()
        self.request()
        with self.board() as sw, sw.tx():
            sw.update_agent("eve", state="offline", offline_at=core.iso())
        out = self.sw("join", "--as", "eve", "--kind", "claude", "--resume")
        self.assertIn("join token: hwt_", out)
        self.assertEqual(self.ticket()["state"], "void")
        with self.board() as sw:
            self.assertFalse(deadhand.proven(sw, "eve"))
        self.assertIn("verify-agent eve", self.sw("human", "pending"))

    def test_ec387_a_proven_resume_keeps_standing(self):
        self.join("ann")
        self.give_tokens()
        with self.board() as sw, sw.tx():
            sw.update_agent("ann", state="offline", offline_at=core.iso())
        out = self.sw("join", "--as", "ann", "--kind", "claude", "--resume", env={**os.environ, "SWARM_TOKEN": TOKENS["ann"]})
        self.assertNotIn("join token:", out)
        with self.board() as sw:
            self.assertTrue(deadhand.proven(sw, "ann"))

    def test_ec388_arming_needs_a_person_at_a_terminal(self):
        until = core.iso(core.utcnow() + timedelta(hours=2))
        piped = self.sw("deadhand", "arm", "--until", until, input_text=f"arm dead hand until {until}\n", ok=False)
        self.assertIn("person at a terminal", piped, "piping the phrase in is not a person")
        self.assertIn("at most 72 hours", self.sw("deadhand", "arm", "--until", core.iso(core.utcnow() + timedelta(hours=80)), ok=False))
        self.join("ann")
        self.assertIn("Only the human", self.sw("deadhand", "arm", "--until", until, "--as", "ann", ok=False))
        with mock.patch.dict(os.environ, {"MSYSTEM": ""}):
            self.assertFalse(deadhand.msys_pty())
        with mock.patch.object(deadhand.sys, "stdin") as stdin:
            stdin.isatty.return_value = True
            stdin.readline.return_value = "arm dead hand until X\n"
            deadhand.person_at_terminal("arm dead hand until X")
            stdin.readline.return_value = "something else\n"
            with self.assertRaises(core.SwarmError):
                deadhand.person_at_terminal("arm dead hand until X")

    def test_ec388_tokens_never_reach_gates_or_records(self):
        self.join("ann")
        token = "hwt_" + "a" * 32
        self.assertNotIn(token, core.redact_text(f"leaked {token} here"))
        with self.board() as sw, mock.patch.dict(os.environ, {"SWARM_TOKEN": token}):
            self.assertNotIn("SWARM_TOKEN", sw.env_for(sw.agent("ann"), None))
        self.assertIn("join token: hwt_", self.join("bob"))

    def test_ec390_inherited_children_and_verification_never_see_the_token(self):
        self.join("ann")
        token = "hwt_" + "b" * 32
        marker = "cafebabe00112233"
        with mock.patch.dict(os.environ, {"SWARM_TOKEN": token, "SWARM_MERGE_ATTEMPT": marker}):
            done = core.run(
                [
                    sys.executable,
                    "-c",
                    "import os; print(os.environ.get('SWARM_TOKEN')); print(os.environ.get('SWARM_MERGE_ATTEMPT'))",
                ]
            )
        self.assertNotIn(token, done.stdout)
        self.assertNotIn(marker, done.stdout)
        cfg = self.root / ".agents" / "swarm" / "config.toml"
        text = cfg.read_text(encoding="utf-8")
        old = next(line for line in text.splitlines() if line.startswith("commands = "))
        check = (
            "import os,sys; sys.exit(0 if 'SWARM_TOKEN' not in os.environ and "
            "'SWARM_MERGE_ATTEMPT' not in os.environ else 1)"
        )
        cfg.write_text(text.replace(old, "commands = " + json.dumps([[sys.executable, "-c", check]])), encoding="utf-8")
        self.git("commit", "-qam", "checks cannot read the join token")
        self.to_ready("ann", "T1")
        self.sw("merge", "--as", "ann")
        out = self.sw(
            "verify", "T1", "--as", "ann", env={**os.environ, "SWARM_TOKEN": token, "SWARM_MERGE_ATTEMPT": marker}
        )
        self.assertIn("verification", out)
        self.assertIn("passed", out)
