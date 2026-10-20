# Resilient workforce implementation

This tracks the incremental implementation of
[the workforce proposal](../agents-collaboration-resilient-workforce-design.md).
The proposal remains the target, rather than a claim that every stage has shipped.
The [conformance audit](workforce-conformance.md) maps each requirement and
resilience invariant to current evidence and unfinished work.

| Stage | State | Deliverable |
|---|---|---|
| A: reasoned contracts | Implemented and locally verified; unreleased | Architecture gate, bounded contracts, recoverable expiry, checkpoints, explanation |
| B: communication and interrupts | Implemented and locally verified; unreleased | Typed durable envelopes, replay/acknowledgement, targeted interrupt lifecycle, handoff |
| C: oversight and memory | Implemented and locally verified; unreleased | Frozen incident review, independent evidence, scoped lessons and provenance |
| D: hardening | Unreleased candidate; acceptance open | Versioned JSON/events, operator diagnostics, final-commit gates, conformance tests, fixed-task trial harness; remaining gates below |

Current source uses CLI protocol **2**, schema **12** and bus/message/event
versions **1**. For current navigation and source-bound acceptance, use the
[documentation index](README.md). The verification chronology below preserves
earlier snapshots; it does not validate later working-tree edits. Command blocks
are workflow outlines: replace placeholders, complete all template fields and use
actual current epochs rather than assuming the illustrated IDs exist.

## Architecture decision

Extend the existing SQLite/Git engine and its standard-library CLI. A separate
scheduler service would introduce a second authority and deployment dependency.
Keep assignment transitions in SQLite transactions and retain the existing
rebase, gate, merge-intent and target-update path. Architecture and contracts are
coordination records; names and human/coordinator roles remain unauthenticated.

Every open goal requires a concise architecture brief. Existing goals retain
`workflow_version=1` as provenance, but that value grants no workflow exemption.
Record and approve a brief before continuing a migrated open goal. Goal edits invalidate its
approval; existing contracts then need a checkpoint/release and fresh offer.
Source fingerprints are checked when the brief is approved. Approved evidence
describes that baseline; subsequent legitimate merges do not invalidate it.

Schema 2 adds architecture metadata, contract history and checkpoints in one
transaction. Migration retries are idempotent and newer schemas are refused
before schema changes. Keep a database backup before installing an older binary:
schema compatibility is forward migration, not downgrade support.

Schema 3 extends messages with versioned envelope metadata and per-recipient
delivery/acknowledgement receipts, and adds targeted control records. Migration
preserves legacy direct and broadcast read state. SQLite remains authoritative;
the optional monitor polls it, and no push service or external broker is needed.

Schema 4 adds immutable incident review revisions, reviewer reservations, scoped
memory/history/observations, optional full-text indexing and retained integration
proofs. Existing boards migrate without retroactive incident requirements.

Schema 5 versions durable events. Legacy events become event version 1 without
changing their IDs or content; migration still rolls back atomically on a crash.

Schema 6 adds owned execution records and indexes in the same transactional
migration path. [Process supervision](process-supervision.md) documents captured
stop policies, private job/group ownership, uncertain supervisor recovery and
artifact preservation. It does not authenticate local actors or isolate credentials.

Schema 7 adds durable verification runs and goal closure receipts. Existing closed
goals remain explicitly legacy/unverified. [Completion evidence](completion-evidence.md)
describes executable outcome policy, checked external records, retained checkouts,
current-target closure and separately attested owed-check resolution.

Schema 8 adds the [usage ledger](usage-budgets.md): atomic reservations,
reported numeric token/cost facts with source hashes, observed owned-command
time and labeled conservative settlement. Running, blocked and tool time remain
distinct. Unknown/exhausted usage blocks new permissions and completion;
replacement assignments retain consumption. Hashed native Claude/Codex imports are available. Automatic collection, provider
billing authentication and full external-command coverage remain outstanding.

Schema 9 adds bounded headless worker output with typed capture metadata,
per-execution files and constant-memory drain/hash/tail accounting. Overflow
requests a policy-controlled stop; incomplete streams retain unknown supervision.
See [process supervision](process-supervision.md) for limits and provenance.

Schema 10 records owned Git allocations before process creation; schema 11 adds
leased bus receipts; schema 12 adds local advisory wake hints. CLI protocol 2 is
a separate interface version, not a database migration.

## Architecture before assignment

After defining outcomes and drafting tasks:

```text
swarm goal architecture health --template
swarm goal architecture health --set current_system="..." --set constraints="..." ... --evidence src/app.py
swarm goal architecture health
swarm goal architecture health --approve
swarm goal review health
swarm goal commit health --assign
```

The template names the ten fields: current system, constraints, options,
decision, boundaries, failure modes, rollout, rollback, acceptance checks and
unresolved decisions. Give concrete answers and repository-file evidence; set
`unresolved_decisions=none` only when settled. Short answers are sufficient for a
small fix. High-risk briefs require the human to approve; ordinary briefs allow
the coordinator. An approval never comes from a message.

## Bounded assignments

Every fresh task claim accepts the configurable default contract shown in the
claim output. Use an explicit offer when terms need negotiation before claiming:

```text
swarm contract offer T1 ann --active-time-min 30 --deadline-min 45
swarm contract show T1
swarm contract accept T1 --as ann
swarm claim T1 --as ann
```

An offer can instead specify `--deadline` as an absolute ISO timestamp with a
timezone. Its decision window is bounded by both the debate limit and absolute
deadline. The owner may `counter --reason "evidence and alternative"` once, or
report `blocked --reason "..."`. The coordinator uses `decide --reason "..."`
(optionally `--active-time-min N`). A decision does not reset the deadline or
counter allowance. The owner must accept the final offer before claiming.

