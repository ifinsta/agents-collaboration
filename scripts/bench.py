"""Time the tool's commands in a throwaway repository.

    python scripts/bench.py                    # this checkout
    python scripts/bench.py --source ../other  # another checkout (to compare two versions)
    python scripts/bench.py --runs 15
    python scripts/bench.py --no-config        # a project without a config.toml

Reports the fastest and the median wall time of each command, with bare Python start-up for scale. Timing depends on
the machine and on what else is running, so this is a guide for people. It is never an assertion in the test suite:
the suite counts work instead (git processes started, modules loaded), which does not flake under load.
"""

from __future__ import annotations

import argparse
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "bench",
    "GIT_AUTHOR_EMAIL": "bench@example.invalid",
    "GIT_COMMITTER_NAME": "bench",
    "GIT_COMMITTER_EMAIL": "bench@example.invalid",
}
ENV.pop("SWARM_AS", None)


CONFIG = """[project]
target = "main"

[swarm]
max_agents = 5

[gates]
commands = [["python", "-c", "pass"]]

[hotspots]
config = { paths = ["settings/**"] }
"""


def run(argv: list[str], cwd: Path | None = None) -> float:
    start = time.perf_counter()
    done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=ENV, check=False)
    elapsed = (time.perf_counter() - start) * 1000
    if done.returncode != 0:
        raise SystemExit(f"{' '.join(argv)} failed:\n{done.stdout}{done.stderr}")
    return elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=str(HERE), help="the checkout to install and time (default: this one)")
    parser.add_argument("--runs", type=int, default=9)
    parser.add_argument("--no-config", action="store_true", help="time a project that has no config.toml")
    args = parser.parse_args()
    source = Path(args.source).resolve()
    base = Path(tempfile.mkdtemp(prefix="swarm-bench-"))
    repo = base / "project"
    repo.mkdir()
    try:
        run(["git", "init", "-q", "-b", "main"], repo)
        (repo / "README.md").write_text("# bench\n", encoding="utf-8")
        run(["git", "add", "-A"], repo)
        run(["git", "commit", "-qm", "start"], repo)
        run(
            [sys.executable, str(source / "install.py"), "--source", str(source), "--project", str(repo), "--all"], repo
        )
        if not args.no_config:  # most real projects have one, and reading it costs something
            (repo / ".agents" / "swarm").mkdir(parents=True, exist_ok=True)
            (repo / ".agents" / "swarm" / "config.toml").write_text(CONFIG, encoding="utf-8")
        tool = repo / ".agents" / "skills" / "agents-collaboration" / "hivewire.py"
        swarm = [sys.executable, str(tool)]
        run([*swarm, "join", "--kind", "claude", "--as", "ann"], repo)
        run([*swarm, "add", "T1", "A first task", "--as", "ann"], repo)
        version = next(
            (
                line
                for line in (source / "pyproject.toml").read_text(encoding="utf-8").splitlines()
                if line.startswith("version")
            ),
            "version = ?",
        )
        print(
            f"agents-collaboration {version.split('=')[1].strip()}  ({source})   {args.runs} runs each, fastest / median ms\n"
        )
        rows = [
            ("python -c pass (scale)", [sys.executable, "-c", "pass"]),
            ("hivewire version", [*swarm, "version"]),
            ("hivewire status", [*swarm, "status"]),
            ("hivewire agents", [*swarm, "agents"]),
            ("hivewire whoami", [*swarm, "whoami", "--as", "ann"]),
            ("hivewire inbox", [*swarm, "inbox", "--as", "ann"]),
            ("hivewire environment", [*swarm, "environment", "--json"]),
        ]
        for label, argv in rows:
            run(argv, repo)  # the first run writes the bytecode cache and warms the file system
            times = [run(argv, repo) for _ in range(args.runs)]
            print(f"  {label:<26} {min(times):6.0f} / {statistics.median(times):6.0f}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
