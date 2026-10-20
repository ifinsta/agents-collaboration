"""Bounded Claude runner for workforce_bench; never used by the production engine.

Defaults: Haiku, USD 0.25/session, 8 turns, file tools only, 120 seconds.
The harness permits at most seven sessions per full three-mode trial.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assignment", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--provider", choices=("claude", "codex", "opencode"), default="claude")
    parser.add_argument("--max-budget-usd", type=float, default=0.25)
    args = parser.parse_args(argv)
    args.model = args.model or {"claude": "haiku", "codex": "gpt-6-luna", "opencode": "opencode/minimax-m3.1-flash-free"}[args.provider]
    if not 0 < args.max_budget_usd <= 1:
        parser.error("--max-budget-usd must be positive and at most 1")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "agents-collaboration"))
    import swarm_core as core

    executable = shutil.which(args.provider)
    # npm's Windows shim is a batch file; invoke the installed executable directly.
    if args.provider == "claude" and os.name == "nt" and executable:
        native = Path(executable).parent / "node_modules/@anthropic-ai/claude-code/bin/claude.exe"
        if native.is_file():
            executable = str(native)
    if not executable:
        parser.error(f"{args.provider} is not installed; install/sign in before a live trial")
    assignment = json.loads(args.assignment.read_text(encoding="utf-8"))
    prompt = (
        "Implement this one coding assignment now using Read/Edit/Write. Only edit durations.py. "
        "Preserve the other function and every test file. Do not delegate, use network tools, or change configuration. "
        "The harness independently runs the acceptance tests after you finish.\n"
        "The harness already owns all coordination, planning and integration. Do not invoke swarm commands; implement the assigned function only.\n"
        + json.dumps({k: assignment[k] for k in ("task", "requirement", "scope")})
    )
    command = [executable, "-p", "--model", args.model, "--max-budget-usd", str(args.max_budget_usd),
               "--max-turns", "8", "--output-format", "json", "--no-session-persistence",
               "--tools", "Read,Edit,Write", "--allowedTools", "Read,Edit,Write",
               "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
               "--disable-slash-commands", "--setting-sources", "", prompt]
    if args.provider == "codex":
        if os.name == "nt":
            script = Path(executable).parent / "node_modules/@openai/codex/bin/codex.js"
            prefix = [shutil.which("node") or "node", str(script)]
        else:
            prefix = [executable]
        command = [*prefix, "exec", "--model", args.model, "--json", "--ephemeral", "--sandbox", "workspace-write",
                   "-c", 'approval_policy="never"', "-c", 'model_reasoning_effort="low"', prompt]
    if args.provider == "opencode":
        if not args.model.endswith("-free"):
            parser.error("The default OpenCode benchmark permits only an explicitly free model")
        if os.name == "nt":
            executable = str(Path(executable).parent / "node_modules/@opencode/cli/bin/opencode.exe")
        command = [executable, "run", "--standalone", "--format", "json", "--auto", "--model", args.model, prompt]
    try:
        # Keep the full bounded native result as evidence, rather than the capture helper's 2 KiB tail.
        log = args.result.with_suffix(f".{args.provider}.json")
        with log.open("wb") as output:
            child = core.OwnedProcess(command, Path.cwd(), dict(os.environ), output)
            import time
            deadline = time.monotonic() + 120
            try:
                while child.active() and time.monotonic() < deadline:
                    if log.stat().st_size > 1024 * 1024:
                        raise ValueError("Native result exceeded 1 MiB; inspect retained output")
                    time.sleep(0.05)
                if child.active():
                    raise subprocess.TimeoutExpired(command, 120)
                code = child.returncode
            finally:
                if child.active():
                    child.kill()
                    until = time.monotonic() + 5
                    while child.active() and time.monotonic() < until:
                        time.sleep(0.05)
                child.close()
        text = log.read_text(encoding="utf-8")
        raw = [json.loads(line) for line in text.splitlines() if line.strip()] if args.provider in ("codex", "opencode") else json.loads(text)
        if args.provider == "opencode":
            # Retain raw counters without guessing v2's token/cache overlap.
            parts = [event.get("part", {}) for event in raw if event.get("type") == "step_finish"]
            costs = [part.get("cost") for part in parts]
            cost = sum(costs) if costs and all(type(v) in (int, float) and 0 <= v < float("inf") for v in costs) else None
            usage = {"tokens": None, "cost": cost, "currency": "USD" if cost is not None else None}
        else:
            usage = core.native_usage(raw, args.provider)
        usage["human_interventions"] = 0
        args.result.write_text(json.dumps(usage), encoding="utf-8")
        summary = raw if isinstance(raw, dict) else {}
        print(json.dumps({"native_result": str(log), "usage": usage, "model_usage": summary.get("modelUsage"),
                          "is_error": summary.get("is_error"), "subtype": summary.get("subtype")}))
        return code or int(bool(summary.get("is_error")))
    except (OSError, ValueError, core.SwarmError, subprocess.TimeoutExpired) as exc:
        print(f"Live runner failed; preserve its output: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
