"""Tests for install.py and the release manifest."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.py"


class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "proj"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, *args, ok=True):
        done = subprocess.run(
            [sys.executable, str(INSTALL), "--source", str(ROOT), "--project", str(self.repo), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        out = done.stdout + done.stderr
        self.assertEqual(done.returncode == 0, ok, out)
        return out

    def test_installs_skill_config_and_agents_pointer(self):
        self.install("--agents-md", "--scaffold")
        skill = self.repo / ".agents" / "skills" / "agents-collaboration"
        for name in ("SKILL.md", "swarm.py", "EDGE-CASES.md", "INSTALLED.json"):
            self.assertTrue((skill / name).exists(), name)
        self.assertTrue((self.repo / ".agents" / "swarm" / "config.toml").exists())
        self.assertIn("agents-collaboration:start", (self.repo / "AGENTS.md").read_text(encoding="utf-8"))

    def test_rerun_is_idempotent_and_keeps_project_config(self):
        self.install("--agents-md", "--scaffold")
        cfg = self.repo / ".agents" / "swarm" / "config.toml"
        cfg.write_text("# mine\n", encoding="utf-8")
        self.install("--agents-md", "--scaffold")
        self.assertEqual(cfg.read_text(encoding="utf-8"), "# mine\n")
        self.assertEqual((self.repo / "AGENTS.md").read_text(encoding="utf-8").count("agents-collaboration:start"), 1)

    def test_local_edits_are_not_overwritten(self):
        self.install()
        skill_md = self.repo / ".agents" / "skills" / "agents-collaboration" / "SKILL.md"
        skill_md.write_text("edited", encoding="utf-8")
        self.assertIn("edited locally", self.install(ok=False))
        self.install("--force")
        self.assertNotEqual(skill_md.read_text(encoding="utf-8"), "edited")

    def test_existing_agents_md_is_kept(self):
        (self.repo / "AGENTS.md").write_text("# Rules\n\nKeep me.\n", encoding="utf-8")
        self.install("--agents-md")
        text = (self.repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Rules\n\nKeep me.\n"))

    def test_ec146_agents_md_keeps_its_line_endings(self):
        for ending in (b"\n", b"\r\n"):
            body = b"# Rules" + ending + ending + b"Keep me." + ending
            (self.repo / "AGENTS.md").write_bytes(body)
            self.install("--agents-md", "--force")
            data = (self.repo / "AGENTS.md").read_bytes()
            self.assertTrue(data.startswith(body))
            other = b"\r\n" if ending == b"\n" else None
            if other:
                self.assertNotIn(other, data)
            else:
                self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))

    def test_ec156_claude_code_pointer(self):
        self.install("--all")
        stub = self.repo / ".claude" / "skills" / "agents-collaboration" / "SKILL.md"
        text = stub.read_text(encoding="utf-8")
        self.assertIn("name: agents-collaboration", text)
        self.assertIn(".agents/skills/agents-collaboration/SKILL.md", text)
        self.install("--all")  # its own pointer is refreshed
        stub.write_text("---\nname: agents-collaboration\n---\nmine\n", encoding="utf-8")
        self.assertIn("not this installer's pointer", self.install("--claude", ok=False))

    def test_ec157_user_install_serves_every_repository(self):
        home = Path(self.tmp.name) / "home"
        home.mkdir()
        env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
        done = subprocess.run(
            [sys.executable, str(INSTALL), "--source", str(ROOT), "--user", "--claude"],
            cwd=self.tmp.name,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        tool = home / ".agents" / "skills" / "agents-collaboration" / "swarm.py"
        self.assertTrue(tool.exists())
        stub = (home / ".claude" / "skills" / "agents-collaboration" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(tool.parent.as_posix(), stub)
        run = subprocess.run(
            [sys.executable, str(tool), "version"], cwd=self.repo, env=env, capture_output=True, text=True, check=False
        )
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_ec168_nothing_about_the_project_is_assumed(self):
        self.install("--all")
        self.assertFalse((self.repo / ".agents" / "swarm").exists())
        self.install("--scaffold")
        self.assertTrue((self.repo / ".agents" / "swarm" / "config.toml").exists())
        self.assertFalse((self.repo / ".agents" / "swarm" / "backlog.md").exists())

    def board(self):
        subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", "init"],
            cwd=self.repo,
            check=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
            },
        )
        done = subprocess.run(
            [sys.executable, ".agents/skills/agents-collaboration/swarm.py", "status", "--all"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_ec171_a_fresh_install_starts_with_an_empty_board(self):
        self.install("--all")
        lines = self.board().strip().splitlines()
        self.assertEqual(len(lines), 1, lines)  # only the "agents live" line: no tasks
        self.install("--scaffold")
        lines = self.board().strip().splitlines()
        self.assertEqual(len(lines), 1, lines)

    def test_ec171_the_example_backlog_is_never_work(self):
        self.install("--scaffold")
        swarm_dir = self.repo / ".agents" / "swarm"
        (swarm_dir / "backlog.md").write_bytes((ROOT / "examples" / "backlog.md").read_bytes())
        cfg = swarm_dir / "config.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("# backlog = ", "backlog = ", 1), encoding="utf-8")
        out = self.board()
        self.assertNotIn("EX-", out)

    def test_installed_tool_runs(self):
        self.install()
        done = subprocess.run(
            [sys.executable, ".agents/skills/agents-collaboration/swarm.py", "environment", "--json"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("rules", json.loads(done.stdout))


class Release(unittest.TestCase):
    def test_installer_is_ascii_for_powershell_pipes(self):
        INSTALL.read_bytes().decode("ascii")

    def test_manifest_is_current(self):
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "make_manifest.py"), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_tool_version_matches_release(self):
        text = (ROOT / "skills" / "agents-collaboration" / "swarm.py").read_text(encoding="utf-8")
        version = next(
            line.split("=", 1)[1].strip().strip('"')
            for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()
            if line.startswith("version")
        )
        self.assertIn(f'__version__ = "{version}"', text)

    def test_installer_default_ref_matches_version(self):
        version = next(
            line.split("=", 1)[1].strip().strip('"')
            for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()
            if line.startswith("version")
        )
        self.assertIn(f'DEFAULT_REF = "v{version}"', INSTALL.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