The default contract policy is configurable in `.agents/swarm/config.toml`:

```toml
[contracts]
active_time_min = 30
deadline_min = 45
debate_min = 5
review_reserve_min = 5
checkpoint_min = 5
grace_min = 2
```

Active time means elapsed time between `start` and `block`/`submit`, accumulated
across resumes. It is **not measured tool time or token/cost usage**. Blocked
time is recorded separately; blocking does not move the absolute deadline.
`start` resumes after blocking. The review reserve stops new implementation
while still allowing submission, integration and recovery. Checkpoints are due
at the configured interval; a due checkpoint blocks new planning/start/step
permissions until recorded. These are initial heuristics, not benchmark results.

Task scope is bound by the offer's scope hint, or frozen from the first plan
when no hint exists. Later plans cannot broaden it. The old `task_budget_min` setting is refused with migration guidance; use
contract active-time/deadline limits. Every fresh claim receives a contract.
Already-held uncontracted work must checkpoint/release before reclaiming.

## Checkpoint and recovery

```text
swarm explain T1
swarm checkpoint --as ann --epoch 1 --note "progress and evidence" --next "concrete next step" --blockers "none"
swarm release --as ann "Checkpoint retained; run the fixture test before continuing."
```

Checkpoints record commit, tracked-diff fingerprint, status (including untracked
filenames), worktree/branch, locks, progress, blockers and next action. They do
not copy file contents into the board. Worktrees retain uncommitted contents;
commit valuable changes when possible. A checkpoint is not an acceptance check
or a claim of completion.

Expiry persists a cooperative interrupt, fences the old epoch, blocks new
planning/work/submission/integration and retains the branch, worktree and locks.
Read `explain` for the new epoch and checkpoint during the grace window. Release
with a handoff note, or ask the coordinator for one justified
`contract extend T1 --minutes 5 --reason "..."`. High-risk extensions require a
human. For expired terms, inspect the retained work and explicitly extend or
release/re-offer before reclaiming. Ordinary unexpired reclaim carries the prior
deadline, remaining allowance, scope and usage lineage; it is not a fresh budget.

If an agent disappears, takeover retains the original absolute deadline and
remaining active allowance. It does not silently grant another full budget.
A retained plan returns to planning/awaiting answers: read it, resolve critical
questions, replan if needed, then run `start` before resuming steps. Observed
owner loss or exit settles running time; start resumes its clock. Returning
owners use the same gate, including a return during reclaim grace.
An untouched assignment returned to the pool keeps the same deadline as well.
Expired assignments require an explicit extension or release/re-offer.

The sweep runs on every CLI invocation and in the optional monitor. Without a
monitor, enforcement occurs when the next command runs. After grace, the engine
escalates for recovery once; it does not terminate arbitrary agent processes or
remove their files. Owned headless and foreground execution can additionally
apply their captured explicit termination policy after grace. Owned command time
and supported usage imports are recorded; authenticated billing and uninstrumented
external calls remain outside that evidence.

## Reliable communication

The subsequent [standard local bus contract](../skills/agents-collaboration/BUS.md)
and [JSON Schema](../skills/agents-collaboration/BUS.schema.json) define the
machine-facing interface and consumer lifecycle. Schema 11 adds bounded
per-recipient leases through `bus receive/ack/retry/renew --json`. All current
producers use typed messages; historical read-once records remain inspectable.

```text
swarm send bob "Review the fixture decision" --as ann --kind decision --priority critical --key fixture-1 --task T1 --epoch 1
swarm inbox --as bob --json
swarm bus receive --as bob --consumer bob:boot-1 --json
swarm bus ack 42 --as bob --consumer bob:boot-1 --token TOKEN --json
swarm inbox --as bob --all --after 40 --limit 100 --json
swarm messages dead-letter
swarm messages resolve 42 --reason "The operator reviewed and deferred this decision"
```

Envelope version 1 includes the message/thread IDs, typed kind, sender,
recipient, task/epoch, priority, timestamps, reply/correlation references, body
reference and acknowledgement state. IDs increase globally, preserving each
thread's order. `--reply-to ID` keeps a reply in its parent's thread without
acknowledging transport delivery. Supported kinds are question, decision,
status, warning, experience, review request/result, interrupt, ack and handoff
(the CLI spells review kinds `review_request` and `review_result`).

Reading and acknowledging are distinct. Typed messages and all critical
messages redeliver until acknowledgement or expiry; acknowledgements do not
require another acknowledgement. Plain `send` defaults to reliable `status`; `--ping` and plain `ack` are
removed. Only `bus ack` with a consumer receipt acknowledges delivery. `--all` replays history; `--after` restricts that
explicit replay window and does not acknowledge earlier messages. Use the
leased `bus receive` batch for standalone processing, or the supervised
`SWARM_BUS_INBOX` receipts. An observational inbox read is not a processing lease. Broadcast
recipients are frozen at send time; joining later does not grant receipt or
acknowledgement rights for an earlier broadcast. Read/ack state is per recipient.

A sender-scoped `--key` makes retries idempotent. The same key with different
content is refused. Committed critical messages survive both lost send replies
and an inbox reader dying before it prints output. Optional `--expires-at`
accepts an ISO timestamp with timezone and is normalized to UTC. Critical expiry
records a durable dead letter and escalates once. Resolving it is a separate,
audited coordinator/human decision; it never forges recipient acknowledgement.

Defaults in `[messages]` are `max_body_bytes=65536`, `ttl_min=10080` (seven
days), `critical_ttl_min=1440` and `retention_days=30`. After retention, resolved,
acknowledged or expired payloads are pruned while their envelope and retry key
remain. Unresolved critical payloads stay available for recovery. Obvious
credential forms are redacted from new bodies and event details; metadata that
looks like a credential is rejected. This is best-effort minimization, not
general secret detection. Existing stored text is not retroactively scrubbed.

