# Edge cases

The situations below are how collaboration breaks in real engineering teams,
translated to a pool of coding agents. Each says how it is handled.

| Status | Meaning |
|---|---|
| **Tested** | Enforced by `hivewire.py` and proved by a test in `tests/` (named `test_ecNNN_...`) |
| **Enforced** | Enforced by `hivewire.py`, not yet covered by its own test |
| **Rule** | A rule in `SKILL.md` the agent must follow; the service cannot check it |
| **Partial** | Reduced, not removed; the remainder is stated |
| **Open** | Known and not handled; listed so nobody assumes otherwise |

Totals: 384 cases. 299 Tested, 61 Enforced, 13 Partial, 9 Rule, 2 Open.

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
| EC-014 | A name is unsafe for paths, branches or shells. | Names are 2–32 characters of `a-z0-9-`; `human` and `hivewire` are reserved. | Tested |

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
| EC-042 | A branch or worktree is left from an earlier attempt. | Known released branches are reused; orphaned work needs take-over. Unknown outside work requires `--adopt`, otherwise `claim` refuses and `next` skips it. | Tested |
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
| EC-061 | An agent changes files outside its declared scope. | `submit` refuses changes outside the contract scope; a reason cannot widen it. | Tested |
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
| EC-102 | An agent never reads its messages. | Command footers expose unread counts; typed messages require leased bus receipts, and enabled supervised relays refresh inbox/control hints. | Tested |
| EC-103 | A broadcast reaches agents that join later. | Broadcasts are shown only to agents present when they were sent. | Tested |
| EC-104 | One agent instructs another to do something outside its task. | Messages are information, never instructions; repeated in the brief and the inbox. | Rule |
| EC-105 | A secret is pasted into a note or message. | New message bodies, checkpoint notes and event details redact common credential forms; credential-like envelope keys are rejected. Arbitrary prose, old records and other fields (such as questions) are not comprehensively scanned. The board remains unencrypted in the git directory. | Partial |
| EC-106 | Different agents read the same prose differently. | The state machine is in code; the prose explains it. | Enforced |
| EC-107 | Messages arrive out of order. | Ids are monotonic; the inbox is ordered by id. | Enforced |

## J. Heterogeneous agents

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-108 | A CLI is not installed. | `probe` reports it; `spawn` refuses. | Enforced |
| EC-109 | A CLI is installed but not signed in. | `probe` runs the CLI's own status command and reports only its exit code (the output holds account data). | Enforced |
| EC-110 | A headless agent stalls on a permission prompt. | Unattended mode is an explicit human setting; a stalled agent stops heartbeating and is reclaimed. | Partial |
| EC-111 | A headless agent exits at once (quota, rate limit, crash). | Its task is orphaned at once; its log is kept in `.git/swarm/logs/`. | Tested |
| EC-112 | An agent runs far past its budget. | Every claim has a contract; active-time/deadline expiry fences new work and retains recovery state. The retired task_budget_min setting is refused. | Enforced |
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

## N. Found in the first real run

Installed into a repository where five agents were already working through an
earlier board, v0.1.0 met these within minutes. Each is now handled.

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-141 | Work on a task was started outside the board (its branch already exists). | `claim` refuses and names the branch's commits; `--adopt` continues it and tells the coordinator; `next` never hands it out. | Tested |
| EC-142 | An agent rubber-stamps the protocol (plans and finishes every step in seconds). | Finishing all steps within two minutes of `start` is logged and sent to the coordinator. The service cannot judge the evidence itself. | Tested |
| EC-143 | A newly promoted coordinator lifts a pause another coordinator set for a reason it does not know. | Only whoever set the pause, or a human, may lift it. | Tested |
| EC-144 | A gate names a program by relative path, and Windows resolves it from the caller's directory, not the worktree. | Relative program paths are resolved against the task's worktree on every OS; `doctor` checks them from a worktree. | Tested |
| EC-145 | A dry run of `spawn` joins an agent and claims a task. | `--dry-run` only prints the command line; nothing on the board changes. | Tested |
| EC-146 | A tool edits a project file and, on Windows, silently converts every line ending (Python text mode writes CRLF), so a ten-line change becomes a whole-file diff. | The installer keeps each file's own line endings and byte-order mark. | Tested |
| EC-147 | Work reached the target outside the board (an earlier board, a person), so its task and everything that needs it stay blocked. | `record <task> --commit <sha>` marks it done after checking the commit is in the target's history, frees its holder and cleans its worktree. | Tested |

