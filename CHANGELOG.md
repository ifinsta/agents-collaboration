# Changelog

## Unreleased

- Add dead-hand authority for when the human is away: off unless the human arms
  it from a terminal (`deadhand arm --until T`, at most 72 hours), it delegates a
  short allowlist of human-only decisions through an engine-chosen deputy's review
  and the coordinator's approval, bound to exact arguments and used once. Add join
  tokens, `human pending`, `deadhand veto/disarm/verify-agent`, and record every
  human-only refusal so it can be listed and waited on.

- Free the merge queue as soon as the merging process is proven gone on this host
  (pid, start time, boot), instead of after 45 minutes; access denied is not gone.
  Settle a tool-time-only usage run whose supervisor is proven gone as
  `engine-verified`. Add `merge --detach`, which runs the merge in the background.

- Keep a task's state when its holder rejoins within `reclaim_after_min` and
  nothing moved (epoch, worktree HEAD, interrupts), instead of sending it back to
  planning. Let a coordinator demoted while away take the role back once, at
  `join --resume`, within `[swarm] coordinator_return_min` and only to a quiet
  board; add `coordinator hand-over --to NAME`. Promotion skips reviewers and
  incident subjects.

- Let incident-gated work merge through a version hook: `[merge] generated_paths`
  names the files the hook writes, final integration leaves them to the hook, and
  clearance accepts a hook commit that differs from the reviewed work only there.
  Keep a clearance when identical work is rebased onto a moved target, matched by
  a verbatim patch id. Version the review policy so a clock no longer stales a
  review: exactly six contract clock fields and the evidence text are left out,
  and every other field stays bound. `submit` refuses a branch that edits a
  generated path.

- Stop recovery tripping the plan cap: steps already done no longer count toward
  `max_steps`, with a ceiling of twice the cap on the whole plan. Give a live owner
  one audited doubling of the deliberation window instead of expiring the contract
  while it is still reading; a silent owner still expires on time.

- Make every command that names a live agent a heartbeat, read-only ones such as
  `status --as` included, refreshed before the sweep and throttled to one write a
  minute; an agent past its timeout or offline is still not revived. Polling no
  longer gets a coordinator demoted. Correct the edge-case totals, which had drifted.

- Refuse a missing identity on `send`, contract mutations and incident mutations
  instead of recording `human`. Identity resolves from `--as`, then `SWARM_AS`,
  then refuses; the send confirmation names the recorded sender. This closes the
  impersonation-by-omission path in `docs/proposals/identity-scope-offers.md`
  without removing explicit `--as human` as an operator assertion.

- Let a coordinator or human widen an active contract additively with
  `contract scope add TASK --path P [--path P ...] --reason R`. The addition is
  recorded in the terms and event log, preserves the task, epoch, queue position
  and review state, and notifies the owner. Submit still checks every changed file
  against plan scope plus additions, and absolute or `..` paths are refused.

- Keep queue and review waiting out of the active budget. Submission stops
  accounted running time, and a `ready_to_merge` task behind a busy merge queue or
  a held task lock now receives one automatic, audited `queue_grace` extension
  when its deadline is within `[liveness] ready_to_merge_grace_min` (default 240
  minutes). It does not consume the owner's one manual extension and a second
  expiry still applies. `explain` retains the blocking queue/lock and reason.

- Add `hivewire why TASK [--json]`, which composes the current state, owner, epoch
  and enforced blockers (dependencies, reservations, locks, merge queue, contract,
  checkpoints, merging and a recorded failure) with one concrete next action.

- Add `hivewire inbox --wait [--after ID] --timeout N`: one versioned JSON envelope
  per stdout line, no human footer, exit 0 on timeout. An empty stream is silence,
  not an error, so watchers no longer parse prose.

