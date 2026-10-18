# agents-collaboration

Up to five coding agents (Claude Code, opencode, Qoder, Codex, Gemini, Kilo Code,
DeepSeek through opencode, or any CLI that can run a shell command) working on one git
repository without stepping on each other.

It is a **skill** that tells each agent the protocol, and a **coordination
service** (`swarm.py` and `swarm_core.py`: standard-library Python, no dependencies) that enforces it.

[![ci](https://github.com/ifinsta/agents-collaboration/actions/workflows/ci.yml/badge.svg)](https://github.com/ifinsta/agents-collaboration/actions/workflows/ci.yml)

![The console while three agents work: the live board on the left, the event monitor and the agent launcher on the right](docs/console.svg)

_The console during a simulated session, drawn by the tool's own board and monitor:
the goal committed, three agents working at once, the merge queue catching a
conflict, a silent agent's task taken over, the gate catching a wrong test, and
the goal closed on evidence._

**See it before you install it:** [the whole session, step by step](docs/simulation.md).
Three agents and a human take one goal from a sentence to merged, verified work,
with real output from the real tool. CI replays it on every change.

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

[200 edge cases](skills/agents-collaboration/EDGE-CASES.md) are listed with how
each is handled. 115 are proved by tests on Linux, Windows and macOS, and the few
that are not handled are stated.

## Install

**Tell your agent:** "Install agents-collaboration by following
https://github.com/ifinsta/agents-collaboration/blob/main/INSTALL.md". The guide is
written for agents: it checks the OS, Python and shell before it runs anything.

### Into a repository

Requires Python 3.11+ and git. From the repository's root:

```bash
# bash, zsh, Git Bash
curl -fsSL https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --all
```

```powershell
# PowerShell
irm https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --all
```

This installs `.agents/skills/agents-collaboration/`, verified against the
release manifest. It creates no project files unless you add `--scaffold`
(an explained `.agents/swarm/config.toml` holding defaults, nothing else). A fresh install always
starts with an empty board: no tasks, no goals, nothing from any other project. `--all` adds the pointers agent
CLIs look for: a short marked section in `AGENTS.md` (opencode, Codex, Qoder,
DeepSeek-TUI) and a pointer skill in `.claude/skills/` (Claude Code). It refuses to
overwrite files you edited unless you pass `--force`, and keeps the line endings
of the files it edits. `swarm update` reinstalls the latest release.

### Once, for every repository

```bash
curl -fsSL https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --user --claude
```

The tool is then `python ~/.agents/skills/agents-collaboration/swarm.py`, in any
repository.

## Use

Nothing about your project is assumed. Give the pool a piece of work, and the
agents turn it into tasks:

```bash
S="python .agents/skills/agents-collaboration/swarm.py"
$S goal new health "Ship a health endpoint operators can rely on"
$S goal answer health --set done_looks_like="..." ...   # hard questions: understand, backward, forward, challenge
$S goal outcome health "GET /health answers 200 with the version" --check "curl returns 200"
$S goal task health H-api "Add the endpoint" --serves 1 --done-when "the endpoint test passes"
$S goal review health                            # backward and forward views; refuses gaps
$S goal commit health --assign                   # opens tasks, assigns the first wave
```

Each agent then works one task at a time:

```bash
$S environment                                   # the machine, and the rules for it
$S join --as ann --kind claude                   # SOLO or peers; coordinator or worker
$S next --as ann                                 # one task, its own worktree
$S context --as ann                              # what it builds on, and what waits on it
$S plan --as ann --template                      # the critical questions
$S plan --as ann --set ... --step ... --step ...
$S start --as ann
$S step 1 --as ann --evidence "..."
$S submit --as ann --evidence "..."
$S merge --as ann                                # join the work, then ask for the next
```

Watching and driving the pool from a terminal:

```bash
$S console                                       # monitor, live board, agent launcher: one terminal, split
$S console --agents opencode,claude              # plus one interactive pane per agent, each on its own task
```

The board takes the left half; the event monitor and the agent launcher share the
right. The launcher starts each agent in its own tab, on the next task, a task you
choose, or no task yet. On Windows this is Windows Terminal; on Linux and macOS,
tmux in a new terminal window. The coordinating agent asks you once whether you
want it.

Running agents headless:

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

**0.4.4, experimental.** The protocol and the service are tested. Headless
command lines come from each CLI's own help, for the versions listed in
[docs/agents.md](docs/agents.md). One machine per pool; agent names are not
authenticated (see [SECURITY.md](SECURITY.md)).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). New edge cases are especially welcome.

## Licence

[MIT](LICENSE)
