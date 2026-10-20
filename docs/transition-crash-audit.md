# Transition crash audit history

This document preserves the investigation at the source hashes named below.
Its inventories and remaining-work statements describe those stages, not the
latest working tree. Later tests cover additional boundaries, including default
owned terminal launches; see the [current conformance map](workforce-conformance.md)
and [platform evidence](platform-validation.md). Full branch/external-effect
coverage is still unestablished. Historical counts are not cumulative acceptance.

## Schema-10 candidate follow-up

The full frozen 326-test baseline finished with 325 passes and the same recovery
fixture failure on each of three runtimes. The fixture now requires start and
submit after owner resume. Its [raw results and inside-Git counterexample](validation/pre-allocation-baseline/results.json)
are retained separately: a real smudge filter paused checkout, the actual calling
CLI was killed, a successor claimed and edited the worktree, and the old Git
writer subsequently removed it. This was an actual data-loss failure, not a
passing boundary test.

Allocation intent now commits before owned Git creation. Pending writers fence
reuse/work/checkpoints/cleanup, while observed quiescence and explicit human
cessation attestation remain distinct. EC-319/320 use real Git filters and
migration rollback to exercise this repair. EC-322/323 add actual CLI kills on
both sides of covered plan/start/step/submit, question/answer, pause/resume and
contract publication. EC-326–328 cover foreground terminal groups, descendants,
caller OS-kill, creation-commit rollback and real POSIX controlling-terminal I/O.

The [candidate syntax inventory](validation/transition-inventory.json) records
129 explicit transaction contexts and 53 failpoint call sites, including the two
generic changed-transaction hooks. `sw.tx()` names those hooks from its caller;
explicit labels distinguish publication from earlier read/heartbeat commits.
Every changed transaction can therefore be interrupted before/after commit.
This is injection capability, not evidence that every branch or external effect
has been executed under a crash. The family audit below remains applicable to
that broader acceptance claim. Source-bound candidate results are independent
of these selected passing checks.

## Prior audit and outstanding branch enumeration

The proposal requires failures at every state transition. Selected green tests
do not establish that requirement. This inventory guides the remaining work;
it does not change the proposal's scope or mark its completion gate passed.

An AST inventory of core SHA-256
`a3440fdac603486c44112f586151b14efea276bdcc557d610c0d6d24d7592904`
found 117 explicit transaction contexts and 38 failpoint calls. Fourteen contexts
contained a direct local failpoint call. These are syntactic counts: helper
functions can contain a failpoint, some transactions only record observations,
and branches inside one transaction have different side effects. The counts
neither prove coverage nor identify 103 missing state transitions.

| Transition family | Evidence at that audit | Additional evidence identified then |
|---|---|---|
| Claim ownership/locks, takeover and Git allocation | EC-286–290 allocation races; EC-310–313/316 OS-kill both sides of ownership, Git creation, setup publication and failed-allocation cleanup, including contracted takeover | Extend to adopted/preexisting branches without registered worktrees, mid-copy/inside-Git interruption, intervening expiry/control, and remaining allocation failure branches |
| Release and slot reassignment | Release/epoch and handoff tests; EC-314–315 kill plain release before/after commit, settle running clocks and reclaim while the old command is paused | Cover coordinator-selected release, same-name replacement, and release-helper calls inside leave, automatic return and other transactions at their own boundaries |
| Architecture approval and goal commit/assignment | Revision/source checks and executable-check-definition kill tests | Approval/commit/offer transaction kills plus source-pin/filesystem effects; no authority from orphaned evidence artifacts |
| Plan, questions, start, steps and submission | Ordering, acceptance, epoch, clock and pause-race tests | Before/after each durable revision/progress/submission commit, including late answers and interrupted clocks |
| Message and control delivery | Actual kills around message/inbox/request/checkpoint/handoff; replay and acknowledgement tests | Complete ack/resume/global pause coverage; separate message observations from control permissions |
| Incident and memory revisions | Killed transactions, independent provenance and stale-source tests | Enumerate each resolution/refresh/promotion/retirement branch and its retained Git refs |
| Usage reservations and reports | Real killed before/after reservation/report commits; lost tool intent and conservative settlement | Tool-observation commit kills and live-parent/late-report interactions; never infer actual zero usage |
| Headless startup and execution finish | EC-291–300 cover original-receipt brief writes, stale intents/PIDs, late control/policy/caller changes, actual handoff commit kills and child creation before its commit; EC-285 covers finalization | Extend startup pipe/SQLite/filesystem failures and interactive launches; enumerate remaining branches instead of inferring complete coverage |
| Merge intent and target compare-and-swap | Before/after Git move, late edits, pause, final-commit proof and recovery tests | Finish branch-by-branch enumeration; do not infer all filesystem/SQLite interleavings from one merge kill point |
| Verification, external record and goal close | Actual intent/results/completion/record/close kills with immutable receipts | Extend to every remaining outcome/platform/legacy branch while keeping owed checks visible |
| Cleanup and retained refs/files | Ignored content, edited briefs, live/unknown workers and failed removal tests | Actual kills around Git removal and reference publication; preserve artifacts and expose drift instead of deleting uncertain work |

