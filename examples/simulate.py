#!/usr/bin/env python3
"""A scripted session: three agents and a human take one goal from a sentence to merged, verified work.

It runs the real installer and the real tool against a real git repository in a temporary directory,
and writes what happened as a transcript, so anyone can see what to expect before installing:

    python examples/simulate.py                         # print the transcript
    python examples/simulate.py --write docs/simulation.md
    python examples/simulate.py --check                 # run it and verify every milestone, quietly (CI)

Agents are simulated by one script calling `swarm.py --as <name>`, which is exactly what each real agent's
shell does. The only things faked are time passing (an agent going silent for hours) and the human typing.
Every step checks its own result; if the tool ever stops behaving as described, the script stops there.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.py"
VERSION = next(
    line.split("=", 1)[1].strip().strip('"')
    for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    if line.startswith("version")
)


class Diverged(SystemExit):
    pass


class Sim:
    def __init__(self, base: Path):
        self.base = base
        self.repo = base / "shop"
        self.out: list[str] = []
        self.tool = self.repo / ".agents" / "skills" / "agents-collaboration" / "swarm.py"

    # ---- recording
    def norm(self, text: str) -> str:
        for raw in {str(self.base), self.base.as_posix(), str(self.base.resolve()), self.base.resolve().as_posix()}:
            text = text.replace(raw, "~/demo")
        for raw in {str(ROOT), ROOT.as_posix()}:
            text = text.replace(raw, f"github.com/ifinsta/agents-collaboration@v{VERSION}")
        text = text.replace("\\", "/")
        text = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", "<time>", text)
        text = re.sub(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b", "<sha>", text)
        text = re.sub(r"pid \d+", "pid <n>", text)
        text = re.sub(r"\d+\.\d+ min", "<n> min", text)
        text = re.sub(r"python \S*~/demo", "python ~/demo", text)
        return text

    def section(self, title: str, text: str) -> None:
        self.out += [f"## {title}", "", text.strip(), ""]

    def note(self, text: str) -> None:
        self.out += [text.strip(), ""]

    def block(self, command: str, output: str) -> None:
        self.out += ["```console", f"$ {command}"]
        if output.strip():
            self.out += [self.norm(output.rstrip())]
        self.out += ["```", ""]

    # ---- running things
    def swarm(
        self,
        *args: str,
        who: str | None = None,
        cwd: Path | None = None,
        ok: bool = True,
        expect: tuple[str, ...] = (),
        show: bool = True,
        display: str = "",
    ) -> str:
        argv = [sys.executable, str(self.tool), *args, *(["--as", who] if who else [])]
        env = {k: v for k, v in os.environ.items() if k != "SWARM_AS"}
        done = subprocess.run(
            argv, cwd=cwd or self.repo, capture_output=True, text=True, encoding="utf-8", env=env, check=False
        )
        output = (done.stdout + done.stderr).rstrip()
        shown = "swarm " + " ".join(f'"{a}"' if " " in a else a for a in args) + (f" --as {who}" if who else "")
        if (done.returncode == 0) != ok:
            raise Diverged(f"simulation diverged: `{shown}` exited {done.returncode}\n{output}")
        for text in expect:
            if text not in output:
                raise Diverged(f"simulation diverged: `{shown}` did not say {text!r}\n{output}")
        if show:
            self.block(display or shown, output)
        return output

    def git(self, *args: str, cwd: Path, who: str | None = None, ok: bool = True) -> str:
        ident = ["-c", f"user.name={who}", "-c", f"user.email={who}@agents.invalid"] if who else []
        done = subprocess.run(
            ["git", *ident, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "GIT_EDITOR": "true"},
            check=False,
        )
        if (done.returncode == 0) != ok:
            raise Diverged(f"simulation diverged: git {' '.join(args)}\n{done.stdout}{done.stderr}")
        return (done.stdout + done.stderr).strip()

    def write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def worktree(self, task: str) -> Path:
        return self.base / "shop-wt" / task

    def commit(self, task: str, who: str, message: str) -> None:
        wt = self.worktree(task)
        self.git("add", "-A", cwd=wt)
        self.git("commit", "-qm", message, cwd=wt, who=who)

    def age_agent(self, name: str, hours: int) -> None:
        """The one shortcut: pretend an agent has been silent for hours."""
        con = sqlite3.connect(self.repo / ".git" / "swarm" / "swarm.db")
        then = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=hours)
        old = then.isoformat()
        con.execute(
            "UPDATE agents SET heartbeat_at=?, offline_at=CASE WHEN offline_at IS NULL THEN NULL ELSE ? END "
            "WHERE name=?",
            (old, old, name),
        )
        con.commit()
        con.close()


APP = """VERSION = "1.4.0"


