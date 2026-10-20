"""The seeded demo board behind the README pictures: it builds, and the pictures it feeds are present."""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))
import dashboard_demo  # noqa: E402


class DemoBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = dashboard_demo.build(Path(cls.tmp.name) / "shop")
        cls.db = cls.repo / ".git" / "swarm" / "swarm.db"

    @classmethod
    def tearDownClass(cls):
        def writable(func, path, _exc):
            os.chmod(path, 0o700)
            func(path)

        shutil.rmtree(cls.tmp.name, **{("onexc" if sys.version_info >= (3, 12) else "onerror"): writable})

    def rows(self, sql, *args):
        with closing(sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)) as db:
            return db.execute(sql, args).fetchall()

    def test_five_agents_one_of_them_silent(self):
        agents = dict(self.rows("SELECT name, kind FROM agents"))
        self.assertEqual(agents, {"ann": "claude", "ola": "opencode", "quinn": "qodercli", "bo": "codex", "mia": "gemini"})
        self.assertEqual(self.rows("SELECT name FROM agents WHERE state='offline'"), [("bo",)])

    def test_tasks_cover_every_state_the_pictures_show(self):
        states = dict(self.rows("SELECT id, state FROM tasks"))
        self.assertEqual(states["H-schema"], "done")
        self.assertEqual(states["H-docs"], "ready_to_merge")
        self.assertEqual(states["H-metrics"], "orphaned")  # its holder went silent and the sweep noticed
        self.assertEqual(self.rows("SELECT COUNT(*) FROM tasks WHERE state='done'"), [(2,)])

    def test_an_open_incident_has_an_independent_reviewer(self):
        self.assertEqual(self.rows("SELECT subject, state FROM incidents"), [("bo", "open")])
        self.assertEqual(self.rows("SELECT reviewer FROM incident_reviews"), [("mia",)])

    def test_the_human_has_something_to_answer_and_approve(self):
        self.assertEqual(self.rows("SELECT COUNT(*) FROM questions WHERE answer IS NULL AND waived=0"), [(1,)])
        (architecture,) = self.rows("SELECT architecture FROM goals WHERE id='health'")[0]
        self.assertIn('"revision": 2', architecture)

    def test_the_steward_has_reminded_someone(self):
        self.assertGreaterEqual(self.rows("SELECT COUNT(*) FROM messages WHERE sender='steward'")[0][0], 1)

    def test_a_populated_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as busy:
            (Path(busy) / "x").write_text("x", encoding="utf-8")
            with self.assertRaises(SystemExit):
                dashboard_demo.build(Path(busy))


class Pictures(unittest.TestCase):
    def test_every_dashboard_picture_a_document_names_exists(self):
        missing = []
        for doc in (ROOT / "README.md", ROOT / "docs" / "web-dashboard.md"):
            for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", doc.read_text(encoding="utf-8")):
                if "://" in target:
                    continue
                path = (doc.parent / target).resolve()
                if not path.is_file() or path.stat().st_size < 2000:
                    missing.append(f"{doc.name}: {target}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
