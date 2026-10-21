# Proposal: liveness under contention

**Status:** proposal, not implemented behavior. Written against Hivewire 0.4.4,
CLI protocol 2, board schema 13.

**Implementation status (2026-10-21):** the smallest useful set is implemented:
queue-aware active accounting (submission stops accounted time), one automatic
audited `queue_grace` deadline extension when a `ready_to_merge` task waits
behind the merge queue or a held task lock, additive audited scope for files
discovered mid-task, and `why TASK`. Still proposals: the fair FIFO lock
service, merge-owned generated paths, patch-identity review clearance, neutral
coordinator election, isolated target checkout and late-result rules, owned-work
heartbeats, and `queue`/`locks --waiters`/`timeline`/`next --explain`.

## Summary

Hivewire is good at **safety**: isolated worktrees, one task per agent, explicit
contracts, checkpoints, retained branches, independent review, and exact-commit
merge gates. It is weaker at **liveness under contention**. A task can be fully
implemented, reviewed, and submitted while the only remaining work is waiting for
a merge queue, a hotspot lock, a reviewer, or a human decision. If that wait is
longer than the contract deadline, the engine expires the task and starts a
recovery chain even though nothing about the work is wrong.

The central proposal is:

> Treat "ready but waiting" as a first-class state with an owner, an ETA, and a
> progress path. Do not charge implementation time for queue or review time.

The rest of this document describes the failure this proposal addresses, the
specific changes, and the tests that would make them real.

## The observed failure

A real downstream recovery task followed this path:

1. The implementation and tests were ready and submitted.
2. An independent review was required. The review was refreshed against each new
   head; when its window elapsed, only a human could clear it.
3. The task then waited behind a single `changelog` hotspot lock held by other
   merges. A blocked merge in front of it held the lock through a failed gate run.
4. The contract expired while the task was `ready_to_merge`. A one-time extension
   was needed, followed by an operator handoff because the task owner had
   temporarily become coordinator and could not extend its own contract.
5. The handoff invalidated the prior review clearance. A later rebase over a new
   target and a metadata-only version reset invalidated it again.
6. Main moved while the task waited, so the task required a hand rebase and a
   fresh review of the same semantic patch.
7. The final merge, once it started, was normal gate time.

The code was not the bottleneck. The engine had several **safe states with no
liveness path**: `ready_to_merge`, `needs_rebase`, `needs_human`, and
`waiting for a lock` all had guards, but no owned next action or bounded wait.

## Goals

- A task that is ready to merge must not expire merely because the merge queue is
  busy, a lock is held, or a reviewer is late.
- Queue time, lock time, and human-review time must be visible and attributable.
- A single slow task must not freeze unrelated work through an author-held
  changelog lock.
- A metadata-only rebase must not invalidate a review of an unchanged semantic
  patch.
- The coordinator role must not create a conflict-of-interest deadlock.
- A human-only decision must have a durable queue, not a one-shot review window.
- Existing safety properties must remain: no stale merge, no silent force, no
  unverified completion.

## Proposal

### 1. Queue-aware contracts and task states

Separate **active work** from **waiting**.

Add an explicit queue state between submission and merge:

```text
open -> claimed -> planning -> in_progress -> ready_to_merge -> queued -> merging -> merged
                                  |               |               |
                                  v               v               v
                          awaiting_answers   needs_rebase    merge_blocked
```

Contract accounting should follow the state:

| State | Counts toward active budget? | Absolute abandonment clock? |
|---|---:|---:|
| `in_progress`, `needs_rebase` | yes | yes |
| `ready_to_merge` | no | yes, generous |
| `queued` | no | yes, generous |
| `merging` | no | yes, generous |
| `awaiting_answers` | no | yes |
| `needs_human` | no | yes, with escalation |

When a task first enters `ready_to_merge`, grant one automatic, audited
extension if the merge queue or a required lock is occupied. Do not require the
owner to notice and ask. Keep a bounded wall-clock maximum so a forgotten task
still surfaces, but make the default long enough for a real gate run and queue.

Add a **liveness watchdog** that emits one durable event when a task has been in
`ready_to_merge`, `queued`, or `needs_human` beyond a threshold. The event names:

- the state,
- the blocking object (lock, queue position, reviewer, or human decision),
- the owner of that object,
- the next action, and
- the time at which the engine will escalate.

This is not a new authority. It is the missing "why is this not moving" record.

### 2. A fair lock service, and merge-owned release files

The current "locks never wait" rule is safe but creates starvation and churn.
Replace it with a lock service:

- FIFO waiter queue with a visible position.
- Short leases renewed by heartbeat.
- Automatic release when the owning task ends, expires, or is handed off.
- `lock --wait` with a bounded timeout and a clear refusal.
- `locks --waiters` showing holder, task, lease age, and the queue.
- One lock per logical resource; no author lock for merge-generated files.

