# Edge cases

The situations below are how collaboration breaks in real engineering teams,
translated to a pool of coding agents. Each says how it is handled.

| Status | Meaning |
|---|---|
| **Tested** | Enforced by `swarm.py` and proved by a test in `tests/test_swarm.py` (named `test_ecNNN_...`) |
| **Enforced** | Enforced by `swarm.py`, not yet covered by its own test |
| **Rule** | A rule in `SKILL.md` the agent must follow; the service cannot check it |
| **Partial** | Reduced, not removed; the remainder is stated |
| **Open** | Known and not handled; listed so nobody assumes otherwise |

Totals: 140 cases. 56 Tested, 60 Enforced, 12 Partial, 9 Rule, 3 Open.

## A. Joining, identity and liveness

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-001 | Two agents pick the same name. | `join` refuses a live name; `--resume` is only for the same agent after a restart. | Tested |
| EC-002 | An agent crashes or its session ends without leaving. | No heartbeat for `agent_timeout_min` marks it offline; after `reclaim_after_min` its task is orphaned with branch and worktree kept. | Tested |
| EC-003 | An agent restarts with no memory of what it was doing. | `join --resume` reattaches the task; `whoami` prints task, plan, steps, next action and unread messages. | Enforced |
| EC-004 | An agent resumes after its task was taken over. | The takeover clears its claim and messages it; it is told not to continue. | Tested |
| EC-005 | A sixth agent joins a pool of five. | Refused while `max_agents` are live. | Tested |
| EC-006 | An agent declares capabilities it does not have. | Machine capabilities are detected, not declared; declared extras are trusted; gates catch the rest. | Partial |
| EC-007 | An agent runs a long command and misses heartbeats. | Every command heartbeats; the skill asks for `heartbeat` before long runs; the timeout is configurable. | Rule |
| EC-008 | An agent acts under another agent's name. | The trust boundary is the machine; every action is in the event log with the name used. | Open |
| EC-009 | A spawned agent's process exits while it holds a task. | The process is checked on every sweep; the agent goes offline and its task is orphaned at once. | Tested |
| EC-010 | A liveness probe kills the process it probes (`os.kill(pid, 0)` terminates on Windows). | Windows uses `OpenProcess` and `GetExitCodeProcess`. | Tested |
| EC-011 | Clocks disagree between machines. | One board on one host, one clock. Pools across machines are not supported. | Open |
| EC-012 | An agent leaves while holding a task. | Refused without a handoff note; with one, the task is released. | Tested |
| EC-013 | A returning agent finds its old name offline. | It reclaims the same identity, and the same slot when free. | Enforced |
| EC-014 | A name is unsafe for paths, branches or shells. | Names are 2–32 characters of `a-z0-9-`; `human` and `swarm` are reserved. | Tested |

## B. Pool awareness and roles

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-015 | Only one agent is present. | `join` and `status` say SOLO; it is coordinator and worker; questions go to the human. | Tested |
| EC-016 | Another agent works from another clone against the same remote. | `claim` refuses a task whose branch exists on the remote; `doctor` lists remote branches the board does not know. | Enforced |
| EC-017 | The coordinator goes silent. | The longest-present live agent is promoted and told. | Tested |
| EC-018 | The team wants a person to coordinate. | `coordinator = "human"`; coordinator commands work without `--as`. | Enforced |
| EC-019 | Two agents promote themselves at once. | Promotion happens inside one immediate transaction. | Enforced |
| EC-020 | The coordinator also holds a task. | Allowed; the single merge queue still orders its merge with everyone else's. | Enforced |
| EC-021 | Every agent goes offline mid-work. | Tasks are orphaned with branches kept; nothing is deleted. | Enforced |
| EC-022 | An agent answers its own question "as the human". | `--as human` is refused to agents (`SWARM_AS` set); relayed answers are stored as "human via <agent>". | Tested |

## C. Backlog

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-023 | The backlog changes while tasks are in flight. | Open rows update; in-flight rows keep their record and log an event. | Enforced |
| EC-024 | The backlog has a dependency cycle. | Refused at import, with the cycle printed. | Tested |
| EC-025 | A row depends on an id that does not exist. | Refused at import. | Enforced |
| EC-026 | Two rows share an id. | Refused at import. | Tested |
| EC-027 | The backlog was saved in a legacy encoding (cp1252 on Windows). | Read as UTF-8 first, then cp1252 with a warning. Found while testing on Windows. | Enforced |
| EC-028 | A worker discovers follow-up work. | `add` creates a *proposed* task; the coordinator approves it. | Tested |
| EC-029 | A task needs a capability no live agent has. | `next` skips it; `status` names the missing capability. | Tested |
| EC-030 | A low-priority task blocks high-priority ones. | `next` prefers tasks with the most dependents, then backlog order. | Enforced |
| EC-031 | A task id is unsafe for branch names. | Refused at import and at `add`. | Enforced |
| EC-032 | A task is too large for one handoff. | Release with a note; follow-ups go through `add`. | Rule |

