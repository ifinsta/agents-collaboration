# Design

How the coordination service works, what it guarantees, and where it stops.

## Shape

```
agent CLIs (Claude Code, opencode, Qoder, Codex, Gemini, ...)
      │  shell commands: python swarm.py <subcommand> --as <name>
      ▼
swarm.py → swarm_core.py ── every command: BEGIN IMMEDIATE → sweep → act → COMMIT
      │
      ├── .git/swarm/swarm.db     SQLite (WAL): agents, tasks, questions, locks, messages, events
      ├── .git/swarm/logs/        output of spawned agents
      └── git                     worktrees, branches, rebase, gates, compare-and-swap on the target
```

There is no daemon to keep alive. The database sits in the repository's git
common directory, so every worktree of one clone shares it, and none of it is
committed. Agents of any brand take part by running shell commands. That is the
one interface every coding agent has.

`swarm monitor` is optional. It runs the same sweep on a timer, sends nudges, and
prints the event stream. Correctness never depends on it.

## The task state machine

```
open ─claim─▶ claimed ─plan─▶ planning ─start─▶ in_progress ─steps…─▶ submit ─▶ ready_to_merge ─merge─▶ done
                 │               ▲  │                │                                     │
                 │      answers  │  └─unknown/ask───▶ awaiting_answers ◀── ask --critical ─┘
                 │               │                                                      ├─▶ needs_rebase ─submit─┐
                 │                                                                      ├─▶ gates_failed ─submit─┤
                 │                                                                      └─▶ merge_blocked ─merge─┘
any held state ── holder offline long enough, or its process exited ──▶ orphaned ─claim --take-over─▶ (same state)
any held state ── release "note" ──▶ open
proposed ─approve─▶ open
```

- **One task per agent.** `next` and `claim` refuse while the agent holds a task.
  The only ways out are `merge` (the work joins the target) and `release` (with a
  handoff note).
- **Fencing.** Each claim increments the task's epoch. A take-over clears the
  previous holder's claim. An offline agent can do nothing until it
  `join --resume`s, and then it holds nothing.

## Planning is a gate, not advice

`plan` requires an answer to every checklist question. The defaults are outcome,
acceptance, scope, out of scope, dependencies, risks, rollback and unknowns, and
projects add their own.

- `unknown` creates a critical question.
- Listed unknowns must be asked.
- `start` waits for every critical question.
- An answer that arrives after the plan forces a re-plan.

Steps are ordered and recorded one by one with evidence. These are the questions
a senior engineer asks before touching code, made mandatory.

## Conflicts are prevented before they are resolved

1. **Scope.** The declared scope is compared with every task in flight at
   planning time.
2. **Hotspots.** Shared files are named in the config. Appending is free;
   rewriting needs a lock; `always` hotspots (migrations) always need one. Locks
   never wait, so they cannot deadlock.
3. **Declared locks.** Taken at claim, so exclusive work is never scheduled
   beside conflicting work.
4. **Early rebases.** After every merge, agents whose scope the merged files
   touch are told to rebase now.

## The merge: joining the work safely

Inside the single merge lock (a lease):

1. Rebase the task branch onto the current target, in the task's worktree. On
   conflict: abort, `needs_rebase`, list the files. The target is untouched.
2. Run the gates on the rebased tree, with the agent's slot environment. Gates
   are argument lists, per OS if configured, with timeout and retry.
3. Run the message hook (versions, changelogs). It runs inside the lock, so it
   sees every earlier merge.
4. Stage tracked files only, then squash (or keep commits) into the merge commit.
5. If the target moved meanwhile, retry from 1, up to three times.
6. Advance the target:
   - If a worktree has the target checked out, run `git merge --ff-only` there.
     Git refuses rather than overwrite a person's changes; unrelated changes are
     kept.
   - Otherwise run `git update-ref` with the expected old value (compare-and-swap).
7. Optionally push. A failed push leaves the local merge standing and tells the
   coordinator.
8. Release locks, mark the task done, free the agent, nudge overlapping agents,
   remove the worktree and branch. On Windows a folder in use defers the removal.

## Environment intelligence

`detect_environment()` gathers facts, never guesses: the OS and release, WSL,
the shell, the Python command (skipping the Microsoft Store `python3` stub), 14
common tools, the default encoding and UTF-8 mode, `core.autocrlf`,
`core.longpaths`, and filesystem case sensitivity. From them:

- **rules** (`environment_rules`): plain sentences for each mistake an agent
  makes when it assumes Linux;
- **capabilities** (`environment_caps`): `windows`, `linux`, `macos`, `docker`,
  `linux-docker`, `bash`, `make`, `pwsh`, `postgres-client`, merged into the
  agent's declared ones, so routing respects the machine;
- **per-OS gates**: `[gates.<os>]` replaces `[gates]` on that OS.

`join` and `whoami` point at it, spawned agents get it in their brief, and
`environment` warns when the pool mixes operating systems.

## Heterogeneous agents

Adapters describe each CLI: version, sign-in status, headless command, model
flag, unattended flags. `probe` reports installed, version and signed-in. It
never prints the status output, which holds account data. `probe --live` sends a
one-line prompt.