## Targeted interrupts and handoff

```text
swarm interrupt request bob --mode pause --reason "Review the interface boundary" --key pause-1
swarm interrupt show 1
swarm interrupt ack 1 --as bob --epoch 2
swarm checkpoint --as bob --epoch 2 --note "progress and blockers" --next "review the fixture"
swarm interrupt complete 1 --as bob --epoch 2 --checkpoint 7 --note "Stopped safely at this checkpoint"
swarm interrupt resume 1
```

Only the coordinator or human requests control. `attention` asks for a response
while work may continue; `pause`, `yield` and `cancel` immediately fence the task
epoch and stop new coordination permissions. The worker reads the new epoch,
acknowledges the control record, captures a checkpoint and completes it. A
generic message acknowledgement does not acknowledge control. An ordinary
message with kind `interrupt` cannot change a task's permissions.

Pause retains ownership and edits until an explicit coordinator/human resume;
resumption fences the epoch again. Yield and cancel complete with an atomic
checkpoint-backed handoff, keeping the branch and worktree and leaving the task
unfinished. Cancel requires a human by default; `[interrupts]
allow_coordinator_cancel=true` explicitly delegates it. The default decision
window is `[interrupts] deadline_min=2`; an absolute `--deadline` or
`--deadline-min` may override it within a maximum of 24 hours.

```text
swarm handoff --as bob --epoch 2 --checkpoint 7 --note "what remains and the evidence"
swarm checkpoint --as ann --task T1 --epoch 2 --note "operator recovery snapshot" --next "replan the fixture"
swarm handoff --as ann --task T1 --epoch 2 --checkpoint 8 --note "owner timed out; replan preserved work"
```

After timeout the control record escalates once and an operator can capture a
read-only recovery snapshot and hand off the assignment without pretending its
owner acknowledged. Operator handoff marks the unresponsive worker offline until
an explicit `join --resume`, preventing immediate reassignment. Plain release
cannot bypass an outstanding stop interrupt.
A checkpoint used for completion or handoff must belong to the current task and
epoch, follow the request, and still match the commit, tracked diff and untracked
contents. Altering an untracked file after checkpoint therefore requires a new
checkpoint. Retries of committed control requests/completions/handoffs are
idempotent. A contract extension does not resume a targeted pause.

The final permission check and Git target update share a SQLite write
transaction, so an interrupt either commits before that update and blocks it,
or observes the update after it finishes. The earlier committed merge intent
still recovers a process dying after Git moves. No interrupt or handoff removes
files or kills arbitrary processes; cooperative control is not OS isolation.
Late results bind both the task ID and epoch, so a worker moving to a different
task with the same numeric epoch cannot authorize the old merge. A late gate
failure cannot overwrite a newer pause state. Failed message hooks retain their
uncommitted edits. Handoff waits until an in-flight merge releases its queue lease.

## Independent incident review

```text
swarm incident open T1 --signal "The fixture may not cover the returned value" --reviewer cat --key fixture-review-1
swarm incident brief 1
swarm incident review 1 --as cat --snapshot <digest> --verdict not_confirmed --evidence diff:<hash> --remediation "Keep the fixture and require the configured acceptance gate"
swarm incident resolve 1 --revision 1 --outcome cleared --reason "Independent evidence did not confirm the suspected defect"
swarm incident refresh 1 --revision 1 --reviewer cat --reason "The code or policy changed; inspect the new committed evidence"
```

The coordinator/human opens an incident with a concrete signal; a coordinator
can also be its subject. The assigned reviewer must differ from the subject and
task owner, hold no implementation assignment, and have no other review. The
human is the fallback when no independent agent is free. Assignment reserves
the reviewer for read-only commands, and `agents`/`whoami` identify that role.
The engine never changes the accused worktree to perform review.

Each immutable revision includes task/owner/epoch, source and tree SHAs, scope,
policy hash, submitted/step checks, relevant events, diff and source citations.
Uncommitted content is separately fingerprinted, not claimed as a committed
review result. Evidence commits are pinned under `refs/swarm/evidence/` so a
squash, task-branch cleanup or Git GC cannot discard the inspected source.

Only the assigned reviewer may submit `confirmed`, `not_confirmed` or
`inconclusive`, naming the exact snapshot digest and actual citations from its
brief. Reports are immutable. Agent reviewers/subjects cannot resolve their own
findings; the coordinator or human makes a separate decision. `cleared`
requires `not_confirmed`; `upheld` and `escalated` keep integration blocked until
remediation and a fresh review. Findings never automatically sanction an agent.

Resolution and refresh require the expected revision. A changed commit, epoch,
submission or policy invalidates clearance. Rebase onto a changed target needs
current submission/review evidence. Engine squash may produce a new commit only
when its tree exactly equals the reviewed tree; the resulting source-to-merge
proof is retained in the task's `integration_evidence`. Configured gates still
run, and policy-file edits during a merge stop the attempt. Ordinary typed
`review_result` messages cannot clear incidents, mark work done or bypass gates.

Review and subsequent decision windows default to `[review] deadline_min=10`;
expiry escalates once and does not infer guilt. Agents get at most
`max_refreshes=2` before a human decision is required. Rule detection is opt-in:
`detect=true` opens sourced incidents for `detect_kinds` (default gate failure,
budget warning and stale merge result). Repeated sweeps do not reopen the same
event. Manual and detector incidents share the same independent review path.

## Scoped memory and learning