- Add a deterministic operations scout and a bounded deputy coordinator. The scout
  converts critical messages, unanswered human decisions, stuck or orphaned tasks,
  failing verification, expiring contracts and aging incidents into one durable,
  deduplicated attention queue with lease-based claims and retained history. It never
  interrupts a productive agent, never creates a sixth worker, and never treats an
  unread message, a missing heartbeat or an open incident as misconduct. A coordinator
  or human can grant one scoped, time-bounded deputy lease for triage only: the deputy
  cannot pass coordinator checks, merge, cancel work, resolve its own findings, approve
  architecture or acknowledge another agent's inbox, and the lease is revoked when its
  coordinator term, policy digest, role or holder changes. Two capabilities can be
  granted explicitly: `incident.propose` opens a task-scoped incident whose opener is
  never the reviewer, and `interrupt.request` asks for attention or a safety pause on a
  scoped target. The scout also reports inconsistent review reservations without
  reassigning them or inferring misconduct. Unowned P0/P1 items past their response
  deadline, or past the queue SLA when they have none, get one visible reminder to the
  coordinator or human without changing the item's status. Add `hivewire deputy status/nominate/activate/release/scan` and
  `hivewire attention list/show/claim/investigate/report/escalate/resolve/reopen`.

- Type verification attention subjects as `goal:`, `task:` or `verification:`
  so a failed goal check is never addressed as a task, and skip writes when a
  repeated scan finds unchanged evidence.

- Add a recorded comparative benchmark for solo, coordinator-only and
  coordinator+deputy triage with crash, scope, all-busy and coordinator-term
  fault checks. On the tested Windows host all arms completed every scripted
  task and lost no work; the deputy arm was about 7.6% slower because a second
  agent consumed a slot on a three-task workload. The results are coordination
  measurements, not evidence of model-driven throughput.

- Show the attention queue and the live deputy lease in the web dashboard: a new
  Attention tab lists open items with severity, owner, deadline and history, and the
  overview names an active deputy, its scope and remaining time. The panels are
  read-only views over the same SQLite data.

- Show read versus unread in the web inbox: each message counts opened recipient
  copies, an Unread filter finds messages with an unopened copy, the recipient
  table shows per-agent read and acknowledgement timestamps, and opening a message
  addressed to the human records a read observation without acknowledging it.
  Message bodies render their Markdown (headings, lists, tables and code blocks)
  as aligned blocks instead of raw markers. Add `inbox --id MESSAGE` for observing
  one addressed message.

- Make starting a worker from the session viewer obvious: `s` lists the installed
  CLIs and defaults the CLI, task and name, explains a bad answer and asks again,
  and Ctrl+C cancels the prompt rather than the viewer. The empty view names the
  real `hivewire spawn` command. Hide offline agents that hold nothing from
  `agents` and the dashboard (`agents --all` shows them); owners of unfinished
  tasks stay visible and nothing is deleted.

- Add `agents --prune [--older-than MIN] [--dry-run]` for the coordinator or a human:
  archive agents that have been offline longer than `reclaim_after_min` and hold
  no task, review or live execution. Rows and history are kept and the name can
  join again.

- Stop a dead agent's "done" steps from hiding lost work. On orphaning, compare
  the recorded steps with the branch's commits and the worktree's uncommitted
  files, snapshot those files under `refs/swarm/rescue/` without touching the
  worktree, and flag the progress UNVERIFIED in the event, the coordinator
  message, `explain` and the `claim --take-over` output.

- Fix `next` aborting with "fatal: not a git repository" for every agent. A finished
  task whose worktree removal stopped halfway left a folder without `.git`; cleanup
  ran Git inside it and the error ended the command. Such a folder is now removed when
  empty, kept and reported when it holds files, and a failing cleanup is reported
  without withholding the next task.

- Open assignment visibility through `hivewire workspace`: reuse a hidden local
  dashboard, open its browser once, and manage agent tabs in one visible terminal.
  Add retryable viewer leases, headless/dry-run modes and explicit browser reopen.
  Coordinators now open the workspace at startup instead of asking people to do it.

- Name the product Hivewire: independent agents, accountable teamwork. Add the
  sole `hivewire.py` launcher, dashboard, installer pointers and current guides.
  Remove the old command alias and payload fallback; retire obsolete managed
  launcher files while preserving board/configuration data.

- Drain every buffered POSIX terminal-output chunk after an owned worker exits,
  including short PTY reads, before closing the terminal bridge.

- Polish the team canvas with spaced cards, recorded task-step progress, zoom,
  background panning, fit/reset, search, relationship navigation and participant
  focus. Preserve each board's camera across live updates, add keyboard controls
  and keep mobile cards readable. Patch cards and inspector sections in place
  while retaining the canvas and controls, and connect cards with smooth curves
  and directional arrowheads. Validate interactions under the production CSP.

