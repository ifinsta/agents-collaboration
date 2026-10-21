"""Liveness under contention: identified commands keep an agent live, and recovery keeps its work."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import test_swarm as fixtures
from test_hardening import HardeningCase, core


class LivenessCase(HardeningCase):
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


class IdentifiedCommandsHeartbeat(LivenessCase):
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


class RejoinAndTheCoordinatorRole(LivenessCase):
    def started(self):
        self.join("ann")
        self.sw("claim", "T1", "--as", "ann")
        wt = Path(self.task("T1")["worktree"])
        self.sw("plan", "--as", "ann", *fixtures.PLAN, cwd=wt)
        self.sw("start", "--as", "ann", cwd=wt)
        return wt

    def go_offline(self, name):
        self.set_heartbeat(name, 25)
        self.sw("status")
        self.assertEqual(self.row("agents", "name=?", (name,))["state"], "offline")

    def rejoin(self, name):
        return self.sw("--as", name, "join", "--kind", "claude", "--resume")

    def events(self, kind):
        with self.board() as sw:
            return sw.db.execute("SELECT * FROM events WHERE kind=?", (kind,)).fetchall()

    def coordinator(self):
        with self.board() as sw:
            return sw.meta("coordinator")

    def test_ec380_a_clean_rejoin_keeps_the_task_state(self):
        self.started()
        self.go_offline("ann")
        self.rejoin("ann")
        self.assertEqual(self.task("T1")["state"], "in_progress")
        self.assertEqual(len(self.events("task_state_restored")), 1)

    def test_ec380_a_moved_worktree_head_means_replanning(self):
        wt = self.started()
        self.go_offline("ann")
        (wt / "src").mkdir(exist_ok=True)
        (wt / "src" / "late.txt").write_text("written while the board thought ann was gone\n", encoding="utf-8")
        self.git("add", "src/late.txt", cwd=wt)
        self.git("commit", "-qm", "late work", cwd=wt)
        self.rejoin("ann")
        self.assertEqual(self.task("T1")["state"], "planning")
        self.assertFalse(self.events("task_state_restored"))

    def test_ec380_a_new_interrupt_means_replanning(self):
        self.started()
        self.go_offline("ann")
        with self.board() as sw, sw.tx():
            sw.db.execute(
                "INSERT INTO interrupts(target,requester,task,epoch,mode,reason,state,requested_at) "
                "VALUES('ann','human','T1',?,'pause','stop and report','requested',?)",
                (self.task("T1")["epoch"], core.iso()),
            )
        self.rejoin("ann")
        self.assertEqual(self.task("T1")["state"], "planning")

    def test_ec380_past_the_reclaim_window_there_is_no_restore(self):
        self.started()
        self.go_offline("ann")
        with self.board() as sw, sw.tx():
            sw.update_agent("ann", offline_at=core.iso(core.utcnow() - timedelta(minutes=121)))
        self.rejoin("ann")
        self.assertNotEqual(self.task("T1")["state"], "in_progress")
        self.assertFalse(self.events("task_state_restored"))

    def coordinator_moves(self):
        self.join("ann")
        self.join("bob")
        self.assertEqual(self.coordinator(), "ann")
        self.go_offline("ann")
        self.assertEqual(self.coordinator(), "bob")

    def test_ec381_a_prompt_return_to_a_quiet_board_takes_the_role_back(self):
        self.coordinator_moves()
        self.rejoin("ann")
        self.assertEqual(self.coordinator(), "ann")
        self.assertTrue(any("returned" in e["detail"] for e in self.events("coordinator")))

    def test_ec381_no_return_while_a_merge_holds_the_queue_and_it_is_decided_once(self):
        self.coordinator_moves()
        with self.board() as sw, sw.tx():
            sw.set_meta("merge_lock", json.dumps({"agent": "bob", "task": "T2", "at": core.iso()}))
        self.rejoin("ann")
        self.assertEqual(self.coordinator(), "bob")
        self.assertEqual(len(self.events("coordinator_return_refused")), 1)
        with self.board() as sw, sw.tx():
            sw.set_meta("merge_lock", None)
        self.sw("status", "--as", "ann")
        self.assertEqual(self.coordinator(), "bob", "never flipped later by a sweep")
        self.assertIn("Only", self.sw("coordinator", "hand-over", "--to", "ann", "--as", "ann", ok=False))
        self.sw("coordinator", "hand-over", "--to", "ann", "--as", "bob")
        self.assertEqual(self.coordinator(), "ann")

    def test_ec381_no_return_after_the_window(self):
        self.coordinator_moves()
        with self.board() as sw, sw.tx():
            away = json.loads(sw.meta("coordinator_away"))
            away["at"] = core.iso(core.utcnow() - timedelta(minutes=31))
            sw.set_meta("coordinator_away", json.dumps(away))
        self.rejoin("ann")
        self.assertEqual(self.coordinator(), "bob")

    def test_ec381_promotion_skips_a_reviewer(self):
        self.join("ann")
        self.join("bob")
        self.join("cat")
        with self.board() as sw, sw.tx():
            sw.update_agent("bob", reviewing=1)
        self.go_offline("ann")
        self.assertEqual(self.coordinator(), "cat")

    def test_ec381_the_human_may_hand_the_role_over(self):
        self.join("ann")
        self.join("bob")
        self.sw("coordinator", "hand-over", "--to", "bob")
        self.assertEqual(self.coordinator(), "bob")
        self.assertIn("not a live agent", self.sw("coordinator", "hand-over", "--to", "zed", ok=False))