```text
swarm memory propose "Create the task fixture before the acceptance gate" --applicability "For this repository's isolated interface tests" --event 42 --commit <sha> --key fixture-lesson-1
swarm memory show 1
swarm memory verify 1 --as bob --revision 1 --confidence medium --reason "Inspected the pinned commit and source event; the applicability matches"
swarm memory search fixture --task T1
swarm memory mark 1 --revision 2 --state contradicted --event 51 --reason "New evidence contradicts this applicability"
swarm memory retire 1 --revision 3 --reason "Retain the historical lesson but stop offering it as current context"
```

Candidates start provisional and need a source event, addressed message or
commit. Promotion requires a different verifier, real local events and commit
SHAs. Foreign assertions and unreferenced chat are insufficient. Claim,
applicability, author, verifier, confidence, sensitivity, expiry, supersedes and
version/revision are stored with append-only transition history. Mutations fence
the expected revision. Proposal keys make lost-reply retries idempotent.
Evidence commits are pinned before the database commit; a killed write can
leave an extra preservation ref, never a committed reference to missing work.

Default scope is this repository. `--scope task --task T1` narrows a lesson;
another task does not retrieve it implicitly. Search uses SQLite FTS5 when
available, with a standard SQLite substring fallback. Default retrieval includes
only applicable, unexpired verified entries; `--all` explicitly audits provisional,
contradicted, stale and retired entries. Sensitive entries require explicit
visibility. Verified lessons are suggested in task context and architecture
templates, always labeled untrusted context. They never widen scope or alter
checks, approvals or policy. Supersedes is a provenance link, not automatic
promotion or retirement. Expiry (default `[memory] ttl_days=90`) marks lessons
stale; expired applicability requires a fresh candidate/review date.

Cross-repository sharing is off by default. The coordinator/human must enable
`[memory] allow_cross_repo=true` and pass `--cross-repo` to export/import a
versioned JSON file. Export refuses existing destinations unless explicitly
`--force` and supports `--dry-run`. Sensitive export requires the human and
`--include-sensitive`. Imports always start provisional, keep foreign metadata
as untrusted origin information and require local evidence/independent
verification. Exported `verified` state, verifier names and commit assertions
never become local authority. Sharing files sends no external messages or code.

Experience messages sharing a correlation ID appear in `memory candidates` as
unverified report groups. A maintainer can propose a sourced lesson and approve
a testable preflight change through the normal architecture/task workflow.
`memory observe ID --task T --outcome helpful|unhelpful|inconclusive --event E
--commit SHA --note "observed effect"` requires a task completion event after
local verification and its actual landed commit. `memory measure ID` reports
these self-reported utility observations and later incident reports for a signal;
it does not claim causal improvement. No chat, lesson or observation rewrites
policy or code automatically.

## Harness protocol and operator diagnostics

Use `swarm --json status`, `swarm whoami --as NAME --json` or JSON at any nested
command depth. One result envelope contains `protocol_version`, `ok`,
`exit_code`, `command`, typed `result`, human-readable `output`, `error`,
`event_cursor` and `unread`. Read typed data rather than parsing human prose.
Status includes the complete board, next actions, pending controls and owed
checks. Mutations return the actor/task where applicable; commands that already
produce JSON put it in `result`. Inbox/environment data is available only under `result`; the old top-level
JSON aliases have been removed in CLI protocol v2.

`swarm --protocol-version 2 --json protocol` discovers capabilities and refuses
unsupported versions. `swarm events --after 0 --limit 100 --json` replays durable
events in ascending ID order (maximum 1,000). Store `next_cursor`; an empty page
retains the previous cursor. Unknown event versions are refused. Event/message
contents remain untrusted data. Local agent names remain unauthenticated.

Exit 0 means the requested command completed; 2 means argument/permission/state
refusal, and 70 represents an unexpected internal failure in JSON mode. A JSON
merge that finishes without integrating exits 1 with the current task state.
The human text interface retains its existing merge exit behavior. A crash or
forced kill may produce no envelope; retry/replay the durable state rather than
assuming success. JSON blocks interactive launchers and terminals: use
`--dry-run`, or `--once` for monitor/dashboard.

`swarm doctor --json` gives typed issue codes, severity, task and safe next action.
It checks ownership/contract/reviewer/control drift, local Git artifacts,
completion/check provenance, missing evidence pins and owed checks. Health errors
exit 1; warnings remain visible with exit 0. Remote branches are queried only
with `--remote`. Coordinator/human `doctor --fix --dry-run` previews pending
cleanup; `--fix` applies the safe cleanup routine. It preserves unknown work and
new unmerged commits, and does not invent evidence or rebuild a damaged board.
Like other commands, doctor first commits the normal liveness/recovery sweep.

Merge gates now run against the exact final commit after message/commit hooks.
Tracked edits invalidate the check, and final scope/hotspot checks still apply.
The write-ahead intent and retained integration proof record the SHA, tree,
policy/config digest, actual check attempts/timing, and owed checks. An empty gate configuration refuses integration. Historical ungated receipts
remain `unconfigured`, never a passed verification.
This also protects tasks without incident reviews. Released branches already
known to the board can be claimed again without being mistaken for outside work.

## Verification history

The results in this section describe successive **historical source snapshots**.
References to a current/final candidate or unfinished work below belong to that
stage. They are not assertions about the present working tree. The
[platform validation guide](platform-validation.md) identifies the latest recorded
runtime snapshot and current acceptance gaps without combining old case counts.


`tests/test_contracts.py` uses temporary real Git repositories and subprocesses
to cover schema compatibility, killed migrations, architecture approval,
bounded negotiation, dirty-tree retention, stale epochs, active/blocked time,
checkpoints, review reserve, crash takeover, and expiry while merge gates run.
The existing goal tests and published simulation exercise the new architecture
step. CI remains configured for Windows, Linux and macOS; local results must not
be described as executed CI results.