- Add `sessions` and `console --managed`: one terminal with audit tabs over owned
  headless workers, reusable kind-count startup, policy-bound controls and detach
  without stopping workers. Retain failed/exited sessions and add bounded
  `execution logs`/follow plus selected-board dashboard session views. Captured
  Windows helper calls use CREATE_NO_WINDOW. Existing native interactive layouts
  remain explicit; uncaptured foreground output is never invented.

- Add `swarm dashboard --web`: a compact browser tool for the board, in `swarm_web.py`
  (standard library only, bound to 127.0.0.1).
  - Pages: an overview with a team and work table and a "waiting on you" list; a team canvas
    that shows agents as `Alex (claude) – Orchestrator` with agent icons and solid, dotted and
    dashed lines for approval and assignment, collaboration and independent review (pan, zoom,
    search, fit; no lane backgrounds); an inbox with delivery and receipt state; a decisions
    page; a Sessions page; and a page per task with its plan, evidence, checkpoints and locks.
    Roles are derived from the board, not configured. Pages fit the window height and work
    from 390 px wide.
  - Acting as the human: answer or waive a question, reply to and acknowledge messages
    addressed to the human, and approve an architecture brief, in place. Each runs the real
    `swarm` command through one guarded `POST /api/act`; `--read-only` turns actions off.
    Reads use read-only SQLite connections, a stored token and a Host check; the
    Content-Security-Policy allows only per-run nonces and the page never builds markup from
    board text.
  - Inbox steward (`swarm steward`, `--once`): a system participant that reminds agents of
    messages they leave unacknowledged, escalates offline recipients and critical messages to
    the coordinator, reports dead letters, and never acknowledges on anyone's behalf. Its
    reminders expire by themselves. From the page, "Review inboxes now" runs one review, and
    an LLM reviewer can be started on its own `INBOX-n` task.
  - One dashboard per user at a fixed address (port 8787, else the next free one, saved) with
    a stable link: a later run from any repository adds its board to the running dashboard,
    prints the same link and returns, and a board switcher lists them. `--reset-link` makes a
    new token. `--port`, `--no-open` and `--observe` (no sweeps) are the other options.
  - A seeded demo board (`examples/dashboard_demo.py`) and a screenshot script
    (`scripts/dashboard_screenshots.py`) produce the pictures in the README and
    `docs/images/`. They show seeded data, not live agents. See docs/web-dashboard.md.

- Remove runtime compatibility defaults: all sends use canonical typed kinds,
  acknowledgement requires a bus receipt, replies/control acknowledgements do
  not acknowledge transport, and every foreground launch is supervised. Remove
  no-task launches, old readiness commands and the task_budget_min setting.
  Give all fresh claims contracts, carry allowances across reclaim, require
  architecture for migrated open goals and executable gates for new merges.
  CLI protocol v2 removes duplicate top-level JSON fields; preserve forward
  migrations and historical unverified evidence. See docs/legacy-migration.md.

- Relay inboxes automatically for headless/supervised terminal adapters with
  schema-12 loopback wake hints, bounded fallback and renewable receipts. Add
  configured message/interrupt hooks plus `bus hook/listen`, keeping control
  acknowledgements explicit. Configure the complete suite on six OS/Python CI jobs
  with retained evidence and parent-case accounting for failed subtests; this
  configuration is not an executed hosted-matrix result.

- Standardize the local message bus with an installed version-1 contract and
  JSON Schema. Add `bus publish/receive/ack/retry/renew --json`, schema-11
  consumer receipts, bounded leases and stale-token fencing. Keep observational inbox reads and require idempotent effects across recovered delivery attempts.

- Fence real Git allocation writers with schema-10 receipts committed before
  owned process creation. Refuse reassignment and work while a writer may exist;
  retain uncertain state, inspection and explicit human cessation attestation.
  Add `allocation show/prepare/reconcile` recovery and interrupted-migration checks.
- Make `launch` use foreground job/group ownership, captured stop
  policy, descendant tracking, POSIX controlling PTY input/resize/restoration,
  and durable uncertainty on launcher/commit failure. The redundant
  `--supervised` flag and unsupervised path are removed.
- Import hashed native Claude/Codex usage without guessing absent costs or
  double-counting cached input. Bound configuration/file/command inputs and
  expose typed lifecycle subjects and paginated questions. Add named before/after
  hooks for changed transactions and actual lifecycle commit-kill regressions.
