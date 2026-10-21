"""Liveness under contention: identified commands keep an agent live, and recovery keeps its work."""

from __future__ import annotations

from datetime import timedelta

from test_hardening import HardeningCase, core


class IdentifiedCommandsHeartbeat(HardeningCase):
    def row(self, table, where="1=1", args=()):
        with self.board() as sw:
            return sw.db.execute(f"SELECT * FROM {table} WHERE {where}", args).fetchone()

    def heartbeat(self, name):
        with self.board() as sw:
            return sw.agent(name)["heartbeat_at"]

    def set_heartbeat(self, name, minutes_ago, state=None):
        with self.board() as sw, sw.tx():
            fields = {"heartbeat_at": core.iso(core.utcnow() - timedelta(minutes=minutes_ago))}
            if state:
                fields["state"] = state
            sw.update_agent(name, **fields)

    def test_ec374_read_only_command_with_identity_keeps_an_agent_live(self):
        self.join("ann")
        self.set_heartbeat("ann", 19)  # agent_timeout_min is 20
        before = self.heartbeat("ann")
        self.sw("status", "--as", "ann")
        after = self.heartbeat("ann")
        self.assertGreater(after, before, "a read-only command with --as is a heartbeat")
        self.set_heartbeat("ann", 25)  # a later sweep must not see a stale heartbeat for this live agent
        self.sw("status", "--as", "ann")
        self.assertEqual(self.row("agents", "name='ann'")["state"], "offline", "past the timeout it is not revived")

    def test_ec374_identity_heartbeat_is_throttled_and_never_revives_offline_agents(self):
        self.join("ann")
        self.set_heartbeat("ann", 0)
        fresh = self.heartbeat("ann")
        self.sw("status", "--as", "ann")
        self.assertEqual(self.heartbeat("ann"), fresh, "written at most once per minute")
        self.join("bob")
        self.set_heartbeat("bob", 5, state="offline")
        stale = self.heartbeat("bob")
        self.sw("status", "--as", "bob")
        self.assertEqual(self.heartbeat("bob"), stale)
        self.assertEqual(self.row("agents", "name='bob'")["state"], "offline")

    def test_ec374_swarm_as_identity_counts_too(self):
        self.join("ann")
        self.set_heartbeat("ann", 10)
        before = self.heartbeat("ann")
        self.sw("status", env={"SWARM_AS": "ann"})
        self.assertGreater(self.heartbeat("ann"), before)
