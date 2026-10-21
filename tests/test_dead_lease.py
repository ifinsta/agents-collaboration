"""A merge whose process is proven gone frees the queue; nothing short of proof does."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from unittest import mock

from test_hardening import HardeningCase, core


def dead_identity():
    """The identity of a process that has really exited on this host."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    ident = core.process_identity(proc.pid)
    proc.kill()
    proc.wait()
    return ident


class DeadMergeLease(HardeningCase):
    def lease(self, proc, groups=()):
        with self.board() as sw, sw.tx():
            sw.set_meta(
                "merge_lock",
                json.dumps({"agent": "ann", "task": "T1", "at": core.iso(), "attempt": "a" * 16, "proc": proc, "groups": list(groups)}),
            )

    def lock(self):
        with self.board() as sw:
            return sw.meta("merge_lock")

    def test_ec382_a_lease_whose_process_exited_is_broken(self):
        self.join("ann")
        self.lease(dead_identity())
        self.sw("status", "--as", "ann")
        self.assertIsNone(self.lock())
        with self.board() as sw:
            detail = sw.db.execute("SELECT detail FROM events WHERE kind='merge_lock_broken'").fetchone()[0]
        self.assertIn("proven", detail)

    def test_ec382_a_live_merge_is_not_broken(self):
        self.join("ann")
        self.lease(core.process_identity(core.os.getpid()))
        self.sw("status", "--as", "ann")
        self.assertIsNotNone(self.lock())

    def test_ec382_a_live_owned_group_keeps_the_lease(self):
        self.join("ann")
        self.lease(dead_identity(), groups=[core.process_identity(core.os.getpid())])
        self.sw("status", "--as", "ann")
        self.assertIsNotNone(self.lock())

    def test_ec382_only_proof_counts(self):
        me = core.process_identity(core.os.getpid())
        self.assertFalse(core.proven_gone(me))
        self.assertTrue(core.proven_gone({**me, "start": "1"}), "a different process under the same pid")
        self.assertFalse(core.proven_gone({**dead_identity(), "ns": "another-host/boot"}), "another namespace")
        with mock.patch.object(core, "process_start", return_value=None):  # access denied or unknown
            self.assertFalse(core.proven_gone({**me, "start": "1"}))
        self.assertFalse(core.proven_gone({**me, "start": None}), "an unknown start time proves nothing")

    def test_ec383_a_tool_run_whose_supervisor_is_gone_is_settled_by_the_engine(self):
        self.join("ann")
        with self.board() as sw, sw.tx():
            sw.db.execute(
                "INSERT INTO usage_runs(id,task,owner,kind,state,reserved_tokens,reserved_micros,reserved_seconds,created_at,heartbeat_at,supervisor_pid) "
                "VALUES('run1','T1','ann','tool','unknown',0,0,60,?,?,1)",
                (core.iso(), core.iso()),
            )
            sw.set_meta("usage_supervisor:run1", json.dumps(dead_identity()))
        self.sw("status", "--as", "ann")
        row = self.row_of("SELECT state, detail FROM usage_runs WHERE id='run1'")
        self.assertEqual(row[0], "charged")
        self.assertIn("engine-verified: supervisor gone", row[1])

    def test_ec383_a_run_with_a_token_reservation_still_needs_the_human(self):
        self.join("ann")
        with self.board() as sw, sw.tx():
            sw.db.execute(
                "INSERT INTO usage_runs(id,task,owner,kind,state,reserved_tokens,reserved_micros,reserved_seconds,created_at,heartbeat_at,supervisor_pid) "
                "VALUES('run2','T1','ann','tool','unknown',500,0,60,?,?,1)",
                (core.iso(), core.iso()),
            )
            sw.set_meta("usage_supervisor:run2", json.dumps(dead_identity()))
        self.sw("status", "--as", "ann")
        self.assertEqual(self.row_of("SELECT state FROM usage_runs WHERE id='run2'")[0], "unknown")

    def row_of(self, sql):
        with self.board() as sw:
            return sw.db.execute(sql).fetchone()

    def test_ec384_merge_detach_runs_in_the_background_and_lands(self):
        self.join("ann")
        self.to_ready("ann", "T1")
        out = self.sw("merge", "--detach", "--as", "ann")
        self.assertIn("runs in the background", out)
        attempt = out.split("merge attempt ", 1)[1].split()[0]
        deadline = time.monotonic() + 120
        while self.task("T1")["state"] != "done" and time.monotonic() < deadline:
            time.sleep(1)
        self.assertEqual(self.task("T1")["state"], "done")
        with self.board() as sw:
            started = sw.db.execute("SELECT detail FROM events WHERE kind='merge_started'").fetchone()[0]
        self.assertIn(attempt, started)
