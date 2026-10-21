"""Merge-owned generated files, and reviews that survive the version hook and a rebase of identical work."""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
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

    def with_version_hook(self, generated=("VERSION",), hook=VERSION_HOOK):
        (self.root / "VERSION").write_text("1\n", encoding="utf-8")
        self.git("add", "VERSION")
        self.git("commit", "-qm", "version file")
        self.config(
            "[merge]\nmessage_command = "
            + json.dumps(list(hook))
            + "\ngenerated_paths = "
            + json.dumps(list(generated))
        )

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
