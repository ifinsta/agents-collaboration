# Completion evidence

Integration, verification and goal closure are separate facts. A commit's presence
in the target does not establish acceptance, and prose is not a check result.
Schema 7 retains verification runs and goal closure receipts in SQLite while Git
pins the inspected commits. Existing closed goals migrate as legacy/unverified;
migration never invents a passed result for them.

The implementation extends the current local engine and owned command runner.
Durable receipts give interrupted checks an inspectable state without adding a
service or Python dependency. Detached checkouts protect the operator's main
checkout and retain diagnostic files. They remain local worktrees, with the
user's OS permissions; they are not a sandbox or hermetic build environment.

The following blocks are workflow outlines with placeholder IDs/paths. They
assume a drafted goal, completed goal answers/tasks, a recorded complete
architecture brief and authorized actor context. Define executable checks before
approving that brief:

```text
hivewire goal outcome health "The health result includes the running version" --check "Assert the returned fields against VERSION"
hivewire goal check health 1 --command '["python","checks/health.py"]'
hivewire goal architecture health --approve
hivewire goal commit health --assign
```

Repeat `--command` for multiple argv arrays for one outcome. Setting the same
definition is idempotent; changing it increments the goal revision and invalidates
architecture approval and old receipts. Definitions have argument/payload bounds;
common credential forms are refused. Supply secrets through the environment.
Goal checks are policy, so only the coordinator or human defines them. Approval
still follows the architecture's risk policy.

After the tasks land:

```text
hivewire goal verify health --key health-final
hivewire verification list
hivewire verification show RECEIPT
hivewire goal close health
```

`goal verify` runs configured project gates and every approved outcome command on
the exact current target commit. All goal tasks must have landed commits; open
questions, stale architecture/review clearance and owed checks block it. A check
that exits zero but changes tracked source cannot produce a passed receipt.
Target, goal revision, assignment context and policy changes invalidate the run.

Closure requires the latest matching run to have passed. A later failure or
uncertain run cannot be hidden behind an older pass. Closure records its commit,
revision, policy and receipt. Optional `--evidence N=RESULT` adds explanatory
notes; it cannot replace an engine receipt. Empty/uncommitted goals and fabricated
`done` rows cannot close. Repeating a committed close does not create a second
success event; closed goal policy remains immutable.

For work landed through another integration path:

```text
hivewire record T1 --commit COMMIT --key imported-T1 --note "Why this commit carries the task"
hivewire verify T1 --key recheck-T1
```

`record` checks target ancestry, current authorization and incident clearance,
runs configured gates on that commit, then atomically records completion and its
receipt. Failed, absent or unconfigured gates cannot mark external work done.
`verify` rechecks a completed task without moving the target. Proof states which
commands ran; it cannot infer that weak checks cover every aspect of a task.
New merges require executable gates. Historical ungated merges remain labeled
unconfigured, never passed.

An owed check is an obligation, not another spelling of success. After an actual
task verification on the needed machine, a human can relate the receipt to that
obligation:

```text
hivewire verify T1 --key required-machine
hivewire verification resolve-owed T1 --receipt RECEIPT --reason "What was checked on the required machine"
```

The receipt must match the current assignment, commit, obligation and policy.
The resolution retains the original owed text, platform, receipt, reason and
human identity as an explicitly labeled attestation. It does not fabricate a
foreign-platform check. Changing submission evidence can require fresh incident
clearance. Agent/coordinator prose cannot resolve owed checks by itself.

Each run commits intent before launching checks and commits each observed result.
Receipts include actual exit codes, attempts, bounded redacted output tails,
timing, platform, source tree and retained checkout. The gate timeout bounds the
run's preparation/command budget; retries are bounded and recorded. Metadata/Git
guards also have bounded timeouts. Commands use owned jobs/groups; timeout or
refusal cleans only their owned descendants. Configured environment templates and
ignored local file copies apply, as they do for implementation worktrees.

Retry keys bind to source/policy/context. A completed retry replays its receipt.
Lost supervision becomes `unknown`, not passed or terminated, and blocks a fresh
run for that subject. Inspect retained processes and artifacts before a human
reconciles it:

```text
hivewire verification reconcile RECEIPT --confirm-stopped --reason "How cessation was confirmed"
```

Reconciliation labels the old run `abandoned` by human attestation, retains its
results/files, and permits an explicit fresh run. Registry PIDs never authorize
signals. `doctor` reports unknown verification and legacy/missing closure proof.
Checkouts and receipts are retained for inspection; automatic pruning, remote
receipt trust and OS credential isolation are not provided by this workflow.
