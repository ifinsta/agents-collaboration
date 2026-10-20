# Candidate validation

> Historical source snapshot: commands, metrics and completion statements below
> apply only to the recorded inputs and runtimes. They do not validate later
> working-tree changes. See the [current evidence index](../../README.md).

| Runtime | Distinct snapshot cases | Passed | Platform skips | Unresolved failures |
|---|---:|---:|---:|---:|
| windows312 | 354 | 352 | 2 | 0 |
| windows311 | 354 | 352 | 2 | 0 |
| linux313 | 354 | 354 | 0 | 0 |
| windows313 | 354 | 352 | 2 | 0 |
| linux311 | 354 | 354 | 0 | 0 |

Full 348-case baseline runs found two test-fixture issues (strict boolean validation and a legitimate preflight heartbeat). Their failing logs remain retained. Corrected/new tests and the final JSON/latency follow-up passed on all five runtimes. The table combines latest outcomes by test ID.

The final core is `bffab9ed0273ab9705fac8beabd6c34c97e3c3f175e5f4c77d9e04032cdd2efb`. All frozen input hashes remained unchanged during their runs. The follow-up production changes at that stage were additive JSON message/environment/lock views, covered by 14 focused tests per runtime. Subsequent source changes require separate acceptance.

**This is staged validation, not a consolidated full final-snapshot pass. macOS is unexecuted.** Full branch/external-effect coverage and authenticated billing are not established.

Exact commands, elapsed times, raw logs, input hashes and per-case evidence are in [results.json](results.json).
