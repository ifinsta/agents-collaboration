"""OS-kill claim/release boundaries and inspect both SQLite and physical Git work."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from test_hardening import HardeningCase, core, fixtures


PAUSING_CLI = r"""
import json,os,sys,time
from pathlib import Path
launcher,selected,marker,*command=sys.argv[1:]
sys.path.insert(0,str(Path(launcher).parent))
import swarm_core as core
def pause(name):
    if name==selected:
        Path(marker).write_text(json.dumps({'point':name,'pid':os.getpid()}),encoding='utf-8')
        while True:
            time.sleep(0.05)
core.failpoint=pause
sys.argv=[launcher,*command]
raise SystemExit(core.main())
"""


class ClaimCrashes(HardeningCase):
    def setUp(self):
        super().setUp()
        self.join("ann")
        self.join("bob")
        ignore = self.root / ".gitignore"
        ignore.write_text(ignore.read_text(encoding="utf-8") + ".local-settings\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.config('[worktree]\ncopy = [".local-settings"]')
        (self.root / ".local-settings").write_text("preserve local settings", encoding="utf-8")
        self.sw("contract", "offer", "T5", "ann", "--token-limit", "100", "--as", "human")
        self.sw("contract", "accept", "T5", "--as", "ann")
        self.target = self.git("rev-parse", "main").strip()
        with self.board() as board:
            self.path = board.worktree_path("T5")

    @contextmanager
    def paused(self, point, *command):
        marker = Path(self.tmp.name) / (point + ".json")
        log = Path(self.tmp.name) / (point + ".log")
        with log.open("wb") as output:
            proc = subprocess.Popen(
                [sys.executable, "-c", PAUSING_CLI, str(fixtures.SWARM), point, str(marker), *command],
                cwd=self.root,
                env={**os.environ, "SWARM_FAILPOINT": ""},
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 45
                ready = None
                while time.monotonic() < deadline:
                    if marker.exists():
                        try:
                            ready = json.loads(marker.read_text(encoding="utf-8"))
                        except json.JSONDecodeError:
                            pass
                        if ready:
                            break
                    if proc.poll() is not None:
                        self.fail(f"CLI exited before {point}: {log.read_text(encoding='utf-8', errors='replace')}")
                    time.sleep(0.02)
                self.assertEqual(ready, {"point": point, "pid": proc.pid}, log.read_text(encoding="utf-8", errors="replace"))
                self.assertIsNone(proc.poll())
                yield proc
            finally:
                if proc.poll() is None:
                    proc.kill()  # Actual Popen child owned by this fixture; never a stored registry PID.
                proc.wait(timeout=10)

    def kill(self, proc):
        proc.kill()
        code = proc.wait(timeout=10)
        self.assertNotEqual(code, 0)
        if os.name != "nt":
            self.assertEqual(code, -signal.SIGKILL)

    def kill_claim(self, point, *, takeover=False):
        args = ["claim", "T5", "--as", "bob" if takeover else "ann"]
        if takeover:
            args.append("--take-over")
        with self.paused(point, *args) as proc:
            self.kill(proc)

    def snapshot(self):
        with self.board() as board:
            return {
                "task": dict(board.task("T5")),
                "agents": {name: dict(board.agent(name)) for name in ("ann", "bob")},
                "contracts": [dict(row) for row in board.db.execute("SELECT * FROM task_contracts WHERE task='T5' ORDER BY id")],
                "usage": [dict(row) for row in board.db.execute("SELECT * FROM usage_runs WHERE task='T5' ORDER BY id")],
                "locks": [tuple(row) for row in board.db.execute("SELECT name,task,agent FROM locks WHERE task='T5'")],
                "claims": board.db.execute("SELECT count(*) FROM events WHERE kind='claimed' AND task='T5'").fetchone()[0],
                "releases": board.db.execute("SELECT count(*) FROM events WHERE kind='released' AND task='T5'").fetchone()[0],
            }

    def assert_restart_preserves(self):
        before = self.snapshot()
        self.sw("status")
        self.sw("status")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git("rev-parse", "main").strip(), self.target)
        self.assertNotEqual(before["task"]["state"], "done")
        return before

    def assert_owned(self, *, owner="ann", worktree=False, published=False):
        snapshot = self.assert_restart_preserves()
        task = snapshot["task"]
        self.assertEqual((task["state"], task["assignee"]), ("claimed", owner))
        self.assertEqual(task["worktree"], str(self.path))
        self.assertEqual(snapshot["agents"][owner]["task"], "T5")
        self.assertEqual(snapshot["agents"][owner]["state"], "busy")
        self.assertEqual(snapshot["locks"], [("config", "T5", owner)])
        contract = snapshot["contracts"][-1]
        self.assertEqual((contract["state"], contract["owner"], contract["epoch"]), ("active", owner, task["epoch"]))
        self.assertEqual(task["base_sha"], self.target if published else None)
        self.assertEqual(self.path.is_dir(), worktree)
        if worktree:
            self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.path).strip(), self.target)
            self.assertIn(str(self.path).replace("\\", "/"), self.git("worktree", "list", "--porcelain").replace("\\", "/"))
        else:
            self.assertEqual(self.git("branch", "--list", "swarm/T5").strip(), "")
        return snapshot

    def reassign(self):
        task = self.task("T5")
        with self.board() as board:
            contract = board.db.execute("SELECT * FROM task_contracts WHERE task='T5' ORDER BY id DESC LIMIT 1").fetchone()
        if not task["assignee"] and contract["state"] == "accepted":
            self.sw("claim", "T5", "--as", contract["owner"])
            task = self.task("T5")
        if task["assignee"]:
            self.sw("release", "--task", "T5", "Preserve the crashed assignment's artifacts for a bounded successor.")
        self.sw("contract", "offer", "T5", "bob", "--token-limit", "100", "--as", "human")
        self.sw("contract", "accept", "T5", "--as", "bob")
        self.sw("claim", "T5", "--as", "bob")
        self.assertEqual(self.task("T5")["assignee"], "bob")
        self.assertEqual(self.git("rev-parse", "main").strip(), self.target)

    def test_ec310_kill_before_claim_commit_rolls_back_owner_contract_locks_and_event(self):
        before = self.snapshot()
        self.kill_claim("before_claim_commit")
        self.assertEqual(self.assert_restart_preserves(), before)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.git("branch", "--list", "swarm/T5").strip(), "")
        self.reassign()

    def test_ec310_kill_after_claim_commit_retains_a_planned_path_without_inventing_setup(self):
        self.kill_claim("after_claim_commit")
        snapshot = self.assert_owned()
        self.assertEqual(snapshot["claims"], 1)
        self.reassign()

    def test_ec311_kill_before_git_creation_preserves_the_committed_claim(self):
        self.kill_claim("before_worktree_create")
        self.assert_owned()
        self.reassign()

    def test_ec311_kill_after_git_creation_preserves_registered_work_without_setup_proof(self):
        self.kill_claim("after_worktree_create")
        self.assert_owned(worktree=True)
        self.assertFalse((self.path / ".local-settings").exists())
        (self.path / "retained-work.txt").write_text("retain this orphaned setup work", encoding="utf-8")
        self.reassign()
        self.assertTrue((self.path / "retained-work.txt").is_file())

    def test_ec312_kill_before_setup_commit_keeps_physical_copies_and_the_original_claim(self):
        self.kill_claim("before_claim_setup_commit")
        self.assert_owned(worktree=True)
        self.assertEqual((self.path / ".local-settings").read_text(encoding="utf-8"), "preserve local settings")
        self.reassign()
        self.assertTrue((self.path / ".local-settings").is_file())

    def test_ec312_kill_after_setup_commit_retains_published_base_and_copies(self):
        self.kill_claim("after_claim_setup_commit")
        self.assert_owned(worktree=True, published=True)
        self.assertTrue((self.path / ".local-settings").is_file())
        self.reassign()

    def orphan(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.DEVNULL)
        try:
            self.sw("join", "--as", "ann", "--kind", "fake", "--resume", "--pid", str(proc.pid))
            self.sw("claim", "T5", "--as", "ann")
            (self.path / "retained-work.txt").write_text("preserve previous owner work", encoding="utf-8")
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
        self.sw("status")
        self.assertEqual(self.task("T5")["state"], "orphaned")
        return self.snapshot()

    def takeover_boundary(self, point, *, committed):
        before = self.orphan()
        self.kill_claim(point, takeover=True)
        after = self.assert_restart_preserves()
        if committed:
            self.assertEqual(after["task"]["epoch"], before["task"]["epoch"] + 1)
            self.assertEqual(after["task"]["assignee"], "bob")
            self.assertIsNone(after["agents"]["ann"]["task"])
            self.assertEqual(after["agents"]["bob"]["task"], "T5")
            self.assertEqual(after["locks"], [("config", "T5", "bob")])
            self.assertEqual([c["state"] for c in after["contracts"]], ["closed", "active"])
            self.assertEqual(after["contracts"][-1]["owner"], "bob")
            self.assertEqual(after["claims"], 2)
            self.assertEqual(json.loads(after["contracts"][-1]["terms"])["budget"], json.loads(before["contracts"][-1]["terms"])["budget"])
        else:
            self.assertEqual(after, before)
            self.sw("claim", "T5", "--as", "bob", "--take-over")
        self.assertEqual((self.path / "retained-work.txt").read_text(encoding="utf-8"), "preserve previous owner work")
        self.assertTrue((self.path / ".local-settings").is_file())

    def test_ec313_takeover_kill_before_ownership_commit_preserves_the_previous_owner(self):
        self.takeover_boundary("before_claim_commit", committed=False)

    def test_ec313_takeover_kill_after_ownership_commit_retains_one_new_epoch_and_contract(self):
        self.takeover_boundary("after_claim_commit", committed=True)

    def test_ec313_takeover_kill_before_setup_commit_preserves_committed_transfer_and_work(self):
        self.takeover_boundary("before_claim_setup_commit", committed=True)

    def test_ec313_takeover_kill_after_setup_commit_retains_the_published_transfer(self):
        self.takeover_boundary("after_claim_setup_commit", committed=True)

    def release_boundary(self, point, *, committed, concurrent=False):
        self.sw("claim", "T5", "--as", "ann")
        window = self.json_command(
            "usage", "reserve", "T5", "--as", "ann", "--key", "release-fixture", "--tokens", "1", "--json"
        )["result"]["run"]["id"]
        self.sw("plan", "--as", "ann", *fixtures.PLAN, cwd=self.path)
        self.sw("start", "--as", "ann", cwd=self.path)
        report = Path(self.tmp.name) / "fixture-usage.json"
        report.write_text(json.dumps({"tokens": 0}), encoding="utf-8")  # This local fixture made no provider calls.
        self.sw("usage", "report", window, "--as", "ann", "--source", str(report))
        with self.board() as board, board.tx():
            contract = core.current_contract(board, "T5")
            self.assertIsNotNone(contract["active_since"])
            board.db.execute(
                "UPDATE task_contracts SET active_since=? WHERE id=?",
                (core.iso(core.utcnow() - timedelta(seconds=60)), contract["id"]),
            )
        (self.path / "retained-work.txt").write_text("keep release work", encoding="utf-8")
        before = self.snapshot()
        with self.paused(point, "release", "--as", "ann", "Preserve these retained edits for the successor assignment.") as proc:
            if concurrent:
                self.reassign()
                replacement = self.snapshot()
            self.kill(proc)
        after = self.assert_restart_preserves()
        self.assertEqual(after["usage"], before["usage"])
        if concurrent:
            self.assertEqual(after, replacement)
            self.assertEqual(after["task"]["assignee"], "bob")
        elif committed:
            self.assertEqual((after["task"]["state"], after["task"]["assignee"]), ("open", None))
            self.assertEqual(after["task"]["epoch"], before["task"]["epoch"] + 1)
            self.assertEqual(after["locks"], [])
            self.assertEqual(after["contracts"][-1]["state"], "closed")
            self.assertIsNone(after["contracts"][-1]["active_since"])
            self.assertGreaterEqual(after["contracts"][-1]["active_seconds"], 60)
            self.assertEqual(after["agents"]["ann"]["state"], "ready")
            self.assertIsNone(after["agents"]["ann"]["task"])
            self.assertEqual(after["releases"], before["releases"] + 1)
            self.assertEqual(after["task"]["branch"], before["task"]["branch"])
            self.assertEqual(after["task"]["worktree"], before["task"]["worktree"])
        else:
            self.assertEqual(after, before)
        self.assertEqual((self.path / "retained-work.txt").read_text(encoding="utf-8"), "keep release work")

    def test_ec314_release_kill_before_commit_retains_the_held_assignment(self):
        self.release_boundary("before_release_commit", committed=False)

    def test_ec314_release_kill_after_commit_retains_one_release_and_all_work(self):
        self.release_boundary("after_release_commit", committed=True)

    def test_ec315_old_release_killed_after_reclaim_cannot_mutate_the_successor(self):
        self.release_boundary("after_release_commit", committed=True, concurrent=True)

    def failed_allocation(self, point, *, committed):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("preserve the preexisting collision", encoding="utf-8")
        self.kill_claim(point)
        snapshot = self.assert_restart_preserves()
        task = snapshot["task"]
        self.assertEqual((task["state"], task["assignee"]), ("open", None) if committed else ("claimed", "ann"))
        self.assertEqual(snapshot["locks"], [] if committed else [("config", "T5", "ann")])
        self.assertEqual(snapshot["contracts"][-1]["state"], "closed" if committed else "active")
        self.assertEqual(snapshot["releases"], int(committed))
        self.assertEqual(self.path.read_text(encoding="utf-8"), "preserve the preexisting collision")
        self.assertEqual(self.git("branch", "--list", "swarm/T5").strip(), "")

    def test_ec316_failed_allocation_kill_before_cleanup_commit_preserves_claim_and_collision(self):
        self.failed_allocation("before_claim_cleanup_commit", committed=False)

    def test_ec316_failed_allocation_kill_after_cleanup_commit_releases_once_without_deleting(self):
        self.failed_allocation("after_claim_cleanup_commit", committed=True)
