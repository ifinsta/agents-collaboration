#!/usr/bin/env python3
"""Build a populated demo board, so the browser dashboard can be seen without running real agents.

    python examples/dashboard_demo.py [DIRECTORY]      # default: a new temporary directory

It creates a throw-away Git repository with five agents and a goal in progress: an orchestrator, three implementers
(one working, one waiting on an answer, one gone silent), an independent reviewer on an open incident, a task in the
merge queue, two merged tasks, questions, messages of several kinds and a few inbox-steward reminders. Then, from
that directory:

    python PATH_TO/hivewire.py dashboard --web

The agents are seeded, not running. They are real rows on a real board made with real `hivewire` commands, except that a
silent agent, an open incident and some merged tasks are written straight into the database, because producing them
legitimately takes real commits and a long wait. Heartbeats are fresh when the script ends and expire after 20
minutes, so a demo left alone turns into a board of silent agents: rebuild it to see it live again.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWARM = ROOT / "skills" / "agents-collaboration" / "hivewire.py"

CONFIG = """[project]
name = "shop"
target = "main"
branch_prefix = "agent/"
backlog = "backlog.md"
check_remote = false

[gates]
commands = [["python", "-m", "unittest", "discover", "-s", "tests", "-q"]]
"""

BACKLOG = """# Backlog

