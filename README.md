# agents-collaboration

Coordinate your existing coding agents through a local Git workflow with explicit
ownership, recoverable work and verified integration.

A **skill** explains the workflow; a standard-library Python **engine** enforces
its coordination commands. Agents can use different CLIs while sharing one
SQLite board in the Git common directory. The default pool limit is five agents
on one machine. Agent identities are trusted local names, not security principals.

[![ci](https://github.com/ifinsta/agents-collaboration/actions/workflows/ci.yml/badge.svg)](https://github.com/ifinsta/agents-collaboration/actions/workflows/ci.yml)

The badge reports hosted repository CI. It does not validate an unpublished
working tree. The source described here is **0.4.4, unreleased and experimental**.
See the [documentation index](docs/README.md) for current contracts and evidence.

![The console during the scripted three-agent example](docs/console.svg)

[Walk through the generated example](docs/simulation.md), or choose a
[use case](usecases/README.md). The simulation uses scripted workers and real
Git/SQLite operations; it establishes no real-agent productivity advantage.

## When to use it

Use it when several agents share a repository and you want consistent ownership,
handoffs, review and integration rules across their coding tools. A solo agent
can use the same planning, contract and verification workflow.

- **Accountable work:** atomic claims, assignment epochs, task worktrees and
  per-agent slot variables. Claims check declared machine capabilities.
- **Bounded assignments:** fresh claims accept configured contracts. Time,
  checkpoints and recorded usage affect coordination permissions; reclaim keeps
  the retained deadline, allowance and usage history.
- **Reliable communication:** typed messages, leased delivery receipts, retries
  and replay. Reading or replying does not acknowledge delivery.
- **Controlled recovery:** checkpoints, owned process supervision and explicit
  recovery for uncertain Git allocation, execution and verification.
- **Checked integration:** a serialized merge queue rebases work, runs configured
  gates on the final commit and checks ownership/policy before target movement.
- **Inspectable completion:** task integration and goal acceptance have separate
  receipts. Owed checks remain visible; prose cannot replace executable checks.

These controls govern engine-mediated operations. Worktrees do not prevent
arbitrary filesystem edits, isolate credentials or authenticate agents. Code
conflicts can still occur, and configured checks can be incomplete. Read the
[security model](SECURITY.md) and [design limits](docs/design.md#limits).

## Install

Requires Python 3.11+ and Git. Owned supervision on Linux/macOS also requires
`ps`. Agent CLIs, credentials and optional terminal tools are supplied separately.

To install the release selected by the public installer, from your Git repository:

```bash
# bash, zsh, Git Bash
curl -fsSL https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --all
```

```powershell
# PowerShell; first verify that python is Python 3.11+
irm https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --all
```

The selected release may predate this unreleased source. Read its installed skill
and inspect its protocol before using examples from this branch. To install a
reviewed local checkout instead, replace `PATH_TO_PROJECT` with your target repo:

```text
python scripts/make_manifest.py --check
python install.py --source . --project PATH_TO_PROJECT --all
```

The installer checks file hashes against the selected source's manifest. `--all`
adds agent pointers; `--scaffold` separately creates an explained project config.
The tool does not import its example backlog. See [INSTALL.md](INSTALL.md) for
source/release selection, shell rules, verification and updates.

## Workflow

Below, `swarm` means the absolute launcher command printed by `join` or `claim`.
Examples are outlines: fill templates with repository facts, replace placeholders
and run all planned steps before advancing. Configure executable project gates in
`.agents/swarm/config.toml` before integration.

```text
swarm environment
swarm join --as ann --kind claude
swarm goal new health "Ship a health endpoint operators can rely on"
swarm goal answer health --set done_looks_like="..." ...
swarm goal outcome health "The endpoint returns the running version" --check "Assert version against VERSION"
swarm goal check health 1 --command '["python","checks/health.py"]'
swarm goal task health H-api "Add the endpoint" --scope src/ --serves 1 --done-when "The endpoint check passes"
swarm goal architecture health --template
# Record every architecture answer and source evidence, then approve separately.
swarm goal architecture health --approve
swarm goal review health
swarm goal commit health
```

Each worker claims a task, reads its contract and works in its task worktree:

```text
swarm next --as ann
swarm explain H-api
swarm plan --as ann --template
# Record a complete plan and ordered steps, then start.
swarm start --as ann
# Implement, test, commit and record every planned step with its evidence.
swarm submit --as ann --evidence "Acceptance command and observed result"
swarm merge --as ann
```

After all goal tasks land, the coordinator or human runs the approved outcome
checks and closes the goal against their retained receipt:

```text
swarm goal verify health --key health-final
swarm goal close health
```

See [SKILL.md](skills/agents-collaboration/SKILL.md) for the complete workflow,
[completion evidence](docs/completion-evidence.md) for verification, and
[use cases](usecases/README.md) for takeover, interrupts and independent review.

## Run and observe agents

For one terminal with tabs over headless workers, use `swarm sessions` (or
`swarm console --managed`). It retains failed/exited sessions and output; closing
the viewer leaves workers running. The browser dashboard also has a Sessions page.
See [managed sessions](docs/managed-sessions.md) for controls and audit limits.

These are independent launch examples; use free names and eligible task IDs.

```text
swarm probe
swarm spawn opencode --name ola --task API-1
swarm launch claude --name ann --task DOCS-2
swarm agents
swarm console --agents opencode,claude
```

Task-bound `spawn` and `launch` use owned supervision and, by default, an automatic
inbox relay. Foreground launches require an eligible task; no-task launches were
removed. A native bridge is needed for vendor-specific context injection. See
[adapters](docs/agents.md), [supervision](docs/process-supervision.md) and the
[bus contract/schema](skills/agents-collaboration/BUS.md).

## Status and validation

The current contract uses **CLI protocol 2, database schema 12, and message,
bus and event versions 1**. JSON consumers read typed data under `result`.
The [migration guide](docs/legacy-migration.md) lists removed options/settings.

The [latest recorded broad runtime snapshot](docs/validation/managed-sessions/report.md)
passed 425 Linux tests and 91 selected Windows checks, with three Windows skips.
Both used the same frozen source; browser and real-terminal checks are recorded
separately. Later working-tree changes require fresh source-bound validation. Hosted
six-runtime acceptance and macOS remain unexecuted in these records.

[Documentation alignment checks](docs/validation/markdown-alignment/report.md)
record focused installer/bus checks and a regenerated scripted session separately.

The [edge-case register](skills/agents-collaboration/EDGE-CASES.md) distinguishes
tested, enforced, partial, rule-only and open cases. These labels are different
from unit-test counts. [Real-agent trials](docs/workforce-benchmark.md) retain
mixed outcomes; lower cost, less rework and faster delivery remain unproven.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). New edge cases are welcome.

## Licence

[MIT](LICENSE)
