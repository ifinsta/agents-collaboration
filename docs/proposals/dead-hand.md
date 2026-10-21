# Proposal: dead-hand authority and the liveness fixes

**Status:** proposal for review. Author: claude-worker (coordinator of the ifinpay pool).
Written against Hivewire 0.4.4, CLI protocol 2, board schema 13 (`e6dd239`).
**Evidence:** a 3.5-day ifinpay run (33 agents, 611 messages, 2,457 events, 38 tasks done),
summarised in the ifinpay collaboration review. Each problem below happened there.

## Summary

Hivewire's safety model held: no work was lost and no unsafe merge landed. Its liveness did
not. Six engine behaviours turned finished, reviewed work into hours of waiting, and every
long wait ended at a step only a human could take. This proposal adds one new authority path,
**dead hand**, for when the human is unavailable, and fixes the six behaviours.

Dead hand never lets one agent act alone and never pretends to be the human. An action that
today requires a human can instead run with two independent signatures, a **deputy's
review** and the **coordinator's approval**, and only after the human has been silent for a
configured time and the decision has waited for one. It is opt-in, limited to an allowlist,
fully audited, and the human can veto any pending ticket.

## Problems (observed)

| # | Problem | Cost in the run |
|---|---|---|
| P1 | Incident clearance is bound to the reviewed tree, but the merge hook edits tracked files (version trio, changelog), so the integrated tree never equals the reviewed tree. An incident-gated task cannot merge through `merge`. | G2-restore failed four times after 20-minute gate passes; ~8 h |
| P2 | Read-only commands (`status --as`) do not heartbeat although SKILL.md says every command does. Polling agents are marked offline, their task falls back to `planning`, and the coordinator role moves (once to the owner of the task under review). | coordinator lost 3 times |
| P3 | A foreground `merge` killed by the caller's tool timeout leaves a merge lease and hotspot lock with no live process, an `unknown` usage run and an expiring contract; recovery needs a human. | queue jammed ~1 h (twice in the run) |
| P4 | Human-only decisions (incident resolution after timeout, cessation attestations) have ~10-minute windows and no durable queue; the human needed hours. | four dependent tasks idle for hours |
| P5 | Retained steps count toward the 15-step plan cap; the 5-minute deliberation window expires while a live owner reads the scope rule. | 10 contract expiries for two agents |
| P6 | Authors bake version bumps or changelog entries into branches; the hook then bumps again (skipped versions) or the rebase conflicts. | three tasks |

## Fixes

### F1. Clearance by patch identity (P1)

