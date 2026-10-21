"""Plan limits that recovery cannot trip over, and that cannot be dodged."""

from __future__ import annotations

import json
from pathlib import Path

from test_hardening import HardeningCase
import test_swarm as fixtures


class RetainedStepsAndTheCap(HardeningCase):
    def claim_with_done_steps(self, done: int):
        self.join("ann")
        self.sw("claim", "T1", "--as", "ann")
        with self.board() as sw, sw.tx():
            steps = [{"text": f"retained step number {i}", "done": True, "evidence": "x"} for i in range(done)]
            sw.update_task("T1", steps=json.dumps(steps), step_idx=done)
        return Path(self.task("T1")["worktree"])

    def plan(self, wt, steps: int, ok=True):
        args = fixtures.PLAN[: fixtures.PLAN.index("--step")]  # the answers only; steps are given below
        step_args = [x for i in range(steps) for x in ("--step", f"a concrete new step {i} on the fixture")]
        return self.sw("--as", "ann", "plan", *args, *step_args, cwd=wt, ok=ok)

    def test_ec375_done_steps_do_not_count_toward_the_cap(self):
        wt = self.claim_with_done_steps(15)
        self.plan(wt, 3)
        steps = json.loads(self.task("T1")["steps"])
        self.assertEqual(len(steps), 18)
        self.assertEqual(sum(1 for s in steps if s["done"]), 15)

    def test_ec375_new_steps_are_still_capped(self):
        wt = self.claim_with_done_steps(2)
        self.assertIn("At most 15 open steps", self.plan(wt, 16, ok=False))

    def age_deliberation(self, deliberation_min_ago: float, heartbeat_min_ago: float):
        from datetime import timedelta

        from test_hardening import core

        with self.board() as sw, sw.tx():
            c = core.current_contract(sw, "T1")
            sw.db.execute(
                "UPDATE task_contracts SET deliberation_at=?, active_since=NULL, active_seconds=0, blocked_at=NULL WHERE id=?",
                (core.iso(core.utcnow() - timedelta(minutes=deliberation_min_ago)), c["id"]),
            )
            sw.update_agent("ann", heartbeat_at=core.iso(core.utcnow() - timedelta(minutes=heartbeat_min_ago)))

    def contract_row(self):
        from test_hardening import core

        with self.board() as sw:
            return dict(core.current_contract(sw, "T1"))

    def test_ec376_a_live_owner_gets_one_audited_deliberation_extension(self):
        self.join("ann")
        self.sw("claim", "T1", "--as", "ann")
        self.age_deliberation(6, 2)  # past debate_min (5); the owner was heard from after deliberation began
        self.sw("status")
        c = self.contract_row()
        self.assertEqual(c["state"], "active")
        self.assertEqual(json.loads(c["terms"])["debate_min"], 10)
        with self.board() as sw:
            self.assertEqual(sw.db.execute("SELECT COUNT(*) FROM events WHERE kind='deliberation_extended'").fetchone()[0], 1)
        self.age_deliberation(11, 1)  # only once: past the doubled window it expires
        self.sw("status")
        self.assertEqual(self.contract_row()["state"], "expired")

    def test_ec376_a_silent_owner_gets_no_extension(self):
        self.join("ann")
        self.sw("claim", "T1", "--as", "ann")
        self.age_deliberation(6, 7)  # last heard from before deliberation began
        self.sw("status")
        self.assertEqual(self.contract_row()["state"], "expired")

    def test_ec375_an_absolute_ceiling_stops_the_cap_being_dodged(self):
        wt = self.claim_with_done_steps(25)
        self.assertIn("At most 30 steps in total", self.plan(wt, 6, ok=False))
        self.plan(wt, 5)
