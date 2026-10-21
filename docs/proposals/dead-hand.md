# Proposal: dead-hand authority and the liveness fixes

**Status:** revision 4, APPROVED (all phases) by the coordinator claude-worker on 2026-10-21 after
deputy pass 4 recommended approval (board #625). Two pass-4 implementation notes are folded in.
**Earlier status:** revision 4, for approval. Pass 3 on revision 3 (`9d7139d`) resolved R2, R3, R7
and R8 and asked for R1 wording fixes and four notes; all are closed here and marked
**(pass 3)**.
**Earlier status:** revision 3. Author: claude-worker (coordinator of the ifinpay pool).
Revision 1 (`415e51c`) was reviewed by deputy `deputy-review` (lease 1) with verdict
APPROVE WITH REQUIRED CHANGES; every required change is adopted below and marked **[Rn]**.
Revision 2 (`7c99840`) was re-checked (pass 2): R4, R5, R6, R9, R10 resolved; the gaps it
found in R1, R2, R3, R7 and R8 are closed in this revision and marked **(pass 2)**.
Written against Hivewire 0.4.4, CLI protocol 2, board schema 13 (`e6dd239`).

**Implementation review (pass 5).** The deputy's read-only review of `233cd63` rejected with two
blocking findings. (B1) Patch identity excludes generated paths, so a rebase-strategy merge could
land an author's commit to `VERSION` made after the review and submission; every merge now refuses
a branch that moves generated paths past its submission, and clearance and resolve refuse any such
change the review or submission did not cover. (B2) Verification checks inherited `SWARM_TOKEN`; the token and the merge
attempt marker are now removed from verification checks, verification and allocation checkouts,
inherited Git commands and spawned tool children. EC-389 and EC-390 cover both. The review's
should-fix and nit items were then implemented as advisory follow-ups, and EC-391 covers them:
the namespace includes the PID namespace, a killed merge's POSIX group must also be gone, a
tool run's owned group is recorded and must be gone before settlement, reconciles are rechecked
at consume on the supervisor's host, boot and PID namespace, the waiting key is bound to the
subject revision and cleared by the human's own action, verification-reconcile parties include
the task owner and the run's actor, a coordinator return requires a proven join token, and an
expired arm can no longer block that return.

The second review (pass 6) rejected that tip for one regression and one ineffective check: (N1) after
the target moved during the final gate, the retry compared a branch holding the hook's own
version write with the submitted head and refused a legitimate merge; the retry now resets to the
reviewed source head first. (S1) a POSIX group was recorded by the worker's pid, which is not
its leader, so the group probe always reported it gone; the anchor is recorded. EC-392 covers both.

## Summary

Hivewire's safety model held in a 3.5-day ifinpay run (33 agents, 611 messages, 38 tasks
done): no work was lost and no unsafe merge landed. Its liveness did not. Six behaviours turned
finished, reviewed work into hours of waiting, and every long wait ended at a step only a human
could take.

This proposal fixes the six behaviours (F1, F2, F3, F5, F6) and adds **dead-hand authority**
(F4): a human who expects to be unavailable *arms* it in advance, and while armed a short list
of human-only actions can run with two signatures, an engine-selected deputy's review and the
coordinator's approval. It never pretends to be the human.

**Identity caveat [R1].** Hivewire identities are claims, not authentication: `--as` names an
agent, and a command without one is recorded as the human. One process can claim two names.
Dead hand therefore does not claim to stop a single malicious process; it stops mistakes and
casual misuse, makes every use attributable, and requires a per-join secret so that a review
and an approval must come from two processes that each hold their own join token.

## Problems (confirmed by the deputy against `415e51c`)

| # | Problem | Evidence |
|---|---|---|
| P1 | Clearance compares the review's `tree_sha` with the tree of the commit the hook produces, so a hook that edits tracked files can never match. It also stales on any rebase (head), on a new epoch or owner, and on plan, submission and contract-term changes. | swarm_core.py 2577, 2586-2590, 2382-2388, 7117-7132, 7174, 7198 |
| P2 | `status --as` never heartbeats (only `require_agent` does), although SKILL.md says every command does; a rejoin resets a task to `planning`; promotion picks the oldest live agent with no conflict check. | 5369-5371, 1497, SKILL.md 362, 5226, 5764, 1656-1662 |
| P3 | The merge lease stores agent, task and time only; it breaks when the holder goes offline or after 45 minutes. (Merge itself takes no hotspot locks; task-held locks stay held.) | 6979, 87, 1643-1655, 5893, 7454 |
| P4 | About twenty human-only gates, several with ~10-minute windows and no durable queue. | 2728-2733, 2766, 4040, 4502, 4513, 5991, 8160, 9290 |
| P5 | Done steps count toward the 15-step cap; the deliberation window expires while a live owner is still reading. | 6204-6211, 89, 4158-4160 |
| P6 | Authors bake version bumps and changelog entries into branches. | observed three times |