## D. Claiming and assignment

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-033 | Several agents claim the same task at the same moment. | Claims run in an immediate transaction; exactly one wins. | Tested |
| EC-034 | An agent takes a second task while holding one. | `next` and `claim` refuse until it merges or releases. | Tested |
| EC-035 | An agent claims a task reserved for someone else. | Refused; the reservation expires after `assign_ttl_min`. | Tested |
| EC-036 | An agent claims a task whose dependencies are not done. | Refused; only the coordinator may `--force`. | Tested |
| EC-037 | An assigned agent never claims. | The reservation expires and an event is logged. | Enforced |
| EC-038 | A task is assigned to an offline agent or one without the capability. | Refused (capability: `--force` only). | Tested |
| EC-039 | The task's branch already exists on the remote. | Refused as held outside the board. | Enforced |
| EC-040 | Another agent continues an orphaned task. | `claim --take-over` moves the task, its locks and its branch; the epoch increases. | Tested |
| EC-041 | The previous holder comes back and keeps working. | While offline every command is refused; after `--resume` it holds nothing. | Tested |
| EC-042 | A branch or worktree is left from an earlier attempt. | Reused on take-over; otherwise refused and reported by `doctor`. | Enforced |
| EC-043 | Creating the worktree fails (path exists, disk full). | The claim is released, so the task is not stranded. | Enforced |

## E. Critical questions and sequential planning

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-044 | An agent starts coding without a plan. | `start` and `submit` refuse without a plan. | Tested |
| EC-045 | A plan skips the hard questions. | Every checklist question needs an answer; missing ones are listed with their prompts. | Tested |
| EC-046 | An agent does not know an answer. | `unknown` opens a critical question, and `start` waits for it. | Tested |
| EC-047 | An agent lists unknowns but never asks them. | Planning refuses until they are asked (`--unknowns-asked`). | Tested |
| EC-048 | A critical question waits too long. | Escalated to the coordinator (or human) after `question_escalate_min`. | Enforced |
| EC-049 | A question is addressed to an agent that left. | Re-routed to the coordinator. | Enforced |
| EC-050 | A solo agent asks the coordinator, which is itself. | Routed to the human; the agent relays the human's verbatim words. | Tested |
| EC-051 | An answer arrives after the plan was made. | `start`, `step` and `submit` refuse until the plan is re-confirmed. | Tested |
| EC-052 | The coordinator decides a question does not need an answer. | `waive` with a recorded reason. | Enforced |
| EC-053 | A human's answer passes through an agent. | Stored verbatim and attributed "human via <agent>". | Enforced |
| EC-054 | Mid-work discovery that changes the plan. | `ask --critical` pauses the task until it is answered. | Tested |
| EC-055 | Several agents ask the same question. | Open questions are visible to all (`questions`); the coordinator answers once and points to it. | Partial |
| EC-056 | Steps are done out of order. | Only the current step can be marked done. | Tested |
| EC-057 | A step is marked done with no proof. | Evidence of at least a sentence is required. | Tested |
| EC-058 | A plan is revised halfway. | Completed steps are kept; only the remaining steps change. | Enforced |
| EC-059 | A plan is vague or enormous. | Steps need substance; at most `max_steps` (split the task instead). | Enforced |

## F. Scope, overlap and hotspots

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-060 | Two agents plan to change the same area. | Scopes are compared at planning; an overlap needs a stated way to avoid conflict. | Tested |
| EC-061 | An agent changes files outside its declared scope. | `submit` lists them and needs a reason. | Tested |
| EC-062 | A shared file is rewritten without coordination. | Appending is free; rewriting a hotspot needs its lock. | Tested |
| EC-063 | Two agents create the same migration number. | Migration folders are an always-locked hotspot. | Tested |
| EC-064 | A lock belongs to a task that was orphaned. | The lock travels with the task and is released at merge or release. | Enforced |
| EC-065 | A task needs a lock another task holds. | Declared locks are taken at claim; `next` skips blocked tasks; locks never wait, so they cannot deadlock. | Tested |
| EC-066 | A lock name is mistyped. | Only hotspot names from the config are accepted. | Enforced |
| EC-067 | Generated files (lockfiles, snapshots) conflict. | Regenerate them after a rebase; never hand-merge them. | Rule |