More importantly, release files should not be author-owned at all. If a project
declares generated merge files, the **merge process** should be their only writer.
Authors should never take a `changelog` lock just to reserve a version number.

### 3. Generated-file policy

Add a project configuration list:

```toml
[merge]
generated_paths = [
  "CHANGELOG.md",
  "pyproject.toml",
  "backend/config/__init__.py",
]
```

For paths in this list:

- exclude them from task scope widening checks;
- exclude them from author hotspot locks;
- let the merge hook write them;
- auto-resolve conflicts that touch only these paths;
- do not invalidate review clearance when the semantic diff is unchanged.

The current rule that every source commit must carry a manually aligned version
trio creates avoidable rebases and conflicts. A version belongs to the published
merge commit, not to each task commit. If a project wants source-commit versions,
that remains configurable, but it should not be the engine default.

### 4. Clearance by patch identity

Bind independent review clearance to the thing that was reviewed:

```text
clearance = hash(patch_id, policy_hash, base_constraints)
```

A new head should inherit clearance when:

- its patch-id is unchanged, or
- the diff differs only in configured generated paths, and
- the review policy and base constraints are unchanged.

If the semantic diff changes, refresh the review automatically and keep the same
reviewer where possible. The current exact-SHA binding is correct for preventing
stale approval, but too strict for a rebase that changes only version metadata.
That strictness caused repeated human review cycles for an unchanged restore
implementation.

`needs_human` should be a durable decision item, not a dead end. A human console
or a small local approval queue should show:

- the frozen diff and review report,
- the exact question,
- the consequences of each outcome, and
- a one-click/short command path to clear, uphold, or escalate.

### 5. Neutral coordination and conflict-of-interest routing

Do not auto-promote an agent that holds a critical-path task to coordinator.
Add one of:

- a duty coordinator that is not a task owner,
- an explicit `--deputy` role for a bounded window, or
- a rule that coordinator election skips agents with `ready_to_merge` or
  `merging` tasks.

When the coordinator is also the task owner, the engine should route contract
extensions, offers, and incident resolutions to a neutral agent or the human
queue. The current hard refusal is safe, but it produced a deadlock in which
every participant was following the rules and no one could move the task.

### 6. Merge preflight, isolated target, and late results

The merge queue should be a subsystem, not a retry loop.

Add a preflight before a task joins the queue:

- target branch is known and its checkout is clean or isolated;
- no generated-file conflicts that the hook cannot resolve;
- required hotspot locks are acquirable by the merge process;
- contract is active and review clearance matches the patch identity.

Merge in an isolated checkout of the target, not the user's main checkout. A
dirty main checkout should not turn a valid merge into a fast-forward refusal
after a full gate run.

Expose:

- queue position,
- tasks ahead,
- estimated gate duration,
- current gate step, and
- the exact reason a merge is blocked.

Allow a late merge result to continue when the head, tree, and policy are
unchanged and only the task epoch changed through a recorded extension or
handoff. Refuse it when the semantic head changed. The current blanket refusal
discards valid work after a queue wait.

### 7. Activity heartbeats during owned work

A gate run, merge, verification, or Docker drill can take longer than the
offline threshold. Being marked offline during owned work caused orphan
recovery and handoffs in the observed case.

Keep an agent live while an engine-owned command group is running, up to a
configurable maximum. Record the activity source (`tool`, `gate`, `merge`,
`verification`) so an operator can distinguish a long gate from a silent agent.
Do not turn this into an unbounded heartbeat: the maximum and the owned process
group still bound it.

### 8. Better observability and `next --explain`

Add read-only commands:

```bash
hivewire why TASK
hivewire queue
hivewire locks --waiters
hivewire timeline TASK
hivewire next --explain
```

`why` should compose the current contract state, lock waiter position, incident
review state, merge queue position, target movement, and the exact next action.
`status` should say "merging now since 03:53" and "waiting for changelog lock
held by task X since 03:27", not make agents reconstruct that from events.

`next` should explain, per candidate, why it is unavailable: unmet dependency,
missing capability, held lock, reservation, or expired contract. An opaque
"nothing you can take" is not actionable.

### 9. Offer windows and stale branches

- Scale the contract decision window with task size and queue state. Five
  minutes is too short when an agent is in a long tool call.
- Send offers through the actionable bus path, not only as an inbox message that
  may be read later.
- When `claim` finds a branch that is zero commits ahead of the target and whose
  author is offline, offer `--adopt` with the author and last activity shown,
  after coordinator approval.
- When a task is submitted and the target moves, auto-rebase generated-file-only
  changes before asking the owner to rebase by hand.

