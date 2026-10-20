"""Real Git filters exercise the writer inside worktree creation, not a mock boundary."""

from __future__ import annotations

import shlex
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

from test_hardening import HardeningCase, core, fixtures


class GitAllocation(HardeningCase):
    def setUp(self):
        super().setUp()
        self.join("ann")
        self.join("bob")
        self.ready, self.release_filter = (Path(self.tmp.name) / name for name in ("filter-ready", "filter-release"))
        script = Path(self.tmp.name) / "smudge.py"
        script.write_text(
            "import os,sys,time\nfrom pathlib import Path\n"
            "ready,release=map(Path,sys.argv[1:])\ndata=sys.stdin.buffer.read()\n"
            "ready.write_text(str(os.getpid()),encoding='utf-8')\n"
            "limit=time.monotonic()+40\n"
            "while not release.exists() and time.monotonic()<limit: time.sleep(0.02)\n"
            "sys.stdout.buffer.write(data)\nsys.stdout.buffer.flush()\n", encoding="utf-8"
        )
        (self.root / "src").mkdir(exist_ok=True)
        (self.root / "src/slow.txt").write_text("original content\n", encoding="utf-8")
        (self.root / ".gitattributes").write_text("src/slow.txt filter=delayed\n", encoding="utf-8")
        self.git("add", "src", ".gitattributes")
        self.git("commit", "-qm", "controlled real Git filter")
        command = shlex.join([sys.executable.replace("\\", "/"), script.as_posix(), self.ready.as_posix(), self.release_filter.as_posix()])
        self.git("config", "filter.delayed.smudge", command)
        self.git("config", "filter.delayed.required", "true")

    def wait_for(self, predicate, timeout=20):
        limit = time.monotonic() + timeout
        while not predicate() and time.monotonic() < limit:
            time.sleep(0.02)
        self.assertTrue(predicate())

    def run_checkout(self, *, kill):
        log = Path(self.tmp.name) / "claim.log"
        with log.open("wb") as output:
            caller = subprocess.Popen([sys.executable, str(fixtures.SWARM), "claim", "T1", "--as", "ann"],
                                      cwd=self.root, stdout=output, stderr=subprocess.STDOUT)
            try:
                self.wait_for(self.ready.exists)
                with self.board() as sw:
                    row = dict(core.pending_allocation(sw, "T1"))
                self.assertEqual(row["state"], "running")
                self.assertIn("may still write", self.sw("plan", "--as", "ann", *fixtures.PLAN, ok=False))
                self.assertIn("may still write", self.sw("checkpoint", "--as", "ann", "--note", "Retain pending allocation", "--next", "Confirm all Git writers stopped", ok=False))
                if kill:
                    caller.kill()  # This fixture's actual Popen, never a stored PID.
                    caller.wait(timeout=10)
                self.sw("release", "--task", "T1", "Preserve checkout until every Git writer has stopped.")
                refused = self.json_command("claim", "T1", "--as", "bob", "--json", ok=False)
                self.assertIn("allocation", refused["error"]["message"])
                self.assertIsNone(self.task("T1")["assignee"])
                self.assertIn("Only a human", self.sw("allocation", "reconcile", "T1", "--as", "bob", "--confirm-stopped", "--reason", "Agent cannot attest cessation", ok=False))
                if kill:
                    pid = int(self.ready.read_text(encoding="utf-8"))
                    self.wait_for(lambda: not core.pid_alive(pid))
                    self.sw("status")
                    self.assertIn("may still write", self.sw("claim", "T1", "--as", "bob", ok=False))
                    result = self.json_command("allocation", "reconcile", "T1", "--confirm-stopped", "--reason", "Actual caller exited and its filter process was independently observed stopped", "--json")
                    self.assertEqual(result["result"]["allocations"][-1]["state"], "reconciled")
                    self.assertIn("Human attestation", result["result"]["allocations"][-1]["detail"])
                else:
                    self.release_filter.touch()
                    caller.wait(timeout=20)
                    self.assertNotEqual(caller.returncode, 0)  # Its original lease was released.
                    self.sw("claim", "T1", "--as", "bob")
                    tree = Path(self.task("T1")["worktree"])
                    edited = tree / "src/slow.txt"
                    edited.write_text("successor work must survive\n", encoding="utf-8")
                    self.sw("status")
                    self.assertEqual(edited.read_text(encoding="utf-8"), "successor work must survive\n")
                    with self.board() as sw:
                        self.assertIsNone(core.pending_allocation(sw, "T1"))
                        self.assertEqual(sw.db.execute("SELECT state FROM allocations WHERE id=?", (row["id"],)).fetchone()[0], "quiescent")
            finally:
                self.release_filter.touch()
                if caller.poll() is None:
                    caller.kill()
                caller.wait(timeout=10)

    def test_ec319_live_git_writer_blocks_replacement_until_observed_quiescence(self):
        self.run_checkout(kill=False)

    def test_ec319_caller_os_kill_contains_git_and_retains_uncertainty_until_human_attestation(self):
        self.run_checkout(kill=True)

    def test_ec320_migration_rollback_retains_legacy_board_and_retries_without_fabricated_proof(self):
        # An older schema has no allocation receipts; migration must not invent any.
        with self.board() as sw:
            sw.db.execute("DROP TABLE allocations")
            sw.set_meta("schema_version", "9")
        def fail(name):
            if name == "during_migration":
                raise core.SwarmError("controlled migration interruption")
        with mock.patch.object(core, "failpoint", side_effect=fail):
            with self.assertRaisesRegex(core.SwarmError, "controlled migration"):
                core.Swarm(self.root)
        db = self.db()
        try:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='allocations'").fetchone())
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "9")
        finally:
            db.close()
        with self.board() as sw:
            self.assertEqual(sw.meta("schema_version"), str(core.SCHEMA_VERSION))
            self.assertEqual(sw.db.execute("SELECT count(*) FROM allocations").fetchone()[0], 0)
        self.release_filter.touch()
        self.sw("claim", "T1", "--as", "ann")
        status = self.json_command("status", "--json")
        self.assertEqual(status["result"]["allocations"][-1]["state"], "quiescent")