At the earlier takeover-repair stage, the suite contained 326 distinct tests, including 11 takeover/start/clock
checks, 15 claim/release OS-kill
tests, 15 interactive-launch
tests, 16 owned-process tests,
eight preservation/policy-snapshot checks, 16 completion-verification tests,
14 usage-budget tests, nine headless-output checks, five allocation-race tests and
ten startup-fence tests. Schema-8 usage accounting
and its coverage limits are
described in [usage budgets](usage-budgets.md). Historical results below predate
that addition unless explicitly labeled schema 8.
Broad runs during this implementation and focused checks of subsequent fixes
are recorded separately; none establishes that an unexecuted matrix passed:

| Executed environment | Scope and authoritative result |
|---|---|
| Windows, Python 3.12.2 | Before schema-7 verification: full development suite, 231 passed, 966.496 seconds |
| Linux container, Python 3.13.16 | Before schema-7 verification: full development suite, 231 passed, 963.965 seconds |
| Windows, Python 3.11.14 | Earlier full 220-test run: 219 passed, one latency-instrumentation failure. The probe counted the standard-library `ver` OS query as Git. Repaired and covered by the focused checks below |
| Linux container, Python 3.12.15 | Earlier full suite at the 219-test revision: 219 passed; later guards are not established on this runtime by that run |

Focused checks ran with `ResourceWarning` treated as an error:

| Final focused environment | Result |
|---|---|
| Windows, Python 3.12.2 | Eight final preservation/snapshot tests plus reused-worktree coverage: nine passed, 54.575 seconds |
| Windows, Python 3.11.14 | Process, preservation and startup-cost suites: 29 passed, 105.020 seconds; before the final filename-whitespace subcase |
| Linux container, Python 3.13.16 | Eight final preservation/snapshot tests: eight passed, 21.187 seconds |

The filename-whitespace repair and simulation update were made during the broad
development runs. The focused checks establish the final filename guard; both
broad runs executed the updated simulation successfully. Repeat the full suite
from a frozen release candidate before publication. The simulation now moves
its known ignored bytecode caches to a recovery directory before cleanup; its
transcript and figures were regenerated. A harmless temporary `.cmd` adapter in
a path containing spaces also ran inside an owned Windows job and returned its
expected stdout with exit zero. That smoke check does not establish a real
provider trial.

macOS, Windows Python 3.13, Linux Python 3.11 and the full remote CI matrix remain
owed. See [platform reproduction](platform-validation.md).
Lint, manifest consistency and whitespace checks pass; the transcript and console
figures have been regenerated. No real-provider benchmark has been executed.

Schema-7 completion evidence was subsequently checked separately. During
development, affected suites passed 50 tests on Windows 3.12.2, 38 on Linux
3.13.16 and 19 on Windows 3.11.14, before the last control/accounting refinements.
The final completion-verification suite ran with resource warnings treated as
errors:

| Environment | Final receipt suite |
|---|---|
| Windows, Python 3.12.2 | 16 passed, 226.905 seconds |
| Linux container, Python 3.13.16 | 16 passed, 240.937 seconds |
| Windows, Python 3.11.14 | 16 passed, 238.702 seconds |

An earlier 40-test Windows run and 35-test Linux run each had one fixture-clock
failure: fast `start`/`block` calls shared a whole-second timestamp. The other 39
and 34 tests passed, including all 19 contract tests on each platform and five
Windows startup-cost tests. The clock fixture was repaired before the final
16-test runs above; both its running and blocked clocks were then made explicitly
deterministic and its final case passed again on all three runtimes (6.756, 7.383
and 7.060 seconds respectively). The final simulation also passed and regenerated
its transcript/figures with executable outcome checks and a retained receipt.

The production core during these receipt checks has SHA-256
`9ddb53fe838e272274891fbe917f116a0b92d8bea00a817d7af3f7db84555032`.
These results do not establish a full 247-test frozen-candidate or remote CI pass.

Schema-8 usage changes were then checked with resource warnings treated as
errors, with the production core frozen at SHA-256
`0d6ba94b548d4d8db25735f4346340fbfe54b110d83bcbe03e15699b2b5463fe`:

| Environment | Affected suites | Additional late-usage/goal-receipt case |
|---|---|---|
| Windows, Python 3.12.2 | 62 passed, 405.837 seconds: 13 budget, four owned-group, 19 contract, 16 verification, five startup-cost and five integration tests | Passed, 22.393 seconds |
| Windows, Python 3.11.14 | 33 passed, 330.828 seconds: 13 budget, four owned-group and 16 verification tests | Passed, 26.074 seconds |
| Linux container, Python 3.13.16 | Same 33 passed, 343.425 seconds | Passed, 25.366 seconds |

All 14 new budget cases therefore have focused evidence on these three
environments. The simulation also passed and regenerated its published
transcript/figures. This is not a full 261-test frozen-candidate or macOS/remote
CI result. No provider calls or paid benchmarks were performed; provider choice
and a human trial-spend decision remain pending. Native usage extraction,
interactive supervision, agent-log bounds and remaining transition fault tests
are still tracked in the conformance audit.

Eleven additional JSON-protocol/doctor/storage checks passed on Windows 3.12.2
in 46.363 seconds at the same core revision. Final review then added a refusal
to change currency on a replacement offer while retaining the prior ledger.
The expanded EC-275 case passed on Windows 3.12.2 (3.493 seconds), Windows
3.11.14 (3.831 seconds) and Linux 3.13.16 (4.888 seconds). That final core has
SHA-256 `48ec66db23ac7ac89dbfc752d3460d8e240073686b5eb1e2bd0ac6ed2bf98b93`;
the broader runs above precede only this currency guard. Lint, manifest and
whitespace checks were repeated after it.