## Suggested command surface

The exact names are less important than the behavior:

| Command | Purpose |
|---|---|
| `hivewire queue [--json]` | Merge queue, position, current gate, ETA |
| `hivewire why TASK` | One composed explanation of the current blocker |
| `hivewire locks --waiters` | Holder, lease age, waiter order |
| `hivewire timeline TASK` | Contract, review, queue, lock and merge events |
| `hivewire next --explain` | Per-task eligibility reasons |
| `hivewire lock NAME --wait --timeout N` | Bounded fair waiting |
| `hivewire merge --queue` | Join and report position without an immediate retry loop |

## Configuration sketch

```toml
[liveness]
queue_pauses_active_budget = true
ready_to_merge_grace_min = 240
watcher_warn_after_min = 20
watcher_escalate_after_min = 60

[merge]
generated_paths = ["CHANGELOG.md", "pyproject.toml", "version.py"]
queue_position_events = true
auto_rebase_generated_only = true
late_result_if_tree_unchanged = true

[locks]
fair_queue = true
default_lease_sec = 900
auto_release_on_task_end = true
```

## Tests and acceptance

Every behavior above needs a test against a real temporary Git repository, per
the project's contribution rules. At minimum:

1. A `ready_to_merge` task waiting behind a busy merge queue does not expire.
2. Queue time does not consume the active budget; work time still does.
3. A FIFO lock queue grants the lock to the next waiter, not the fastest caller.
4. A holder that goes offline releases its lock.
5. The merge hook owns generated files; an author never needs a changelog lock.
6. A rebase that changes only generated files keeps review clearance.
7. A semantic rebase invalidates clearance and refreshes review.
8. A coordinator who owns the critical-path task cannot be elected coordinator,
   or the conflict is routed to a neutral decision path.
9. A dirty main checkout cannot block a queued merge after its gates run.
10. A late merge result with an unchanged tree continues; a changed tree refuses.
11. An owned gate/merge keeps the agent live for its bounded duration.
12. `why`, `queue`, `locks --waiters` and `next --explain` report the same state
    the engine enforces.

Cross-platform coverage is required for the command surface and for path handling
in the generated-file list. Commands must remain cheap: `why` and `queue` should
read the board and a bounded amount of Git state, not start a merge or a gate.

## Rollout

A staged rollout limits risk:

1. **Non-breaking observability first:** `why`, `queue`, `locks --waiters`,
   `timeline`, `next --explain`, and the liveness watcher.
2. **Accounting:** queue-aware contracts and the automatic ready-to-merge
   extension.
3. **Merge-owned generated files:** config, merge-hook writes, auto-rebase, and
   clearance inheritance.
4. **Lock fairness:** FIFO waiters, leases, and auto-release.
5. **Coordination:** neutral coordinator election and the human decision queue.

Backward compatibility: old boards should load without migration; new config
keys should have safe defaults; projects that want the old strict behavior can
set `queue_pauses_active_budget = false` and keep the changelog author lock.

## Risks and tradeoffs

- Pausing deadlines can hide abandonment. Keep a generous wall-clock maximum,
  the liveness watcher, and an explicit `blocked_by` record.
- Automatic extension can mask queue starvation. Cap it at one, audit it, and
  escalate if the same task waits twice.
- Generated-file exemption can hide a real conflict. Only configured paths are
  exempt; everything else keeps the normal review and lock rules.
- Human identity is currently a trusted local name. If Hivewire is used across
  users or machines, human-only decisions should move behind a signed local
  approval session rather than `--as human`.
- Lock fairness adds state and failure modes. It should be introduced with the
  same crash/retry tests as the existing merge and message paths.

## What should not change

The safety model is worth keeping:

- one task per agent and explicit ownership;
- isolated worktrees and retained branches;
- contracts and checkpoints;
- independent review before integration;
- exact-commit gates and fail-closed behavior;
- no silent force, no implicit completion, and no stale merge.

The proposal is about giving those safeguards a progress path when the only
remaining work is waiting.

## Open questions

1. Should generated paths be configured per project only, or can a task declare
   additional generated outputs?
2. Should a queue wait pause the absolute deadline entirely, or only the active
   budget, with a separate long abandonment clock?
3. Can a neutral coordinator clear a `needs_human` incident after an independent
   review, or must every clearance remain human-only?
4. Should the merge queue support priority for critical-path tasks, and who
   assigns that priority?
5. Should stale zero-ahead branches be auto-adopted, or always require an
   explicit coordinator decision?

The smallest useful version is tests 1, 2, 6 and 8: queue-aware contracts, fair
locks, generated-file ownership, and a `why` command. Those four would have
removed most of the observed delay without weakening any existing gate.
