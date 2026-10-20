"""Run fixed coding tasks in solo, uncoordinated and coordinated local trials.

    python scripts/workforce_bench.py --output /path/to/new/trial
    python scripts/workforce_bench.py --output /path/to/new/trial --runner runner.json

The default deterministic runner tests mechanics, not LLM productivity. runner.json is an argv
array for a real agent; placeholders are {assignment}, {result}, {worktree}. No shell is used.
Artifacts, branches and worktrees are retained. External tools execute with the user's permissions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
MODES = ("solo", "uncoordinated", "coordinated")
TASKS = {
    "T1": {
        "title": "Parse whole seconds or minutes",
        "test": "test_duration.Parse",
        "requirement": "Implement parse_seconds(value): nonnegative integer followed by s or m; return seconds; reject other inputs with ValueError.",
        "stub": 'raise NotImplementedError("parse")',
        "solution": "if not isinstance(value, str) or len(value) < 2 or value[-1] not in 'sm' or not value[:-1].isascii() or not value[:-1].isdigit():\n        raise ValueError('invalid duration')\n    return int(value[:-1]) * (60 if value[-1] == 'm' else 1)",
    },
    "T2": {
        "title": "Format whole seconds",
        "test": "test_duration.Format",
        "requirement": "Implement format_seconds(value): nonnegative int excluding bool; use m for exact multiples of 60 including zero, otherwise s; reject other inputs with ValueError.",
        "stub": 'raise NotImplementedError("format")',
        "solution": "if type(value) is not int or value < 0:\n        raise ValueError('invalid seconds')\n    return str(value // 60) + 'm' if value % 60 == 0 else str(value) + 's'",
    },
}
CODE = """def parse_seconds(value):
    raise NotImplementedError("parse")


def format_seconds(value):
    raise NotImplementedError("format")
"""
CHECKS = """import unittest
from durations import parse_seconds, format_seconds

class Parse(unittest.TestCase):
    def test_valid(self):
        for text, want in [('0s', 0), ('2m', 120), ('61s', 61), ('123m', 7380)]:
            self.assertEqual(parse_seconds(text), want)
    def test_invalid(self):
        for text in ['', 's', '-1m', '1.5m', '1h', ' 1s', '1s ', 2, True, None, '²s']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_seconds(text)

