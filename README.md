# agents-collaboration

Up to five coding agents (Claude Code, opencode, Qoder, Codex, Gemini, DeepSeek
through opencode, or any CLI that can run a shell command) working on one git
repository without stepping on each other.

It is a **skill** that tells each agent the protocol, and a **coordination
service** (`swarm.py`, one standard-library Python file) that enforces it.

[![ci](https://github.com/ifinsta/agents-collaboration/actions/workflows/ci.yml/badge.svg)](https://github.com/ifinsta/agents-collaboration/actions/workflows/ci.yml)

## What it guarantees

- **An agent knows whether it is alone.** `join` reports SOLO or names its peers.
  A solo agent coordinates itself and routes questions to the human.
- **An agent knows what machine it is on.** The OS, shell, Python command,
  tools, encoding and git settings are detected and turned into rules. No more
  `python3`, `sudo` or `make` on a Windows box that has none of them. Tasks a
  machine cannot verify are never routed to it.
- **One task per agent, never two agents on one task.** Claims are atomic. Each
  task gets its own worktree, branch and slot (ports, test database, container
  name).
- **Questions before code.** A plan needs an answer to every critical question.
  `unknown` becomes a question that blocks work until someone answers it, and
  steps are done in order, with evidence.
- **Conflicts are prevented, not just resolved.** Overlapping scopes are caught
  at planning, shared files need locks to be rewritten, and agents are told to
  rebase as soon as a merge touches their area.
- **Work joins safely before new work starts.** A single merge queue rebases
  each branch, runs the gates on the rebased tree, and advances the target with
  compare-and-swap. It never overwrites a person's uncommitted work. Only then
  is the agent free for its next task.
- **Nothing is lost when an agent dies.** Silent agents go offline, and their
  tasks become orphaned with branch and worktree intact, ready for
  `claim --take-over`.

[147 edge cases](skills/agents-collaboration/EDGE-CASES.md) are listed with how
each is handled. 64 are proved by tests on Linux, Windows and macOS, and the few
that are not handled are stated.

## Install into a repository

Requires Python 3.11+ and git. From the repository's root:

```bash
# bash, zsh, Git Bash
curl -fsSL https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --agents-md
```

```powershell
# PowerShell
irm https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --agents-md
```

This installs `.agents/skills/agents-collaboration/`, verified against the
release manifest. It creates `.agents/swarm/config.toml` and
`.agents/swarm/backlog.md` if they do not exist. `--agents-md` adds a short
pointer to `AGENTS.md`, which most agent CLIs read on start. Re-run it to update;
it refuses to overwrite files you edited unless you pass `--force`.

## Use

```bash
S="python .agents/skills/agents-collaboration/swarm.py"
$S environment                                   # the machine, and the rules for it
$S init                                          # import .agents/swarm/backlog.md
$S join --as ann --kind claude                   # SOLO or peers; coordinator or worker
$S next --as ann                                 # one task, its own worktree
$S plan --as ann --template                      # the critical questions
$S plan --as ann --set ... --step ... --step ...
$S start --as ann
$S step 1 --as ann --evidence "..."
$S submit --as ann --evidence "..."
$S merge --as ann                                # join the work, then ask for the next
```

Running several agents:

```bash
$S probe                                         # which agent CLIs are installed and signed in
$S spawn opencode --name ola --task API-1        # headless, in its own worktree, with a brief
$S spawn qodercli --name quinn --task DOCS-2
$S agents                                        # who is ready, busy or silent
$S monitor                                       # the event stream; nudges idle agents
```

The full protocol for agents is in [SKILL.md](skills/agents-collaboration/SKILL.md).
How it works is in [docs/design.md](docs/design.md), and the supported CLIs in
[docs/agents.md](docs/agents.md).

## Status

**0.1.2, experimental.** The protocol and the service are tested. Headless
command lines come from each CLI's own help, for the versions listed in
[docs/agents.md](docs/agents.md). One machine per pool; agent names are not
authenticated (see [SECURITY.md](SECURITY.md)).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). New edge cases are especially welcome.

## Licence

[MIT](LICENSE)
