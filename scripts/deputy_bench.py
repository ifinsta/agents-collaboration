"""Compare solo, coordinator-only and coordinator+deputy triage on a fixed scripted workload.

    python scripts/deputy_bench.py
    python scripts/deputy_bench.py --trials 5 --json
    python scripts/deputy_bench.py --keep /tmp/deputy-bench

Every arm runs in a throwaway Git repository with the same three verified tasks and the same two
seeded signals (a critical unacknowledged message and a failed task). Worker steps are fixed CLI
calls, not LLM work: this measures coordination overhead, triage latency, false alarms and
recovery on the tested host. It is not evidence of model-driven throughput.

Fault checks run in separate repositories: deputy crash recovery, scope violation fencing,
all-five-busy capacity, and coordinator term change. Exit status is non-zero if any arm loses a
verified task or any fault check fails.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
TOOL = SOURCE / "skills" / "agents-collaboration" / "hivewire.py"
ARMS = ("solo", "coordinator", "coordinator+deputy")
TASKS = {"T1": "src/", "T2": "docs/", "T3": "lib/"}
STUCK = "T6"
GATES = [["python", "-c", "import pathlib,sys; sys.exit(1 if pathlib.Path('FAIL').exists() else 0)"]]
CONFIG = f"""[project]
target = "main"
branch_prefix = "swarm/"
backlog = "backlog.md"
check_remote = false

[swarm]
max_agents = 5

[gates]
commands = {json.dumps(GATES)}

[hotspots]
config = {{ paths = ["config/**"] }}

[deputy]
enabled = true
"""
BACKLOG = """# Backlog