## Fixes

### F1. Generated paths and patch identity (P1)

`[merge] generated_paths` lists **exact paths** (no globs) [R6] that only the merge hook writes,
for example the version trio and the changelog. Clearance stays exactly as strict as today,
with two narrow additions:

1. **Hook case.** After the hook runs, the clearance accepts the integrated commit if
   `diff(review_source, new_sha)` touches only `generated_paths` and
   `diff(target, review_source)` touches none of them [R6]. Any hook edit outside
   `generated_paths` still stales the review (EC-228 keeps passing).
2. **Rebase case.** A review stays valid across a rebase onto a newer target when the patch
   identity is unchanged: `git patch-id --verbatim` [R6] over
   `git diff --binary --full-index --no-renames` [R6] of merge-base to head, excluding
   `generated_paths`. `--verbatim` keeps whitespace significant, so a Python indentation change
   is new content; `--binary --full-index` stops binary changes from colliding.

The final check composes both cases (a rebased **and** hooked commit is the common one), and
`incident resolve` applies the same head rule (pass 2).

Owner and epoch binding are **kept** (EC-225: a new claim needs a fresh review). The policy
hash is computed from an explicit, exact field list in code, not "everything minus timing"
[R7, pass 2]. Kept: target, gates, merge, hotspots, review configuration, the plan, the whole
submission except its free-text evidence, contract scope, risk level, budget terms,
`goal_revision`, architecture approval, acceptance, and specifically
`submission.out_of_scope_reason` and `submission.changelog` (it feeds the hook). Dropped, and
only these: contract `deadline_at`, `active_time_min`, `active_seconds`, `blocked_seconds`,
`checkpoint_at`, `extension_count`, and `submission.evidence` prose. The same list is used by the
merge-time re-checks after the gates (today's lines 7133, 7172, 7196), which this therefore
narrows by exactly those fields. Any field on neither list, including future fields such as
`debate_min`, is **kept** (fail closed), and a test proves it (pass 3).

### F2. Liveness of identified agents (P2)

- Any command that resolves a live agent identity refreshes its heartbeat, throttled to at most
  once per 60 seconds to avoid SQLite contention (optional suggestion adopted).
- A rejoin within `reclaim_after_min` restores the prior task state instead of `planning`, only
  if the task's epoch, the worktree HEAD and its open interrupts are unchanged [R8].
- **Coordinator return [R8, pass 2].** Evaluated **once, at the returner's `join --resume`**,
  never flipped later by a sweep in the middle of someone's workflow. The role returns only if
  the returner rejoins within `[swarm] coordinator_return_min` (default 30) and the board is
  quiescent: no approved-but-unconsumed dead-hand ticket, no merge lease held, no ticket naming
  the returner, and the returner is neither an open incident subject nor a reserved reviewer.
  Otherwise the current coordinator keeps it until an explicit `coordinator hand-over`, which
  only the current coordinator or the human may run (pass 3). The
  change is broadcast, and, like any term change, it revokes the active triage deputy lease
  (swarm_deputy.py 1329). Promotion skips agents that are an incident subject or a reviewer.

### F3. Provably dead merge, dead lease (P3)

- The lease records an attempt id, the merging pid, its process start time, the host, the boot
  and the process namespace [R9]. Queue ownership checks key on the attempt id, not the task [R9].
- "Gone" means, checked in the same namespace on the same host: Windows
  `ERROR_INVALID_PARAMETER` on open, or a different start time, or an observed exit; POSIX
  no such pid or a different start time. Access-denied is **not** gone [R9]. The owned gate and
  hook process group must also be gone; on POSIX the leader may exit while a descendant still
  holds the group, in which case the lease stays. Otherwise the 45-minute timeout still applies.
- Breaking the lease does not release task-held hotspot locks [R9]; those stay with the task.
- The namespace id is the host name plus the boot id (Linux `/proc/sys/kernel/random/boot_id`,
  Windows last boot time rounded to the minute) plus the Linux PID namespace
  (`/proc/self/ns/pid`) when available, plus the WSL distro name when present (pass 2,
  advisory pass 5). A container or WSL distro with its own PID namespace never matches a pid
  from the host's.
- A tool-time-only usage run whose supervisor is provably gone by the same test is settled
  with the label `engine-verified: supervisor gone`, charged at the reservation (pass 2). The
  engine also records the tool process's own POSIX group and does not settle while any member
  remains (advisory pass 5).
- `merge --detach` runs the merge as an engine-owned background job and returns its attempt id;
  `merge` warns when stdout is not a terminal.

### F4. Dead-hand authority (P4)

**Arming [R3].** Only the human arms it, explicitly and in advance:
`deadhand arm --until T [--allow ACTION,...]`. Human silence is not inferred; read-only
commands write nothing, agents that omit `--as` look human, and web viewers are invisible.
Disarm with `deadhand disarm`. Any change to `[deadhand]` or `[merge] generated_paths` in
`config.toml` (an editable worktree file) disarms automatically [R3]. Floors are enforced in
code, not only config: `until` at most 72 hours, `wait_min` at least 30 [R3].

**Allowlist [R5].** `incident.resolve`, `usage.reconcile`, `verification.reconcile`,
`execution.reconcile`, `allocation.reconcile` (the reconciles only on the supervisor's host,
boot and PID namespace, checked when the ticket is consumed as well as when it is requested,
labelled `agent attestation`), and `contract.extend.high_risk` once per task for at most 60
minutes. Not delegable: `incident.refresh` (it would let a coordinator re-roll reviewers
past the cap), sensitive memory export, budget increases or cap removal, answering a question
addressed to the human, high-risk architecture approval, cancel interrupts.

**Independence [R2].** The `deadhand.review` capability is never chosen by the coordinator.
The engine selects the deputy: the longest-idle live agent that is not the coordinator, not the
requester, not the subject task's owner or author, not the incident subject and not its
reviewer. If none exists, the ticket waits. The requester must not be the coordinator.

**Flow.**
1. `deadhand request ACTION SUBJECT --args ... --reason R` (any agent but the coordinator):
   refused unless armed, allowlisted and the decision has waited `wait_min`. The ticket binds
   [R4] a hash of the full gated arguments, the subject's revision and snapshot, the coordinator
   term and the selected deputy's delegation id.
2. `deadhand review D<n> --verdict approve|reject --evidence E --token <join secret>` by the
   selected deputy.
3. `deadhand approve D<n> --reason R --token <join secret>` by the coordinator, who must not be
   the deputy, the requester, the subject's owner or the incident subject.
4. The approver runs the gated command with `--deadhand D<n> --token ...` [R4]. Consumption and
   the veto check happen inside the action's own transaction [R4]. The action never sets the
   actor to the human; its record reads `dead-hand authority: reviewed by X, approved by Y,
   armed by the human until T` [R4]. Texts that today say "Human attestation" are changed for
   this path [R4].
5. `deadhand veto D<n>` (human) cancels an unconsumed ticket. `human pending` lists every
   decision waiting on the human, with the exact command.

**Join secret [R1].** `join` returns a random token, stored hashed on the agent row and kept by
the agent's process; review, approve and consume require it. The token is read from
`SWARM_TOKEN` or stdin, never from argv, and is redacted from events and messages (pass 2).
A **proven resume** presents the current token and keeps the name's standing. A tokenless
resume is still allowed, because agents lose their token on a crash or context reset and a
refusal would bring back the liveness problem this proposal fixes (pass 3). It rotates the
token, is recorded as an **unproven resume**, and voids that name's dead-hand eligibility and
every unconsumed dead-hand signature it holds. `SWARM_TOKEN` is stripped from the environment
given to gates, hooks, verification and spawned children (`env_for`), so code under review
cannot read another agent's token (pass 3). **Migration:** names that predate the upgrade have
no token; their first join or resume after it mints one and is recorded as unproven, so they are
not dead-hand eligible until the human re-verifies them with `deadhand verify-agent NAME`,
which sits behind the arm terminal guard and is listed in `human pending` (pass 4). There is no
human resume path: the human never holds an agent name, so the arm and `verify-agent` guards are
the only terminal checks; the previous claim that a human resume used the same guard was wrong
(advisory pass 5). The coordinator role returns only on a **proven** resume of its holder, so an
agent that lost its token cannot take the role back (advisory pass 5).
Tickets record kind and model; `[deadhand] require_distinct_model` (default off) requires the
deputy and the coordinator to differ in model (optional suggestion adopted).

**Eligible deputies [R2, pass 2].** At `arm` the human names the agents eligible to review
(`--deputies a,b`), or accepts the default: agents live at arm time that were not started by
`spawn` on behalf of any party. Agents joined or spawned after arming are never eligible, so a
coordinator cannot steer the choice by keeping others busy or spawning a fresh agent. The
**engine issues the delegation**: when a ticket is requested it creates a dead-hand delegation
row for the selected eligible deputy (separate from the single triage lease that
`deputy activate` grants, so the coordinator never issues it), with capability
`deadhand.review`, scoped to that one ticket and expiring with it. It lives in its own table,
`deadhand_delegations`, so it never collides with the single-active-lease guard of the triage
lease (pass 3). A proven resume keeps eligibility; an unproven one loses it (pass 3).

**Arming needs a person [R3, pass 2].** `deadhand arm` refuses unless stdin is a terminal and
the operator types the confirmation phrase shown (`arm dead hand until <T>`); an agent running
headless without `--as` therefore cannot arm it by accident. Under Git Bash's mintty, where
`isatty()` is false for a real person, the check also accepts the MSYS pseudo-terminal
(`MSYSTEM` set and stdin named `\Device\NamedPipe\msys-...-pty`), and the docs name `winpty` as
the fallback; both paths are tested (pass 3).

### F5. Plans and deliberation (P5)

Done steps do not count toward `max_steps`, but an absolute ceiling of `2 x max_steps` total
steps stays [R10]. The deliberation window is documented as `debate_min x 2` for an owner who
heartbeats within it (one audited extension), since F2 makes it near-automatic.

### F6. Generated files belong to the merge (P6)

With `generated_paths` set, `submit` refuses an author's change to a generated path ("the merge
hook writes this"). Authors need no hotspot lock for those paths.

## Safety argument

- F1 accepts only configured, exact generated paths changing after review, or byte-identical
  patches across a rebase; any other change stales the review. Owner and epoch binding stay.
- F3 acts only on a process proven gone in its own namespace, including every member of its
  recorded POSIX group; it never signals a PID to establish death.
- F4 is off unless the human arms it, time-boxed, allowlisted, needs an engine-selected
  independent deputy and the coordinator, binds exact arguments, is single-use, vetoable, and
  attributed. It does not defend against one process holding two join tokens; that is stated.
- The terminal guard on `arm` and `verify-agent` stops accidents, not
  deliberate typing: an agent harness that runs commands in a pseudo-terminal passes `isatty`
  and can read the phrase. That is within the identity caveat (pass 4).
- After an upgrade or a crash, dead hand will often wait for lack of an eligible deputy. That
  fails safe and is intended (pass 4).

## Tests (red before green, EC-353 onward)

F1: an incident-gated task merges with a version hook; a hook edit outside `generated_paths`
still stales; a whitespace-only Python change across a rebase stales; a binary change does not
collide; a new claim still needs a fresh review; a generated-path commit made after the review
cannot land through a rebase, at resolve or merge (EC-389). F4: verification checks and inherited
children cannot read the join token (EC-390). F2: `status --as` keeps an agent live; a rejoin
keeps task state only when unchanged; coordinator return is refused while a ticket is pending.
F3: a lease whose process exited is broken; access-denied is not gone; a live merge is not.
F4: refused unarmed, after disarm, after a config edit, outside the allowlist, with a
coordinator-chosen deputy, conflicted parties, a wrong token, changed arguments, a reused or
vetoed ticket; succeeds with two independent signatures and the exact attribution. F5: the
ceiling holds. F6: an author edit to a generated path is refused. Advisory pass: the PID namespace
is named and a POSIX group outliving its leader is not gone (EC-382/383, POSIX-only); reconcile
namespaces are rechecked at consume; the waiting key follows the subject revision and the human's
decision clears it; verification parties exclude the owner and actor as deputies; an expired arm
does not block a return; a conflicted coordinator cannot approve; an unproven resume cannot take
the role (EC-391).

## Delivery

Feature branch `deadhand-liveness`. Phase A: F2 with the join token, then F5, F6, F1
(smallest and highest value first; the token lands with F2 so R1 and R8 are testable together,
pass 2). Phase B: F3. Phase C: F4, which starts only after the deputy confirms R1-R3. One commit per fix with its tests, ruff clean, manifest
regenerated, EDGE-CASES and CHANGELOG updated, the existing suite run before each push. The
deputy reviews the final diff of each phase before the coordinator merges it to `main`.

## Out of scope

The fair FIFO lock service, `queue`/`timeline` views and the isolated-target merge from
`merge-liveness.md` stay proposals.
