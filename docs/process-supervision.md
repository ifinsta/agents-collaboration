# Owned execution supervision

For one terminal with tabs over owned headless workers, use `hivewire sessions` or
`hivewire console --managed`. Closing the viewer does not close its independently
supervised workers. `execution logs ID` exposes bounded retained worker/supervisor
output after exit. See [managed sessions](managed-sessions.md) for controls,
finite JSON inspection and the distinction from interactive foreground terminals.

Headless `spawn` now creates a durable execution record and a small local
supervisor. The supervisor owns the actual job/group it creates. The board stores
observations, deadlines and stop requests; a PID in a row never grants authority
to signal a process. This extends the existing SQLite/Git engine without an
external service or third-party Python package. POSIX supervision currently
requires the system `ps` utility for group inspection.

```toml
[spawn]
timeout_action = "cooperative"  # default; no signals after a timeout
grace_sec = 30                 # manual execution-stop grace
signal_grace_sec = 5           # POSIX TERM -> KILL grace
poll_sec = 1
startup_sec = 10
allow_unattended = false
max_turns = 80
max_output_bytes = 8388608     # worker stdout + stderr retained per execution
```

Changing `timeout_action` to `"terminate"` explicitly authorizes termination of
that new execution's owned group after cooperative grace. Policies are captured
at spawn and apply for the execution's lifetime; later config edits affect new
executions. Contract expiry uses the contract's checkpoint grace. A timed-out
targeted pause/yield/cancel uses its control deadline as the cooperative period.
Explicit execution-stop requests also stop new coordination permissions and use
`grace_sec`. The old task_budget_min setting is refused; contract limits govern
current task time. New task claims cannot bypass an
execution that is still stopping or has lost supervision.

Schema 9 adds bounded output for new headless executions. Worker stdout/stderr
flow through a pipe into a file named `.git/swarm/logs/<execution-id>.log`.
The captured `max_output_bytes` defaults to 8 MiB and accepts integers from
1024 to 268435456. A drain thread retains at most that many bytes, a 2000-byte
tail and a streaming SHA-256 digest with constant memory. Once capped, it keeps
draining/discarding; disk usage cannot grow with noisy worker output. Logs from
earlier executions remain separate and are never overwritten or auto-deleted.
This is a per-execution worker-output cap, not a total log-retention quota.
Engine startup diagnostics use the companion `<execution-id>.supervisor.log`.

`execution show`, `execution list` and JSON status expose typed `output` metadata:
observed/retained bytes, limit, observed hash, stream completion and errors.
The hash covers bytes actually drained, including discarded excess; it does
not assert that buffered/unobserved output was captured. Legacy executions have
no invented metadata. Raw retained logs are local, unencrypted output, with no
promise of arbitrary secret removal; the small metadata tail uses best-effort
redaction.

Excess output or a capture error requests a stop and fences the current epoch.
The existing captured cooperative/terminate policy controls signals and grace.
Cooperative mode sends no signals, keeps storage capped and awaits worker exit;
terminate mode stops only the supervisor's owned group. Group exit with truncated
or failed capture records a failed execution, even when its exit code is zero.
No task is completed as a side effect. `doctor` exposes failed/limited capture.
If a write handle remains open after the owned group exits, supervision becomes
unknown and cleanup remains blocked. A crashed reader can also break a worker's
output pipe; cooperative policy promises no signals, not continued I/O after its
supervisor disappears. Unknown state always requires inspection and preserves work.

`execution list` and `execution show ID` report startup/running/stop/signal/exit
phases, task/epoch, captured policy, timestamps and residence time. JSON status
includes execution records. `doctor` reports stopping and unknown supervision
with safe next actions. Reading a record or message does not grant authority.

```text
hivewire execution stop ID --reason "Checkpoint before recovering this assignment" --dry-run
hivewire execution stop ID --reason "Checkpoint before recovering this assignment"
```

Only the coordinator or a human can request that stop. The preview does not
change execution control state. An actual request fences active task work and
asks the worker to checkpoint and exit. Default cooperative policy never sends
signals. Under captured terminate policy, the creating supervisor signals only
the job/group it owns. The engine observes group quiescence before recording an
actual exit/termination; stopped or uncertain work is retained, never completed
as a side effect. Normal verified task integration remains a separate gate.

