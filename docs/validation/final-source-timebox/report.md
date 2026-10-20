# Ten-minute acceptance follow-up

> Historical source snapshot: commands, metrics and completion statements below
> apply only to the recorded inputs and runtimes. They do not validate later
> working-tree changes. See the [current evidence index](../../README.md).

Engine SHA-256: `bffab9ed0273ab9705fac8beabd6c34c97e3c3f175e5f4c77d9e04032cdd2efb`.
Production behavior was unchanged during this follow-up.

The additional memory acceptance test passed on Windows Python 3.12 in
112.180 seconds. It kills the actual CLI before and after five commits:
proposal, provisional promotion, stale marking, stale re-verification and
retirement. It checks complete database snapshots, repeated recovery, unchanged
target, retained evidence refs and exclusion of retired context. The executable
test is retained alongside results.json; this extends selected branch coverage.

Installed headless option compatibility passed for Claude Code 2.1.303,
Codex 0.104.0 and OpenCode 2.0.32. Qoder's version command timed out at 20 seconds
under concurrent validation load. These checks make no provider requests and
do not establish live adapter or billing acceptance. The timeout is unresolved.

`scripts/validate_candidate.py` now performs complete discovery, runs disjoint
process shards, records every case, compares exact discovery coverage and checks
source hashes before/after. CI uses it on the existing six OS/Python combinations,
uploads evidence even on failure, and supports manual dispatch. Lint and manifest
checks passed when the runner was added. The workflow has not been published or
executed remotely; no macOS result is claimed.

Consolidated local suites were launched but did not establish a complete pass
within this timebox. Temporary commands/logs remain at the path in results.json.
Interrupted/incomplete attempts are not passing evidence. Broad transition and
adapter acceptance remain open; these changes do not close the original goal.