def greet(name):
    return f"hello {name}"
"""
APP_TEST = """import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import app  # noqa: E402


class Greet(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(app.greet("ada"), "hello ada")
"""
CONFIG = """[project]
target = "main"
branch_prefix = "agent/"
check_remote = false

[gates]
commands = [["python", "-m", "unittest", "discover", "-s", "tests", "-q"]]

[merge]
strategy = "squash"
message = "{task}: {title}"
"""


def run(sim: Sim) -> None:
    repo = sim.repo
    repo.mkdir(parents=True)
    sim.git("init", "-q", "-b", "main", cwd=repo)
    sim.git("config", "user.name", "Maintainer", cwd=repo)
    sim.git("config", "user.email", "maintainer@example.invalid", cwd=repo)
    sim.write(repo / "src" / "app.py", APP)
    sim.write(repo / "tests" / "test_app.py", APP_TEST)
    sim.write(repo / "README.md", "# shop\n\nA small service.\n\nEndpoints: none yet\n")
    sim.write(repo / ".gitignore", "__pycache__/\n")
    sim.git("add", "-A", cwd=repo)
    sim.git("commit", "-qm", "the starting point", cwd=repo)

    sim.out += [
        "# A simulated session",
        "",
        "Three coding agents and one human take a single goal from a sentence to merged, verified work.",
        "Everything below is real output from the real tool and real git, produced by",
        "[`examples/simulate.py`](../examples/simulate.py) in a throwaway repository. Only two things are",
        "simulated: the human typing, and an agent going silent for hours. Paths, times and commit hashes",
        "are normalised.",
        "",
        f"Generated with agents-collaboration on {platform.system()}, Python {platform.python_version()}.",
        "Regenerate it with `python examples/simulate.py --write docs/simulation.md`.",
        "",
        "`swarm` below stands for `python .agents/skills/agents-collaboration/swarm.py`, the command every",
        "agent runs from its own shell.",
        "",
        "**The cast:**",
        "",
        "- `claude-1`, `opencode-1` and `qoder-1`: agents that could be Claude Code, opencode and Qoder;",
        "- the human, who answers what only a person can.",
        "",
        "**The repository:** a tiny Python service with one function and one test. Its gate is",
        "`python -m unittest`.",
        "",
    ]

    # 1. install
    done = subprocess.run(
        [sys.executable, str(INSTALL), "--source", str(ROOT), "--project", str(repo), "--all"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if done.returncode != 0:
        raise Diverged(done.stdout + done.stderr)
    sim.write(repo / ".agents" / "swarm" / "config.toml", CONFIG)
    sim.git("add", "-A", cwd=repo)
    sim.git("commit", "-qm", "install agents-collaboration", cwd=repo)
    sim.section(
        "1. Install",
        "The installer adds the skill, a pointer in `AGENTS.md` for most agent CLIs, and one for "
        "Claude Code. Nothing else: no tasks, no backlog. This project then states its own facts in a short "
        "config: its gate, and a branch prefix.",
    )
    sim.block(
        "curl -fsSL https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --all",
        done.stdout.split("\nVerify")[0],
    )
    sim.block("cat .agents/swarm/config.toml", CONFIG)

    # 2. environment and joining
    sim.section(
        "2. Where am I, and who else is here?",
        "Every agent starts by reading the machine it is on, so it "
        "does not assume Linux on Windows (or the reverse). Then it joins. The first agent finds itself "
        "alone, becomes the coordinator, and is told to ask the human about a console.",
    )
    sim.swarm("environment", expect=("rules:",))
    sim.swarm(
        "join", "--kind", "claude", "--model", "sonnet", who="claude-1", expect=("SOLO", "coordinator", "ASK THE HUMAN")
    )
    sim.note(
        "The human says no to the console for now (`swarm console` opens one later). Two more agents join; "
        "the pool is no longer solo."
    )
    sim.swarm("console", "--decline", who="claude-1", expect=("no console",))
    sim.swarm("join", "--kind", "opencode", "--model", "deepseek-chat", who="opencode-1", expect=("peers: claude-1",))
    sim.swarm("join", "--kind", "qodercli", who="qoder-1", expect=("peers: claude-1, opencode-1",))
    sim.swarm("agents", expect=("*claude-1",))

    # 3. the goal and its hard questions
    sim.section(
        "3. A sentence becomes a goal",
        "The human asks for a health check. Before anyone may split it into "
        "tasks, the coordinator must answer hard questions in four stages: understand, backward, forward, "
        "challenge. It does not know the riskiest assumption, so it says `unknown`, and that becomes a "
        "question for the human.",
    )
    sim.swarm(
        "goal",
        "new",
        "health",
        "Operators can check the service is healthy and which version runs",
        who="claude-1",
        expect=("done_looks_like",),
    )
    answers = {
        "done_looks_like": "calling health() returns ok together with the running version",
        "who_uses_it": "operators and the uptime monitor; they need a stable shape they can parse",
        "not_included": "no network server, no authentication, no metrics endpoint",
        "must_not_break": "greet() and its test keep working exactly as before",
        "true_now": "src/app.py has VERSION and greet(); tests run with python -m unittest",
        "last_step": "documentation tells operators what health() returns",
        "before_that": "health() exists and is covered by a test the gate runs",
        "first_moves": "write health() and the docs page in parallel; tests follow health()",
        "in_parallel": "health() in src/ and the docs in docs/ touch different files except README",
        "smallest_version": "a function returning a dict with status and version, one test, one doc page",
        "wrong_if": "operators need more than status and version; we would hear it when they read the docs",
        "hard_to_undo": "the shape of the health() answer, once the monitor parses it; the human approves it",
        "how_verified": "python -m unittest discover -s tests in the gate, plus calling health() by hand",
        "unknowns": "none",
    }
    sim.swarm(
        "goal",
        "answer",
        "health",
        *[f"--set={k}={v}" for k, v in answers.items()],
        "--set=riskiest_assumption=unknown",
        who="claude-1",
        expect=("14 of 15", "Q1, asked of human"),
        display='swarm goal answer health --set done_looks_like="..." --set who_uses_it="..." ... '
        "--set riskiest_assumption=unknown --as claude-1",
    )
    sim.swarm("questions", expect=("Q1", "-> human"))
    sim.note("Review refuses to pass while a question is open and nothing is planned yet.")
    sim.swarm("goal", "review", "health", who="claude-1", ok=False, expect=("Q1 is open", "no outcomes"))
    sim.note("The human answers. The coordinator records the substance.")
    sim.swarm(
        "answer",
        "1",
        "that operators accept a plain dict; check with the monitor owner before freezing it",
        expect=("answered",),
    )
    sim.swarm(
        "goal",
        "answer",
        "health",
        "--set=riskiest_assumption=that a plain dict is enough for the monitor; H-api checks it with its owner first",
        who="claude-1",
        expect=("15 of 15",),
    )

    # 4. backward: outcomes and tasks
    sim.section(
        "4. Backward from the outcomes, then forward",
        "Outcomes are what is observably true when the goal is "
        "done, each with its check. Tasks work backward from them. The coordinator forgets one, and review "
        "says so.",
    )
    sim.swarm(
        "goal",
        "outcome",
        "health",
        "health() answers ok with the running version",
        "--check",
        "python -c 'import app; print(app.health())' prints status ok and the version",
        who="claude-1",
    )
    sim.swarm(
        "goal",
        "outcome",
        "health",
        "health() is covered by a test the gate runs",
        "--check",
        "python -m unittest discover -s tests runs test_health and passes",
        who="claude-1",
    )
    sim.swarm(
        "goal",
        "outcome",
        "health",
        "operators can read what health() returns",
        "--check",
        "docs/api.md describes health() and README lists it under Endpoints",
        who="claude-1",
    )
    sim.swarm(
        "goal",
        "task",
        "health",
        "H-api",
        "Add health() returning status and version",
        "--serves",
        "1",
        "--scope",
        "src/, README.md",
        "--done-when",
        "health() returns ok and VERSION when called by hand",
        who="claude-1",
    )
    sim.swarm(
        "goal",
        "task",
        "health",
        "H-docs",
        "Document health() for operators",
        "--serves",
        "3",
        "--scope",
        "docs/, README.md",
        "--done-when",
        "docs/api.md explains both fields and README lists health()",
        who="claude-1",
    )
    sim.swarm("goal", "review", "health", who="claude-1", ok=False, expect=("outcome 2 has no task",))
    sim.swarm(
        "goal",
        "task",
        "health",
        "H-tests",
        "Test health() in the gate",
        "--serves",
        "2",
        "--needs",
        "H-api",
        "--scope",
        "tests/",
        "--done-when",
        "test_health passes under python -m unittest discover -s tests",
        who="claude-1",
    )
    sim.swarm(
        "goal",
        "review",
        "health",
        who="claude-1",
        expect=("wave 1 (now): H-api, H-docs", "wave 2 (after wave 1): H-tests", "review passed"),
    )
    sim.note(
        "Committing opens the tasks and gives the first wave to free agents whose machines can verify them. "
        "H-tests waits for H-api."
    )
    sim.swarm(
        "goal", "commit", "health", "--assign", who="claude-1", expect=("H-api -> claude-1", "H-docs -> opencode-1")
    )

    # 5. claims and context
    sim.section(
        "5. One task each, with its place in the work",
        "Each claim creates the agent's own worktree and "
        "branch, and shows the task's context. **Previous** is what it builds on. **Next** is what waits on "
        "it, and what that will need.",
    )
    sim.note(
        "Every command has been telling claude-1 it has unread messages. It reads them before taking its own task: "
        "the human's answer, and its own assignment."
    )
    sim.swarm("inbox", who="claude-1", expect=("Answer to Q1", "You are assigned H-api"))
    sim.swarm("claim", "H-api", who="claude-1", expect=("feeds (next):", "-> H-tests"))
    sim.swarm("claim", "H-docs", who="opencode-1", expect=("claimed H-docs",))
    sim.note("qoder-1 asks for work, but nothing it may take is free yet: H-tests waits on H-api.")
    sim.swarm("next", who="qoder-1", ok=False, expect=("Nothing you can take",))

    # 6. planning, with an overlap
    sim.section(
        "6. Plans, and a conflict caught before it happens",
        "Plans answer the task-level questions and list "
        "ordered steps. opencode-1's scope overlaps claude-1's (both touch README.md), so its plan is refused "
        "until it says how they avoid the clash.",
    )
    plan_common = [
        "--set=out_of_scope=anything outside the scope above",
        "--set=dependencies=none beyond main",
        "--set=risks=low; README is shared with another task",
        "--set=rollback=revert the squash commit",
        "--set=unknowns=none",
    ]
    api = sim.worktree("H-api")
    sim.swarm(
        "plan",
        "--set=outcome=health() in src/app.py and README lists it",
        "--set=acceptance=calling health() by hand prints status ok and 1.4.0",
        "--set=scope=src/,README.md",
        *plan_common,
        "--step",
        "add health() to src/app.py",
        "--step",
        "list health() in README endpoints",
        who="claude-1",
        cwd=api,
        expect=("plan recorded",),
    )
    docs = sim.worktree("H-docs")
    docs_plan = [
        "--set=outcome=docs/api.md and README describe health()",
        "--set=acceptance=docs/api.md names both fields and README links it",
        "--set=scope=docs/,README.md",
        *plan_common,
        "--step",
        "write docs/api.md for health()",
        "--step",
        "link docs/api.md from README endpoints",
    ]
    sim.swarm("plan", *docs_plan, who="opencode-1", cwd=docs, ok=False, expect=("overlaps",))
    sim.swarm(
        "plan",
        *docs_plan,
        "--ack-overlap",
        "only the Endpoints line; whoever merges second rebases",
        who="opencode-1",
        cwd=docs,
        expect=("plan recorded",),
    )

    # 7. claude-1 works and merges
    sim.section(
        "7. Work in order, with evidence, then join it to main",
        "Steps are recorded in order, each with "
        "evidence. `merge` joins the single queue: it rebases onto main, runs the gate on the rebased "
        "result, and only then advances main. Only after that is the agent free.",
    )
    sim.swarm("start", who="claude-1", cwd=api)
    sim.write(api / "src" / "app.py", APP + '\n\ndef health():\n    return {"status": "ok", "version": VERSION}\n')
    sim.swarm(
        "step",
        "1",
        "--evidence",
        "python -c 'import app; print(app.health())' printed status ok, 1.4.0",
        who="claude-1",
        cwd=api,
    )
    sim.write(api / "README.md", "# shop\n\nA small service.\n\nEndpoints: health()\n")
    sim.block("git diff   # in claude-1's worktree", sim.git("diff", cwd=api))
    sim.commit("H-api", "claude-1", "health() and README")
    sim.swarm("step", "2", "--evidence", "README Endpoints line now reads health()", who="claude-1", cwd=api)
    sim.swarm(
        "submit",
        "--evidence",
        "health() prints ok and 1.4.0; unittest passes",
        "--changelog",
        "health() reports status and version",
        who="claude-1",
        cwd=api,
        expect=("ready to merge",),
    )
    sim.swarm("merge", who="claude-1", cwd=repo, expect=("merged H-api",))
    sim.note("The merge told opencode-1, whose scope it touched, to rebase now rather than later.")
    sim.swarm("inbox", who="opencode-1", expect=("rebase",))

    # 8. a real conflict
    sim.section(
        "8. A real merge conflict, resolved by the agent that owns it",
        "opencode-1 changed the same README "
        "line. The queue refuses to merge it and touches nothing on main. The agent rebases in its own "
        "worktree, resolves the conflict, and submits again.",
    )
    sim.swarm("start", who="opencode-1", cwd=docs)
    sim.write(
        docs / "docs" / "api.md",
        '# API\n\n## health()\n\nReturns `{"status": "ok", "version": '
        '"<VERSION>"}`. `status` is always `ok` when the service answers.\n',
    )
    sim.swarm("step", "1", "--evidence", "docs/api.md describes status and version", who="opencode-1", cwd=docs)
    sim.write(docs / "README.md", "# shop\n\nA small service.\n\nEndpoints: see docs/api.md\n")
    sim.commit("H-docs", "opencode-1", "docs for health()")
    sim.swarm("step", "2", "--evidence", "README Endpoints line points at docs/api.md", who="opencode-1", cwd=docs)
    sim.swarm(
        "submit",
        "--evidence",
        "docs/api.md and README reviewed",
        "--changelog",
        "operator docs for health()",
        who="opencode-1",
        cwd=docs,
    )
    sim.swarm("merge", who="opencode-1", cwd=repo, expect=("conflicts in", "README.md"))
    sim.git("rebase", "main", cwd=docs, ok=False)
    sim.write(docs / "README.md", "# shop\n\nA small service.\n\nEndpoints: health() (see docs/api.md)\n")
    sim.git("add", "README.md", cwd=docs)
    sim.git("rebase", "--continue", cwd=docs, who="opencode-1")
    sim.block(
        "git rebase main   # in opencode-1's worktree; README.md conflicts, resolved by hand, then --continue",
        "Successfully rebased and updated refs/heads/agent/H-docs.",
    )
    sim.swarm(
        "submit",
        "--evidence",
        "conflict resolved: README lists health() and links docs/api.md",
        "--changelog",
        "operator docs for health()",
        who="opencode-1",
        cwd=docs,
    )
    sim.swarm("merge", who="opencode-1", cwd=repo, expect=("merged H-docs",))

    # 9. silence and take-over
    sim.section(
        "9. An agent goes silent; another continues its work",
        "qoder-1 takes H-tests (its input, H-api, has "
        "merged), reads what H-api produced, plans and starts, then stops answering. The service marks it "
        "offline and, after the reclaim window, orphans the task with its branch and worktree intact.",
    )
    sim.swarm("next", who="qoder-1", expect=("claimed H-tests", "produced: health() reports status and version"))
    tests_wt = sim.worktree("H-tests")
    sim.swarm(
        "plan",
        "--set=outcome=tests/test_health.py checks health()",
        "--set=acceptance=python -m unittest discover -s tests passes with the new test",
        "--set=scope=tests/",
        *plan_common,
        "--step",
        "write tests/test_health.py",
        "--step",
        "run the suite and commit",
        who="qoder-1",
        cwd=tests_wt,
    )
    sim.swarm("start", who="qoder-1", cwd=tests_wt)
    sim.age_agent("qoder-1", 1)
    sim.note(
        "_(Simulated: an hour passes with no heartbeat from qoder-1.)_ The service marks it offline but leaves "
        "its task alone: a crashed agent often comes back."
    )
    sim.swarm("status", expect=("H-tests",))
    sim.swarm("agents", expect=("offline",))
    sim.age_agent("qoder-1", 3)
    sim.note(
        "_(Simulated: two more hours pass, beyond the two-hour reclaim window.)_ The task is orphaned: its "
        "branch, worktree and plan stay, ready for someone else."
    )
    sim.swarm("status", expect=("orphaned",))
    sim.swarm("claim", "H-tests", "--take-over", who="claude-1", expect=("claimed H-tests",))
    sim.note("If qoder-1 comes back, it is fenced: nothing it does counts until it rejoins, and then it holds nothing.")
    sim.swarm("whoami", who="qoder-1", ok=False, expect=("offline",))

    # 10. a failing gate
    sim.section(
        "10. The gate catches a mistake",
        "claude-1 continues qoder-1's plan, but its first test expects the "
        "wrong value. The gate runs on the rebased branch, fails, and nothing reaches main.",
    )
    sim.write(
        tests_wt / "tests" / "test_health.py",
        APP_TEST.replace("class Greet", "class Health").replace(
            'def test_greet(self):\n        self.assertEqual(app.greet("ada"), "hello ada")',
            'def test_health(self):\n        self.assertEqual(app.health(), {"status": "fine", "version": app.VERSION})',
        ),
    )
    sim.swarm("step", "1", "--evidence", "wrote tests/test_health.py", who="claude-1", cwd=tests_wt)
    sim.commit("H-tests", "claude-1", "test health()")
    sim.swarm("step", "2", "--evidence", "committed the test", who="claude-1", cwd=tests_wt)
    sim.swarm("submit", "--evidence", "test written", "--changelog", "health() is tested", who="claude-1", cwd=tests_wt)
    sim.swarm("merge", who="claude-1", cwd=repo, expect=("Gates failed",))
    sim.write(
        tests_wt / "tests" / "test_health.py",
        (tests_wt / "tests" / "test_health.py").read_text(encoding="utf-8").replace('"fine"', '"ok"'),
    )
    sim.note("claude-1 reads the failure, fixes the expected value, and submits again.")
    sim.block("git diff   # in claude-1's worktree", sim.git("diff", cwd=tests_wt))
    sim.commit("H-tests", "claude-1", "expect ok")
    sim.swarm(
        "submit",
        "--evidence",
        "python -m unittest discover -s tests: 2 tests OK",
        "--changelog",
        "health() is tested",
        who="claude-1",
        cwd=tests_wt,
    )
    sim.swarm("merge", who="claude-1", cwd=repo, expect=("merged H-tests",))

    # 11. closing with evidence
    sim.section(
        "11. Done means the outcomes are checked, not just the tasks merged",
        "Closing the goal needs the result of each outcome's own check. The coordinator runs them on main.",
    )
    sim.swarm("goal", "close", "health", who="claude-1", ok=False, expect=("Run each outcome's check",))
    health = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0, 'src'); import app; print(app.health())"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    suite = (
        subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        .stderr.strip()
        .splitlines()[-1]
    )
    sim.block('python -c "import app; print(app.health())"   # on main', health)
    sim.block("python -m unittest discover -s tests -q   # on main", suite)
    sim.swarm(
        "goal",
        "close",
        "health",
        f"--evidence=1=health() printed {health}",
        f"--evidence=2=unittest on main: {suite}, including test_health",
        "--evidence=3=docs/api.md describes status and version; README lists health()",
        who="claude-1",
        expect=("closed",),
    )

    # 12. what remains
    sim.section(
        "12. What is left behind",
        "Main carries one squash commit per task. Every worktree and task branch "
        "is gone, and the board remembers who did what.",
    )
    log = sim.git("log", "--oneline", "main", cwd=repo)
    sim.block("git log --oneline main", log)
    sim.note(
        "The coordinator's inbox holds what the service flagged along the way. It warned about steps finished within "
        "two minutes of starting: worth checking in real work, expected here because the simulation runs instantly. "
        "It also said that H-tests was orphaned."
    )
    sim.swarm("inbox", who="claude-1", expect=("orphaned",))
    sim.swarm("goal", "list", expect=("closed",))
    sim.swarm("agents")
    if "H-api: Add health()" not in log or "H-tests: Test health()" not in log:
        raise Diverged("main does not carry the merged tasks:\n" + log)
    leftover = sim.git("worktree", "list", cwd=repo).splitlines()
    if len(leftover) != 1:
        raise Diverged("worktrees were left behind:\n" + "\n".join(leftover))
    sim.note(
        "**What to take from it:**\n\n"
        "- No task was touched before its questions were answered.\n"
        "- A missing outcome, an overlap, a conflict, a silent agent and a wrong test were each caught, by the "
        "service, at the point they happened, with the next step named.\n"
        "- Main only ever moved through the queue, after the gate passed on the rebased result.\n"
        "- The goal closed on evidence for its outcomes, not on merged tasks alone."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", default="", help="write the transcript to this file")
    parser.add_argument("--check", action="store_true", help="run every milestone; print only the outcome")
    args = parser.parse_args()
    base = Path(tempfile.mkdtemp(prefix="swarm-sim-"))
    sim = Sim(base)
    try:
        run(sim)
    except Diverged as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=sim.repo, capture_output=True, check=False)
        shutil.rmtree(base, ignore_errors=True)
    text = "\n".join(sim.out).rstrip() + "\n"
    if args.check:
        print("simulation: every milestone held")
    elif args.write:
        Path(args.write).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.write}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