Schema-9 output checks then exercised capped binary retention, typed metadata,
overflow policy, actual descendants, still-open stream handles, storage failure,
and killed execution-finalization commits. Broader affected suites passed 48
tests on Windows 3.12.2 (192.638 seconds: eight output, 16 process, eight
preservation, five startup-cost and 11 protocol/doctor/storage checks), and 24
each on Windows 3.11.14 (100.186 seconds) and Linux 3.13.16 (105.579 seconds).
The latter runs covered the eight output and 16 process checks. They began with
core SHA-256 `08e9039b5572f05a608c4d8750295fd9e9f53e8925df33391ef173b86dfb91af`;
only inactive execution-finish kill points were subsequently added while the
last Windows checks were finishing. The simulation also regenerated successfully
before those final kill points were added.

The final nine-case output suite, including before/after final-commit deaths,
then passed with resource warnings treated as errors against the unchanged core
SHA-256 `a3440fdac603486c44112f586151b14efea276bdcc557d610c0d6d24d7592904`:

| Environment | Final output suite |
|---|---|
| Windows, Python 3.12.2 | Nine passed, 46.541 seconds |
| Windows, Python 3.11.14 | Nine passed, 51.099 seconds |
| Linux container, Python 3.13.16 | Nine passed, 46.414 seconds |

No full 270-test frozen-candidate run, macOS run or remote CI result is implied.
The final manifest, lint, whitespace checks and edge-case totals were verified.
No paid provider calls or real-agent trials were made.

The complete schema-9 baseline then ran with resource warnings treated as errors
on three runtimes. All 53 source input hashes matched before/after the runs;
the core remained at `a3440fdac603486c44112f586151b14efea276bdcc557d610c0d6d24d7592904`.
[Logs, hashes and input manifest](validation/schema9-baseline/results.json) are retained.

| Complete baseline environment | Observed result |
|---|---|
| Windows, Python 3.12.2 | 270 run: 269 passed, one error; 1717.893 seconds |
| Windows, Python 3.11.14 | 270 run: 269 passed, one error; 1791.871 seconds |
| Linux container, Python 3.13.16 | 270 run: 269 passed, one error; 1826.510 seconds |

Each error came from EC-220's obsolete interception of `run`: the hook now uses
the owned/metered runner, so the fixture's fake `controlled-hook` executable was
actually launched. The fixture was replaced with a real failing Python hook
and a coordinator pause, preserving assertions about edits, interruption and an
unchanged target. These baseline runs are **not full-suite passes**.

A concurrent source audit independently reproduced an allocation bug: an old
failed claim released a newer holder, leaving the newer agent's task reference
inconsistent. The repair records the intended path before Git setup, checks the
original owner/epoch before failure cleanup or finalization, and holds the
ownership transaction through local file copies. Copy failure retains known
paths and partial files. An interrupted setup can checkpoint and hand off once
the retained path exists. Preparation error cleanup preserves a newer busy task.

The repaired core, SHA-256
`d8d288811ae341b043ed35f03de3000f6552530badeb9ccd8fec75d1cce722fc`,
passed 51 affected tests in an isolated copy before byte-identical promotion:

| Environment | Allocation, claims, contracts, startup and real-hook checks |
|---|---|
| Windows, Python 3.12.2 | 51 passed, 317.076 seconds |
| Windows, Python 3.11.14 | 51 passed, 344.858 seconds |
| Linux container, Python 3.13.16 | 51 passed, 391.508 seconds |

This includes five new allocation cases. It does not establish a passing full
275-test run. Further startup publication interleavings and transition kill
points remain explicit in the [crash audit](transition-crash-audit.md).

After promotion, all five allocation cases and all 20 communication/control
tests passed again in the workspace on Windows 3.12.2: 25 passed in 104.087
seconds. The simulation passed and regenerated its transcript and console
figures. The core still matches the tested repair hash above; lint, manifest,
whitespace and all three archived-log hashes were checked after the changes.

The startup audit then reproduced stale brief creation, PID publication and
child creation after an earlier assignment check, plus a coordinator stop that
did not prevent its pending worker launch. Claims now return their original
receipt; preparation and process handoff keep that task/epoch. Brief writes,
PID/packet publication and actual child creation have checked transaction
boundaries. Startup rechecks caller authority and configuration; refused old
helpers cannot offline a newer assignment. Unknown handoff/start observations
remain unknown, with retained work.

Before the final caller recheck, affected suites passed 61 tests on Windows
3.12.2 (233.647 seconds), 39 on Windows 3.11.14 (172.419 seconds), and 39 on Linux
3.13.16 (165.782 seconds). They covered the initial nine startup cases, process,
output and allocation suites; the Windows 3.12 run also covered first-run,
startup-cost and protocol/doctor/storage checks. That core had SHA-256
`432e490787f62c6306cb407b49a2febce9e96c2ba9a100e775f83d02eb3eb843`.

The final core, SHA-256
`f350cb33f63dce6cad064d28b91db23da5caf8950e93166138ab0eb0a3a39f3c`,
then passed all ten startup cases plus three existing coordinator/expiry checks
with resource warnings treated as errors:

| Environment | Final startup/caller checks |
|---|---|
| Windows, Python 3.12.2 | 13 passed, 57.592 seconds |
| Windows, Python 3.11.14 | 13 passed, 60.300 seconds |
| Linux container, Python 3.13.16 | 13 passed, 56.670 seconds |

Actual killed subprocesses cover both sides of PID/command handoff and child
creation before its observation commits. These are focused results, not a full
285-test or macOS/remote CI pass. Pipe/SQLite/filesystem failure combinations,
interactive supervision and other transition families remain required work.
No paid provider call or real-agent benchmark was performed.

