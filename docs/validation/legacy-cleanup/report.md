# Legacy cleanup validation

> Historical source snapshot: commands, metrics and completion statements below
> apply only to the recorded inputs and runtimes. They do not validate later
> working-tree changes. See the [current evidence index](../../README.md).

Runtime compatibility paths were removed from the unreleased 0.4.4 source.
See [migration instructions](../../legacy-migration.md) for the breaking CLI,
configuration and workflow changes. Stored history and forward migrations remain.

## Verified source

- Engine SHA-256: `d819647a59aa9415257f2d4384d5bb4f87a42b35b149ea6960cb87229e298a22`.
- Normalized validation-source fingerprint: `d4c491289996a7c82617d5a4bb90cf9d7d4a0a171faa9217dff7e9ffb22f100e`.
- Frozen ZIP SHA-256: `d1a767c8247f4f305611a2eff4c276e521eac2505c6d5782c8ec4b2ef1aaf3e8`.
- Schema 12; CLI protocol 2; bus, message and event versions 1.
- Working validation inputs matched the frozen inputs after both recorded runs.

| Runtime | Scope | Passed | Skipped | Failed |
|---|---|---:|---:|---:|
| Linux Python 3.13.16 | Complete discovery, 379 unique cases | 379 | 0 | 0 |
| Windows Python 3.11.14 | 48 focused cases | 46 | 2 | 0 |

Linux used four exhaustive disjoint shards and an init process to reap orphaned
fixture children. Windows exercised the installed tool, bus receipts, default
supervised launch, ownership fences, terminal stops/rollback, contracted claims,
scope/hotspot/merge gates and an unchanged-policy stale-review case. Two Windows
skips are POSIX terminal-specific checks. Both runs retained unchanged source
hashes and exact coverage of their declared scopes. Raw per-case results, logs,
input hashes and capture helpers are included here. Lint, manifest and whitespace
checks passed; the simulation passed and its transcript/SVGs were regenerated.

## Behavior covered

All current producers write canonical typed messages. Plain sends require
acknowledgement; only consumer receipts acknowledge transport. Reading, replying
and acknowledging control requests do not acknowledge message delivery. All
foreground launches use owned supervision. Fresh claims receive contracts;
reclaim retains the deadline, remaining active time, scope and usage origin.
Open historical goals must satisfy current architecture rules. New integration
requires executable gates. Removed options/settings refuse and JSON protocol 2
exposes typed data only under result.

## Limits and retained diagnostics

This is local validation. The hosted six-runtime matrix and macOS were not run.
The focused Windows run does not constitute a complete Windows suite pass.

The development directory preserves an early incomplete Linux run, a complete
failed 379-case run (373 passed, 6 failed), failed focused Windows runs and a
failed preflight. These exposed retired-flow fixtures, POSIX anchor interception,
undeclared test scopes and numeric contract-term representation in a review
fixture. They were corrected before the accepted runs. Earlier sources/results
remain diagnostics; no failed or cancelled result was relabeled as a pass.
