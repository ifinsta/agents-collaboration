"""The engine's own integration commit never strands on a branch: every merge exit that does not land drops it."""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path

from test_generated_paths import VERSION_HOOK, GeneratedPaths
from test_hardening import core
from test_oversight import OversightCase

FAILING_HOOK = [
    sys.executable,
    "-c",
    "from pathlib import Path; Path('VERSION').write_text('2\\n'); raise SystemExit(1)",
]


class IntegrationDiscard(OversightCase):
    config = GeneratedPaths.config
    with_version_hook = GeneratedPaths.with_version_hook

    @contextmanager
    def board(self):
        sw = core.Swarm(self.root)
        try:
            yield sw
        finally:
            sw.db.close()

    def ready(self, hook=VERSION_HOOK):
        self.with_version_hook(hook=hook)
        self.join("ann")
        return self.to_ready("ann", "T1")

    def version(self, wt):
        return (wt / "VERSION").read_text().strip()

    def test_ec393_a_raise_after_the_intent_keeps_the_marker_until_recovery_clears_it(self):
        wt = self.ready()
        out = self.sw("merge", "--as", "ann", env={"SWARM_FAILPOINT": "after_intent"}, ok=False)
        self.assertEqual(self.version(wt), "2", "the process died with the engine's commit on the branch")
        with self.board() as sw:
            self.assertIsNotNone(sw.task("T1")["merge_intent"], out)
            core.discard_integration(sw, "T1", "ann")
            self.assertIsNotNone(sw.meta("integration:T1"), "an intent is still set: recovery owns it, keep the marker")
        self.assertEqual(self.version(wt), "2")
        self.sw("--as", "ann", "submit", "--evidence", "The merge died after its intent; nothing else changed", cwd=wt)
        self.assertEqual(self.version(wt), "1", "recovery cleared the intent, then the engine's commit was dropped")
        self.sw("merge", "--as", "ann")
        self.assertEqual(self.task("T1")["state"], "done")
        self.assertEqual(self.git("show", "main:VERSION").strip(), "2", "bumped once")

    def test_ec393_a_failed_hook_leaves_no_edit_for_the_author_to_clean_up(self):
        wt = self.ready(hook=FAILING_HOOK)
        self.assertIn("merge message hook failed", self.sw("merge", "--as", "ann"))
        self.sw("--as", "ann", "submit", "--evidence", "The hook failed; the branch is as submitted", cwd=wt)
        self.assertEqual(self.version(wt), "1")

    def test_ec393_a_dirty_main_checkout_does_not_strand_the_engine_commit(self):
        wt = self.ready()
        (self.root / "VERSION").write_text("a local edit in the main checkout\n", encoding="utf-8")
        self.assertIn("changes that the merge would overwrite", self.sw("merge", "--as", "ann"))
        self.sw("--as", "ann", "submit", "--evidence", "The fast-forward was refused; the work is unchanged", cwd=wt)
        self.assertEqual(self.version(wt), "1")
        self.git("checkout", "--", "VERSION")
        self.sw("merge", "--as", "ann")
        self.assertEqual(self.task("T1")["state"], "done")
        self.assertEqual(self.git("show", "main:VERSION").strip(), "2", "bumped once, not twice")

    def test_ec393_a_submit_during_a_live_merge_leaves_it_alone(self):
        wt = self.ready()
        with self.board() as sw, sw.tx():
            sw.set_meta("merge_lock", json.dumps({"agent": "ann", "task": "T1", "at": core.iso(), "attempt": "b" * 16}))
            sw.set_meta("integration:T1", json.dumps({"sha": None, "source": self.git("rev-parse", "HEAD", cwd=wt).strip(), "epoch": 1}))
        with self.board() as sw:
            core.discard_integration(sw, "T1", "ann", attempt=None)
            self.assertIsNotNone(sw.meta("integration:T1"), "another attempt holds the queue for this task")
        self.assertEqual(Path(wt).exists(), True)
