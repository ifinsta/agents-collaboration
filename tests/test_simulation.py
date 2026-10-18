"""The published simulation (docs/simulation.md) must still describe what the tool does.

examples/simulate.py runs a full session against a real repository and checks every milestone as it goes;
this runs it on every OS in CI.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Simulation(unittest.TestCase):
    def test_every_milestone_of_the_published_session_holds(self):
        done = subprocess.run(
            [sys.executable, str(ROOT / "examples" / "simulate.py"), "--check"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("every milestone held", done.stdout)


if __name__ == "__main__":
    unittest.main()