## O. Seeing and driving the pool (v0.2.0)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-148 | A worktree lacks the git-ignored local files the project needs (`.env`), so gates and servers fail there. | `[worktree] copy` lists files copied from the main checkout at claim; only git-ignored ones, so they can never be committed. | Tested |
| EC-149 | The human cannot see what the agents are doing, or start more of them, without reading logs. | The coordinator runs `hivewire workspace` at assignment startup: one managed terminal with agent tabs and the browser dashboard. Existing views are reused; explicit decline is respected. | Tested |
| EC-150 | The console's monitor pane competes with a monitor that already runs. | The pane observes the event stream instead of holding the monitor lease. | Tested |
| EC-151 | A pane command contains the terminal's separator (`;` in Windows Terminal) and is split into two commands. | Pane commands are checked and refused before anything opens. | Tested |
| EC-152 | The machine has no split-capable terminal, or no display at all (a server over SSH). | Windows Terminal, else tmux plus a new terminal window, else one window per pane, else tmux attach instructions or one printed command per pane. | Tested |
| EC-153 | An interactive agent started in the main checkout edits it instead of a worktree. | `launch` joins and claims first, writes the brief, and starts the CLI inside the task's worktree. | Tested |
| EC-154 | Two console panes start the same CLI and race for one agent name. | Names are assigned when the console is planned. | Tested |
| EC-155 | A CLI cannot take a first message on its command line (Qoder's interactive mode). | The pane prints the exact first message to paste. | Tested |
| EC-156 | Claude Code does not look in `.agents/skills/`. | `install.py --claude` adds a pointer skill in `.claude/skills/`; it refuses an unowned/edited destination unless replacement is explicitly forced. | Tested |
| EC-157 | Every repository needs its own install. | `install.py --user` installs once into the home folder; the tool works in any repository. | Tested |
| EC-158 | An installed copy falls behind the releases. | `hivewire version` and `hivewire update`, which reinstalls and keeps the pointers already present. | Tested |

## P. Turning a piece of work into tasks (v0.3.0)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-159 | Work is broken down before anyone knows what "done" means, who uses it, or what is risky. | A goal must answer hard questions in four stages (understand, backward, forward, challenge) before review or commit; thin answers are refused; "unknown" becomes a critical question that blocks commit. | Tested |
| EC-160 | Tasks appear that serve nothing the goal needs (scope creep). | Every task names the outcome(s) it serves; one that serves none is refused. | Tested |
| EC-161 | An outcome is promised but no task works toward it. | Review lists every outcome without work and refuses to pass. | Tested |
| EC-162 | A task has no way to tell when it is finished. | Every task needs a done-check. | Tested |
| EC-163 | A task is too large for one agent to finish, verify and merge. | Size L fails review until it is split. | Tested |
| EC-164 | A task depends on work that does not exist. | Refused when the task is drafted. | Tested |
| EC-165 | An agent starts a task blind to what its inputs actually produced. | `hivewire context`, the claim output and the brief show each task it builds on: what it produced, how it was proved, its files and commit, anything still owed. | Tested |
| EC-166 | An agent does not know who consumes its result or what they need. | The same context shows every task waiting on it, with that task's done-check and scope. | Tested |
| EC-167 | Work is assigned to an agent whose machine cannot verify it. | `goal commit --assign` gives the first wave to free agents whose detected and declared capabilities match. | Tested |
| EC-168 | The tool assumes a project layout, settings or a pre-written backlog. | Config and backlog are optional; the installer creates them only with `--scaffold`; goals produce the tasks. | Tested |
| EC-169 | A goal is declared done because its tasks merged, though its outcomes were never checked. | Closure needs landed task commits and a current passed engine receipt for executable outcome checks; prose and fabricated done rows cannot close it. | Tested |
| EC-171 | Example content shipped with the tool is imported as real work (v0.3.1's `--scaffold` put two placeholder tasks on every new board). | `--scaffold` creates only a config of explained defaults that names no backlog; the example backlog carries a marker, and the tool never imports it; `hivewire sync` withdraws tasks imported from it that nobody touched. | Tested |
| EC-172 | The config names a backlog file that does not exist. | Reported as a warning; the board stays as it is. | Tested |
| EC-173 | An agent answers a goal question with "unknown" and is told every question is answered, so it believes the interrogation is finished. | An unknown is not counted: the output says which questions wait, and which question each became and who it went to. Found by the published simulation. | Tested |
| EC-170 | On Windows, the tool's output through a pipe (how agents read it) is cp1252: "§" arrives garbled and "→" in a note crashes the command. | Output is UTF-8 on every OS, whatever the console or pipe. | Tested |

## Q. A console people can read (v0.4.0)

Found by using the v0.2.0 console for real.

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-174 | Views wider or taller than their pane wrap into noise, and the board scrolls past the part that matters. | Every view reads its pane's size: the board fits its height (most important lines first, events fill the rest), and lines are clipped or wrapped to the width. | Tested |
| EC-175 | Events print as raw records: UTC timestamps, internal kinds, Python lists. | Events read as sentences in local time, with colour by kind when the pane is a terminal (`NO_COLOR` turns it off). | Tested |
| EC-176 | Long-running panes keep running old code after `hivewire update`. | The monitor and the board notice a changed `hivewire.py` and restart themselves on it. | Enforced |
| EC-177 | Leaving the launcher silently drops the pane to a bare shell, and the person starts an agent by hand, in the main checkout, without a brief. | Leaving says what the pane now is, how to reopen the menu, and why the menu is the safer way. | Tested |
| EC-178 | The person wants an agent present without handing it a task yet. | No-task launches are refused before registration. Add or release an eligible task before starting a supervised worker. | Tested |
| EC-179 | The person wants an agent on a particular task, not whatever is next. | The launcher lists the open tasks this machine can take and starts the agent on the chosen one. | Tested |
| EC-189 | The target branch advanced, then the worker ended before the board recorded the merge (the crash window EC-087 does not cover; EC-087 only breaks an expired lease and aborts a half-done rebase). The task could never finish: its branch "changes nothing", and `next` handed it to another agent as unfinished work. | Every merge writes its intent (the commit about to land) before the target moves. Any later command finds a task whose intent commit is already in the target, and records the merge as done. `record` (EC-147) remains for work that landed outside the board. | Tested |
| EC-190 | The worker ended after writing its intent but before the target moved. | Nothing is merged. Once the merger is gone, the stale intent is dropped and the merge can be run again. | Tested |
| EC-191 | A bad, missing or unrelated commit in a recorded intent completes a task that was never merged. | Only git's answer counts: the commit must be an ancestor of the target. A malformed, unknown or unlanded commit never completes anything. | Tested |
| EC-192 | The live merge and recovery both record the same merge (a slow acknowledgement racing a sweep), so it completes twice: two events, two nudges. | One compare-and-set (`state<>'done'`) in one place: exactly one caller wins and emits the event; the other changes nothing. | Tested |
| EC-193 | The merger died holding the queue, and everyone waits out the lease (45 minutes). | A queue lease whose holder is offline is broken at once. | Tested |
| EC-194 | The acknowledgement is lost and the agent retries `hivewire merge`. | If the agent's last task is already merged, `merge` says so and changes nothing. | Tested |
| EC-187 | A project's gate (its whole test suite) runs longer than the agent timeout, so the merging agent is marked offline in the middle of its own merge. Seen in a real project: a 26-minute gate. | While gates run, the merge renews the agent's heartbeat and the queue's lease every `keepalive_sec` (default 30 s). | Tested |
| EC-188 | The merge queue's lease is broken while a merge is still running, so two merges could advance the target at once. | Before the target moves, the merge checks it still holds the queue. If not, it stops, touches nothing, and asks for `hivewire merge` again. | Tested |
| EC-182 | An agent CLI updates itself and drops options its adapter passes (Qoder went from 0.1.46 to 1.1.73 mid-session and dropped `-q` and `--max-turns`). | Before `spawn`, `launch` or `probe` uses a CLI, every option it is about to pass is checked against that CLI's own `--help`. A missing one stops the launch and names the options. | Tested |
| EC-183 | An interactive CLI cannot take a first message, and the message printed before it opens is hidden behind its screen, so the agent starts without its instructions. | Adapters pass the first message where the CLI allows it (Qoder's `-i`). Otherwise it goes on the clipboard, and the launch waits for Enter before the CLI starts. | Enforced |
| EC-184 | An agent exits before doing anything, and its task is held as orphaned, out of the pool. | A task with no plan, no step, no commit and nothing uncommitted goes straight back to the pool, and its empty worktree is removed. Boards that already hold such orphans are cleaned on the next command. | Tested |
| EC-185 | A task with real work in it is orphaned and waits for someone to know they should take it over. | When nothing is open, `next` offers it as a take-over, telling the agent to read its plan and steps first. The board lists it as needing a new owner. | Tested |
| EC-186 | The skill is installed but not committed, so task worktrees (made from the target branch) contain neither the skill nor the `AGENTS.md` pointer. | `doctor`, and the coordinator's `join`, say so and what to commit. The brief always carries the skill's full path. | Tested |
| EC-181 | An agent CLI has its own parallel or worktree mode (Kilo Code's `--parallel`, Qoder's `--worktree`) that creates branches beside the swarm's worktree, so work lands where no task tracks it. | No adapter uses those modes, and a test fails if one does. The agent works in the worktree its claim made. | Tested |
| EC-180 | The board gets a quarter of the screen, and agent TUIs are squeezed into small panes. | The board takes the left half at full height; agents open in their own tab (the launcher opens each new agent in a new tab of the same terminal). | Tested |

## R. What a command costs (v0.4.4)

Found by measuring, after a reader asked about a rewrite in Rust: the tool took
half a second to a second per command, and agents call it for every step.

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-195 | Every command took 0.5-0.8 s: a script run directly is recompiled from source on every start (never cached), rarely used modules were imported eagerly, 17 tool lookups each rescanned PATH, and git was started three times to find the repository. | The tool is an importable module (Python caches its bytecode) behind a 31-line launcher; rarely used imports are lazy; tools are found with one scan of PATH; the git directory is read from files. The historical v0.4.4 measurement reported 2.3-2.5 times faster commands; it is not a latency claim for subsequent source. Tests pin the work (git processes started, modules loaded), never the time. | Tested |
| EC-196 | The bytecode cache appears in the project's `git status`. | The installer writes a `.gitignore` inside the skill folder. | Tested |
| EC-197 | A half-updated install (a new launcher beside an old module, or the reverse) fails in confusing ways. | The launcher checks the module's version and refuses with the exact reinstall command. | Tested |
| EC-198 | Finding the git directory without git gives a different answer from git in an unusual layout. | Only an ordinary repository, a linked worktree, or a subdirectory of either is read from files; `GIT_DIR`-style variables and anything unusual ask git. A test compares both answers on each layout. | Tested |
| EC-199 | Parsing `config.toml` (importing `tomllib`, about 30 ms) on every command, for exactly the projects that have a config. | The parsed config is cached beside the board and reused only while its checked content digest and metadata match. A damaged cache is rebuilt, never trusted. | Tested |
| EC-200 | A merged task's worktree directory is reused for other work (an agent switches branch inside it). The task's pending cleanup, which any free agent may now run, would remove that directory as soon as its tree was clean, taking the new work's checkout with it. Seen in a real project, with four new files staged in such a directory. | Cleanup removes a worktree only while it is still on the task's own branch. Otherwise it keeps the directory, clears the flag, still deletes the merged task branch, and says so (`cleanup_skipped`). | Tested |

## S. Reasoned contracts (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-201 | A schema upgrade loses old board data or an older binary changes a newer board. | Transactional, repeatable migration preserves existing goals/messages; old workflow versions remain provenance without bypassing current architecture checks; newer schemas are refused before DDL. | Tested |
| EC-202 | Work starts without an architecture decision, or approval outlives a goal revision. | New goals require a concrete, source-backed architecture brief and approval bound to goal/brief revisions. Goal edits invalidate approval and contracts bind their scope. | Tested |
| EC-203 | An agent approves high-risk architecture, or a brief's source changes before approval. | High risk requires the human; approval checks source fingerprints and settled decisions. Names remain coordination roles, not authenticated principals. | Tested |
| EC-204 | Contract negotiation loops indefinitely or an unaccepted offer is claimed. | Owner accepts before claim; one evidence-backed counter, original decision deadline retained, decision expiry persisted even if the requested operation fails. | Tested |
| EC-205 | An expired worker continues coordination or expiry discards unfinished edits. | Expiry fences the epoch, blocks work/integration, persists an interrupt and retains branch, locks and dirty worktree. Current-epoch checkpoint and release remain possible across restart. | Tested |
| EC-206 | Blocking resets a deadline or running time grows without enforcement. | Accounted running and blocked time are separate; wall, active and deliberation limits enforce expiry. Only one justified extension is allowed. | Tested |
| EC-207 | Checkpoints are missed or repeated sweeps flood recovery notifications. | Due checkpoints stop new work until a fenced snapshot records progress, commit/diff fingerprint and next step. Due reminders and post-grace escalation are idempotent. | Tested |
| EC-208 | A contract expires while merge gates run and the old permission advances the target. | The integration path rechecks contract permission and epoch after gates and before merge intent; the target remains unchanged on expiry. | Tested |
| EC-209 | Taking over a crashed worker silently resets its entire budget. | Takeover creates an independently owned contract retaining the original absolute deadline and remaining active allowance; the former holder is fenced. | Tested |
| EC-210 | Implementation consumes the time reserved for review. | The review reserve stops new plan/start/step permissions while leaving submission and recovery available. | Tested |
| EC-211 | A process dies halfway through migration. | SQLite rolls back schema changes and version together; a real killed subprocess proves the migration can be retried. | Tested |

## T. Reliable communication and targeted interrupts (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-212 | A committed message is lost when the sender or inbox reader crashes, or upgrade forgets read state. | Versioned envelopes and per-recipient receipts survive restart; typed/critical messages redeliver until ack/expiry, legacy read state migrates, history replays and send retries keep the same ID. | Tested |
| EC-213 | Duplicate retries create duplicate messages, replies reorder threads, or one agent acknowledges another's broadcast. | Sender-scoped keys reject conflicting content and concurrent retries commit once; replies retain thread order; broadcast audience and per-recipient acknowledgements are frozen. | Tested |
| EC-214 | Critical messages expire silently or retention deletes unresolved evidence. | Durable dead letters escalate once; explicit operator resolution is distinct from recipient ack. Payload retention preserves unresolved critical messages and keeps pruned envelopes/keys. Deadlines normalize to UTC. | Tested |
| EC-215 | Credentials or oversized bodies enter message storage, or forged typed text becomes control authority. | Bounded bodies and best-effort credential redaction minimize new persisted data; typed chat has no authority to change task/control records. General secret detection remains partial (EC-105). | Tested |
| EC-216 | A targeted pause blocks the whole pool, discards edits, or a stale acknowledgement resumes it. | Only its task is fenced; current-epoch ack and fresh checkpoint complete the pause, separate coordinator resume fences again. Attention can leave work running. Generic inbox ack grants no control authority. | Tested |
| EC-217 | A handoff uses an old checkpoint or silently misses changed untracked contents. | Checkpoint task/epoch, request order and current commit/diff/untracked fingerprints are verified; yield/handoff retain edits, and committed completion retries are idempotent. | Tested |
| EC-218 | An agent never acknowledges an interrupt. | A bounded deadline emits one timeout escalation; operator recovery captures its own snapshot and hands off without claiming owner acknowledgement or deleting work. | Tested |
| EC-219 | A coordinator cancels work without policy, or cancellation is recorded as verified success. | Cancel requires a human or explicit delegation; completion preserves unfinished work and never fabricates a merge or acceptance result. | Tested |
| EC-220 | A pause or reassignment arrives during rebase, gates or after merge intent. | Checks bind both task ID and epoch; late results cannot overwrite a newer state, failed hook edits remain, and ref updates serialize with control transactions. Interrupts that commit first prevent integration. | Tested |
| EC-221 | A process dies around interrupt/checkpoint/handoff commits. | Real killed subprocesses prove rollback before commit, durable state after commit and safe retry, with branch and dirty worktree retained. | Tested |
| EC-222 | Extending an expired contract bypasses a targeted pause. | Control remains stopped across contract expiry and extension; an operator must recover the pending pause with a fresh checkpoint/handoff. | Tested |

## U. Independent oversight and scoped memory (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-223 | Oversight/memory migration loses prior board data or stops half-applied. | Schema 4 adds records/indexes transactionally; a killed migration rolls back, retries preserve committed schema-3 messages and tasks. | Tested |
| EC-224 | The accused reviews itself, a coordinator cannot be reviewed, or a reviewer implements work while reserved. | A different free agent/human reviews a frozen brief; reviewer commands are read-only, claims/assignments are blocked, and agents cannot resolve findings about themselves or their own reports. | Tested |
| EC-225 | Cleared evidence is reused after commit, epoch, submission, policy or review-revision changes, or squash discards its source. | Clearance binds exact source/tree/epoch/policy; stale decisions are refused, rebased code needs fresh review, and final proofs plus pinned source refs survive cleanup/GC. | Tested |
| EC-226 | Forged chat, unsupported citations or a false-alarm resolution bypasses gates. | Only the assigned snapshot reviewer records a cited report; clear requires not_confirmed and a separate decision. Confirmed/inconclusive findings keep integration blocked, and actual gates always run. | Tested |
| EC-227 | Detection loops create duplicate allegations or reviewer deliberation never ends. | Opt-in rule detection records its source event once; review/decision deadlines escalate without inferring guilt, and agent refreshes are bounded before human intervention. | Tested |
| EC-228 | Incidents or policy-file changes arrive during integration, or a post-gate hook changes reviewed code. | Final checks serialize with ref updates; current source/tree/policy must remain covered, including after squash/hook edits. | Tested |
| EC-229 | Chat or an author promotes an unsupported lesson to verified memory. | Proposals remain provisional; a different verifier, real local events/commit SHAs and current revision are required. Missing/foreign assertions cannot authorize promotion. | Tested |
| EC-230 | Lessons leak between task scopes, expiry is hidden, supersedes silently changes state, or SQLite lacks FTS5. | Scoped verified retrieval, explicit state history/expiry and nonautomatic supersession are enforced; ordinary SQLite search remains usable without FTS. | Tested |
| EC-231 | Credentials enter review/memory artifacts or poisoned lesson text becomes authority. | Common credential forms are filtered in claims, snapshots, diffs and policy argument lists; contextual text never changes task scope, checks or policy. General secret detection remains partial. | Tested |
| EC-232 | An imported verified label or foreign verifier grants local authority, or sensitive lessons export by default. | Cross-repo sharing needs explicit policy/flags; imports remain provisional with local verification owed. Sensitive visibility/export require explicit choices and human export authority. | Tested |
| EC-233 | Repeated experience reports automatically rewrite code, or fabricated utility counts claim improvement. | Reports only form unverified candidates; independent lessons and normal maintainer-approved tasks precede change. Observations require later landed task evidence and are labeled self-reported, not causal. | Tested |
| EC-234 | A crash loses a review/promotion or a lost reply duplicates an incident/lesson. | Real killed subprocesses prove atomic records, idempotent create keys, immutable report retries and revision fencing. Evidence pins precede commit so source objects remain recoverable. | Tested |

## V. Protocol, diagnostics and integration hardening (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-235 | Harnesses parse human text/footers, refusals escape as tracebacks, or JSON invokes interactive prompts. | Global `--json` gives one versioned result including argument/refusal errors, typed board status and task outcomes; interactive views require `--once` or `--dry-run`. CLI protocol 2 exposes inbox/environment fields under `result` only; retired top-level aliases and protocol 1 are refused. | Tested |
| EC-236 | Event replay changes order or silently reads a future protocol; migration loses historical events. | Schema 5 versions old/new events, migrates atomically and supports bounded ascending replay/cursors. Future event versions are refused. Killed migration retries preserve history. | Tested |
| EC-237 | A message/commit hook changes content after gates passed, or cleanup discards the check proof. | Gates run again on the exact final commit; proof records SHA/tree/policy, actual check attempts/timing and owed checks in the write-ahead intent and durable integration record. Failing hook edits cannot land. | Tested |
| EC-238 | Gates change tracked files, a hook widens scope, or edits arrive after verification/intent. | Final commit/head, clean tracked content, policy, declared scope and hotspot locks are rechecked before target movement; edits and branches survive refusal. | Tested |
| EC-239 | A merged task branch accumulates new clean commits before delayed cleanup. | Cleanup requires landed completion and a fully landed branch tip; new unmerged commits keep the branch/worktree and pending cleanup. | Tested |
| EC-240 | Operators miss ownership/evidence drift or remove work while trying a repair. | Structured diagnostics include severity, task and next action, missing evidence pins and owed/unverified checks. Authorized `--fix --dry-run` previews cleanup, then safe repair is idempotent. | Tested |
| EC-241 | SQLite is busy, a transition rolls back, or randomized/repeated claims and takeovers produce two owners. | Real SQLite fail-fast busy/retry and rollback checks, seeded claim/release model and concurrent takeovers assert ownership/epoch invariants and retained worktrees. | Tested |
| EC-242 | A benchmark accepts a runner's success claim, altered tests or missing cost as improvement. | Fixed real coding tasks, immutable acceptance checks, three Git/CLI workflows, retained trial artifacts and explicit unknown usage. Default scripted trials make no LLM productivity claim. | Tested |

## W. Owned execution and timeout recovery (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-243 | Execution tracking upgrades a schema-5 board halfway or loses prior state. | Schema 6 creates execution records/indexes transactionally; killed migration rolls back and a retry keeps prior tasks/agents/events. | Tested |
| EC-244 | A worker leaves descendants behind, or its PID/group ID is recycled. | Windows assigns a suspended child to a private job before resuming; POSIX keeps a live session anchor. Only captured handles/anchored groups authorize termination, including after the actual leader exits. Unrelated processes remain alive. | Tested |
| EC-245 | A timed-out/refused gate or message hook leaves children running, deadlocks on inherited stdout, or captures unlimited output. | Owned command groups, file-backed capture, per-stream tails and a monitored 1 MiB output limit stop groups on timeout/refusal. Actual stdout/stderr stay separate for hooks; gate keepalives recheck permission. | Tested |
| EC-246 | An expired contract or timed-out stop interrupt leaves a spawned CLI running indefinitely under a termination policy. | Cooperative checkpoint grace precedes captured explicit escalation; only its owned job/group stops. Task epochs remain fenced, no acknowledgement/success is invented, and worktrees/edits survive. | Tested |
| EC-247 | Cooperative policy or a dry-run unexpectedly kills work. | Cooperative stop records never signal; authorized stop previews leave execution state unchanged. Actual stopping blocks new work/claims and exposes next actions. | Tested |
| EC-248 | Stored or forged PIDs become kill authority. | Operator commands only record requests; a creating supervisor holds actual job/group authority. Numeric registry values cannot signal unrelated processes. | Tested |
| EC-249 | Startup or supervision crashes cause blind restart/cleanup or a false terminated result. | Durable startup intent and heartbeat expose unknown supervision; uncertain work is retained. Human reconciliation is explicitly an attestation after confirming cessation, not fabricated engine proof. | Tested |
| EC-250 | Quoted permission booleans, NaN limits or invalid retry counts alter process authority. | Spawn/gate execution configuration is type/range checked before commands; malformed permissions and unbounded limits are refused with a repair condition. | Tested |
| EC-251 | Ignored files or an edited generated brief disappear during automatic return/cleanup, or failed removal clears ownership. | Ignored local content is retained; only a brief identical to a retained archive is disposable. Removal uses Git without force and must succeed before task/contract references are cleared. | Tested |
| EC-252 | External completion or delayed cleanup removes a worktree while its worker/descendants still run or supervision is uncertain. | Cleanup checks all nonterminal executions associated with the task or its agent, including after that worker moves to another task. Live launcher PIDs conservatively defer removal; unknown supervision requires labeled human reconciliation. | Tested |
| EC-253 | A transient config edit makes parsed policy disagree with its digest, or malformed encoding/syntax becomes an internal error. | Cache misses parse the same UTF-8 byte snapshot whose digest is checked, refuse mismatches and give an explicit TOML repair instruction. Snapshot-versioned cache stamps invalidate earlier parsed entries. | Tested |

## X. Observed completion evidence (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-254 | Schema-6 migration partially creates verification tables or invents verification for legacy goals. | Schema 7 migrates atomically, preserves prior state and labels old closures unverified; killed migration rolls back and retries idempotently. | Tested |
| EC-255 | An external task record treats ancestry or an empty gate set as acceptance. | Record runs configured gates on the landed commit before completion; failure/unconfigured checks retain ownership and artifacts. Receipts retain observed results and source. | Tested |
| EC-256 | An empty goal, forged done row or result prose closes unverified work, or checks overwrite human dirt. | Approved outcome commands run in separate retained checkouts; closure requires real landed commits and a matching passed receipt. Human main-checkout dirt stays untouched. | Tested |
| EC-257 | A check definition, policy, target or goal revision changes after a receipt, or an unprivileged actor edits executable policy. | Definitions are bounded argv arrays controlled by coordinator/human; changes require architecture reapproval. Receipts and retry keys bind source, policy and context. | Tested |
| EC-258 | Owed checks disappear under new prose or a check from a different assignment. | Owed checks block goal verification. Human resolution requires a current passed task receipt and preserves the original obligation and labeled attestation. | Tested |
| EC-259 | A zero-exit check edits its source, the target moves during checks, or an older pass hides a later failure. | Final head/clean-source/context guards reject invalid runs; latest matching receipt must pass. Failed check files and results remain inspectable. | Tested |
| EC-260 | A verifier dies before/after a result or completion commit and a retry assumes success or blindly restarts. | Durable intent/results and before/after kill points expose unknown state; human cessation attestation abandons uncertain runs without a passed result. Completed keyed retries replay once. | Tested |
| EC-261 | External completion crashes between observed gates and the task record. | Receipt precedes the atomic completion/event transaction; retry checks unchanged context and records completion exactly once. | Tested |
| EC-262 | Goal closure crashes or repeats and rewrites its acceptance evidence. | Atomic closure links the immutable receipt; killed before/after commit and repeated requests preserve one success event. Closed goals refuse policy changes. | Tested |

## XI. Usage allowances and evidence (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-263 | Schema-7 migration partially installs usage storage or invents spend limits/history for old contracts. | Atomic schema-8 migration rolls back when killed; legacy terms retain uncapped dimensions and unknown actual usage. | Tested |
| EC-264 | An agent invents a larger budget, malformed currency or nonfinite limits weaken policy, or rounding enlarges a cap. | Humans own increases; coordinator offers obey configured ceilings. Typed finite bounds and uppercase currency are checked, caps round down to micro-units. | Tested |
| EC-265 | Reservations or retries double-debit allowance, expose unbounded ledger pages, or present held allowance as actual usage. | Atomic reservations hold remaining capacity, exact external retries replay and changed terms refuse. Pages are bounded; unreported actuals remain null. | Tested |
| EC-266 | Prompt data leaks into billing evidence, currencies mix, missing cost becomes zero or a report silently refunds consumption. | Reports retain normalized numeric facts and a source hash; omitted reserved dimensions remain unknown, currencies match, consumption rounds up and cannot decrease. Closed reports are immutable. | Tested |
| EC-267 | Actual overrun is discarded or a time-only extension/completion bypass reopens exhausted usage. | Actual consumption is retained, expiry fences the epoch, and completion refuses. An explicit human extension keeps consumption/history and must leave headroom. Work survives. | Tested |
| EC-268 | Human reconciliation fabricates measured consumption or a late report refunds a conservative charge. | Confirmed cessation charges at least the reservation against policy, with actuals still null. Late reported facts can increase but never refund the debit. | Tested |
| EC-269 | Failed commands are claimed as completed tasks or keyed retries launch commands twice. | Creating supervisors measure owned commands and retain failure/cessation evidence. Accounting closure is separate from task success; a tool key never launches again. | Tested |
| EC-270 | Reservation/report crashes between SQLite commit and caller response double-account or lose facts. | Before/after-commit killed subprocesses prove atomic reservations/reports and exact replay without a duplicate debit. | Tested |
| EC-271 | A dead tool supervisor is treated as zero usage, safe cleanup or permission to record completion. | Lost supervision becomes unknown; new work/completion/cleanup refuse and doctor exposes it. Human cessation settlement stays labeled, without invented actual tool seconds. | Tested |
| EC-272 | Submission/integration happens before external usage settles or gates escape command-time observation. | Pending usage blocks submission. Settled reports permit ordinary checks; configured merge gates use the owned, measured runner and retain command receipts. | Tested |
| EC-273 | Concurrent windows each reserve the same remaining allowance. | SQLite allocation transactions serialize competing requests; the loser gets a remaining-allowance refusal. | Tested |
| EC-274 | A tool timeout loses edits or reports task success without observing command cessation. | Timeout cleans up only its owned group, retains work, records measured duration and expires exhausted policy. Tests advance a controlled clock after real child work. | Tested |
| EC-275 | A replacement offer erases previous consumption, relabels its currency or a released contract's running clock keeps increasing. | Replacement offers retain the original budget origin/debit and prior policy, and refuse currency changes; release settles running and blocked clocks. | Tested |
| EC-276 | A late factual usage report leaves an earlier goal receipt valid even though its evidence changed. | Goal verification binds settled usage summaries. Later reports invalidate the fingerprint; closure requires a fresh observed receipt. | Tested |

## XII. Bounded headless output (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-277 | Output migration partially changes execution storage or invents old log provenance. | Atomic schema-9 migration rolls back when killed. Legacy executions retain null output metadata; typed status/inspection report that absence honestly. | Tested |
| EC-278 | Quoted, boolean, nonfinite or huge byte limits disable capture bounds. | New executions capture an integer max_output_bytes from 1024 through 268435456; malformed policy refuses with a repair instruction. | Tested |
| EC-279 | stdout/stderr is lost, byte decoding changes evidence or ordinary process exit falsely completes work. | A bounded binary pipe/file retains observed bytes and SHA-256, reports exact counts and EOF, and exposes typed metadata. Process exit remains separate from task acceptance. | Tested |
| EC-280 | A noisy worker fills disk or overflow cleanup kills unrelated processes/loses work. | The file retains at most the captured cap while a constant-memory reader drains excess. Overflow fences work and follows captured termination policy only for its owned group. Truncated capture records failure, retains work and is visible in doctor. | Tested |
| EC-281 | Default cooperative mode sends unexpected signals or a later config edit changes a live execution's cap. | Cooperative overflow fences work and keeps draining/discarding without signals. Original captured policy remains authoritative until exit; completion stays failed rather than verified. | Tested |
| EC-282 | Owned-group exit is treated as complete output while another write handle stays open. | A still-open stream records unknown supervision and refuses cleanup. Tests hold a real duplicate pipe handle outside an exited owned group; EOF does not get fabricated. | Tested |
| EC-283 | Supervisor death presents a complete log or deletes retained work. | Startup intent precedes observation; a crash leaves incomplete metadata and unknown supervision. Bounded retained bytes/work survive, with no claimed observed termination. | Tested |
| EC-284 | A file-write failure looks like a captured result or log memory grows with output. | Reader failure retains observed versus stored counts, bounded tail and an explicit evidence error. Capture failure cannot count as successful complete output. | Tested |
| EC-285 | A complete output log is mistaken for an execution completion after the supervisor dies at the final commit. | Before/after-commit kills preserve bytes/hash. Before commit leaves unknown control state with no exit event and no blind restart; after commit retains one exit event. Neither marks the task complete. | Tested |

## XIII. Claim allocation races (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-286 | An old Git-allocation error releases a newer owner, clears its locks or marks a newer busy agent left. | Cleanup checks the original task/owner/epoch/branch. Failure cleanup cannot act on a replacement epoch, including the same agent name; preparation preserves any current held task. | Tested |
| EC-287 | Delayed allocation success publishes stale paths or copies local settings into a newer assignment. | Finalization rechecks task/agent ownership and epoch before publishing or copying. A stale result refuses further writes and preserves the existing task and files. | Tested |
| EC-288 | A release races local file copying after the ownership check. | Local copies share the checked SQLite transaction, so another coordination writer cannot change ownership during those writes. | Tested |
| EC-289 | Copy failure rolls back the only worktree reference or removes partially written files. | Known path publication commits with a failure event; the command gives a repair refusal and retains partial files and the held task. | Tested |
| EC-290 | Pause during allocation leaves no path for checkpoint/handoff, or a missing directory is treated as ready. | Claim records its intended path before Git setup. Checkpoint refuses an uncreated directory; after setup, the fenced attempt refuses implementation but its retained path supports a fresh checkpoint and handoff. | Tested |

## XIV. Startup assignment and authority fences (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-291 | Preparation re-fetches a newer task after its original claim finishes and writes a brief for that assignment. | Explicit and automatic claims return the original task/epoch receipt. Preparation rechecks that receipt before brief writes; replacement tasks/epochs are retained unchanged. | Tested |
| EC-292 | Ownership changes between brief authorization and physical writes. | Brief and archive writes share the checked ownership transaction, blocking competing coordination writers during those writes. | Tested |
| EC-293 | A stale prepared task creates an execution intent for an obsolete lease. | The original assignment and policy are rechecked before committing startup intent; no helper is launched or intent invented for the stale request. | Tested |
| EC-294 | A delayed supervisor launch overwrites a newer task's PID or delivers an obsolete command. | PID publication and packet delivery share the ownership transaction. A stale unstarted helper receives no worker command and is stopped through its actual Popen handle; newer assignment metadata survives. | Tested |
| EC-295 | A supervisor's early assignment check becomes stale before worker creation. | The supervisor rechecks task/epoch/policy under the transaction that creates its actual owned group and publishes startup. A refused old helper clears only its own inherited PID reference, preserving a newer busy task. | Tested |
| EC-296 | A stop request arrives during startup and is overwritten by a running transition. | Startup control state and the original assignment are checked immediately before child creation; the command is refused without a worker or fabricated acknowledgement. | Tested |
| EC-297 | Parent death around the command-handoff commit silently starts a worker or fabricates delivery. | Actual before/after-commit kills prove rolled-back PID publication cannot authorize a worker; committed delivery can finish independently. Unknown control state and retained work remain explicit. | Tested |
| EC-298 | Supervisor dies after actual child creation but before its startup observation commits. | The observation rolls back and supervision becomes unknown. Cooperative fixture work survives; missing child metadata is never presented as proof no process ran or as task completion. | Tested |
| EC-299 | An old startup uses policy that changed during preparation/delivery. | New intents retain a configuration digest. Parent and supervisor refuse a mismatched startup snapshot before worker launch; running execution policies remain captured. | Tested |
| EC-300 | A coordinator stops while its worker is being prepared but the pending request still launches it. | Caller role and captured coordinator execution are rechecked at intent and handoff commits. Stopping/uncertain callers cannot create a new worker; prepared artifacts are retained. | Tested |

## XV. Interactive startup and exit fences (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-301 | An interactive launch uses an obsolete explicit/automatic task receipt, a newer epoch of the same name, or a replacement PID. | Startup rechecks its original task/epoch and prior process reference before creating the child. Changed assignments/processes refuse without overwriting the replacement. | Tested |
| EC-302 | A release races interactive child creation or PID publication. | Child creation and publication share the checked ownership transaction; a competing SQLite writer cannot change the assignment in between. | Tested |
| EC-303 | An old interactive child's exit clears a resumed name's replacement PID and makes its newer assignment offline. | Owned finalization changes agent/task state only when the registry still references its actual supervisor. Replacement PID, agent state and task survive. | Tested |
| EC-304 | A no-task launch becomes stale while copying its prompt or waiting for terminal confirmation. | The obsolete no-task path and its option are removed; argparse refuses it before registration. All launches require a prepared task. | Tested |
| EC-305 | Pause, policy edits or a stopped coordinator arrive during interactive preparation. | Current caller authority, captured parent execution, assignment and policy are checked immediately before interactive creation. A stopped caller cannot finish its pending launch. | Tested |
| EC-306 | A live interactive worker takes another task, then exits, and cleanup only settles its original task. | After observing its actual child exit, finalization checks that same process reference and handles its current held task; dirty work stays recoverable with the same epoch. | Tested |
| EC-307 | Interactive process creation fails and its claim/files are discarded or an unhelpful OS error escapes. | A repair refusal retains the claim, brief/worktree and current agent state; no launched event or child PID is invented; a recorded supervisor reference remains inspectable while startup is uncertain. | Tested |
| EC-308 | Interactive PID publication rolls back after an actual foreground child starts and a retry duplicates it. | Owned terminal startup retains an unknown execution after creation/commit failure, preserves work and requires reconciliation; it does not invent a successful publication or task completion. | Tested |
| EC-309 | SQLite refuses COMMIT but leaves the write transaction open, retaining locks and uncommitted changes after an error. | The transaction manager attempts rollback while still in a transaction, then propagates the error. A real SQLite authorizer denial proves task/event rollback and a second connection acquiring the writer afterward; rollback failure remains an error. | Tested |

## XVI. Claim, takeover and release OS-kill windows (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-310 | A CLI dies on either side of the ownership/lock/contract claim commit. | OS-kill tests prove pre-commit rollback and post-commit ownership with a planned path. Restart does not invent Git allocation, completion or duplicate claim events; explicit recovery preserves the offer rules. | Tested |
| EC-311 | A CLI dies just before or after Git creates its worktree and branch. | Tests inspect real refs, registered worktrees and the committed lease separately. A planned path can remain uncreated; created work survives without fabricated setup proof. A successor can retain local edits. | Tested |
| EC-312 | Physical local copies survive while setup publication rolls back, or a committed setup is mistaken for task completion. | Before/after setup-commit kills preserve ignored copies and the lease. The base SHA is published only on the committed side; target and task completion remain unchanged. | Tested |
| EC-313 | Takeover dies during ownership transfer or setup, splitting epochs, lock owners or contract history. | Real owner-process loss precedes the takeover trial. Before/after transfer/setup kills verify atomic new ownership, closed/active contract history, retained usage origin/limits and unchanged old work. | Tested |
| EC-314 | A plain release dies while closing the running contract and publishing a handoff. | Before/after commit kills prove atomic ownership/epoch/lock/agent/clock changes and one release event. Dirty work, branch and worktree stay retained; repeated status preserves the observed result. | Tested |
| EC-315 | A successor reclaims work while the old release CLI is paused after its commit. | Killing the actual old process cannot clear the successor's lease, agent state, contract or locks. The new assignment and retained edits survive repeated recovery. | Tested |
| EC-316 | Allocation fails on an existing path and the CLI dies during cleanup publication. | Before/after cleanup-commit kills preserve the collision and planned path. The committed side releases once; the other retains the original held claim/contract/locks. Neither deletes the preexisting file or invents a branch. | Tested |
| EC-317 | Takeover or a returning owner bypasses the original start refusal or a required replan. | Planned work returns to planning/awaiting answers and must pass start again. Contracted and legacy takeover, same-owner resume and answered-question replanning retain progress/files while refusing premature steps. | Tested |
| EC-318 | Owner loss, takeover or normal process exit leaves a running clock unaccounted or resets elapsed limits. | Observed loss/exit settles running time once, retaining elapsed policy. Takeover carries remaining time/deadline/usage origin; start resumes the clock. Tests cover blocked time, same-owner/grace resume, actual headless/interactive exit and active/debate expiry. | Tested |

## XVII. Allocation writers, terminal ownership and bounded protocol inputs (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-319 | Git continues checkout after its calling CLI dies and removes a successor's files. | Commit allocation intent before creating an owned Git job/group; block reuse, work and checkpoints while a writer may exist. Real smudge-filter tests cover live writers, caller OS-kill, observed group quiescence and labeled human reconciliation. | Tested |
| EC-320 | Allocation migration is interrupted or its failed constructor retains an open database handle. | Schema 10 creates receipts atomically without inventing legacy proof; failed initialization closes the connection. Rollback/retry preserves the old board. | Tested |
| EC-321 | Native usage counts cached tokens twice, invents cost, or accepts incomplete/malformed evidence. | Import bounded Claude result JSON or Codex JSONL with raw hashes; preserve missing accounting as unknown and reject invalid counters. Provider reports remain unauthenticated evidence. | Tested |
| EC-322 | Plan/start/progress/submission publication dies midway or is confused with target integration. | Actual CLI kill tests on both sides of each covered commit retain exact rollback/publication, clocks, steps, files and unchanged target refs. Every changed transaction exposes named before/after fault hooks. | Tested |
| EC-323 | Question/answer, pause/resume or offer publication dies and leaves contradictory control. | Actual before/after commit kills retain committed question/control/offer state once, require replan after late answers and recover idempotently. | Tested |
| EC-324 | Huge inputs, malformed configuration types or unbounded history requests exhaust a command or escape as internal errors. | Bound command/file reads, validate known configuration shapes and history limits, and refuse with repair actions while preserving board/files. | Tested |
| EC-325 | JSON lifecycle results omit the released subject or force clients to parse question prose. | Retain the original command subject and expose typed task/contract/questions/checkpoints plus paginated question history and next actions. | Tested |
| EC-326 | A terminal worker or its descendants outlive the initial child or receive another process's stop signal. | All foreground launches own private jobs/groups, inherit a Windows console or bridge a POSIX PTY, and share captured cooperative/terminate policy. Tests preserve unrelated processes and unfinished work. | Tested |
| EC-327 | A terminal launcher dies or child-creation publication rolls back and a retry invents cessation. | Durable intent precedes creation; uncertainty blocks automatic restart. Actual launcher OS-kills exercise cooperative/terminate policy and explicit human cessation attestation. | Tested |
| EC-328 | Supervision removes terminal input/controlling-tty semantics or leaves terminal settings changed. | Real POSIX PTY tests verify controlling terminal, input, window size, restoration and complete final output across short reads. The launcher drains all buffered output after group exit. Windows uses its inherited console; terminal output is streamed without inventing a retained capture. | Tested |

| EC-329 | Approval/assignment, counter/acceptance, manual locks/leave or control acknowledgements die during publication. | Actual before/after CLI kills compare the complete board snapshot, preserving architecture authority, one bounded offer, single ownership, acknowledgements/checkpoints and a checked start after pause resume. | Tested |

## XVIII. Standard local bus and consumer receipts (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-330 | Adapters disagree on envelope shape, retry identity or installed contract. | Version-1 JSON Schema and normative contract ship in the manifest; canonical envelopes and sender-scoped publication retries have conformance checks. | Tested |
| EC-331 | Two consumers process one mailbox message, or an acknowledgement bypasses a lease. | Atomic per-recipient leases issue one receipt; plain acknowledgement is removed, and delivery acknowledgement requires the matching current consumer/token receipt. | Tested |
| EC-332 | A restarted handler uses an expired or replaced token, or work needs renewal/retry. | Consumer/token/deadline fences, bounded renewal and explicit retry preserve pending work with a fresh token and incremented attempt. External effects still require idempotency. | Tested |
| EC-333 | Expiry or a broadcast acknowledgement fabricates another recipient's completion. | Receipt state stays per recipient; critical expiry becomes a dead letter without forging acknowledgement. | Tested |
| EC-334 | Unbounded leases/batches, historical notifications or priority hints change consumer semantics. | Bounded leases/batches, typed acknowledgement-required delivery and FIFO eligible IDs are explicit; historical read-once rows remain outside the leased dispatcher. | Tested |
| EC-335 | Adding consumer receipts rewrites historical mailbox observations. | Transactional schema-11 migration adds an empty claims table while preserving existing messages and recipient records. | Tested |
| EC-336 | A consumer dies before/after lease acquisition or acknowledgement commits. | Actual CLI kills on both sides retain only committed receipts; lost delivery output recovers after lease expiry and repeated successful ack is idempotent. | Tested |

## XIX. Adapter dispatch, wake hints and CI evidence (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-337 | A wake signal exposes an uncommitted message or survives a rolled-back write. | Queue hints inside the transaction and send only after successful commit; rollback clears the queue. Real loopback tests distinguish both boundaries. | Tested |
| EC-338 | A forged/lost datagram or unavailable sender replaces durable delivery. | Loopback tokens carry no control payload; invalid hints are ignored. Sender failure cannot fail a committed message; SQLite and bounded fallback remain authoritative. | Tested |
| EC-339 | Automatic dispatch acknowledges unseen work, loses receipts or lets a hook outlive its timeout. | Supervised adapters publish committed receipts to atomic inbox files, renew leases and run bounded owned hooks. Hook success is notification only; failure/timeout retains pending work. | Tested |
| EC-340 | A native tool hook treats notification as permission or acknowledges a stop automatically. | `bus hook` re-reads current control and epoch; optional enforcement exits 2 when blocked without completing or acknowledging interrupts. Native wrappers must allow recovery commands. | Tested |
| EC-341 | Listener migration invents historical deliveries or commits only part of schema 12. | Migration rollback leaves the old board intact, then creates an empty advisory listener table on retry. | Tested |
| EC-342 | A long supervisor poll delays messages and targeted stop notifications. | A real supervised worker with a 30-second poll receives committed messages and pause controls through wake-driven hooks; explicit owned stop remains policy-bound and retains work. | Tested |
| EC-343 | CI reports a failed subtest as passed or accepts tests against changing source. | The full discovery runner records parent-case subtest failure, exact ID coverage, log hashes and source drift; actual subprocess fixture runs refuse false success. | Tested |

| EC-344 | Compatibility defaults bypass reliable delivery, supervision, contracts or verification. | Current sends require receipt acknowledgement; replies do not ack; every launch is supervised; fresh claims have contracts and retained allowances survive reclaim. Removed CLI/config inputs refuse; protocol v2 has one result location; empty gates refuse integration. Historical state remains inspectable without fabricated proof. | Tested |

## XX. Managed headless sessions (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-345 | Worker windows vanish, reopening a viewer starts duplicate workers, or detaching loses running work. | A single terminal manages tabs over existing owned executions. Workers start headlessly, active/unknown sessions are reused by requested kind-count, viewer detach preserves live workers, and failed/exited records remain. Controls retain actor, review and captured stop policy; finite JSON inspection never enters a key loop. | Tested |
| EC-346 | Audit tabs expose arbitrary files, execute terminal escapes, mix boards or invent foreground transcripts. | Read-only selected-board session snapshots use execution-ID-derived regular log files, refuse links and forged output paths, sanitize terminal controls, bound reads/lines and follow byte cursors. Captured output and current task evidence remain distinct from completion receipts; uncaptured foreground output stays unavailable. | Tested |
| EC-347 | Captured Git/probe helper processes briefly open console windows on Windows. | Captured runner and Git-environment helpers use CREATE_NO_WINDOW; intentional interactive terminal creation remains explicit. The managed viewer uses the existing terminal and owned headless process path. | Tested |
| EC-348 | Starting a worker from the session viewer is guesswork: it asks for a CLI kind and a name with no choices, rejects a malformed answer with a bare rule, and the empty view names a command that no longer exists. | `s` lists the CLIs installed on this machine, accepts a number, a name or Enter for the first, and offers a free name and the next eligible task as defaults. A wrong kind, a malformed name or a taken name is explained and asked again instead of leaving the viewer; with no CLI installed it says to run `probe`. Ctrl+C cancels the prompt, not the viewer, and the empty view shows the real `hivewire spawn` command. | Tested |
| EC-349 | Agents that went offline long ago stay in every listing, so a long-running pool shows a graveyard and hides who is working. | `agents` and the dashboard hide offline agents that hold no task, no review and no live or uncertain execution, and say how many are hidden; `agents --all` lists them. An offline agent that still holds a task stays visible, so its silent owner is never hidden. Nothing is deleted from the board. | Tested |
| EC-350 | Dead agents accumulate forever: nothing removes them, so every listing grows with history nobody needs. | `agents --prune` (coordinator or human only; `--dry-run` previews) archives agents that are offline for longer than `reclaim_after_min` (or `--older-than MIN`) and hold no task, no review and no live or uncertain execution. Archiving sets them to `left` with reason `pruned` and records one event; rows, events and messages stay, so history and names in old events remain true, and the name can join again. A recently silent agent that may still resume, or the owner of unfinished work, is never archived. | Tested |
| EC-351 | A dead agent's steps are marked done but the work behind them exists only as uncommitted edits, so cleaning the worktree loses it while the board still says done. | When a holder is orphaned, the engine audits its recorded steps against the branch's commits and the worktree's uncommitted files, and snapshots every uncommitted and untracked file as a commit under `refs/swarm/rescue/TASK/eEPOCH` using a temporary index, leaving the worktree, index and branch untouched. The orphaning event and coordinator message state the counts and flag the progress UNVERIFIED when steps rest on uncommitted edits; `explain` shows the same audit; `claim --take-over` prints an UNVERIFIED PROGRESS notice with the files and snapshot ref and records `takeover_unverified`. Committed work is not flagged and leaves no snapshot. The successor must still review and commit the edits: `submit` refuses uncommitted files. | Tested |
| EC-352 | `next` fails for every agent with 'fatal: not a git repository' because one finished task's worktree folder survived a removal that stopped halfway (on Windows a folder in use cannot be deleted), and housekeeping for that task runs before anyone's next task is chosen. | A folder with no `.git` is a leftover, not a worktree. Cleanup removes it only when it is empty (`rmdir`, which cannot delete files), keeps and reports it when it still holds files, and defers when the folder is locked; the task's merged branch is deleted either way. A failing cleanup of someone else's finished task is reported on one line and never withholds the next task. Returning an untouched task, the progress audit and the rescue snapshot treat such a folder as unknown contents and leave it alone. | Tested |

## XXI. Deputy coordinator and attention queue (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-353 | Two scans or two claimers create duplicate attention items or two owners. | `dedupe_key` is unique per source signal; claim atomically compares `lease_epoch` and expiry inside one immediate transaction, so exactly one actor wins. | Tested |
| EC-354 | A scout turns an unread message, missing heartbeat or incident into an accusation. | Severity comes from observable state; the notice says the queue is not evidence of misconduct, and reports require cited evidence and an explicit decision owner. | Tested |
| EC-355 | A deputy acts outside its scope/capability or uses a coordinator-only command. | Every triage write checks live delegate, expiry, coordinator term, policy digest, capability and exact subject; the generic coordinator check still refuses the deputy. A scope violation is revoked after the failed action transaction commits. | Tested |
| EC-356 | A policy edit, coordinator election or agent departure leaves an old lease usable. | Reconcile revokes with a recorded reason and sends the deputy a stop message; status, sweeps and every action fence stale leases. | Tested |
| EC-357 | A deputy or coordinator dies mid-claim. | Claim leases expire; evidence and history survive; the next actor claims with an incremented epoch and the stale owner's report is refused. | Tested |
| EC-358 | Activation interrupts productive work, creates a sixth slot or flips constantly. | Eligibility is rule-based; activation refuses productive agents and a second active lease; minimum active time and cooldown add hysteresis. When all agents are busy the scout sends one capacity notice per day and joins nobody. | Tested |
| EC-359 | The dashboard invents attention state or loses the audit after refresh. | The read-only overview derives severity, status, owner, evidence, lease and action history from SQLite every request; refreshing can only replay committed state. | Tested |
| EC-360 | A deputy report acknowledges another inbox, resolves its own finding or claims authority. | Report sends an evidence-backed recommendation with a decision owner and grants no authority; resolve/reopen remain coordinator/human only; no message is auto-acknowledged. | Tested |
| EC-361 | Crash/retry duplicates a claim or silently changes a decision. | Expired-lease recovery is idempotent by epoch; terminal dispositions are immutable; reopening is explicit, versioned and recorded in history. | Tested |
| EC-362 | A deputy takes worker work or its lease ends while it still owns an attention item. | Reconcile ends the lease when the agent becomes productive, and revocation/release clears that deputy's claimed or investigating items back to `new` with a history note and preserved evidence, so one agent never holds two roles or strands an item. | Tested |
| EC-363 | An unowned P0/P1 item passes its response deadline or, without one, the queue SLA. | The scout sends one reminder to the coordinator or human, records it in the item's history without changing its status, and leaves the item claimable; the text assigns no blame. | Tested |
| EC-364 | A deputy uses incident or interrupt powers to steer its own review, cancel work, or reach beyond its lease. | `incident.propose` opens only a task-scoped incident, and the opener is excluded from the reviewer selection so it can never review its own proposal. `interrupt.request` allows attention or safety pause for a scoped target and refuses `cancel`. Resolve, reopen and cancellation remain coordinator/human only; using either capability outside the subject scope revokes the lease. | Tested |
| EC-365 | An agent holds a review reservation that no longer matches a live incident and revision. | The scout raises a P2 `incident` item citing the agent record, states that a human must settle it without inferring misconduct, and never reassigns the review itself. | Tested |
| EC-366 | A failed goal verification is mistaken for a task, or an unchanged scan rewrites timestamps on every command. | Verification subjects are typed `goal:<id>`, `task:<id>` or `verification:<id>`, so a reminder never addresses a goal ID as a task. Repeating a scan with unchanged summary and details writes nothing; freshness advances at most once a minute. | Tested |

## XXII. Proposal-driven integrity and liveness (unreleased)

| Id | Situation | Handling | Status |
|---|---|---|---|
| EC-367 | An agent omits `--as` and is recorded as `human`, satisfying a human-only gate. | `send`, contract mutations and incident mutations resolve identity from `--as`, then `SWARM_AS`, then refuse; a missing identity is never written as `human`. The send confirmation names the recorded sender. Explicit `--as human` remains an operator assertion. | Tested |
| EC-368 | A file discovered after acceptance forces a release, a replacement task and a lost queue position. | `contract scope add TASK --path P --reason R` lets a coordinator or human widen an active contract additively. The terms and event log record the paths, actor, reason and time; the task, epoch, queue position and review state survive; the owner is notified. Repeated paths change nothing and non-coordinators are refused. | Tested |
| EC-369 | A scope extension silently authorizes paths beyond the repository or outside the reviewed plan. | Extension paths are normalized and refused when absolute, drive-qualified or containing `..`; submit still checks every changed file against plan scope plus additions, and events/`explain` retain the history. | Tested |
| EC-370 | A fully implemented `ready_to_merge` task expires only because the merge queue or a required lock is busy. | When its deadline is within `[liveness] ready_to_merge_grace_min`, the engine grants one automatic, audited `queue_grace` extension at submit or on the next sweep. It names the blocking queue/lock and does not consume the owner's one manual extension; a second expiry still applies. | Tested |
| EC-371 | Queue, review and lock waiting consumes the implementation budget. | Submission stops accounted running time; `status` and `why` never resume it, so queue time is not charged while the active budget still expires within real work. | Tested |
| EC-372 | "Nothing you can take" leaves an agent guessing at the real blocker. | `why TASK [--json]` composes the state, owner, epoch and every enforced blocker (dependency, reservation, lock, merge queue, contract, checkpoint, merging, recorded failure) plus one concrete next action. It reads the board and bounded Git state only. | Tested |
| EC-373 | A watcher treats the human footer or the words "no new messages" as mail. | `inbox --wait --timeout N` emits one versioned JSON message envelope per stdout line, writes no footer and exits 0 on timeout; an empty timeout is silence, not an error or a fabricated message. | Tested |
| EC-374 | A polling agent is marked offline although it is running `status --as` every few minutes: only commands that called `require_agent` refreshed the heartbeat, while SKILL.md said every command did. The coordinator role then moved and the agent's task fell back to planning. | Any command that names a live agent (`--as` or `SWARM_AS`) refreshes its heartbeat before the sweep, so the result does not depend on who swept first. Writes are throttled to one a minute. An agent already past its timeout or already offline is not revived; that still takes `join --resume`. | Tested |
| EC-375 | A recovered task already has 15 recorded steps, so its new owner cannot add a single verification step: done steps counted toward the cap. | Steps already done do not count toward `max_steps`; only open steps do. An absolute ceiling of twice `max_steps` on the whole plan stays, so the cap cannot be dodged by marking steps done. | Tested |
| EC-376 | A live owner still reading the task loses the contract to the five-minute deliberation window, and the work returns to the pool. | When the owner is heard from after deliberation began, the window is doubled once, recorded in the contract terms and as a `deliberation_extended` event, so every reader sees the same window. A silent owner gets no extension, and past the doubled window the contract still expires. | Tested |
| EC-377 | An incident-gated task can never merge in a repository whose merge hook bumps a version file: clearance compared the reviewed tree with the tree after the hook, and the final scope check counted the hook's own edits as the author's. | `[merge] generated_paths` names the exact files the hook writes. Final integration leaves them out of the scope and hotspot checks, and clearance accepts the hook's commit when it differs from the reviewed work only in those paths. A hook edit anywhere else still stales the review. | Tested |
| EC-378 | A cleared review goes stale only because the target moved on an unrelated file, so the rebased head is a new commit carrying byte-identical work. | Reviews record a verbatim patch id of base..head (`git patch-id --verbatim` over a full-index binary diff without rename detection). Clearance, and the submission-head check, accept the identical patch replayed onto the new target; epoch, owner and policy stay bound. The review policy is versioned: version 2 leaves out exactly six contract clock fields (`deadline_at`, `active_time_min`, `active_seconds`, `blocked_seconds`, `checkpoint_at`, `extension_count`) and the submission's evidence text, keeps every other field including unknown ones (fail closed), and each review is compared under the version it was frozen with. | Tested |
| EC-379 | An author bakes the version bump or changelog entry into the branch, and it collides with the merge hook writing the same file. | `submit` refuses a branch that changes a generated path, names the paths and says how to restore them; the changelog text goes in `submit --changelog`. | Tested |
| EC-380 | A holder marked offline after a quiet spell rejoins to find its in-progress or ready task back in planning, and must re-plan work nothing touched. | Going offline records the task's state, epoch, worktree HEAD, its interrupts and whether the contract clock ran. A `join --resume` within `reclaim_after_min` that finds all of them unchanged keeps the state, restarts a clock that was running, and records `task_state_restored`. Anything moved, an operator handoff, or a later return still goes back through the start gate. | Tested |
| EC-381 | A coordinator demoted while polling comes back to find the role gone for good, or a sweep later flips the role back in the middle of the new coordinator's work. Promotion could also pick a reviewer or an incident subject. | The role returns only at the returner's `join --resume`, once, within `[swarm] coordinator_return_min` (30), and only to a quiet board: no merge holding the queue, the returner not an incident subject or reviewer. Otherwise the current coordinator keeps it until `coordinator hand-over --to NAME`, which only it or the human may run. A return or hand-over starts a new term, which fences the deputy lease. Promotion skips reviewers and incident subjects. | Tested |
| EC-382 | A foreground merge killed by an agent tool's timeout leaves the queue lease held for 45 minutes while its live agent keeps heartbeating, and every other merge waits. | The lease records an attempt id, the merging process's pid, start time and namespace (host, boot, WSL distro), and each owned gate or hook group it starts. A sweep breaks it as soon as all of them are proven gone on the same host and boot: no such process, an observed exit, or a different start time under the pid. Access denied, an unknown start time or another namespace prove nothing, and the timeout still applies. Queue ownership checks key on the attempt id. | Tested |
| EC-383 | The killed merge also leaves a tool-time usage run `unknown`, which only a human reconcile could settle. | A tool-time-only run (no token or money reservation) whose supervisor is proven gone by the same test is charged its full reservation, labelled `engine-verified: supervisor gone`. A run reserving tokens or money still needs the human. | Tested |
| EC-384 | Agent shells kill long foreground commands, and a merge's gates outlast them. | `merge --detach` runs the merge as a detached background process with its own log under the board directory and prints its attempt id; a foreground merge without a terminal says so. | Tested |


## What would close the open ones

- **EC-008, EC-011:** a networked service with per-agent credentials and one
  clock. That also enables pools across machines, which this version does not
  claim.
- **EC-121:** rebuilding the board from branches and the event log.
