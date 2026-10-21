"""Merge-owned generated files, and reviews that survive the version hook and a rebase of identical work."""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from test_hardening import core
from test_oversight import OversightCase

VERSION_HOOK = [
    sys.executable,
    "-c",
    "from pathlib import Path; p = Path('VERSION'); n = int(p.read_text().strip()) + 1; p.write_text(f'{n}\\n'); print(f'v{n}')",
]


class GeneratedPaths(OversightCase):
    def config(self, section):
        path = self.root / ".agents" / "swarm" / "config.toml"
        path.write_text(path.read_text(encoding="utf-8") + "\n" + section + "\n", encoding="utf-8")
        self.git("add", ".agents/swarm/config.toml")
        self.git("commit", "-qm", "configure generated paths")

    def with_version_hook(self, generated=("VERSION",), hook=VERSION_HOOK, strategy=None):
        (self.root / "VERSION").write_text("1\n", encoding="utf-8")
        self.git("add", "VERSION")
        self.git("commit", "-qm", "version file")
        self.config(
            "[merge]\nmessage_command = "
            + json.dumps(list(hook))
            + "\ngenerated_paths = "
            + json.dumps(list(generated))
            + (f'\nstrategy = "{strategy}"' if strategy else "")
        )

    def commit_version(self, wt, value="9"):
        (wt / "VERSION").write_text(f"{value}\n", encoding="utf-8")
        self.git("add", "VERSION", cwd=wt)
        self.git("commit", "-qm", "unreviewed version bump", cwd=wt)

    def test_ec389_a_generated_edit_after_clear_cannot_land_through_rebase(self):
        self.with_version_hook(hook=[], strategy="rebase")
        wt = self.setup_incident()
        self.clear()
        self.commit_version(wt)
        target = self.git("rev-parse", "main").strip()
        out = self.sw("merge", "--as", "bob", ok=False)
        self.assertIn("generated path", out)
        self.assertEqual(self.git("rev-parse", "main").strip(), target)
        self.assertEqual(self.task("T1")["state"], "ready_to_merge")

    def test_ec389_a_generated_edit_after_submit_cannot_land_without_an_incident(self):
        self.with_version_hook(hook=[], strategy="rebase")
        wt = self.setup_worker(ready=True)
        self.commit_version(wt)
        target = self.git("rev-parse", "main").strip()
        out = self.sw("merge", "--as", "bob", ok=False)
        self.assertIn("generated path", out)
        self.assertEqual(self.git("rev-parse", "main").strip(), target)
        self.assertEqual(self.task("T1")["state"], "ready_to_merge")

    def test_ec389_incident_resolve_refuses_a_generated_edit_after_submission(self):
        self.with_version_hook(hook=[], strategy="rebase")
        wt = self.setup_incident()
        self.commit_version(wt)
        self.report()
        out = self.sw(
            "incident",
            "resolve",
            "1",
            "--as",
            "ann",
            "--outcome",
            "cleared",
            "--reason",
            "The independent evidence does not confirm the suspected defect",
            ok=False,
        )
        self.assertIn("generated path", out)
        self.assertEqual(self.row("incidents", "id=1")["state"], "reviewed")

    def test_ec377_incident_gated_task_merges_through_a_version_hook(self):
        self.with_version_hook()
        self.setup_incident()
        self.clear()
        out = self.sw("merge", "--as", "bob")
        self.assertNotIn("stale", out)
        self.assertEqual(self.task("T1")["state"], "done", out)
        self.assertEqual(self.git("show", "main:VERSION").strip(), "2")

    def test_ec377_a_hook_edit_outside_generated_paths_still_stales_the_review(self):
        hook = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('VERSION').write_text('2\\n'); Path('src/file.txt').write_text('hook-modified')",
        ]
        self.with_version_hook(hook=hook)
        self.setup_incident()
        self.clear()
        target = self.git("rev-parse", "main")
        self.assertIn("stale", self.sw("merge", "--as", "bob", ok=False))
        self.assertEqual(self.git("rev-parse", "main"), target)

    def test_ec378_identical_work_rebased_onto_a_moved_target_keeps_its_clearance(self):
        self.with_version_hook()
        self.setup_incident()
        self.clear()
        # The target moves on an unrelated file after the review; the rebased patch is byte-identical.
        (self.root / "docs.txt").write_text("unrelated\n", encoding="utf-8")
        self.git("add", "docs.txt")
        self.git("commit", "-qm", "unrelated change on the target")
        out = self.sw("merge", "--as", "bob")
        self.assertEqual(self.task("T1")["state"], "done", out)

    def test_ec379_submit_refuses_an_author_edit_to_a_generated_path(self):
        self.with_version_hook()
        wt = self.setup_worker()
        (wt / "dirty.txt").unlink()
        (wt / "VERSION").write_text("9\n", encoding="utf-8")
        (wt / "src").mkdir(exist_ok=True)
        (wt / "src" / "file.txt").write_text("x\n", encoding="utf-8")
        self.git("add", "-A", cwd=wt)
        self.git("commit", "-qm", "work plus a baked version bump", cwd=wt)
        for step in ("1", "2"):
            self.sw("--as", "bob", "step", step, "--evidence", "did the fixture step", cwd=wt)
        out = self.sw("--as", "bob", "submit", "--evidence", "gates pass locally", cwd=wt, ok=False)
        self.assertIn("the merge hook writes", out)

    @contextmanager
    def board(self):
        sw = core.Swarm(self.root)
        try:
            yield sw
        finally:
            sw.db.close()

    def branch_commit(self, branch, files):
        self.git("checkout", "-q", "-b", branch, "main")
        for name, data in files.items():
            (self.root / name).write_bytes(data)
        self.git("add", *files)
        self.git("commit", "-qm", branch)
        self.git("checkout", "-q", "main")
        return self.git("rev-parse", branch).strip()

    def test_ec378_a_whitespace_only_python_change_is_new_content(self):
        spaces = self.branch_commit("ws-spaces", {"mod.py": b"def f():\n    return 1\n"})
        tabs = self.branch_commit("ws-tabs", {"mod.py": b"def f():\n\treturn 1\n"})
        with self.board() as sw:
            self.assertNotEqual(core.patch_identity(sw, spaces), core.patch_identity(sw, tabs))

    def test_ec378_binary_changes_do_not_collide(self):
        one = self.branch_commit("bin-one", {"blob.bin": b"\x00\x01\x02\xff"})
        two = self.branch_commit("bin-two", {"blob.bin": b"\x00\x01\x03\xff"})
        with self.board() as sw:
            self.assertNotEqual(core.patch_identity(sw, one), core.patch_identity(sw, two))

    def test_ec378_patch_identity_leaves_out_generated_paths(self):
        self.with_version_hook()
        plain = self.branch_commit("work-plain", {"mod.py": b"x = 1\n"})
        baked = self.branch_commit("work-baked", {"mod.py": b"x = 1\n", "VERSION": b"7\n"})
        with self.board() as sw:
            self.assertEqual(core.patch_identity(sw, plain), core.patch_identity(sw, baked))

    def test_ec378_the_policy_drops_only_the_listed_clock_fields(self):
        self.setup_worker()
        base = {"scope": ["src/"], "deadline_at": "2026-01-01T00:00:00Z", "active_time_min": 30, "debate_min": 5}
        with self.board() as sw:
            task = dict(sw.task("T1"))

            def policy(terms, **submission):
                row = {**task, "submit": json.dumps({"head": "abc", "evidence": "ran it", **submission})}
                with mock.patch.object(core, "current_contract", return_value={"terms": json.dumps(terms)}):
                    return core.request_hash(core.review_policy(sw, row))

            same = policy(base)
            for clock in (
                {"deadline_at": "2026-02-02T00:00:00Z"},
                {"active_time_min": 90},
                {"active_seconds": 12},
                {"blocked_seconds": 3},
                {"checkpoint_at": "2026-01-01T01:00:00Z"},
                {"extension_count": 1},
            ):
                self.assertEqual(policy({**base, **clock}), same, clock)
            self.assertEqual(policy(base, evidence="ran it again, still green"), same)
            for bound in ({"debate_min": 10}, {"future_term": True}, {"scope": ["src/", "docs/"]}):
                self.assertNotEqual(policy({**base, **bound}), same, bound)  # unknown fields fail closed
            self.assertNotEqual(policy(base, changelog="a different line for the hook"), same)

    def fail_the_final_gate_once(self):
        """Swap the gate for one that fails on its second run (the final integration commit), then passes."""
        script = Path(self.tmp.name) / "fail_once.py"
        script.write_text(
            "import pathlib, sys\n"
            f"count = pathlib.Path(r'{self.tmp.name}') / 'fail-runs'\n"
            "n = int(count.read_text()) + 1 if count.exists() else 1\n"
            "count.write_text(str(n))\n"
            "sys.exit(1 if n == 2 else 0)\n",
            encoding="utf-8",
        )
        path = self.root / ".agents" / "swarm" / "config.toml"
        text = path.read_text(encoding="utf-8")
        start = text.index("commands = [[", text.index("[gates]"))
        end = text.index("\n", start)
        path.write_text(text[:start] + "commands = " + json.dumps([[sys.executable, str(script)]]) + text[end:], encoding="utf-8")
        self.git("add", ".agents/swarm/config.toml")
        self.git("commit", "-qm", "gate that fails once")

    def move_the_target_during_the_final_gate(self):
        """Swap the gate for one that, on its second run (the final integration commit), lands a commit on main."""
        script = Path(self.tmp.name) / "move_target.py"
        script.write_text(
            "import pathlib, subprocess, sys\n"
            f"count = pathlib.Path(r'{self.tmp.name}') / 'gate-runs'\n"
            "n = int(count.read_text()) + 1 if count.exists() else 1\n"
            "count.write_text(str(n))\n"
            "if n == 2:\n"
            f"    subprocess.run(['git', '-C', r'{self.root}', 'commit', '--allow-empty', '-qm', 'target moved mid-merge'], check=True)\n",
            encoding="utf-8",
        )
        path = self.root / ".agents" / "swarm" / "config.toml"
        text = path.read_text(encoding="utf-8")
        start = text.index("commands = [[", text.index("[gates]"))
        end = text.index("\n", start)
        gate = json.dumps([[sys.executable, str(script)]])
        path.write_text(text[:start] + f"commands = {gate}" + text[end:], encoding="utf-8")
        self.git("add", ".agents/swarm/config.toml")
        self.git("commit", "-qm", "gate that moves the target once")

    def test_ec392_a_retry_after_the_target_moves_keeps_the_hooks_own_writes(self):
        self.with_version_hook()
        self.move_the_target_during_the_final_gate()
        self.join("ann")
        self.to_ready("ann", "T1")
        out = self.sw("merge", "--as", "ann")
        self.assertEqual(self.task("T1")["state"], "done", out)
        self.assertEqual((Path(self.tmp.name) / "gate-runs").read_text(), "4", "two passes of two gates each")
        self.assertEqual(self.git("show", "main:VERSION").strip(), "2", "bumped once, not twice")

    def test_ec392_the_same_retry_for_an_incident_gated_task(self):
        self.with_version_hook()
        self.move_the_target_during_the_final_gate()
        self.setup_incident()
        self.clear()
        out = self.sw("merge", "--as", "bob")
        self.assertEqual(self.task("T1")["state"], "done", out)
        self.assertEqual(self.git("show", "main:VERSION").strip(), "2")

    def test_ec392_a_failed_final_gate_leaves_no_hook_write_for_the_author_to_revert(self):
        self.with_version_hook()
        self.fail_the_final_gate_once()
        self.join("ann")
        wt = self.to_ready("ann", "T1")
        self.assertIn("Gates failed on the final integration commit", self.sw("merge", "--as", "ann"))
        self.assertEqual((wt / "VERSION").read_text().strip(), "1", "the hook's bump is not left on the branch")
        self.sw("--as", "ann", "submit", "--evidence", "The failed gate was a flake; nothing changed", cwd=wt)
        out = self.sw("merge", "--as", "ann")
        self.assertEqual(self.task("T1")["state"], "done", out)
        self.assertEqual(self.git("show", "main:VERSION").strip(), "2", "bumped once, by the hook")
