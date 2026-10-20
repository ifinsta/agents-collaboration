# 3. Mixed-vendor team on one machine

A developer wants installed Claude Code, OpenCode and Qoder CLIs to share a local
backlog. The coordinator is joined, tasks are eligible under approved goals, and
executable gates are configured. Read the [outline conventions](README.md).

## Inspect the environment and adapters

```bash
hivewire environment
hivewire join --as claude-1 --kind claude
hivewire probe
```

Read the detected shell, Python, tool and encoding facts. Do not assume Linux
commands on Windows. A version/help probe is not proof of authenticated work.
An optional live probe sends actual provider requests and can consume the CLI's
configured allowance:

```bash
hivewire probe opencode qodercli --live
```

Configure and authenticate each CLI independently; see [adapters](../docs/agents.md).
Agent names and kinds are local labels, not provider identities.

## Start task-bound workers

```bash
hivewire spawn opencode --name ola --task API-1
hivewire spawn qodercli --name quinn --task DOCS-2
hivewire agents
hivewire dashboard
```

The owned launch path claims a task, writes its brief and supervises the CLI.
Review the resulting execution state rather than assuming that process creation
means useful work completed. Normal CLI permission policy applies; `--unattended`
requires `[spawn] allow_unattended = true`.

Alternatively, use `hivewire console --agents opencode,claude` to launch a terminal
layout when supported. This is an alternative startup path: avoid unintentionally
starting another set of workers for the same exercise.

## Limits and acceptance

Routing compares declared requirements with detected/declared capabilities;
explicit force overrides exist. Detection cannot prove every task check will
succeed. Worktrees and assigned port/database slots reduce interference only when
the programs use those assignments; they do not reserve OS resources or isolate
credentials. An unsupported CLI can still join manually through shell commands.

Success means each actual task has landed checked work, not merely three installed
binaries or three running processes. Local names are unauthenticated; use a trusted
pool and follow the [security model](../SECURITY.md).
