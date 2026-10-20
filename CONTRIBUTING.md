# Contributing

The state-changing engine stays in one standard-library Python module behind
a small launcher, with an installed skill and edge-case register. Keep new
interfaces subordinate to that authority. The optional browser helper is included
in the current source manifest; publication and platform acceptance remain separate.

## Before you start

- Open an issue first for anything larger than a fix, so the approach can be
  agreed before you write it.
- A new edge case is a contribution in itself. Use the "Edge case" issue template:
  describe how it happens in a real team, and what goes wrong.

## Making a change

```bash
git clone https://github.com/ifinsta/agents-collaboration
cd agents-collaboration
python -m pip install ruff
python -m ruff check .
python -m unittest discover -s tests -v
```

Rules:

1. **Standard library only**, Python 3.11+. The tool must run wherever an agent
   runs, with nothing to install.
2. **Every behavior the service enforces needs a test**, named after its edge case
   (`test_ec061_...`), against a real git repository in a temporary directory.
   Update `skills/agents-collaboration/EDGE-CASES.md` and its totals in the same
   change.
3. **Every OS is first-class.** CI is configured for Linux, Windows and macOS.
   Report actual execution per source/runtime; configuration alone is not a pass. Commands are
   argument lists, never shell strings. Files are read and written with an
   explicit UTF-8 encoding.
4. **A refusal says what to do next.** Every error tells the agent the exact
   command or condition that unblocks it.
5. **When the skill files change, regenerate the manifest:**
   `python scripts/make_manifest.py`. CI fails while it is stale, because the
   installer verifies every file against it.
6. `install.py` stays ASCII-only (Windows PowerShell pipes text as ASCII).
7. **The simulation is part of the contract.** `examples/simulate.py --check` runs in the
   suite. When behaviour or output changes on purpose, regenerate the published transcript:
   `python examples/simulate.py --write docs/simulation.md`.
8. **A command must stay cheap.** Agents run the tool for every step, so start-up time is a feature. The
   suite pins the work a command does (git processes started, modules imported), never the time, because a
   timing assertion fails at random on a busy machine. `python scripts/bench.py` measures the time for people
   (`--source ../other-checkout` compares two versions). If `Latency` fails, a command now starts a git process
   or imports something it did not before: that needs a reason, or a lazy import.
   The environment probe uses one Git call; Python 3.11 on Windows may also run
   its standard-library `ver` query. The suite bounds that OS probe separately
   instead of counting it as Git work.

## Adding an agent adapter

Add it to `DEFAULTS["adapters"]` in `swarm_core.py` with its version, sign-in status
and headless command. Mark it `verified: True` only after you have run
`swarm probe --live <kind>` and a real `swarm spawn` with that CLI. Record the CLI
version you verified in `docs/agents.md`.

## Documentation

Use [docs/README.md](docs/README.md) as the navigation and evidence entry point.
Keep current instructions separate from historical proposals, generated examples
and source-pinned validation reports. Example commands must include required
actors/arguments or clearly identify placeholders and preconditions. Do not
rewrite old metrics or turn unexecuted platforms into passing evidence.

Documentation-only checks should validate links, command syntax and the manifest;
run relevant installer/simulation checks when installed skill text changes. New
runtime behavior needs the complete candidate checks and platform acceptance.

## Releases

Bump `version` in `pyproject.toml` and `DEFAULT_REF` in `install.py`, regenerate
the manifest, update `CHANGELOG.md`, then tag `vX.Y.Z`. The installer defaults to
the tag, so a release is what people install.