The final startup source also passed the published simulation and regenerated
its transcript/console figures. Lint, manifest consistency, whitespace checks
and the updated 300-case/285-test counts were verified after documentation edits.

The next audit reproduced interactive startup after reassignment and old exit
finalization overwriting a resumed name's PID. The repair checks the original
lease, current caller/policy and prior process reference at actual child creation,
serialized with publication. No-task launches recheck after clipboard/terminal
waits. Exit handling preserves replacement registrations and settles the current
task of the same observed child. Failed creation retains work; uncertain
publication keeps waiting on the actual child and reports a refusal. A real
SQLite denied COMMIT additionally exposed an open write transaction; the shared
transaction manager now attempts rollback while still active, then propagates
the error. A second real connection verifies the writer is available afterward.

Core SHA-256
`128a96a540998d629fe9aa4ebf11562c595d25600f73b19597856cdee791d588`
passed these final focused sets with resource warnings treated as errors:

| Environment | Interactive/rollback/console follow-up |
|---|---|
| Windows, Python 3.12.2 | 43 passed, 288.971 seconds |
| Windows, Python 3.11.14 | 37 passed, 189.989 seconds |
| Linux container, Python 3.13.16 | 37 passed, 199.261 seconds |

All sets include the 15 new cases, console/menu workflows, doctor/storage and
the stopped-coordinator startup check. Windows 3.12 additionally checks startup
cost and the published simulation. The [raw logs and source fingerprints](validation/interactive-fences/results.json)
also retain the earlier 60-test run's launcher caller-argument regression and its
repair; that earlier run was not a pass. These focused results do not prove the
whole 300-test candidate, macOS, full interactive process supervision or every
transition crash window. The separate frozen 285-test full runs use the earlier
startup source and subsequently passed all 285 tests on each runtime:

| Frozen startup snapshot | Complete suite |
|---|---|
| Windows, Python 3.12.2 | 285 passed, 1796.504 seconds |
| Windows, Python 3.11.14 | 285 passed, 1875.508 seconds |
| Linux container, Python 3.13.16 | 285 passed, 1918.790 seconds |

The [complete logs and input hashes](validation/startup-baseline/results.json)
bind these runs to core
`f350cb33f63dce6cad064d28b91db23da5caf8950e93166138ab0eb0a3a39f3c`.
All 61 frozen input files matched before and after execution. The full runs
predate the interactive/SQLite rollback repairs and claim OS-kill additions;
they do not establish a passing full current 326-test suite or macOS/remote CI.

The claim audit adds 15 real OS-kill cases in `test_claim_crashes.py`, covering
both sides of ownership, Git creation, setup, failed-allocation cleanup and
plain release. Takeover follows actual registered owner-process loss; release
cases reserve/report their local usage window and advance a persisted running
clock before killing. The tests inspect retained refs/files plus atomic
task/agent/epoch/lock/contract state and repeat recovery. Core SHA-256
`3ce4f8ae09924a5dbf29aa8a4f03f84cb87735919a908ac06498922156161c45`
passed the new suite plus existing allocation/contract checks:

| Environment | Claim/release/contract follow-up |
|---|---|
| Windows, Python 3.12.2 | 39 passed, 204.616 seconds |
| Windows, Python 3.11.14 | 39 passed, 220.611 seconds |
| Linux container, Python 3.13.16 | 39 passed, 238.499 seconds |

[Raw logs and source fingerprints](validation/claim-crashes/results.json)
retain all results, including the earlier fixtures' missing-reservation
failures. All 31 recorded final inputs matched before/after the passing runs.
The initial Windows 3.12 run also passed the simulation/startup-cost checks,
but its three fixture failures mean that overall run was not a pass. The
corrected source keeps its production core unchanged. These are selected crash
and contract checks, not a complete 315-test candidate result. Additional probes
at this same core reproduce the unresolved takeover start-gate/running-clock
defects (EC-317/318); passing ownership tests do not resolve them. No provider
call or real-agent benchmark was performed.

The subsequent takeover repair adds 11 tests in `test_takeover.py`. Retained
plans return to planning/awaiting answers, so critical questions and required
replanning still block start. Completed steps, refs/files, epochs, deadline and
usage lineage survive. Observed owner loss or headless/interactive exit settles
running time once; returning owners and successors restart through `start`.
Old blocked time and remaining active allowance are retained, and already
elapsed deliberation/active limits cannot be reset by loss. The published
simulation now explicitly starts the retained plan after takeover. These tests
repair the demonstrated EC-317/318 gaps; broader acceptance remains owed.

The repair core, SHA-256
`2dc0c2d6893ca332ba2ef905ff913e0a143e2570143c08b6e613655decc054c2`,
passed the affected suites with resource warnings treated as errors:

| Environment | Takeover/start/clock repair follow-up |
|---|---|
| Windows, Python 3.12.2 | 99 passed, 562.487 seconds |
| Windows, Python 3.11.14 | 76 passed, 452.316 seconds |
| Linux container, Python 3.13.16 | 76 passed, 475.863 seconds |

All sets include the 11 new cases and existing contract, process, interactive
and claim OS-kill tests. Windows 3.12 additionally checks liveness,
doctor/storage, allocation races, startup cost and the updated simulation.
[Raw logs and source fingerprints](validation/takeover-repair/results.json)
retain the exact scope; all 32 recorded inputs matched before/after. This is
focused evidence for the repaired paths, not a full 326-test, macOS or remote CI
pass. Full interactive supervision and the remaining proposal gates stay owed.

Stage B adds `tests/test_communication.py`: real killed-subprocess windows around
message, inbox, interrupt, checkpoint and handoff commits; concurrent retries;
replay/ack/retention; forged messages and stale epochs; dirty-tree pause,
independent recovery and interrupted integration. The published simulation also
includes a checkpointed targeted pause and resume.