- Update merge-recovery verification to start and submit again after owner
  resume, retaining the explicit start/replan requirement.

- Revalidate start after planned takeover or an offline owner's return. Retain
  completed steps, work, deadlines and usage origin while unresolved questions
  and changed answers block further progress. Settle running clocks on observed
  loss and actual process exit; restart them at start, retaining blocked time
  and elapsed expiry limits. Contracted/legacy and process-exit regressions cover
  the previously reproduced EC-317/318 gaps.

- Add real OS-kill coverage around claim, takeover, Git allocation, setup,
  failed-allocation cleanup and plain release commits. Tests inspect refs/files,
  atomic ownership/locks/contracts, running-clock release and a reclaimed
  successor, preserving the distinction between planned paths and observed setup.

- Fence interactive startup after preparation and terminal confirmation, including
  changed policy/callers and replacement processes. Earlier no-task fences remain
  historical regression evidence; current launches require tasks. Serialize
  child creation/PID publication and preserve newer registrations at old-child
  exit. Settle the current task of the same exiting process; retain work on
  creation or publication failure. The supervised terminal follow-up above adds
  owned-group behavior for every foreground launch.
  SQLite transaction errors now attempt rollback if still active, releasing the
  writer after a refused commit; real authorizer-denial tests cover this path.

- Bind startup to the original claim receipt through brief writing, execution
  intent and command delivery. PID publication/delivery and worker creation are
  fenced against changed assignments, stop requests, policy edits and stopping
  coordinators. Actual helper handles clean up unstarted supervisors; ambiguous
  handoff/child-start crashes retain unknown state and work, with new crash tests.

- Fence delayed claim setup by owner/epoch: an old Git allocation cannot release
  a newer claim, overwrite its paths or copy local settings into its worktree.
  Planned paths survive interruption for checkpoint/handoff; copy failures retain
  known paths and partial files. Old preparation errors preserve newer busy agents.
  The hook/pause regression now uses an actual subprocess instead of an obsolete
  runner interception. Full baseline results and focused repairs are retained.

- Schema-9 bounded headless output: each new execution retains a capped worker
  log, observed byte counts/hash and a limited diagnostic tail. Excess output
  fences work and honors captured cooperative/terminate policy. Incomplete streams
  or capture failures cannot authorize cleanup or claim verified completion.

- Schema-8 usage ledger: atomic allowance reservations, hashed numeric token/cost
  reports, measured owned-command time, conservative human settlement and explicit
  human budget extensions. Unknown/exhausted usage blocks new permissions and
  completion; replacement assignments retain consumption. Provider billing quotas
  and automatic native usage collection remain outstanding; explicit hashed
  Claude/Codex native imports are supported.

- Observed completion evidence: executable revision-bound goal checks, retained
  verification receipts/checkouts, checked external task records, current-target
  goal closure and explicit human resolution of owed checks with retained history.
  Schema 7 preserves legacy closures as unverified. Verifier/record/closure crash
  windows have durable retry/recovery semantics; prose cannot replace check proof.
- Worktree return/cleanup preserves ignored files and edited briefs, defers for
  live or uncertain workers even after they take another task, and retains task
  references when Git refuses removal. Generated briefs retain content archives.
- Parsed policy is bound to one checked UTF-8 snapshot, including transient
  edits during loading; invalid TOML/encoding gives an actionable repair refusal.
- Durable headless execution supervision: captured cooperative/terminate policy,
  contract/interrupt timeout escalation, owned Windows jobs and anchored POSIX
  groups, explicit stop previews and human reconciliation of unknown supervision.
  Registry PIDs never authorize termination; uncertain/forced stops preserve work.
- Gates, message hooks and benchmark runners use owned groups for timeout/error
  cleanup, bounded captured output and descendant handling. Gate keepalives also
  recheck current permissions. Spawn/gate policy rejects quoted permissions and
  invalid/unbounded limits. Schema 6 adds backward-compatible execution records.
- Stage D foundation: global JSON command envelopes, protocol negotiation,
  versioned event replay, structured operator status and actionable diagnostics.
  Doctor offers cleanup previews and reports ownership/evidence drift and owed
  checks; unknown remote work is inspected only with explicit `--remote`.
- Integration runs gates on the exact final commit, including hook changes,
  retains check proof after cleanup, and refuses late edits or scope/hotspot
  violations. Cleanup preserves new unmerged commits on completed task branches.