On Windows, a child starts suspended, joins a private unnamed job, and resumes
only after assignment succeeds. The job tracks descendants even if the initial
worker exits. This follows Microsoft's documented
[suspended assignment](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)
and [job inheritance/cleanup](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
behavior. No detached-console TERM is promised: after cooperative grace,
termination uses the private job handle. The supervisor's own process is outside
that job. Opted-in termination policy also configures kill-on-close if the
supervisor crashes; cooperative policy leaves processes intact on supervisor loss.

Agent jobs permit explicit breakaway for a newly supervised independent worker;
ordinary command jobs retain their descendants. Spawned workers inherit
`SWARM_EXECUTION_ID`; preserve this process context when invoking the engine.
A worker launched by a coordinator starts its supervisor outside the
coordinator's private job, so coordinator termination leaves the new worker
running. This uses Microsoft's documented
[explicit breakaway behavior](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs).
Host policies that prohibit the required breakaway cause startup to refuse;
there is no fallback that silently nests an independent worker in the stopping job.

On Linux/macOS, a private Python session anchor creates the worker and remains
alive while its group has live members. It protects the group identifier from
reuse even after the actual worker exits. The owning supervisor sends TERM and,
if necessary, KILL to that anchored group. A disappeared anchor causes refusal,
never a numeric-PID fallback. Group inspection uses `ps`; creating the session
uses Python's documented
[subprocess process controls](https://docs.python.org/3/library/subprocess.html#popen-constructor).
Embedded callers must keep the default SIGCHLD handler so another handler cannot
reap the owned anchor; otherwise startup refuses and asks for a clean CLI process.

Startup intent precedes child creation. A crash at startup or a missing/stale
supervisor heartbeat produces **unknown**, not a fabricated terminated result.
A reused live PID cannot make a stale heartbeat valid. A supervisor that resumes
with its original live ownership handles can record that restoration; a process
reading registry PIDs cannot recreate that authority. There is no blind restart.

Startup retains the original claim's task/epoch receipt. It does not look up a
possibly newer task after claim returns. Brief and archive writes share a checked
ownership transaction. Before execution intent and command handoff, the engine
rechecks the worker assignment and caller authority, including a stopping
coordinator. New intents also bind a configuration digest; a changed snapshot
refuses a pending launch. This leaves already-running captured policies intact.

Supervisor PID publication and command-packet delivery occur in one transaction.
The waiting helper reads the packet before opening the board, then checks its
committed startup authority. If publication rolls back, receipt of bytes alone
cannot authorize a worker. Before any command-packet attempt, a refused helper
can be closed/stopped through the actual Popen object that created it. This does
not signal an agent group or use a registry PID. Once packet delivery has been
attempted, an ambiguous handoff stays unknown and cannot be blindly restarted.

The supervisor rechecks startup control, assignment and policy under the same
transaction that creates its owned child and publishes the observed start.
Release/cancellation cannot race that coordination boundary. A rejected helper
that never attempted a worker clears only its own inherited PID reference; it
does not mark a newer busy assignment offline. A crash after actual child creation
but before the observation commits remains unknown, even if no child PID was
retained. Process creation and a database commit are separate facts.

`tests/test_startup_fences.py` uses real temporary Git repositories, actual helper
processes and killed handoff/start commits to cover these boundaries. Local
copies and brief writes can briefly hold the board's writer lock; preserving
ownership through those filesystem writes is intentional. Slow filesystem/SQLite
failures and interactive terminal startup still need the remaining audit.

If supervision is unknown, inspect actual processes and preserve the branch,
worktree and dirty changes. After independently confirming all owned processes
have stopped, a human can record an explicit attestation:

```text
hivewire execution reconcile ID --confirm-stopped --reason "Confirmed the fixture group is no longer running"
```

This is labeled human attestation, not engine termination proof. Then use the
normal checkpoint/handoff/re-offer flow and a fresh worker identity. Stopped or
uncertain execution prevents automatic removal even when a worktree looks
untouched. Restarting does not reuse old execution handles or grant stale epochs.

Completion and process exit are separate facts. External `record` or a normal
merge may finish a task while its worker still runs. Cleanup therefore waits for
all nonterminal executions associated with that task or agent, including when the
worker has taken another task but still uses an earlier cwd. A live legacy
launcher PID can defer cleanup but cannot authorize a signal. Unknown supervision
continues to defer cleanup until explicit human reconciliation.

Ignored files are retained during both automatic task return and completion
cleanup, including local settings copied into a worktree. The only disposable
ignored artifact is an unchanged generated brief with a byte-identical retained
archive. Content archives keep earlier assignments' briefs when an agent gets a
new one. Preserve valuable local artifacts outside the worktree, then retry
`doctor --fix`. Git removal runs without force; a failed automatic removal does
not clear task/contract ownership or branch references.

Gates, merge-message hooks and benchmark runners use the same owned-command
primitive. Timeout and permission refusal clean their group up, including live
descendants that inherited stdout. File-backed capture avoids pipe-drain hangs;
returned tails retain at most 2,000 bytes per stream. A monitored 1 MiB combined
output limit refuses noisy commands. The limit is polled, so a burst can briefly
exceed it on disk; this is not a filesystem quota. Gate keepalives sweep and
recheck permissions, stopping an owned gate promptly when an assignment or queue
permission changes.

These controls preserve coordination state; they are not an OS or credential
sandbox. Code can deliberately leave an inherited POSIX group or request allowed
Windows breakaway. Local identities/database access remain unauthenticated.
Interactive `launch` rechecks its original task/epoch, caller, policy and process
reference after prompt/clipboard/terminal preparation. Intent commits before
owned child creation; checked creation/start publication share a transaction.
Finalization preserves newer registrations and settles the current assignment
only while the registry still identifies its creating supervisor. Uncertain
creation/publication retains the execution and work for inspection/reconciliation.
The obsolete no-task and unsupervised paths are removed.
The shared transaction manager attempts rollback after a SQLite error that
leaves a transaction open, then propagates the error. A denied COMMIT is tested
with the real SQLite authorizer, including a second writer acquiring the board
after rollback. This does not guarantee recovery from a failed rollback or
unavailable filesystem.

Use `launch CLI --name NAME --task TASK` for foreground owned-group
supervision. It commits intent before child creation, rechecks the original
assignment/caller/policy, and shares the headless stop/grace/escalation driver.
Windows inherits its console in a private job; POSIX bridges a controlling PTY,
forwards input/window size and restores terminal settings on handled exit.
Descendants remain tracked after their initial parent exits. Actual launcher
OS-kills and creation-commit rollback retain uncertainty until explicit human
reconciliation. Every interactive launch uses this path. The unsupervised
launch implementation, `--no-task` option and redundant `--supervised` flag
have been removed. If no task is eligible, the launcher waits for another choice.

Terminal output streams without retained logs; it is not a capture receipt or
task verification. Closing terminal descriptors can end a program even under
cooperative policy, just as broken pipes can end headless workers. Abruptly
killing a launcher can prevent restoration; its shell may need `stty sane`.
Tests cover real POSIX controlling-PTY input/size/restoration, both stop policies,
descendant ownership, unrelated-process safety and uncertain startup/exit.
OS suspension and SQLite contention
can delay observations. Process residence/check duration is not CPU time, token
usage or monetary metering. [Usage budgets](usage-budgets.md) provide separate
coordination allowances/reports, including hashed native Claude/Codex imports.
Unobserved external calls and authenticated billing remain outside those reports.

With `[bus] enabled = true`, supervised adapters also own an automatic bus relay.
Local wake hints prompt
immediate inbox/control refresh; quiet refresh uses bounded fallback and lease
renewal. Message/interrupt hooks run in separate owned command groups with their
own timeout. Their success never acknowledges the authoritative interrupt or a
message. A failed notification cannot authorize task completion or an unrelated
process signal. Pending receipt leases release on normal shutdown or expire after
loss. See the [relay contract](../skills/agents-collaboration/BUS.md#automatic-adapter-relay-and-hooks).