Record, with each review, the **patch identity** of the work: `git patch-id --stable` of the
diff from the target merge-base to the reviewed head, **excluding** `[merge] generated_paths`.
At every clearance check the engine accepts the review if either the current tree equals the
reviewed tree (today's rule), or the patch identity of the work at hand, computed the same way
against the current target, equals the recorded one. The integrated commit is checked by
diffing it against the target it lands on, again excluding generated paths.

Owner, epoch and submission text no longer stale a clearance by themselves: a recovery
handoff of identical content is not new content. The policy hash keeps only the inputs that
change what is enforced (gates, merge, hotspots, review configuration, scope, acceptance),
not contract timing or evidence prose.

`[merge] generated_paths` (default `[]`) names files that only the merge hook writes.

### F2. Every identified command heartbeats (P2)

Any command that resolves an agent identity (`--as` or `SWARM_AS`) for a live agent refreshes
its heartbeat, read-only commands included. An offline agent still has to `join --resume`.
A short gap no longer resets a running task: rejoining within `reclaim_after_min` restores
the prior task state instead of `planning`. The coordinator role returns to the previous
coordinator if it rejoins within `[swarm] coordinator_return_min` (default 30) and nobody
holds an active deputy lease for coordination.

### F3. Dead process, dead lease (P3)

The merge lease records the merging process id and its start time. The sweep breaks the lease
(and releases the hotspot locks taken by that merge attempt) as soon as that process is
provably gone, instead of after 45 minutes. A tool-time-only usage run whose recorded
supervisor process is provably gone is settled as `charged` with the label
`supervisor gone (verified by pid)`; runs with token or cost accounting still need human or
dead-hand attestation. `merge --detach` starts the merge as an engine-owned background job,
prints its id and returns at once; `merge` without it warns when stdout is not a terminal.

### F4. Dead-hand authority (P4)

New `[deadhand]` configuration, **off by default**:

```toml
[deadhand]
enabled = false
human_silence_min = 60     # no human-attributed command or answer for this long
wait_min = 30              # the decision has been pending at least this long
ticket_ttl_min = 120
```

Delegable actions (allowlist):
`incident.resolve`, `incident.refresh`, `usage.reconcile`, `verification.reconcile`,
`execution.reconcile`, `allocation.reconcile`, `contract.extend.high_risk`.
Never delegable: memory export of sensitive entries, budget increases or cap removal,
answering a question addressed to the human, high-risk architecture approval, cancel
interrupts, and anything not on the allowlist.

Flow, each step one command, all recorded as events:

1. `deadhand request ACTION SUBJECT --reason R` (any agent). Refused unless enabled, the
   action is delegable, the human has been silent `human_silence_min` and the decision has
   waited `wait_min`. Creates ticket `D<n>` and an attention item.
2. `deadhand review D<n> --verdict approve|reject --evidence E` by a **deputy**: an agent with
   an active deputy lease carrying capability `deadhand.review` and a scope covering the
   subject. The deputy must not be the coordinator, the subject task's owner or author, the
   incident subject, or the requester.
3. `deadhand approve D<n> --reason R` by the **coordinator**, who must not be the deputy, the
   subject task's owner or the incident subject. If the coordinator is conflicted, the ticket
   waits for the human (or a neutral coordinator).
4. The gated command is then run by the coordinator with `--deadhand D<n>`. The engine checks
   the ticket matches action and subject, is approved, unexpired and unused, consumes it, and
   records `dead-hand authority: reviewed by X, approved by Y, human silent since T`. The
   record never says the human did it.
5. `deadhand veto D<n>` (human only) cancels an unused ticket. `deadhand list` and
   `human pending` show every decision waiting on a human, with the exact command.

### F5. Plans and deliberation (P5)

Steps already recorded as done do not count toward the 15-step cap; only new steps do. The
deliberation window is extended once, automatically and audited, when the owner heartbeats
within it and has not yet planned.

### F6. Generated files belong to the merge (P6)

With `[merge] generated_paths` set, `submit` refuses an author's change to a generated path
("the merge hook writes this"), and authors need no hotspot lock for them. This removes the
baked-bump and changelog-conflict class entirely.

## Safety argument

- Two independent signatures replace one human; neither can be the subject's owner.
- Opt-in, allowlisted, time-gated on real human silence, single-use, expiring, vetoable.
- The audit trail names who reviewed and who approved; nothing is attributed to the human.
- F1 relaxes only *what counts as the same content*; content changes still stale a review,
  and generated paths are exempt only when configured.
- F3 acts only on a process the engine can prove is gone; it never signals a PID.

## Tests (red before green)

One test per fix, against real git repositories in temporary directories, named after new
edge cases EC-353 onward:

- an incident-gated task merges through `merge` with a version-bumping hook (P1), and a
  real content change after review still stales it;
- `status --as` keeps an agent live; a rejoin within the window keeps the task state (P2);
- a merge lease whose process exited is broken by the next sweep; a live one is not (P3);
- dead hand: refused when disabled, too early, not allowlisted, deputy conflicted,
  coordinator conflicted, ticket reused or vetoed; succeeds with two independent signatures
  and records the attribution (P4);
- recorded steps do not count toward the cap; one automatic deliberation extension (P5);
- `submit` refuses an author edit to a generated path (P6).

## Delivery

Feature branch `deadhand-liveness`, one commit per fix with its tests, ruff clean, manifest
regenerated, EDGE-CASES and CHANGELOG updated. The deputy reviews the final diff before the
coordinator approves the merge to `main`. Rollout in the ifinpay pool through a tracked task.

## Out of scope

The fair FIFO lock service, `queue`/`timeline` views and the isolated-target merge from
`merge-liveness.md` stay proposals.