- Deterministic conformance/storage/takeover tests and a fresh-install workforce
  trial harness with solo, uncoordinated and coordinated modes. The scripted
  runner validates mechanics; real-agent productivity and cost evidence remain owed.
- Stage C: independently assigned read-only incident reviews with immutable
  snapshots, cited reports, revision-fenced decisions, false-alarm support and
  bounded escalation. Commit/tree/epoch/policy checks prevent stale or forged
  review messages from authorizing integration; reviewed source refs and final
  integration proofs survive squash and cleanup.
- Scoped provisional/verified/contradicted/stale/retired lessons with independent
  promotion, local event/commit provenance, full-text search/fallback, expiry and
  history. Explicit cross-repository imports remain provisional. Experience
  grouping and grounded utility observations support a maintainer-approved
  learning loop without automatic code or policy rewrites.
- Stage B: versioned typed inbox envelopes, per-recipient acknowledgement/replay,
  sender-scoped retry keys, bounded payload retention and critical dead letters.
- Targeted attention/pause/yield/cancel controls with fencing, explicit
  acknowledgement, fresh checkpoints and durable handoff; interrupted integration
  rechecks permissions at the Git target update. Common credentials are redacted
  from new message bodies and event details (best effort).
- Stage A of the resilient workforce design: source-backed architecture briefs
  and revision-bound approval for every open goal. Migrated workflow-v1 metadata
  is provenance and no longer exempts an open goal from architecture approval.
- Bounded task contracts with offer/accept, one counter and one justified
  extension; separate accounted running/blocked time, an absolute deadline,
  review reserve and checkpoint interval.
- Expiry fences the assignment and requests a checkpoint without deleting work;
  `checkpoint` and `explain` support recovery. Merges recheck permissions after
  gates. Schema migrations are transactional and recover after a killed process.
- See [the implementation guide](docs/resilient-workforce.md) for policy defaults,
  limits and the remaining hardening stage.

## v0.4.4 - 2026-10-19

### Faster: every command is about 2.4 times quicker

Agents run the tool for every step, so half a second per command was the most
felt cost. It was measured piece by piece before anything was changed. Against
v0.4.3, with alternating runs on the same machine in a project with a config
(median of 15):

| Command | v0.4.3 | v0.4.4 |
|---|---|---|
| `version` | 529 ms | 213 ms |
| `status` | 817 ms | 330 ms |
| `agents` | 603 ms | 238 ms |
| `whoami` | 480 ms | 207 ms |
| `environment` | 722 ms | 311 ms |

What was slow, and what changed (EC-195):

- **Compiling the script, 340-550 ms on every run.** Python caches the bytecode
  of a module it imports, never of the script it is run as. The tool is now
  `swarm_core.py`, behind a 31-line `swarm.py` launcher. The commands to run
  are unchanged.
- **`urllib.request`, about 250 ms,** imported for `swarm update` alone. Rarely
  used imports (`urllib`, `textwrap`, `shlex`, `platform`, `locale`) are now
  imported where they are used.
- **Tool lookups, about 165 ms.** One scan of PATH replaces 17.
- **Three git processes per command, about 60 ms each.** The git directory is
  read from files; git is asked only in unusual layouts, and the environment
  probe asks it once instead of twice (EC-198).
- **`tomllib`, about 30 ms,** to read `config.toml`. The parsed config is cached
  until the file changes (EC-199).

SQLite (1.4 ms) and building the argument parser (16 ms) were measured and left
alone. What remains is mostly the interpreter and the standard library.

### Fixed

- **Cleanup never removes a worktree that has been reused for other work**
  (EC-200). A merged task's worktree is cleaned up by whichever agent next asks
  for work. In a real project an agent had switched such a directory to another
  branch and staged four new files in it. Git would have refused to remove it
  while it was dirty, but the moment those files were committed, the next
  `swarm next` would have deleted the directory. Cleanup now removes a worktree
  only while it is still on the task's own branch; otherwise it keeps it, still
  deletes the merged task branch, and says so.

### Added

- `scripts/bench.py` times the commands in a throwaway project, and compares two
  checkouts with `--source`. The test suite pins the work a command does (git
  processes started, modules loaded), never the time, so it cannot flake under
  load.
