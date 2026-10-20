# Matched real-agent trials

> Historical source snapshot: commands, metrics and completion statements below
> apply only to the recorded inputs and runtimes. They do not validate later
> working-tree changes. See the [current evidence index](../../README.md).

OpenCode 2.0.32; `opencode/minimax-m3.1-flash-free`. Both trials used identical assignments, runner settings and fixed acceptance tests.

| Trial | Mode | Verified tasks | Seconds | Rework | Deadline misses | Reported USD |
|---|---|---:|---:|---:|---:|---:|
| free2 | solo | 2/2 | 73.50 | 0 | 0 | 0 |
| free2 | uncoordinated | 2/2 | 55.62 | 0 | 0 | 0 |
| free2 | coordinated | 2/2 | 146.23 | 0 | 0 | 0 |
| free3 | solo | 2/2 | 104.58 | 0 | 0 | 0 |
| free3 | uncoordinated | 2/2 | 101.94 | 1 | 0 | 0 |
| free3 | coordinated | 2/2 | 89.81 | 0 | 0 | 0 |

All 12 task outcomes passed independent acceptance. Human interventions during the recorded trials were zero. Native event hashes and reported counters are retained in `results.json`; original raw outputs/worktrees remain at the recorded local artifact root.

This small, noisy sample supports no productivity or scaling claim. Aggregate tokens remain unknown; reported free-provider cost is not authenticated billing. These trials predate the final frozen candidate, which has separate reruns.