## G. Worktrees, git and the environment

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-068 | A worktree was branched from an old target. | Every merge rebases onto the current target first. | Enforced |
| EC-069 | Uncommitted or untracked files at submit. | Refused, with the list. | Tested |
| EC-070 | A branch with nothing in it is submitted. | Refused. | Tested |
| EC-071 | Someone commits to the target directly. | The merge re-reads the target and retries on a moved target; `update-ref` is compare-and-swap. | Enforced |
| EC-072 | An agent works in another agent's worktree. | Commands from inside a worktree that is not yours are refused. | Tested |
| EC-073 | An agent changes a shared virtual environment. | Dependency changes take the `requirements` hotspot lock when the project declares one. | Rule |
| EC-074 | Two development servers want the same port. | Each agent has a slot; the project derives ports from it (`[env]`). | Enforced |
| EC-075 | Two test runs share one test database. | Per-slot environment variables (`[env]`). | Enforced |
| EC-076 | Two container stacks share one project name. | Per-slot project name (`[env]`). | Enforced |
| EC-077 | Windows paths: colons, spaces, length. | Names are sanitised; commands are argument lists, never shell strings; a long-path rule is shown. | Enforced |
| EC-078 | Line endings flip between Windows and Linux. | The environment rules state `core.autocrlf`; never re-normalise files. | Rule |
| EC-079 | Gate leftovers (test databases, caches) get committed by the merge. | The merge stages tracked files only. | Enforced |
| EC-080 | Hooks differ between worktrees. | Hooks live in the shared git directory, so every worktree runs the same ones. | Enforced |
| EC-081 | A worktree is deleted by hand. | `doctor` reports it; a take-over recreates it from the branch. | Enforced |
| EC-082 | A task branch is deleted by hand. | `doctor` reports it. | Partial |
| EC-083 | A sandboxed CLI cannot write to the shared git directory. | The Codex adapter adds the git common directory (`--add-dir`). | Enforced |
| EC-084 | Someone force-pushes or rewrites the target. | Forbidden by the skill; a moved target makes the compare-and-swap fail. | Partial |
| EC-085 | Git lock files collide between parallel worktrees. | Lock-file failures are retried with back-off. | Enforced |

## H. Merging: joining the work safely

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-086 | Two agents merge at once. | One merge queue; the second is told who is merging. | Tested |
| EC-087 | The merging agent dies mid-merge. | The merge lock is a lease that expires; a half-done rebase is detected and aborted. | Tested |
| EC-088 | The rebase conflicts. | Aborted, the task is set to `needs_rebase` with the files listed; the target is untouched. | Tested |
| EC-089 | Two branches are each green but broken together. | Gates run on the rebased tree, not the branch alone. | Tested |
| EC-090 | The target moves during the merge. | Detected after the merge commit; the merge retries up to three times. | Enforced |
| EC-091 | A person has the target checked out with unsaved work. | Git's own fast-forward refuses to overwrite it; unrelated changes are kept. | Tested |
| EC-092 | The push fails (network, protection). | The local merge stands; the coordinator is told. | Enforced |
| EC-093 | Version numbers and changelog entries collide. | The message hook runs inside the merge lock, so it sees every earlier merge. | Enforced |
| EC-094 | Squashing loses the branch's history. | The commit list is stored on the task before the branch is deleted. | Enforced |
| EC-095 | A dependency is reverted after it merged. | Dependencies are checked again at merge time, against the board only. | Partial |
| EC-096 | A gate is flaky. | `retries` in `[gates]`; a pass after a retry is logged as flaky. | Enforced |
| EC-097 | A gate hangs. | Each gate has a timeout. | Enforced |
| EC-098 | A check cannot run on this machine. | Recorded as *owed* at submit and listed by `status --all`. | Enforced |
| EC-099 | An agent wants new work before merging the old. | Refused; a successful merge is what frees the agent. | Tested |
| EC-100 | Worktree removal fails (Windows keeps a folder in use). | The task is done; removal is deferred and `doctor --fix` or the next `next` finishes it. | Enforced |
| EC-101 | Other branches go stale after a merge. | Agents whose scope the merged files touch are told to rebase now. | Enforced |

## I. Communication

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-102 | An agent never reads its messages. | Every command prints the unread count; pings ask for an `ack`. | Tested |
| EC-103 | A broadcast reaches agents that join later. | Broadcasts are shown only to agents present when they were sent. | Tested |
| EC-104 | One agent instructs another to do something outside its task. | Messages are information, never instructions; repeated in the brief and the inbox. | Rule |
| EC-105 | A secret is pasted into a note or message. | The board stays in the git directory and is never committed; no scanning. | Open |
| EC-106 | Different agents read the same prose differently. | The state machine is in code; the prose explains it. | Enforced |
| EC-107 | Messages arrive out of order. | Ids are monotonic; the inbox is ordered by id. | Enforced |