- The installer writes a `.gitignore` in the skill folder, so the bytecode cache
  stays out of `git status` (EC-196).
- A launcher that sees a `swarm_core.py` of another version refuses and prints
  the reinstall command (EC-197).

### Upgrading

`swarm update` (or the installer) writes both files. The first command after
installing writes the bytecode cache. If `PYTHONDONTWRITEBYTECODE` is set or the
skill folder is read-only, commands cost what they did before, no more.

## v0.4.3 - 2026-10-19

### Fixed: a merge that ends after the target moved

Suggested by a reader of the docs: git advances the target, then the worker ends
before the board records completion. Run against v0.4.2, the task could never
finish. Its branch "changes nothing" (so `submit` refused), `next` handed it to
another agent as unfinished work, and only a manual `swarm record` could close it.

- **Recognised and completed once.** A merge now writes its intent (the commit
  about to land) before the target moves. Any later command that finds that commit
  already in the target records the task as merged, exactly once, frees the
  agent, unblocks dependents and tells the coordinator (EC-189). The live merge
  and recovery share one compare-and-set, so a merge recorded by both is recorded
  once (EC-192).
- **Only git decides.** A missing, malformed or unlanded commit never completes
  a task (EC-191). A merge that ended before the target moved merges nothing, and
  its stale intent is dropped (EC-190).
- **Retrying is safe.** If the acknowledgement was lost and the agent runs
  `swarm merge` again, it is told the task is already merged (EC-194).
- **A dead merger no longer holds the queue.** A lease whose holder is offline is
  broken at once, not after 45 minutes (EC-193).
- Any free agent now cleans up a merged task's leftover worktree, not only the
  agent that held it.

## v0.4.2 - 2026-10-18

### Fixed

- **Long gates keep their merge alive.** In a real project a 26-minute test suite
  ran inside a merge with no heartbeat, so the service marked the merging agent
  offline mid-merge. The queue's 45-minute lease could expire the same way. Gates
  now run while the merge renews the agent's heartbeat and the lease every
  `keepalive_sec`, 30 seconds by default (EC-187).
- **A merge that lost the queue never moves the target.** Before the target
  branch advances, the merge checks it still holds the queue. If the lease was
  broken, it stops without touching anything (EC-188).

## v0.4.1 - 2026-10-18

### Added

- **Pictures of the console**, at the top of the README. `docs/console.svg` loops
  through six moments of the simulated session:
  - the goal committed;
  - three agents working at once;
  - the merge queue catching a conflict;
  - a silent agent's task taken over;
  - the gate catching a wrong test;
  - the goal closed on evidence.

  `docs/console-three-agents.svg` is a still of the three agents working. The
  simulation draws both from the tool's own board and monitor views, and CI
  builds them on every change.
- The simulated goal gains a third task (a changelog entry), so the first wave
  really runs three agents in parallel.

- **Kilo Code** (`kilocode`, verified with `@kilocode/cli` 0.18.0) is a supported
  agent CLI. It works with `probe`, `spawn` (`--auto`, `--yolo` when unattended,
  `-mo` for the model) and the console's `launch`. The adapter never uses Kilo's
  own `--parallel` branching, and a test keeps every adapter away from a CLI's
  own branching modes (EC-181).

### Fixed: work never leaves the pool

Found when two Qoder agents in a real project each took a task, received no
instructions, and were closed, which left both tasks orphaned and out of reach.

- **Untouched tasks return to the pool.** If an agent exits before planning,
  stepping, committing or changing anything, its task goes straight back to the
  pool and its empty worktree is removed. Existing boards are cleaned on the next
  command (EC-184).
- **Work left behind is offered.** When nothing is open, `next` offers an
  orphaned task as a take-over. The board lists it as "needs a new owner"
  (EC-185).
- **Every agent receives its instructions.** Qoder now starts with its first
  message (`-i`, new in Qoder 1.1.73). For a CLI that cannot take one, the
  message goes to the clipboard and the launch waits for Enter, instead of
  printing it behind the CLI's screen (EC-183).
- **CLIs that change are caught.** Qoder updated itself mid-session and dropped
  `-q` and `--max-turns`. Before `spawn`, `launch` or `probe` uses a CLI, every
  option is checked against its own `--help` (EC-182). The Qoder adapter is
  updated for 1.1.73.
