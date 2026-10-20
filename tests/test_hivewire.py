"""Hivewire is the only supported command entry point."""

from __future__ import annotations

import json
import subprocess
import sys

from test_swarm import SWARM, SwarmCase
import swarm_web  # noqa: E402 (test_swarm adds the skill directory)


class Naming(SwarmCase):
    def canonical(self, *args):
        result = subprocess.run(
            [sys.executable, str(SWARM.with_name("hivewire.py")), *args],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_hivewire_is_the_only_shipped_entry_point(self):
        self.assertIn("usage: hivewire", self.canonical("--help"))
        self.assertTrue(self.canonical("version").startswith("Hivewire "))
        manifest = json.loads(SWARM.with_name("MANIFEST.json").read_text(encoding="utf-8"))
        self.assertIn("hivewire.py", manifest["files"])
        self.assertNotIn("swarm.py", manifest["files"])
        self.assertFalse(SWARM.with_name("swarm.py").exists())
        self.assertEqual(json.loads(self.canonical("protocol", "--json"))["protocol_version"], 2)

    def test_dashboard_refuses_other_launcher_names(self):
        self.assertTrue(swarm_web.launcher_ok({"launcher": str(SWARM), "root": str(self.root)}))
        folder = self.root / "other-launcher"
        folder.mkdir()
        (folder / "swarm_core.py").write_text("# fixture\n", encoding="utf-8")
        for name in ("swarm.py", "other.py"):
            launcher = folder / name
            launcher.write_text("# fixture\n", encoding="utf-8")
            self.assertFalse(swarm_web.launcher_ok({"launcher": str(launcher), "root": str(self.root)}))

    def test_dashboard_command_metadata_defaults_to_hivewire(self):
        entry = {"path": str(self.root / ".git" / "swarm" / "swarm.db"), "name": "board"}
        self.assertEqual(swarm_web.board_ctx(entry, None)["command"], "hivewire")
