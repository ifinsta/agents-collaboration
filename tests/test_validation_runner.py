"""The cross-platform evidence runner must fail closed on subtests and changed inputs."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

from test_hardening import HardeningCase, fixtures


class ValidationRunner(HardeningCase):
    def fixture(self, source):
        script = self.root / "scripts/validate_candidate.py"
        script.parent.mkdir()
        shutil.copy2(Path(fixtures.SWARM).parents[2] / "scripts/validate_candidate.py", script)
        core = self.root / "skills/agents-collaboration/swarm_core.py"
        core.parent.mkdir(parents=True)
        core.write_text("# Evidence-only core fixture\n", encoding="utf-8")
        tests = self.root / "tests"
        tests.mkdir()
        (tests / "test_fixture.py").write_text(source, encoding="utf-8")
        output = Path(self.tmp.name) / "evidence"
        done = subprocess.run([sys.executable, str(script), "--workers", "2", "--output", str(output)], cwd=self.root, capture_output=True, text=True, check=False)
        return done, json.loads((output / "results.json").read_text(encoding="utf-8"))

    def test_ec343_failed_subtest_is_failed_case_and_never_green_ci(self):
        done, report = self.fixture("import unittest\nclass Fixture(unittest.TestCase):\n def test_subtest(self):\n  with self.subTest(value=1): self.assertEqual(1,2)\n def test_good(self): self.assertTrue(True)\n")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertFalse(report["ok"])
        self.assertTrue(report["exact_discovery_coverage"])
        self.assertEqual(report["counts"]["failed"], 1)
        self.assertEqual(report["counts"]["passed"], 1)
        self.assertTrue(all(s["log_sha256"] for s in report["shards"]))

    def test_ec343_source_mutation_refuses_success_even_when_tests_pass(self):
        done, report = self.fixture("import unittest,pathlib\nclass Fixture(unittest.TestCase):\n def test_mutates(self):\n  pathlib.Path('skills/agents-collaboration/swarm_core.py').write_text('# changed source')\n")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertFalse(report["ok"])
        self.assertFalse(report["source_unchanged"])
        self.assertIn("skills/agents-collaboration/swarm_core.py", report["changed_inputs"])

    def test_ec343_full_platform_gate_requires_macos_and_matching_source(self):
        script = Path(fixtures.SWARM).parents[2] / "scripts/validate_matrix.py"
        output = Path(self.tmp.name) / "matrix"
        output.mkdir()
        for system in ("Windows", "Linux", "Darwin"):
            for version in ("3.11", "3.13"):
                folder = output / f"{system}-{version}"
                folder.mkdir()
                data = {"system": system, "python_version": version + ".0", "ok": True,
                        "source_unchanged": True, "exact_discovery_coverage": True, "discovered": 1,
                        "source_fingerprint": "a" * 64, "cases": [{"id": "fixture.test", "outcome": "passed"}]}
                (folder / "results.json").write_text(json.dumps(data), encoding="utf-8")
        def check():
            return subprocess.run([sys.executable, str(script), str(output)], capture_output=True, text=True, check=False)
        self.assertEqual(check().returncode, 0)
        mac = output / "Darwin-3.13/results.json"
        saved = mac.read_text(encoding="utf-8")
        mac.unlink()
        self.assertEqual(check().returncode, 1)
        data = json.loads(saved)
        data["source_fingerprint"] = "b" * 64
        mac.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(check().returncode, 1)