- **An uncommitted skill is named.** `doctor`, and the coordinator's `join`, warn
  when the skill is installed but not committed, because then agents in
  worktrees cannot see it (EC-186).
- A launched agent's exit is recorded with its exit code and how long it ran.
- Events no longer show internals: no Python lists (`needs ['H-api']`), no claim
  epochs, and no list of every answered key. Goal outcomes and answers read as
  sentences.

## v0.4.0 - 2026-10-18

A console people can read, shaped by using the v0.2.0 console for real.

### Changed

- **Layout:** the board takes the left half at full height, and the event monitor
  and the launcher share the right. Agent panes asked for with `--agents` get
  their own tab (EC-180).
- **Fit:** every console view fits its pane. The board shows the most important
  lines first and fills the rest with recent events; lines are clipped or
  wrapped to the width (EC-174).
- **Readable events:** events read as sentences in local time, coloured by kind
  ("opencode joined: opencode / DeepSeek V4.1 Flash Free; caps bash, windows"),
  with no UTC stamps or Python lists. `NO_COLOR` turns colour off (EC-175).
- **The launcher:**
  - it starts each agent in a new tab of the same terminal (Windows Terminal or
    tmux) instead of inside its own small pane;
  - it offers the next open task, a chosen task (EC-179), or no task yet (EC-178);
  - leaving it explains how to reopen it (EC-177).

### Added

- `swarm launch <cli> --no-task`: join in the main checkout and ask for work.
- The monitor and the board restart themselves when `swarm.py` is updated
  (EC-176).

## v0.3.3 - 2026-10-18

### Added

- **[A simulated session](docs/simulation.md)** shows what to expect before you
  install. [`examples/simulate.py`](examples/simulate.py) runs it with the real
  installer, tool and git, and `--check` verifies every milestone in CI on every OS.
  Three agents and a human take one goal from a sentence to merged, verified work.
  On the way they meet hard questions, a refused gap, an overlap, a merge conflict,
  a silent agent taken over, and a failing gate.

### Fixed

- `goal answer` no longer counts an `unknown` as answered. It says which questions
  wait, which question each became, and who it went to (EC-173). Found by the
  simulation.
- The merge message has no trailing space when nothing was pushed.

## v0.3.2 - 2026-10-18

### Fixed

- **`--scaffold` no longer puts example tasks on the board.** In v0.3.1 the example
  config pointed at the example backlog, so the first command imported
  "EX-docs" and "EX-api" as real, claimable work. Now `--scaffold` creates only a
  config that explains every setting and names no backlog. The example backlog is marked, and the
  tool never imports it (EC-171).
- **A backlog file named in the config but missing** is reported instead of
  crashing the command (EC-172).

### If you used `--scaffold` with v0.3.1

Run `swarm update`, then `swarm sync`. It withdraws EX- tasks nobody has
touched. Delete `.agents/swarm/backlog.md` if it is the copied example.

## v0.3.1 - 2026-10-18

- The tool's output is UTF-8 on every OS. Through a pipe, which is how agents
  read it, Windows had used cp1252: "§" arrived garbled and a note containing
  "→" crashed the command (EC-170). Found by running v0.3.0 in a real project.

## v0.3.0 - 2026-10-18

Nothing about a project is assumed any more. A piece of work becomes tasks
through hard questions, backward and forward reasoning, and a review that attacks
the plan.

### Added

- **`swarm goal`:** `new`, `answer`, `ask`, `outcome`, `task`, `review`,
  `commit [--assign]`, `show`, `list` and `close`.
  - Questions come in four stages: understand, backward, forward, challenge. Thin
    answers are refused, and `unknown` becomes a blocking question (EC-159).
  - Every task serves an outcome (EC-160) and carries a done-check (EC-162).
  - Review refuses outcomes without work (EC-161), oversized tasks (EC-163) and
    dependencies on work that does not exist (EC-164).
  - Review shows the backward chain and the forward waves.
  - `commit --assign` gives the first wave to machines that can verify it
    (EC-167).
  - `close` needs evidence for every outcome (EC-169).
- **`swarm context`:** previous and next for a task. It shows what the tasks it
  builds on produced (evidence, files, commit, owed checks), and what each task
  waiting on it must achieve (EC-165, EC-166). The claim output and spawned
  agents' briefs include it.

### Changed

- The installer creates `.agents/swarm/config.toml` and `backlog.md` only with
  `--scaffold`. The tool runs on defaults; a backlog file is optional (EC-168).

