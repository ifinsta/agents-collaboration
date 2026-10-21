# Deputy coordinator benchmark

`scripts/deputy_bench.py` compares three coordination arms on the same scripted
workload: solo, coordinator-only, and coordinator plus a bounded deputy. It
measures coordination mechanics and recovery on the tested host. Worker steps
are fixed CLI calls, not LLM work, so the results are **not evidence of
model-driven throughput**.

```powershell
python scripts/make_manifest.py --check
python scripts/deputy_bench.py --trials 3
python scripts/deputy_bench.py --trials 3 --json > deputy-bench.json
```

Each trial creates a fresh Git repository, seeds a critical unacknowledged
message and a stuck task (`T6`), and then runs three verified tasks (`T1`,
`T2`, `T3`) through the normal claim, plan, start, step, submit and merge
transitions. Every task must pass the configured Python gate and reach `done`.
The harness exits non-zero if any arm loses a verified task or any fault check
fails.

| Arm | Triage and work |
|---|---|
| Solo | One worker identity handles the seeded P1 signals and all three tasks serially |
| Coordinator | The coordinator triages the signals and performs the three tasks |
| Coordinator + deputy | The coordinator grants one time-bounded lease; the deputy claims, investigates and reports the signals while the coordinator works |

## Fault checks

Each check runs in its own repository, outside the timed arms:

| Check | Expected observation |
|---|---|
| Deputy crash | An expired claim lease is recovered once with a new epoch, history and evidence retained; no duplicate intervention |
| Scope violation | A deputy claiming outside its subject scope is refused and loses the lease; a permitted item remains claimable |
| All five busy | Scouting and escalation continue with every slot occupied; no sixth agent is joined |
| Coordinator term change | The old lease is revoked; the former deputy is refused and the queue remains durable |

## Measurements

The JSON payload reports, per arm, the median across trials for wall time,
verified tasks per hour, scan time, triage time, time to first claim,
coordinator and deputy action counts and time, and totals for unseeded
attention items, recorded false alarms, escalations and rework. p95 values are
the 95th percentile across trials; with three trials this equals the slowest
trial, so it is a bound rather than a stable tail estimate.

`unseeded` counts attention items other than the two seeded signals. They are
not automatically false positives: the scout also reports real conditions such
as interrupted or orphaned tasks, and the run leaves their evidence in the
trial repository. `false_alarms` counts only explicit `false_alarm`
dispositions, which a scripted run records as zero because no actor adjudicates
them. The workload assigns no token cost, so extra agent cost is one occupied
pool slot for the lease duration, not a measured monetary value.

## Results

Measured on 2026-10-21: Windows (`win32`), Python 3.12.2, three trials per
arm, one host, current source. Every arm verified all three tasks in all three
trials and lost none.

| Metric (median across trials) | Solo | Coordinator | Coordinator + deputy |
|---|---|---|---|
| Verified tasks (all trials) | 9/9 | 9/9 | 9/9 |
| Lost tasks | 0 | 0 | 0 |
| Trial wall time (s) | 19.503 | 19.468 | 20.940 |
| Verified tasks/hour | 553.8 | 554.8 | 515.8 |
| Triage time (s) | 1.165 | 1.146 | 2.717 |
| p95 triage (s) | 1.250 | 1.351 | 2.882 |
| Time to first claim (s) | 0.456 | 0.454 | 0.701 |
| p95 time to first claim (s) | 0.504 | 0.579 | 0.903 |
| Scan time (s) | 0.239 | 0.248 | 0.245 |
| Coordinator actions / time (s) | 7 / 9.132 | 4 / 0.918 | 4 / 0.920 |
| Deputy actions / time (s) | 0 / 0 | 0 / 0 | 6 / 1.456 |
| Unseeded attention items | 0 | 0 | 0 |
| Recorded false alarms | 0 | 0 | 0 |
| Escalations | 0 | 0 | 0 |
| Rework (reopened) | 0 | 0 | 0 |

On this workload the deputy was **overhead**: median wall time rose by 1.47 s
(7.6%), triage took 1.57 s longer, and scripted tasks per hour fell by about
7%. The coordinator arm and the deputy arm each used four coordinator actions;
the deputy added six actions and 1.456 s. This is the trade-off the design
predicts for a small fixed workload, where a second agent consumes a slot
without shrinking the three tasks. The comparison does not show a throughput
gain for this host or workload.

The seeded message and stuck task were triaged inside their response window in
every trial, so no escalation was recorded and the queue did not need a
reminder. No unseeded attention items appeared, and no scripted actor
adjudicated an item as a false alarm; absence of recorded false alarms is not
proof that the scout would never raise one on real traffic.

Fault checks, all observed in separate repositories:

| Check | Result |
|---|---|
| Deputy crash mid-claim | Passed: another agent claimed once after the lease expired; four history rows retained |
| Scope violation | Passed: the out-of-scope claim was refused and the lease was revoked |
| All five busy | Passed: five live agents, zero leases, one capacity notice, no sixth slot |
| Coordinator term change | Passed: the old lease was fenced and the new coordinator (`bob`) took over |

## Limits

- Only the tested host is reported. No Linux or macOS run of this benchmark is
  included, and the results do not validate another host or source revision.
- The workload is scripted and small; tasks per hour reflects coordination
  overhead on this host, not human or model productivity.
- Three trials per arm do not establish a stable distribution, and trial time
  includes local process startup for every CLI call.
- A deputy can reduce throughput by occupying a slot. Nothing here claims a
  throughput improvement without the measured comparison above.
- Missing cost, token usage or human interventions are not interpreted as free.
