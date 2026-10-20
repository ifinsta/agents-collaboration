"""Additional independent memory branch crash acceptance at the final engine hash."""
import sys
import unittest
from pathlib import Path

root = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(root / "tests"))
from test_final_transitions import FinalTransitions  # noqa: E402
from test_hardening import HardeningCase  # noqa: E402


class MemoryBranches(HardeningCase):
    kill = FinalTransitions.kill
    paused = FinalTransitions.paused
    snapshot = FinalTransitions.snapshot
    row = FinalTransitions.row
    boundary = FinalTransitions.boundary

    def test_memory_refresh_and_retirement_commit_kills(self):
        self.join("ann")
        self.join("bob")
        sha = self.git("rev-parse", "main").strip()
        event = self.row("events")["id"]
        self.boundary(["memory", "propose", "Validate the source fixture before integration", "--as", "ann", "--applicability", "Applies to isolated source fixtures", "--event", str(event), "--commit", sha], "cmd_memory",
                      lambda: self.assertEqual(self.row("memories")["state"], "provisional"))
        for action, state, revision, extra in [
            ("verify", "verified", 1, []),
            ("mark", "stale", 2, ["--state", "stale"]),
            ("verify", "verified", 3, []),
            ("retire", "retired", 4, []),
        ]:
            self.boundary(["memory", action, "1", "--as", "bob", "--revision", str(revision), "--reason", "Independently reviewed the pinned fixture and applicability", *extra], "cmd_memory",
                          lambda state=state: self.assertEqual(self.row("memories")["state"], state))
        self.assertEqual(self.row("memories")["revision"], 5)
        self.assertEqual(self.git("rev-parse", f"refs/swarm/evidence/{sha}").strip(), sha)
        self.assertNotIn("Validate the source fixture", self.sw("context", "--task", "T1"))


if __name__ == "__main__":
    unittest.main(defaultTest="MemoryBranches", verbosity=2)