`spawn` joins and claims on the new agent's behalf, writes `.swarm-brief.md` into
its worktree (ignored through the shared `info/exclude`), and launches the CLI
there, detached. The prompt on the command line is one safe sentence that points
at the brief. On Windows, npm-installed CLIs are `.cmd` shims that pass arguments
through `cmd.exe`, so nothing else may travel there.

## Goals: from a piece of work to tasks

A goal holds three things:

- the answers to the hard questions, in four stages: understand, backward,
  forward, challenge;
- its outcomes, each with the check that proves it;
- draft tasks, each serving outcomes, needing other tasks, carrying a done-check
  and a size.

`goal_problems` is the gate. It finds:

- unanswered or open questions;
- outcomes without work;
- tasks that serve nothing;
- oversized tasks;
- tasks no wave reaches.

`goal_waves` computes the forward view (topological layers within the goal, with
outside dependencies listed as waits). `print_goal_views` prints both directions.
`commit --assign` turns drafts into open tasks and reserves the first wave for
free agents whose capabilities match. Every task then carries its place in the
work: `task_context` reads backward (what its inputs produced) and forward (what
its consumers need), and the claim output and the brief include it.

## The console

`swarm console` turns the pool into something a person can watch and steer:
an event monitor (or an observer, when a monitor already runs), the live board,
a launcher menu, and one pane per requested agent. `plan_console` is a pure
function that takes the panes, the OS and what is installed, and returns the
commands to run:

- Windows Terminal split panes;
- else tmux, plus a new terminal window attached to it;
- else separate windows;
- else instructions.

Tests check every layout on every OS. Agent panes run `swarm launch`, which joins,
claims and writes the brief before starting the CLI interactively in the task's
worktree. The coordinator is told to ask the human once per board, and the answer
is recorded.

## Crash safety of the merge

A merge changes two things that cannot change in one step: the target branch in
git, and the board. It does them in this order, and every crash window is safe:

| Step | Crash here leaves | Recovery |
|---|---|---|
| 1. squash the branch into one commit | the target untouched | the next merge redoes it |
| 2. write the intent (the commit about to land) | the target untouched | once the merger is gone the stale intent is dropped |
| 3. move the target | git has the commit; the board does not know | any command finds the intent's commit in the target and records the task as done |
| 4. record the merge as done | nothing | none needed |

The recovery decision is git's, never the board's: the intent's commit must be an
ancestor of the target. The final write is one compare-and-set shared by the live
merge and recovery, so a merge that is recorded by both is recorded once. The
crash tests kill a real merge at steps 2 and 3 (`SWARM_FAILPOINT`, a test hook
that exits the process without cleanup).

## What a command costs

Agents run the tool for every step, so start-up time matters. Before v0.4.4 every
command took about half a second to a second. The cost was measured, piece by
piece, before anything was changed:

| Where the time went | Cost | What replaced it |
|---|---|---|
| Compiling the script. Python caches the bytecode of a module it *imports*, never of the script it is *run as*. | 340-550 ms | `swarm.py` is a 31-line launcher; the code is `swarm_core.py`, cached after the first run |
| Importing `urllib.request`, used only by `swarm update` | ~250 ms | imported where it is used |
| Looking up 17 tools: `shutil.which` rescans every PATH entry for every name | ~165 ms | one scan of PATH (~30 ms) |
| Three git processes to find the repository | ~60 ms each | the git directory is read from files; git is asked only in unusual layouts |
| Importing `tomllib` to read `config.toml` | ~30 ms | the parsed config is cached until the file changes |

Measured with alternating runs of v0.4.3 and v0.4.4 on the same machine, in a
project with a config (median of 15 runs):

| Command | v0.4.3 | v0.4.4 | |
|---|---|---|---|
| `version` | 529 ms | 213 ms | 2.5x |
| `status` | 817 ms | 330 ms | 2.5x |
| `agents` | 603 ms | 238 ms | 2.5x |
| `whoami` | 480 ms | 207 ms | 2.3x |
| `environment` | 722 ms | 311 ms | 2.3x |

What is left is mostly the interpreter and the standard library (`argparse`,
`re`, `sqlite3`, `subprocess`): about 60 ms of bare Python start plus about 100 ms
of imports. SQLite (1.4 ms to open the board) and building the argument parser
(16 ms) were measured and left alone.

The tests pin the *work* (no git process for `version`, `status`, `agents` or
`whoami`; one for `environment`; no network or TOML modules loaded), not the time.
`python scripts/bench.py` measures the time.

If `PYTHONDONTWRITEBYTECODE` is set, or the skill folder is read-only, Python
cannot write the cache, and a command costs what it did before v0.4.4, no more.

## Limits, stated plainly

- **One machine.** Pools across machines are not supported: there is no network
  service, no per-agent credentials, and one clock (EC-008, EC-011).
- **Names are not authenticated.** The machine is the trust boundary.
- **The board is not rebuilt if lost.** Branches and worktrees survive, and
  `doctor` reports the drift (EC-121).
- **Prose cannot be enforced.** Rules such as "messages are information" depend
  on the agent; the service enforces everything it can see in git and in its
  own state.