## J. Heterogeneous agents

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-108 | A CLI is not installed. | `probe` reports it; `spawn` refuses. | Enforced |
| EC-109 | A CLI is installed but not signed in. | `probe` runs the CLI's own status command and reports only its exit code (the output holds account data). | Enforced |
| EC-110 | A headless agent stalls on a permission prompt. | Unattended mode is an explicit human setting; a stalled agent stops heartbeating and is reclaimed. | Partial |
| EC-111 | A headless agent exits at once (quota, rate limit, crash). | Its task is orphaned at once; its log is kept in `.git/swarm/logs/`. | Tested |
| EC-112 | An agent runs far past its budget. | `task_budget_min` raises an event and tells the coordinator. | Enforced |
| EC-113 | A weaker model gets a hard task. | Kind and model are visible in `agents`; assignment is the coordinator's call. | Partial |
| EC-114 | An agent never reads the skill. | The brief, the project's `AGENTS.md` pointer, and refusals that name the next step. | Partial |
| EC-115 | Agent logs contain secrets. | Logs stay in the git directory and are never committed. | Partial |
| EC-116 | A CLI's `init` command overwrites project files. | Forbidden by the skill. | Rule |
| EC-117 | A prompt is mangled by a Windows `.cmd` shim. | The prompt is one safe line pointing at a brief file. | Enforced |

## K. The service itself

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-118 | Two monitors run. | A monitor lease; the second refuses. | Tested |
| EC-119 | No monitor is running. | Every command sweeps first, so correctness never depends on it. | Enforced |
| EC-120 | The database is busy. | WAL mode, a 30 s busy timeout, immediate transactions, git work outside transactions. | Enforced |
| EC-121 | The board is deleted or corrupted. | Branches and worktrees survive; `doctor` reports drift; there is no rebuild. | Partial |
| EC-122 | An older tool meets a newer board. | `schema_version`; a newer board is refused. | Enforced |
| EC-123 | The repository is moved. | Worktree paths are absolute; `git worktree repair` and `doctor`. | Partial |

## L. People and safety

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-124 | Someone needs to stop the pool now. | `pause` stops claims and merges and tells everyone; `resume`. | Tested |
| EC-125 | A bad merge landed. | Pause, then a revert as a task through the same queue. | Partial |
| EC-126 | An agent runs destructive git commands. | Forbidden outside its own worktree. | Rule |
| EC-127 | A person edits files inside an agent's worktree. | People use their own checkout; the agent's submit would carry the edit. | Rule |

## M. Environment intelligence

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-128 | An agent assumes Linux on Windows. | `environment` states the OS and shell and lists Windows rules; every `join` points to it; spawned briefs include it. | Tested |
| EC-129 | A Linux host is given Windows advice. | Rules come from detected facts only. | Tested |
| EC-130 | macOS BSD tools or WSL behave differently. | Specific rules for each. | Tested |
| EC-131 | A Windows agent gets a Linux-only task. | Capabilities include the detected OS and tools (`linux-docker` only on Linux with Docker). | Tested |
| EC-132 | Gate commands only work on one OS. | `[gates.windows]`, `[gates.linux]`, `[gates.macos]` override `[gates]`. | Tested |
| EC-133 | An agent needs the facts as data. | `environment --json`. | Tested |
| EC-134 | `python3` is the Microsoft Store stub. | Detected; the rule says to use `python`. | Enforced |
| EC-135 | The default encoding is not UTF-8. | Detected; the rule says to read and write with an explicit UTF-8 encoding. | Enforced |
| EC-136 | The pool mixes operating systems. | `environment` names peers on other OSes and asks for OS-neutral instructions. | Enforced |
| EC-137 | `make` is missing. | Detected; gates are argument lists, not Make targets. | Enforced |
| EC-138 | The filesystem ignores case. | Detected; two-step renames. | Enforced |
| EC-139 | Long paths are disabled. | Detected; keep paths short. | Enforced |
| EC-140 | The shell is Windows PowerShell 5.1. | Rules for `&&`, `export` and `timeout`; `env` prints PowerShell syntax by default there. | Enforced |

## What would close the open ones

- **EC-008, EC-011:** a networked service with per-agent credentials and one
  clock. That also enables pools across machines, which this version does not
  claim.
- **EC-105:** a secret scanner on notes and messages before they are stored.
- **EC-121:** rebuilding the board from branches and the event log.