class Format(unittest.TestCase):
    def test_valid(self):
        for value, want in [(0, '0m'), (120, '2m'), (61, '61s'), (7380, '123m')]:
            self.assertEqual(format_seconds(value), want)
    def test_invalid(self):
        for value in [-1, 1.5, '60', True, None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                format_seconds(value)
"""


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class Trial:
    def __init__(self, root, mode, runner, deadline, fault=None):
        self.root, self.mode, self.runner, self.deadline = root, mode, runner, deadline
        self.repo = root / "repo"
        self.repo.mkdir(parents=True)
        self.env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "workforce trial",
            "GIT_AUTHOR_EMAIL": "trial@example.invalid",
            "GIT_COMMITTER_NAME": "workforce trial",
            "GIT_COMMITTER_EMAIL": "trial@example.invalid",
        }
        for key in ("SWARM_AS", "SWARM_EPOCH", "SWARM_TASK", "SWARM_SLOT", "SWARM_FAILPOINT"):
            self.env.pop(key, None)
        self.counter = 0
        self.records = []
        self.fault, self.fault_result = fault, None

    def run(self, argv, cwd=None, required=True, timeout=300, env=None):
        done = subprocess.run(
            argv,
            cwd=cwd or self.repo,
            env={**self.env, **(env or {})},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if required and done.returncode:
            raise RuntimeError(f"command failed ({done.returncode}): {argv}\n{done.stdout}\n{done.stderr}")
        return done

    def git(self, *args, cwd=None, required=True):
        return self.run(["git", *args], cwd, required)

    def swarm(self, *args, env=None, required=True):
        tool = self.repo / ".agents/skills/agents-collaboration/hivewire.py"
        return self.run([sys.executable, str(tool), *args], env=env, required=required)

    def setup(self):
        self.git("init", "-q", "-b", "main")
        (self.repo / "durations.py").write_text(CODE, encoding="utf-8")
        (self.repo / "test_duration.py").write_text(CHECKS, encoding="utf-8")
        (self.repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        self.run(
            [sys.executable, str(SOURCE / "install.py"), "--source", str(SOURCE), "--project", str(self.repo), "--all"]
        )
        cfg = self.repo / ".agents/swarm"
        cfg.mkdir(parents=True)
        # Both modes use the same per-task verifier. Full acceptance always runs independently at the end.
        gate = [
            sys.executable,
            "-c",
            "import os,subprocess,sys; name={'T1':'Parse','T2':'Format'}[os.environ['SWARM_TASK']]; sys.exit(subprocess.call([sys.executable,'-m','unittest','test_duration.'+name]))",
        ]
        (cfg / "config.toml").write_text(
            '[project]\ntarget = "main"\nbacklog = "backlog.md"\ncheck_remote = false\n'
            "[gates]\ncommands = " + json.dumps([gate]) + '\n[hotspots]\nduration = { paths = ["durations.py"] }\n',
            encoding="utf-8",
        )
        backlog = "| Id | Title | Scope | Needs | Locks | Caps |\n|---|---|---|---|---|---|\n"
        backlog += "".join(
            f"| {tid} | {task['title']} | durations.py | — | duration | |\n" for tid, task in TASKS.items()
        )
        (self.repo / "backlog.md").write_text(backlog, encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "fixed duration workload v1")
        self.baseline = self.git("rev-parse", "HEAD").stdout.strip()
        self.verifier_hash = hashlib.sha256((self.repo / "test_duration.py").read_bytes()).hexdigest()

    def prepare(self, tid, worker, base="main", suffix=""):
        if self.mode == "coordinated":
            self.swarm("join", "--as", worker, "--kind", "scripted" if not self.runner else "external")
            self.swarm("claim", tid, "--as", worker)
            data = json.loads(self.swarm("status", "--json").stdout)["result"]
            task = next(t for t in data["tasks"] if t["id"] == tid)
            tree = Path(task["worktree"])
            answers = {
                "outcome": TASKS[tid]["requirement"],
                "acceptance": TASKS[tid]["test"],
                "scope": "durations.py",
                "out_of_scope": "acceptance tests and other functions",
                "dependencies": "fixed workload committed",
                "risks": "local fixture only",
                "rollback": "git revert",
                "unknowns": "none",
            }
            self.swarm(
                "plan",
                "--as",
                worker,
                *[v for k, text in answers.items() for v in ("--set", f"{k}={text}")],
                "--step",
                "implement and verify duration operation",
            )
            self.swarm("start", "--as", worker)
        else:
            tree = self.root / f"{tid}{suffix}"
            self.git("worktree", "add", "-q", "-b", f"trial/{tid}{suffix}", str(tree), base)
        return tree

    def edit(self, tid, tree, attempt):
        assignment = self.root / f"{tid}-{attempt}-assignment.json"
        result_file = self.root / f"{tid}-{attempt}-usage.json"
        write_json(
            assignment,
            {
                "version": 1,
                "task": tid,
                "mode": self.mode,
                "agent": "worker-1" if self.mode == "solo" else f"worker-{list(TASKS).index(tid) + 1}",
                "requirement": TASKS[tid]["requirement"],
                "scope": ["durations.py"],
                "acceptance_command": [sys.executable, "-m", "unittest", TASKS[tid]["test"]],
                "deadline_seconds": self.deadline,
                "attempt": attempt,
                "result_file": str(result_file),
                "usage": "Optional JSON: cost, currency, tokens, human_interventions. Unknown values must be null.",
            },
        )
        if self.runner:
            values = {"assignment": str(assignment), "result": str(result_file), "worktree": str(tree)}
            argv = [part.format(**values) for part in self.runner]
        else:
            argv = [sys.executable, str(Path(__file__).resolve()), "--scripted-edit", tid]
        started = time.monotonic()
        failure = None
        try:
            # Reuse owned jobs/groups so timed-out runners cannot leave live group descendants.
            sys.path.insert(0, str(SOURCE / "skills" / "agents-collaboration"))
            import swarm_core

            done = swarm_core.run_owned(argv, tree, self.env, self.deadline)
            (self.root / f"{tid}-{attempt}-runner.log").write_text(done.stdout + done.stderr, encoding="utf-8")
            if done.returncode:
                failure = f"runner exited {done.returncode}"
        except subprocess.TimeoutExpired:
            failure = "runner exceeded its deadline"
        except Exception as exc:
            failure = f"runner refused ({type(exc).__name__}): {exc}"
        log_file = self.root / f"{tid}-{attempt}-runner.log"
        if not log_file.exists():
            log_file.write_text(failure or "", encoding="utf-8")
        usage = {"cost": None, "currency": None, "tokens": None, "human_interventions": None if self.runner else 0}
        if result_file.exists():
            raw = json.loads(result_file.read_text(encoding="utf-8"))
            for key in usage:
                value = raw.get(key)
                if value is not None and (
                    type(value) is not str
                    if key == "currency"
                    else type(value) not in (int, float) or not 0 <= value < float("inf")
                ):
                    raise ValueError(f"Invalid runner usage {key}")
                if key in ("tokens", "human_interventions") and value is not None and type(value) is not int:
                    raise ValueError(f"Runner usage {key} must be a nonnegative integer or null")
                usage[key] = value
        return {
            "task": tid,
            "attempt": attempt,
            "runner_seconds": time.monotonic() - started,
            "failure": failure,
            "usage": usage,
        }

    def check(self, tree, tid=None):
        if hashlib.sha256((tree / "test_duration.py").read_bytes()).hexdigest() != self.verifier_hash:
            return False
        if self.git("ls-files", "--others", "--exclude-standard", cwd=tree).stdout.strip():
            return False
        files = self.git("diff", "--name-only", self.baseline, cwd=tree).stdout.splitlines()
        if any(name != "durations.py" for name in files):
            return False
        argv = (
            [sys.executable, "-m", "unittest", TASKS[tid]["test"]]
            if tid
            else [sys.executable, "-m", "unittest", "test_duration"]
        )
        done = self.run(argv, cwd=tree, required=False)
        self.counter += 1
        (self.root / f"check-{self.counter}.log").write_text(done.stdout + done.stderr, encoding="utf-8")
        return done.returncode == 0

    def integrate(self, tid, worker, tree):
        self.git("add", "--", "durations.py", cwd=tree)
        if self.git("diff", "--cached", "--quiet", cwd=tree, required=False).returncode:
            self.git("commit", "-qm", f"implement {tid}", cwd=tree)
        if self.mode == "coordinated":
            self.swarm("step", "1", "--as", worker, "--evidence", f"independent {TASKS[tid]['test']} passed")
            self.swarm("submit", "--as", worker, "--evidence", f"independent {TASKS[tid]['test']} passed")
            if self.fault and tid == "T1":
                killed = self.swarm(
                    "merge", "--as", worker, "--json", required=False, env={"SWARM_FAILPOINT": self.fault}
                )
                state = json.loads(self.swarm("status", "--json").stdout)["result"]
                task = next(t for t in state["tasks"] if t["id"] == tid)
                events = json.loads(self.swarm("events", "--limit", "1000", "--json").stdout)["result"]["events"]
                completions = sum(e["task"] == tid and e["kind"] in ("merged", "merge_recovered") for e in events)
                self.fault_result = {
                    "point": self.fault,
                    "process_exit_code": killed.returncode,
                    "recovered_state": task["state"],
                    "completion_events": completions,
                    "retained_check_proof": bool((task["integration_evidence"] or {}).get("verification")),
                }
                write_json(self.root / "fault.json", self.fault_result)
                if killed.returncode != 97 or task["state"] != "done" or completions != 1:
                    return False
            done = self.swarm("merge", "--as", worker, "--json")
            return json.loads(done.stdout)["result"]["task"]["state"] == "done"
        rebase = self.git("rebase", "main", cwd=tree, required=False)
        if rebase.returncode:
            self.git("rebase", "--abort", cwd=tree, required=False)
            return False
        if not self.check(tree, tid):
            return False
        self.git("merge", "--ff-only", str(self.git("rev-parse", "HEAD", cwd=tree).stdout.strip()))
        return True

    def execute(self):
        self.setup()
        started = time.monotonic()
        trees, dispatch, workers = {}, {}, {}
        for i, tid in enumerate(TASKS, 1):
            workers[tid] = f"worker-{i}"
        # The shared-file hotspot serializes the coordinated wave. Uncoordinated agents start together
        # from the same baseline; the resulting integration work is measured, not silently repaired.
        if self.mode == "uncoordinated":
            for tid in TASKS:
                trees[tid] = self.prepare(tid, workers[tid], base=self.baseline)
                dispatch[tid] = time.monotonic()
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {tid: pool.submit(self.edit, tid, tree, 1) for tid, tree in trees.items()}
                records = {tid: future.result() for tid, future in futures.items()}
        else:
            records = {}
        for tid in TASKS:
            if self.mode != "uncoordinated":
                trees[tid] = self.prepare(tid, workers[tid])
                dispatch[tid] = time.monotonic()
                records[tid] = self.edit(tid, trees[tid], 1)
            record = records[tid]
            verified = not record["failure"] and self.check(trees[tid], tid)
            rework = 0
            if verified:
                verified = self.integrate(tid, workers[tid], trees[tid])
                if not verified and self.mode == "uncoordinated":
                    # Preserve the original branch; one bounded retry starts from the integrated target.
                    rework = 1
                    retry_tree = self.prepare(tid, workers[tid], suffix="-retry")
                    retry = self.edit(tid, retry_tree, 2)
                    self.records.append({**retry, "verified": False, "integration_retry": True})
                    verified = (
                        not retry["failure"]
                        and self.check(retry_tree, tid)
                        and self.integrate(tid, workers[tid], retry_tree)
                    )
            record.update(
                verified=bool(verified),
                rework=rework,
                elapsed_seconds=time.monotonic() - dispatch[tid],
                deadline_missed=time.monotonic() - dispatch[tid] > self.deadline,
            )
            self.records.append(record)
        full_acceptance = self.check(self.repo)
        usage = {
            key: sum(r["usage"][key] for r in self.records)
            if all(r["usage"][key] is not None for r in self.records)
            else None
            for key in ("cost", "tokens", "human_interventions")
        }
        currencies = {r["usage"]["currency"] for r in self.records}
        if len(currencies) != 1 or None in currencies:
            usage["cost"] = None
        usage["currency"] = next(iter(currencies)) if len(currencies) == 1 else None
        result = {
            "version": 1,
            "workload": "duration-operations-v1",
            "mode": self.mode,
            "runner": "external" if self.runner else "scripted-mechanics-only",
            "agent_count": 1 if self.mode == "solo" else 2,
            "baseline_commit": self.baseline,
            "task_count": len(TASKS),
            "verified_completion": sum(bool(r.get("verified")) for r in self.records),
            "full_acceptance": full_acceptance,
            "rework": sum(r.get("rework", 0) for r in self.records),
            "deadline_misses": sum(bool(r.get("deadline_missed")) for r in self.records),
            "usage": usage,
            "usage_source": "runner-reported; not independently metered",
            "elapsed_seconds": time.monotonic() - started,
            "attempts": self.records,
            "fault": self.fault_result,
            "owed": (["LLM productivity comparison (scripted runner)"] if not self.runner else [])
            + (["Measured monetary cost"] if usage["cost"] is None else []),
            "limitations": [
                "Tiny shared-file conflict workload; no general productivity inference",
                "Coordinated workers serialize the declared hotspot",
                "Unknown cost or human intervention is null, never zero",
                "Run repeated matched trials before drawing comparisons",
            ],
        }
        write_json(self.root / "results.json", result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=(*MODES, "all"), default="all")
    parser.add_argument("--runner", type=Path, help="JSON argv array; executes a real agent in each worktree")
    parser.add_argument("--deadline-seconds", type=float, default=300)
    parser.add_argument(
        "--fault", choices=["after_target_moved"], help="kill/recover T1 during coordinated integration"
    )
    parser.add_argument("--scripted-edit", choices=TASKS, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.scripted_edit:
        path = Path("durations.py")
        task = TASKS[args.scripted_edit]
        text = path.read_text(encoding="utf-8")
        if task["stub"] not in text:
            raise ValueError("The task stub is absent; preserve the worktree and inspect this trial.")
        path.write_text(text.replace(task["stub"], task["solution"], 1), encoding="utf-8")
        return 0
    if not args.output or not 0 < args.deadline_seconds < float("inf"):
        parser.error("--output is required and --deadline-seconds must be positive and finite")
    runner = json.loads(args.runner.read_text(encoding="utf-8")) if args.runner else None
    if runner is not None and (
        not isinstance(runner, list) or not runner or not all(isinstance(v, str) and v for v in runner)
    ):
        parser.error("--runner must contain a nonempty JSON argv array")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for mode in MODES if args.mode == "all" else (args.mode,):
        trial = None
        try:
            trial = Trial(output / mode, mode, runner, args.deadline_seconds, args.fault)
            result = trial.execute()
        except Exception as exc:
            attempts = trial.records if trial else []
            result = {
                "version": 1,
                "mode": mode,
                "full_acceptance": False,
                "verified_completion": sum(bool(r.get("verified")) for r in attempts),
                "task_count": len(TASKS),
                "failure": str(exc),
                "failure_type": type(exc).__name__,
                "incomplete": True,
                "attempts": attempts,
                "owed": ["Trial did not finish; inspect retained artifacts before comparing modes"],
            }
            write_json(output / mode / "results.json", result)
        results.append(result)
    report = {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "results": results,
        "claim": "Measured local trial outcomes only; no LLM improvement claim",
    }
    write_json(output / "comparison.json", report)
    print(json.dumps(report, indent=2))
    return 0 if all(r["full_acceptance"] and r["verified_completion"] == r["task_count"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