## v0.2.0 - 2026-10-18

See the pool, and drive it, from a terminal. Agents can install the skill
themselves.

### Added

- **`swarm console`** opens a visible terminal in the project, split into at least
  three panes:
  - an event monitor;
  - the live board;
  - an agent launcher;
  - one interactive pane per agent asked for with `--agents`.

  On Windows it uses Windows Terminal split panes; on Linux and macOS, tmux in a
  new window. Without either it uses separate windows, and on a machine with no
  display it prints what to run (EC-152).
- **The console question.** The coordinator is told to ask the human once per
  board whether to open the console; `--decline` records a no (EC-149).
- **`swarm launch <cli>`** starts an agent CLI interactively in the current
  terminal, already joined and holding a task, inside its worktree with its brief
  (EC-153). If the CLI cannot take a first message, it prints the one to paste
  (EC-155).
- **`swarm launcher`** (a menu), **`swarm dashboard`** (the live board) and
  **`swarm monitor --observe`** (follow events beside a running monitor, EC-150).
- **`[worktree] copy`** copies git-ignored local files such as `.env` into each new
  worktree (EC-148).
- **`swarm version`** and **`swarm update`** (EC-158).
- **Installer:**
  - `--claude` adds a Claude Code pointer skill (EC-156);
  - `--user` installs once for every repository (EC-157);
  - `--all` adds every pointer.
- **INSTALL.md**, an install guide written for agents.

### Changed

- `spawn` and `launch` share one preparation step: join, claim, brief.

## v0.1.2 - 2026-10-18

- The installer keeps the line endings and byte-order mark of the files it edits.
  On Windows it rewrote `AGENTS.md` with CRLF throughout, so a ten-line section
  showed as a whole-file change (EC-146).
- `swarm record <task> --commit <sha>` marks a task done when its work reached the
  target outside the board. It is for migrating from an earlier board, or for
  work a person merged. It checks the commit is in the target's history, frees the
  holder and cleans up the worktree (EC-147).

## v0.1.1 - 2026-10-18

Fixes from the first real run, in a repository where five agents were already
working through an earlier board.

- `claim` refuses a task whose branch already exists (work started outside the
  board). `--adopt` continues it and tells the coordinator, and `next` never
  hands such a task out (EC-042, EC-141).
- Gates that name their program by relative path now resolve it from the task's
  worktree on every OS. Windows had resolved it from the caller's directory, so
  the gate failed (EC-144). `doctor` checks gates the same way.
- `spawn --dry-run` changes nothing; it used to join the agent and claim the
  task (EC-145).
- Finishing every step within two minutes of `start` is flagged to the
  coordinator (EC-142).
- Only whoever set a pause, or a human, can lift it (EC-143). `pause` and
  `resume` now run the sweep like every other command.
- Broadcasts are matched to agents by message id, not by a one-second timestamp,
  so an agent joining in the same second never sees an earlier broadcast
  (EC-103). Boards created by v0.1.0 are upgraded in place.

## v0.1.0 - 2026-10-18

First public release.

- `swarm.py`: a coordination service for up to five coding agents on one git
  repository. It is one standard-library Python file, and its state lives in
  SQLite inside the git directory.
  - Pool: join and solo detection, readiness, roles, and an elected coordinator.
  - Tasks: one task per agent, claims with fencing, a worktree, branch and slot
    per task.
  - Planning: critical questions that block work until answered, ordered plans,
    and step evidence.
  - Conflicts: scope overlap checks, and hotspot locks with leases.
  - Merging: a single merge queue that rebases, runs gates on the rebased tree,
    advances the target with compare-and-swap, and never overwrites a person's
    work.
  - Operation: a background monitor, and `doctor` for drift.
- Environment intelligence: the service detects the OS, shell, Python command,
  tools, encoding and git settings. It turns them into rules for agents and
  capabilities for task routing, and gates can differ by OS.
- Agent CLIs: readiness probing and headless spawning for Claude Code, opencode,
  Qoder, Codex and Gemini. DeepSeek's adapter is included but unverified.
- `SKILL.md`: the protocol, written for any agent CLI.
- `EDGE-CASES.md`: 140 collaboration edge cases with their handling and status.
- `install.py`: one-line install from GitHub, verified against the release
  manifest.