| Id | Title | Scope | Needs | Locks | Caps |
|---|---|---|---|---|---|
| T1 | First task | src/ | — | — | |
| T2 | Second task | docs/ | — | — | |
| T3 | Needs T1 | lib/ | T1 | — | |
| T6 | Stuck task | ops/ | — | — | |
| T7 | Capacity task A | lib/ | — | — | |
| T8 | Capacity task B | ops/ | — | — | |
"""
def plan_args(tid: str, scope: str) -> list[str]:
    return [
        "--set", "outcome=the task file exists",
        "--set", "acceptance=gates pass",
        "--set", f"scope={scope}",
        "--set", "out_of_scope=everything else",
        "--set", f"dependencies={'T1' if tid == 'T3' else 'none'}",
        "--set", "risks=low",
        "--set", "rollback=git revert",
        "--set", "unknowns=none",
        "--step", "write the task file",
        "--step", "commit the task file",
    ]
CRITICAL = "The interface decision is blocking the release and needs an owner"
FINDING = "The critical signal has waited beyond its response SLA without an owner"
RECOMMEND = "The coordinator should answer the message or name a decision owner"
REASON = "Delegated triage finished; the coordinator records the decision"
ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "deputy bench",
    "GIT_AUTHOR_EMAIL": "bench@example.invalid",
    "GIT_COMMITTER_NAME": "deputy bench",
    "GIT_COMMITTER_EMAIL": "bench@example.invalid",
    "PYTHONIOENCODING": "utf-8",
}
ENV.pop("SWARM_AS", None)


class BenchError(RuntimeError):
    pass


class Trial:
    def __init__(self, root: Path, arm: str):
        self.root, self.arm = root, arm
        self.repo = root / "repo"
        self.repo.mkdir(parents=True)
        self.coord_actions = self.deputy_actions = 0
        self.coord_s = self.deputy_s = 0.0
        self.scan_s = 0.0

    def run(self, argv, cwd=None, required=True):
        started = time.perf_counter()
        done = subprocess.run(
            [sys.executable, str(TOOL), *argv],
            cwd=cwd or self.repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=ENV,
            timeout=300,
            check=False,
        )
        elapsed = time.perf_counter() - started
        out = done.stdout + done.stderr
        if required and done.returncode:
            raise BenchError(f"{' '.join(argv)} failed ({done.returncode}):\n{out}")
        return out, elapsed

    def j(self, *argv, **kwargs):
        out, seconds = self.run([*argv, "--json"], **kwargs)
        return json.loads(out)["result"], seconds

    def tracked(self, who, *argv, **kwargs):
        out, seconds = self.run([*argv, "--as", who], **kwargs)
        if who == "ann":
            self.coord_actions += 1
            self.coord_s += seconds
        elif who != "bob":
            self.deputy_actions += 1
            self.deputy_s += seconds
        return out, seconds

    def git(self, *argv, cwd=None):
        done = subprocess.run(["git", *argv], cwd=cwd or self.repo, capture_output=True, text=True, env=ENV, check=False)
        if done.returncode:
            raise BenchError(f"git {' '.join(argv)} failed:\n{done.stdout}{done.stderr}")
        return done.stdout

    def db(self):
        return sqlite3.connect(self.repo / ".git" / "swarm" / "swarm.db")

    def setup(self):
        self.git("init", "-q", "-b", "main")
        (self.repo / ".agents" / "swarm").mkdir(parents=True)
        (self.repo / ".agents" / "swarm" / "config.toml").write_text(CONFIG, encoding="utf-8")
        (self.repo / "backlog.md").write_text(BACKLOG, encoding="utf-8")
        for scope in ("src", "docs", "lib", "ops"):
            (self.repo / scope).mkdir()
            (self.repo / scope / ".gitkeep").write_text("", encoding="utf-8")
        (self.repo / ".gitignore").write_text("__pycache__/\nFAIL\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "bench fixture")
        self.run(["join", "--kind", "claude", "--as", "ann"])
        self.run(["join", "--kind", "claude", "--as", "bob"])
        if self.arm == "coordinator+deputy":
            self.run(["join", "--kind", "claude", "--as", "cat"])

    def seed(self):
        self.run(["send", "ann", CRITICAL, "--as", "human", "--priority", "critical", "--kind", "warning"])
        old = (time.time() - 3600)
        con = self.db()
        try:
            con.execute("UPDATE messages SET created_at=? WHERE id=(SELECT MAX(id) FROM messages)", (time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(old)),))
            con.execute("UPDATE tasks SET state='gates_failed',epoch=3 WHERE id=?", (STUCK,))
            con.commit()
        finally:
            con.close()
        result, seconds = self.j("deputy", "scan", "--once")
        self.scan_s = seconds
        return result["created_count"]

    def items(self):
        result, _ = self.j("attention", "list", "--all")
        return result["items"]

    def work(self, who, tid):
        self.run(["claim", tid, "--as", who])
        state, _ = self.j("status")
        task = next(t for t in state["tasks"] if t["id"] == tid)
        tree = Path(task["worktree"])
        scope = TASKS[tid]
        self.run(["plan", *plan_args(tid, scope), "--as", who], cwd=tree)
        self.run(["start", "--as", who], cwd=tree)
        target = tree / scope / f"{tid.lower()}.txt"
        target.write_text(f"{tid} done\n", encoding="utf-8")
        self.run(["step", "1", "--as", who, "--evidence", f"wrote {scope}{tid.lower()}.txt"], cwd=tree)
        self.git("add", ".", cwd=tree)
        self.git("commit", "-qm", f"work {tid}", cwd=tree)
        self.run(["step", "2", "--as", who, "--evidence", "committed the task file"], cwd=tree)
        self.run(["submit", "--as", who, "--evidence", "gates pass locally"], cwd=tree)

    def merge(self, who="ann"):
        return self.tracked(who, "merge")

    def triage(self):
        started = time.perf_counter()
        first = None
        items = [i for i in self.items() if i["subject_ref"] == f"task:{STUCK}" or i["kind"] == "message"]
        if len(items) < 2:
            raise BenchError(f"expected two seeded attention items, found {[i['subject_ref'] for i in items]}")
        if self.arm == "coordinator+deputy":
            self.tracked("ann", "deputy", "activate", "cat", "--scope", "message:*,task:T6", "--minutes", "10")
            for item in items:
                self.tracked("cat", "attention", "claim", str(item["id"]))
                if first is None:
                    first = time.perf_counter() - started
                self.tracked("cat", "attention", "investigate", str(item["id"]), "--note",
                             "Checking the receipt, task epoch and recent events before proposing an action")
                self.tracked(
                    "cat", "attention", "report", str(item["id"]),
                    "--finding", f"{FINDING} (A{item['id']}, {item['subject_ref']})",
                    "--evidence", f"sqlite:{item['subject_ref'].replace(':', '/', 1)}",
                    "--recommend", RECOMMEND,
                )
            for item in items:
                self.tracked("ann", "attention", "resolve", str(item["id"]), "--disposition", "resolved", "--reason", REASON)
            self.tracked("ann", "deputy", "release", "--reason", "Bounded shift finished; returning the agent to the pool", "--force")
        else:
            who = "ann"
            for item in items:
                self.tracked(who, "attention", "claim", str(item["id"]))
                if first is None:
                    first = time.perf_counter() - started
                self.tracked(who, "attention", "resolve", str(item["id"]), "--disposition", "resolved", "--reason", REASON)
        return time.perf_counter() - started, first or 0.0, items

    def execute(self):
        self.setup()
        seeded = self.seed()
        started = time.perf_counter()
        triage_s, first_claim_s, items = self.triage()
        merged = 0
        who = "ann" if self.arm == "solo" else "bob"
        for tid in TASKS:
            self.work(who, tid)
            self.merge(who)
            state, _ = self.j("status")
            merged += sum(1 for t in state["tasks"] if t["id"] == tid and t["state"] == "done")
        elapsed = time.perf_counter() - started
        all_items = self.items()
        unseeded = [i for i in all_items if i["subject_ref"] != f"task:{STUCK}" and i["kind"] != "message"]
        con = self.db()
        try:
            false_alarms = con.execute("SELECT COUNT(*) FROM attention_items WHERE disposition='false_alarm'").fetchone()[0]
            escalations = con.execute("SELECT COUNT(*) FROM attention_items WHERE status='escalated'").fetchone()[0]
            reopened = con.execute("SELECT COUNT(*) FROM attention_history WHERE new_status='reopened'").fetchone()[0]
        finally:
            con.close()
        return {
            "arm": self.arm,
            "seed_created": seeded,
            "verified": merged,
            "expected": len(TASKS),
            "lost": len(TASKS) - merged,
            "total_s": elapsed,
            "tasks_per_hour": merged / elapsed * 3600 if elapsed else 0,
            "scan_s": self.scan_s,
            "triage_s": triage_s,
            "first_claim_s": first_claim_s,
            "coord_actions": self.coord_actions,
            "coord_s": self.coord_s,
            "deputy_actions": self.deputy_actions,
            "deputy_s": self.deputy_s,
            "unseeded": len(unseeded),
            "false_alarms": false_alarms,
            "escalations": escalations,
            "rework": reopened,
        }


def fault_crash(root: Path) -> dict:
    trial = Trial(root, "coordinator+deputy")
    trial.setup()
    trial.seed()
    trial.tracked("ann", "deputy", "activate", "cat", "--scope", "message:*,task:T6", "--minutes", "10")
    item = next(i for i in trial.items() if i["kind"] == "message")
    trial.run(["attention", "claim", str(item["id"]), "--as", "cat", "--lease-sec", "1"])
    time.sleep(1.3)
    trial.run(["attention", "claim", str(item["id"]), "--as", "ann"])
    owner = trial.run(["attention", "show", str(item["id"]), "--as", "ann", "--json"])[0]
    owner = json.loads(owner)["result"]["item"]["owner"]
    history = trial.run(["attention", "show", str(item["id"]), "--as", "ann", "--json"])[0]
    notes = [h["note"] for h in json.loads(history)["result"]["history"]]
    failed = trial.run(
        ["attention", "report", str(item["id"]), "--as", "cat", "--finding", FINDING, "--evidence", "sqlite:messages", "--recommend", RECOMMEND],
        required=False,
    )[0]
    names = [h["new_status"] for h in json.loads(history)["result"]["history"]]
    ok = owner == "ann" and any("evidence preserved" in n for n in notes) and "does not hold" in failed and names.count("claimed") == 2
    return {"check": "deputy crash mid-claim", "ok": ok, "owner": owner, "history": len(notes)}


def fault_scope(root: Path) -> dict:
    trial = Trial(root, "coordinator+deputy")
    trial.setup()
    trial.seed()
    trial.tracked("ann", "deputy", "activate", "cat", "--scope", "message:*", "--minutes", "10")
    task_item = next(i for i in trial.items() if i["subject_ref"] == f"task:{STUCK}")
    denied = trial.run(["attention", "claim", str(task_item["id"]), "--as", "cat"], required=False)[0]
    status, _ = trial.j("deputy", "status")
    message_item = next(i for i in trial.items() if i["kind"] == "message")
    second = trial.run(["attention", "claim", str(message_item["id"]), "--as", "cat"], required=False)[0]
    ok = "outside" in denied and status["deputy"] is None and "no active deputy delegation" in second
    return {"check": "scope violation revokes", "ok": ok, "lease_revoked": status["deputy"] is None}


def fault_all_busy(root: Path) -> dict:
    trial = Trial(root, "coordinator+deputy")
    trial.setup()
    for name in ("dan", "eve"):
        trial.run(["join", "--kind", "claude", "--as", name])
    trial.seed()
    for who, tid in (("bob", "T1"), ("cat", "T2"), ("dan", "T7"), ("eve", "T8")):
        trial.run(["claim", tid, "--as", who])
    trial.j("deputy", "scan", "--once")
    status, _ = trial.j("deputy", "status")
    con = trial.db()
    try:
        live = con.execute("SELECT COUNT(*) FROM agents WHERE state NOT IN ('left','offline')").fetchone()[0]
        leases = con.execute("SELECT COUNT(*) FROM deputy_delegations WHERE state='active'").fetchone()[0]
        notices = con.execute(
            "SELECT COUNT(*) FROM messages WHERE sender='swarm' AND idempotency_key LIKE 'deputy:capacity:%'"
        ).fetchone()[0]
    finally:
        con.close()
    ok = live == 5 and leases == 0 and notices == 1 and status["candidate"]["eligible"]
    return {"check": "all five busy, no sixth slot", "ok": ok, "live": live, "leases": leases, "notices": notices}


def fault_term(root: Path) -> dict:
    trial = Trial(root, "coordinator+deputy")
    trial.setup()
    trial.seed()
    trial.tracked("ann", "deputy", "activate", "cat", "--scope", "message:*,task:T6", "--minutes", "10")
    con = trial.db()
    try:
        con.execute("UPDATE agents SET heartbeat_at='2020-01-01T00:00:00+00:00' WHERE name='ann'")
        con.commit()
    finally:
        con.close()
    status, _ = trial.j("deputy", "status")
    con = trial.db()
    try:
        reason = con.execute(
            "SELECT reason FROM deputy_delegations ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        con.close()
    ok = status["coordinator"] == "bob" and status["deputy"] is None and "coordination term changed" in (reason or "")
    return {"check": "coordinator term fences the lease", "ok": ok, "coordinator": status["coordinator"]}


def med(values):
    return round(statistics.median(values), 3) if values else 0


def p95(values):
    values = sorted(values)
    return round(values[max(0, math.ceil(0.95 * len(values)) - 1)], 3) if values else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trials", type=int, default=3, help="fresh repositories per arm (default 3)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--keep", default=None, help="keep trial repositories below this directory")
    args = parser.parse_args()
    if args.trials < 1:
        raise SystemExit("--trials must be at least 1")

    base = Path(args.keep).resolve() if args.keep else Path(tempfile.mkdtemp(prefix="deputy-bench-"))
    base.mkdir(parents=True, exist_ok=True)
    results, faults = [], []
    try:
        for arm in ARMS:
            for n in range(args.trials):
                root = base / f"{arm.replace('+', '-')}-{n + 1}"
                root.mkdir(parents=True, exist_ok=True)
                try:
                    results.append(Trial(root, arm).execute())
                except Exception as exc:
                    results.append({"arm": arm, "error": f"{type(exc).__name__}: {exc}", "verified": 0, "expected": len(TASKS), "lost": len(TASKS)})
        for check in (fault_crash, fault_scope, fault_all_busy, fault_term):
            root = base / check.__name__
            root.mkdir(parents=True, exist_ok=True)
            try:
                faults.append(check(root))
            except Exception as exc:
                faults.append({"check": check.__name__, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        pass

    arms_summary = []
    for arm in ARMS:
        runs = [r for r in results if r.get("arm") == arm]
        good = [r for r in runs if "error" not in r]
        arms_summary.append(
            {
                "arm": arm,
                "trials": len(runs),
                "errors": [r["error"] for r in runs if "error" in r],
                "verified": sum(r.get("verified", 0) for r in runs),
                "lost": sum(r.get("lost", 0) for r in runs),
                "total_s": med([r["total_s"] for r in good]),
                "tasks_per_hour": med([r["tasks_per_hour"] for r in good]),
                "scan_s": med([r["scan_s"] for r in good]),
                "triage_s": med([r["triage_s"] for r in good]),
                "p95_triage_s": p95([r["triage_s"] for r in good]),
                "time_to_first_claim_s": med([r["first_claim_s"] for r in good]),
                "p95_time_to_first_claim_s": p95([r["first_claim_s"] for r in good]),
                "coord_actions": med([r["coord_actions"] for r in good]),
                "coord_s": med([r["coord_s"] for r in good]),
                "deputy_actions": med([r["deputy_actions"] for r in good]),
                "deputy_s": med([r["deputy_s"] for r in good]),
                "unseeded": sum(r.get("unseeded", 0) for r in runs),
                "false_alarms": sum(r.get("false_alarms", 0) for r in runs),
                "escalations": sum(r.get("escalations", 0) for r in runs),
                "rework": sum(r.get("rework", 0) for r in runs),
            }
        )
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": sys.platform,
        "python": sys.version.split()[0],
        "source": str(SOURCE),
        "trials_per_arm": args.trials,
        "workload": {"tasks": list(TASKS), "stuck": STUCK, "seeded_signals": 2, "scripted": True},
        "arms": arms_summary,
        "faults": faults,
        "note": (
            "Task work is scripted CLI steps, so tasks/hour measures coordination overhead on this host, not LLM "
            "productivity. Time-to-first-claim is measured from the start of the triage round after detection; p95 is "
            "across trials. Unseeded signals are attention items other than the two seeded ones; inspect them before "
            "calling them false positives."
        ),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Deputy benchmark: {payload['host']} / Python {payload['python']} / {args.trials} trial(s) per arm")
        print("Fixed scripted workload: 3 verified tasks, 2 seeded P1 signals; wall-clock seconds.\n")
        print(f"{'arm':22} {'verified':>8} {'lost':>4} {'task/h':>7} {'total_s':>7} {'scan_s':>6} {'triage_s':>8} {'p95tri':>7} {'first_s':>7} {'p95first':>8} {'coord#':>6} {'coord_s':>7} {'deputy#':>7} {'deputy_s':>8} {'unseeded':>8} {'false+':>6} {'esc':>3} {'rework':>6}")
        for row in arms_summary:
            print(
                f"{row['arm']:22} {row['verified']:>8} {row['lost']:>4} {row['tasks_per_hour']:>7.1f} {row['total_s']:>7.2f} "
                f"{row['scan_s']:>6.3f} {row['triage_s']:>8.3f} {row['p95_triage_s']:>7.3f} "
                f"{row['time_to_first_claim_s']:>7.3f} {row['p95_time_to_first_claim_s']:>8.3f} {row['coord_actions']:>6.0f} "
                f"{row['coord_s']:>7.2f} {row['deputy_actions']:>7.0f} {row['deputy_s']:>8.2f} {row['unseeded']:>8} "
                f"{row['false_alarms']:>6} {row['escalations']:>3} {row['rework']:>6}"
            )
            for error in row["errors"]:
                print(f"    error: {error}")
        print("\nFault injection:")
        for f in faults:
            print(f"  {'PASS' if f.get('ok') else 'FAIL'}  {f.get('check')}  { {k: v for k, v in f.items() if k not in ('check', 'ok')} }")
        print("\n" + payload["note"])
        if args.keep:
            print(f"\nTrial repositories: {base}")
        elif args.json:
            pass
    if not args.keep and not args.json:
        shutil.rmtree(base, ignore_errors=True)
    ok = all(r["lost"] == 0 and not r["errors"] for r in arms_summary) and all(f.get("ok") for f in faults)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