The allocation audit reproduced a concrete bug: a delayed old allocation error
released Bob's newer claim and cleared the task while Bob still referred to it.
[The reproduction and baseline results](validation/schema9-baseline/results.json)
retain source hashes and full logs. The repair checks owner/epoch before cleanup
or publication, serializes local copies with ownership, and preserves planned
paths and partial files. Its five race tests establish those covered paths;
they are not a substitute for the missing kill points above.

The next startup pass reproduced stale preparation, PID publication and child
creation after earlier checks. It also reproduced a stopped coordinator finishing
a pending worker launch. EC-291–300 now cover the repaired headless boundaries:
original task/epoch receipts, serialized brief writes and handoff, current caller
authority, configuration binding and actual before/after handoff/start kills.
These checks do not establish every pipe failure, SQLite contention path,
filesystem error or interactive startup interleaving. Those remain required work.

`test_claim_crashes.py` subsequently adds 15 actual OS-kill trials (EC-310–316).
A child runs the CLI entry point with a pausing hook at a named failpoint. The
test waits for that exact child/point, calls `kill()` on its creating Popen
handle, and waits for termination. Linux checks the actual SIGKILL exit status;
Windows uses the actual process handle. No stored registry PID authorizes a
signal. The existing production failpoint default remains an abrupt `os._exit`
only when explicitly selected; the pausing behavior exists solely in the test
wrapper.

The matrix separates ownership commit, Git worktree creation, setup publication,
failed-allocation cleanup and plain release. Each tested boundary checks SQLite
state plus actual files/refs after killing, repeats status recovery, and verifies
the target never advanced or acquired fabricated completion. Takeover begins
with actual registered owner-process loss and checks new epochs, lock ownership,
contract history and retained usage origin. Release starts a real running
contract before its commit tests. These are selected branch results: they do
not establish interruption inside Git/copy calls or every other lifecycle
transition. The later takeover tests cover start/clock restoration; remaining
contract/control branches still need their own audit.

For each added kill point, use a real temporary Git repository and an actual
killed subprocess. Inspect both the committed database and physical Git/files
after restart. Preserve unknown observations, repeat recovery, and check that
the target and newer assignments are unchanged. A complete source log is not
proof that execution completion committed.

## Reproduced interactive-launch follow-up

At core SHA-256
`f350cb33f63dce6cad064d28b91db23da5caf8950e93166138ab0eb0a3a39f3c`,
two controlled real-Git/real-Popen trials reproduced a separate interactive
`launch` defect. In the first, T1 was released and the same agent claimed T2
after preparation but before the interactive child was created. The old launch
still created a child, published its PID, and marked the newer busy agent
offline on exit. In the second, the child exited, a separate status command
observed that exit, and the name was resumed with a live replacement PID and
claimed T2 before the old launch finalized. Old finalization cleared that
replacement PID and again marked its agent offline. T2's task row itself stayed
unchanged in both trials, leaving an inconsistent agent/task pair.