| Id | Title | Scope | Needs | Locks | Caps |
|---|---|---|---|---|---|
| H-schema | Define the response schema | src/schema/ | - | - | |
| H-ci | Run the probe in CI | .github/ | H-schema | - | |
| H-ready | Readiness check | src/ready/ | H-schema | - | |
| H-docs | Document the route | docs/ | H-schema | - | |
| H-metrics | Expose the version metric | src/metrics/ | H-schema | - | |
| H-alerts | Alert on a failing probe | ops/ | H-ready | - | |
"""

AGENTS = (("ann", "claude"), ("ola", "opencode"), ("quinn", "qodercli"), ("bo", "codex"), ("mia", "gemini"))
PLAN = (
    "--set", "outcome=/ready reports whether the service can serve", "--set", "acceptance=the readiness test passes",
    "--set", "scope=src/ready/", "--set", "out_of_scope=everything else", "--set", "dependencies=none",
    "--set", "risks=a slow database", "--set", "rollback=git revert", "--set", "unknowns=none",
)
STEPS = ("Write a failing readiness test", "Return 200 when the database answers", "Return 503 while the cache is cold", "Document the behaviour")


def run(args, cwd: Path, env: dict, check: bool = True) -> str:
    done = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", check=False)
    if check and done.returncode:
        raise SystemExit(f"{' '.join(map(str, args[:6]))} failed ({done.returncode}):\n{done.stdout}{done.stderr}")
    return done.stdout + done.stderr


def build(target: Path) -> Path:
    """Create the demo repository in `target` (which must not exist or be empty) and return it."""
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise SystemExit(f"{target} is not empty; choose a new directory.")
    env = {k: v for k, v in os.environ.items() if k not in ("SWARM_AS", "SWARM_EPOCH")}
    env.update(PYTHONUTF8="1", GIT_AUTHOR_NAME="demo", GIT_AUTHOR_EMAIL="demo@example.com", GIT_COMMITTER_NAME="demo", GIT_COMMITTER_EMAIL="demo@example.com")

    def git(*a):
        return run(["git", *a], target, env)

    def swarm(*a, check=True):
        return run([sys.executable, str(SWARM), *a], target, env, check)

    git("init", "-q", "-b", "main")
    (target / ".agents" / "swarm").mkdir(parents=True)
    (target / ".agents" / "swarm" / "config.toml").write_text(CONFIG, encoding="utf-8")
    (target / "backlog.md").write_text(BACKLOG, encoding="utf-8")
    (target / "README.md").write_text("# shop\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "init")

    for name, kind in AGENTS:
        swarm("--as", name, "join", "--kind", kind)
    with closing(sqlite3.connect(target / ".git" / "swarm" / "swarm.db")) as db:  # the two tasks that have already merged
        db.execute("UPDATE tasks SET state='done', merged_sha='a91f3c2d' WHERE id IN ('H-schema','H-ci')")
        db.commit()
    swarm("--as", "ola", "claim", "H-ready")
    swarm("--as", "quinn", "claim", "H-docs")
    swarm("--as", "bo", "claim", "H-metrics")
    swarm("--as", "ola", "plan", *PLAN, *[x for s in STEPS for x in ("--step", s)])
    swarm("--as", "ola", "start")
    swarm("--as", "ola", "step", "1", "--evidence", "tests/test_ready.py fails with 404, as expected")
    swarm("--as", "ola", "step", "2", "--evidence", "the readiness test passes; commit 3d1c9ab")
    swarm("--as", "ola", "checkpoint", "--epoch", "1", "--note", "Readiness returns 200 when the database answers", "--next", "Decide the cold-cache behaviour")
    swarm("--as", "ola", "ask", "Should /ready fail while the cache is cold?", "--to", "human", "--critical")
    swarm("--as", "ola", "send", "quinn", "Can you review the readiness test when you have a minute?", "--kind", "review_request")
    swarm("--as", "bo", "send", "quinn", "Port 4104 was taken by another process; use the slot ports.", "--kind", "experience")
    swarm("--as", "quinn", "send", "ola", "Looks good. One nit on the cache test name.", "--kind", "status")
    swarm(
        "--as", "ann", "send", "human",
        "I lean **503** here. A cold cache means we cannot confirm the database.\n\n"
        "| Probe state | Response |\n|---|---|\n"
        "| warm | `200 OK` |\n| cold | `503` + `Retry-After: 5` |\n\n"
        "Keep the load balancer honest:\n\n"
        "1. Return `503` only while the cache is cold\n"
        "2. Ask the client to back off for five seconds\n"
        "3. Log the reason once per probe\n\n"
        "```text\nGET /ready -> 503\nRetry-After: 5\n```",
        "--kind", "decision",
    )
    swarm("--as", "ola", "send", "human", "Careful: the probe restarts the service on a 503.", "--kind", "warning", "--priority", "critical")
    swarm("--as", "quinn", "inbox")  # quinn has read the two messages above; neither is acknowledged
    swarm("goal", "new", "health", "Ship a health endpoint operators can rely on")

    now = datetime.now(UTC).replace(microsecond=0)
    steps = [
        {"text": "Expose the version in the metrics registry", "done": True, "evidence": "metrics test passes", "at": now.isoformat()},
        {"text": "Add a build-info gauge", "done": False},
        {"text": "Document the metric", "done": False},
    ]
    with closing(sqlite3.connect(target / ".git" / "swarm" / "swarm.db")) as db:
        db.execute("UPDATE tasks SET goal='health'")
        db.execute("UPDATE tasks SET state='ready_to_merge' WHERE id='H-docs'")
        db.execute("UPDATE tasks SET assignee='bo', state='in_progress', steps=?, step_idx=1, started_at=? WHERE id='H-metrics'", (json.dumps(steps), now.isoformat()))
        db.execute("UPDATE agents SET task='H-metrics' WHERE name='bo'")
        db.execute("UPDATE agents SET state='offline', offline_reason='silent', heartbeat_at=? WHERE name='bo'", ((now - timedelta(minutes=4)).isoformat(),))
        db.execute("UPDATE goals SET architecture=? WHERE id='health'", (json.dumps({"revision": 2, "risk": "medium"}),))
        db.execute(
            "INSERT INTO incidents(task,subject,opened_by,signal,state,revision,created_at,deadline_at) VALUES('H-metrics','bo','ann',?,'open',1,?,?)",
            ("step 1 cites a test that is not in the diff", now.isoformat(), (now + timedelta(minutes=30)).isoformat()),
        )
        incident = db.execute("SELECT MAX(id) FROM incidents").fetchone()[0]
        db.execute("INSERT INTO incident_reviews(incident,revision,reviewer,snapshot,snapshot_hash,epoch,created_at) VALUES(?,1,'mia','{}','demo',1,?)", (incident, now.isoformat()))
        db.execute("UPDATE agents SET reviewing=? WHERE name='mia'", (incident,))
        # messages between agents that sat unacknowledged for a while, so the steward has something to do
        db.execute("UPDATE messages SET created_at=? WHERE sender IN ('quinn','bo') OR (sender='ola' AND recipient='quinn')", ((now - timedelta(minutes=14)).isoformat(),))
        db.commit()
    swarm("steward", "--once")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("directory", nargs="?", help="where to create the demo repository (default: a new temporary directory)")
    args = parser.parse_args()
    target = Path(args.directory) if args.directory else Path(tempfile.mkdtemp(prefix="swarm-demo-"))
    build(target)
    print(f"demo board ready in {target}\n\nSee it in a browser:\n  cd {target}\n  python {SWARM} dashboard --web")


if __name__ == "__main__":
    main()