Stage C adds `tests/test_oversight.py`: reviewer/subject independence, immutable
citations and decision revisions, stale commit/epoch/policy checks, interrupted
integration, actual gates after false-alarm clearance, pinned evidence after GC,
SQLite migration/write crashes, scoped/expiring lessons, secret minimization,
untrusted imports and grounded utility observations. The simulation now includes
independent review of the coordinator's work and a separately verified post-task
lesson. Ordinary status startup still adds no Git processes or network imports.

Stage D adds `tests/test_hardening.py`: global JSON/argument conformance,
versioned replay and killed schema-4 migration, final-commit hook/gate checks,
late edits after intent, safe cleanup preview and unmerged-commit retention,
missing evidence/ownership diagnostics, fail-fast SQLite busy/retry and rollback,
a seeded claim/release ownership model, and concurrent takeovers. The
[workforce harness](workforce-benchmark.md) installs the local source into fresh
repositories and checks fixed coding tasks in all three modes. Its controlled
failure trial kills a merge process after Git advances, then checks exactly-once
recovery and retained proof. Default scripted runs measure mechanics only.

`tests/test_processes.py` adds real owned descendants, gate timeout/overflow and
callback cleanup, killed execution migration/intent, expired live contracts,
cooperative versus configured termination, targeted-pause expiry, unrelated and
reused registry PIDs, uncertain supervisor recovery, startup receipt/failure,
coordinator loss and independent worker lifetime, stale inherited context, and
policy validation/cache changes with restored file statistics. Operator stop
also settles accounted running time and fences the active contract. Unknown
termination remains unknown until inspected; human reconciliation is labeled
attestation. The Windows coordinator-loss regression failed before the private
job inheritance repair and passed after it.

### Historical candidate hardening follow-up

Schema 10 repairs a reproduced inside-Git data-loss window: a checkout continued
after its calling CLI died and removed a successor's files. Allocation intent now
commits before owned Git creation, and pending writers block reuse, work,
checkpoints and cleanup. `allocation show/prepare/reconcile` exposes retained
state and explicitly labeled human cessation attestation. The original
[counterexample and complete 326-test baseline](validation/pre-allocation-baseline/results.json)
are retained; that baseline passed 325/326 on each of Windows 3.11/3.12 and Linux
3.13. Its same merge-recovery fixture failure is repaired by explicitly starting
and submitting after owner resume, preserving the start/replan requirement.

The candidate adds foreground `launch` with captured execution
policy, private jobs/groups, descendant tracking, POSIX controlling-terminal I/O
and durable uncertain startup/exit. Actual launcher OS-kills, commit rollback,
cooperative/terminate stops and terminal restoration are covered by
`test_terminal_supervision.py`. Legacy launch remains available with its existing
limits; terminal output is streamed without fabricated retained capture proof.

Native Claude/Codex usage imports retain raw evidence hashes, avoid cache double
counting and preserve missing cost/counters as unknown. Known configuration
shapes and input/history sizes are checked. JSON lifecycle results retain the
original released subject and expose typed questions/contract/checkpoints;
question history has explicit cursors. Changed transactions expose named before
and after commit fault hooks. Seven new actual CLI-kill tests exercise plan,
start, progress, submit, question/answer, pause/resume and contract publication.

Two [matched real-agent trials](validation/live-agent-trials/report.md) used
OpenCode 2.0.32 with the same selected free model, settings and fixed acceptance
checks across solo, uncoordinated and coordinated modes. All 12 task outcomes
passed. One uncoordinated retry was needed in the second trial. No trial missed
its assignment deadline or needed human intervention; reported provider cost was
USD zero, aggregate tokens remain unknown. Setup failures and original evidence
hashes are retained. This tiny sample under concurrent validation load supports
no causal productivity or scaling claim. Final-source reruns have separate
candidate evidence.

[Completed staged validation](validation/candidate-matrix/report.md) covers 354
distinct snapshot cases per runtime on Windows Python 3.11/3.12/3.13 and Linux
Python 3.11/3.13. Windows has two POSIX-only skips; there are no unresolved
failures. The full 348-case baseline retained its original fixture failures;
corrected/new cases and the final 14-case JSON/latency follow-up have separate
frozen inputs and terminal results. This is not a consolidated full pass at the
final source SHA. No macOS run is claimed.

[The candidate's real-agent trials](validation/candidate-agent-trials/report.md)
include two matched pairs on free models. Results are mixed: timeouts and a
formatter that failed the negative-input check remain failures. GLM trial 1
passed all six outcomes; trial 2 verified five of six. Unfinished work and locks
were retained, and failed implementation was not promoted to a verified result.
These records supersede any inference from the older passing pair; they support
no productivity improvement claim.

## Remaining full-design gates

The implementation remains unreleased. Before claiming the complete proposal
achieved:

- Run a consolidated final-source CI matrix, including macOS on an actual runner;
  this Windows/Linux environment cannot establish a macOS result.
- Complete the transition-family/branch audit beyond the selected killed-process
  paths. Named hooks make every changed SQLite transaction injectable; that is
  not evidence that every external Git/filesystem/process interleaving was tested.
- Broaden native adapter/tool accounting beyond the explicit supported imports
  and owned command measurements where necessary. Uninstrumented external calls
  and authenticated provider billing are not observed by the local ledger.
- Review requirement/evidence mapping and prepare publication only after required
  acceptance. Legacy unconfigured merges remain visibly unverified.

Remote/distributed identity, cross-machine clocks, RTC and OS credential
isolation remain explicitly outside the first implementation, as the proposal
states. Those limits must remain visible in any release.