[Recorded observations](validation/startup-baseline/interactive-launch-reproduction.json)
contain the original source hash and before/after task/agent assertions. The
fixtures used the existing fake adapter and real local Python children; no
provider request was sent. These observations establish the original defect,
not a passing acceptance result.

The subsequent repair adds an original-assignment check serialized with
interactive creation/PID publication and finalization that preserves a
replacement process/assignment. `test_interactive_launch.py` adds 15 regression
cases (EC-301–309), including no-task changes during clipboard/terminal
confirmation, replacement PIDs, the current task of the same actual child,
pause/policy/caller changes, process creation refusal and a rolled-back PID
publication. On publication failure the foreground launcher waits on its actual
child instead of restarting or fabricating completion. A real SQLite authorizer
denial reproduced a COMMIT error that left the write transaction open. The
transaction manager now attempts rollback when an error leaves the transaction
active. EC-309 checks physical writer acquisition by a second connection,
rolled-back task/event changes, and an unchanged prior task. Rollback itself can
also fail under a broken database/filesystem; that is an error, never success.
Executed platform scope
is recorded separately in the implementation guide. At that stage, full interactive process ownership, timeout escalation and output
handling remained unfinished; these fences alone did not establish them. The
later [supervision implementation](process-supervision.md) supersedes that status,
while broader startup/transition interleavings still require acceptance.

## Reproduced takeover start and clock defects

At core `3ce4f8ae09924a5dbf29aa8a4f03f84cb87735919a908ac06498922156161c45`,
additional real-Git/CLI probes with actual registered owner-process loss
reproduced two defects before the subsequent repair:

- [Start-gate reproduction](validation/claim-crashes/takeover-start-gate-reproduction.json):
  the original `start` refused an unanswered critical question. After takeover,
  the task became `in_progress` and the successor recorded step 1 while that
  question remained open. No task integration/completion bypass was established
  by this probe; it establishes a missing start/permission gate.
- [Running-clock reproduction](validation/claim-crashes/takeover-clock-reproduction.json):
  a previously running task resumed as `in_progress` with a new active contract,
  but `active_since` remained null even after a step. Accounted running seconds
  stayed zero. The absolute deadline was preserved and the new deliberation
  clock was present, so this is not evidence of unlimited wall time.

Both probes use the fake adapter/local Python and make no provider calls.
EC-317/318 were Open at that source. The subsequent repair returns stored plans
to planning/awaiting answers for start/replanning checks, preserving completed
steps, work, epochs, deadline and usage origin. Observed loss and actual worker
exit settle running time; start resumes the clock. Eleven `test_takeover.py`
cases cover takeover, original-owner return, reclaim grace, blocked time,
headless/interactive exit, remaining allowance and elapsed expiry. The original
reproductions remain retained as evidence of the prior defect. These selected
repairs do not establish every transition or clock/control interleaving.

The [repair's executed results](validation/takeover-repair/results.json) contain
99 passing affected checks on Windows Python 3.12 and 76 each on Windows Python
3.11/Linux Python 3.13. They bind the repaired core and 32 unchanged inputs.
The old reproduction artifacts are retained unchanged, separate from this
later passing evidence.

EC-329 additionally exercises actual killed commits for architecture approval,
goal assignment, contract counter/decision/acceptance, manual locks/leave and
message/control acknowledgement/completion/resume. Complete board snapshots
remain atomic; resuming pause requires start again. A submission test separately
allows its legitimate preflight heartbeat while checking exact publication
rollback. These test-only corrections and new cases passed on all five available
runtimes; [per-case evidence](validation/candidate-matrix/results.json) preserves
the original baseline failures and source lineage. Broad branch/external-effect
coverage is still not inferred from injection capability.
