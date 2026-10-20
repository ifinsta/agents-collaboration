# Managed sessions: implementation and validation

This unreleased source adds one terminal with tabs over owned headless workers,
plus a Sessions page in the shared browser dashboard. Start with
`swarm sessions` or `swarm console --managed` in the terminal already open.
See [usage and controls](../../managed-sessions.md).

## Behavior

- Workers keep their existing independent supervisors, contracts, process ownership
  and bus relays. Detaching the viewer leaves workers running. Rejoining requested
  kinds reuses active/uncertain executions instead of implicitly restarting them.
- Failed/exited executions and captured output remain inspectable. Tabs provide
  worker output, supervisor diagnostics and current task/evidence/event context.
  The execution epoch distinguishes that context from later task assignments.
- Start/stop controls call the existing engine. Stop requests follow captured
  policy; the viewer never reconstructs signal authority from stored PIDs.
- `sessions --once --json` is finite. `execution logs ID` provides bounded excerpts
  and byte-cursor following outside JSON mode. Log paths are derived from execution
  IDs; linked paths and forged stored output paths are refused. Terminal controls
  are removed and common credentials are redacted on a best-effort basis.
- Captured Windows runner/Git-environment helpers use CREATE_NO_WINDOW. Managed
  sessions use the existing terminal; native interactive consoles remain explicit.
- Headless workers have no interactive stdin forwarding. Uncaptured foreground
  output remains unavailable; logs and exit status are not verification receipts.

## Fixed source

Engine SHA-256:
`b0c475f2b31f1ed2104b8445f9d6ffa31be2e0fa727aae8f73e6255c4e00f9a6`.

Normalized validation fingerprint:
`48c78eefa5418fad3ae62e2520ab5984aec27c2b9ca8bf8235e31478f67b9370`.

[Snapshot file inventory](snapshot.json) binds the [frozen ZIP](source.zip) used by
both platforms. [Combined results](results.json) retain the working-source match
and exact scopes. The implementation remains schema 12 / CLI protocol 2; the
existing execution records supply session identities without another schema.

## Executed checks

| Environment / scope | Result | Evidence |
|---|---|---|
| Linux Python 3.13.16, full discovery, six exhaustive disjoint shards | 425 passed, zero skipped/failed; 321.764 seconds; inputs unchanged and exact discovery coverage | [Per-case results](linux313/results.json), [runner command](linux-run.json), [output](linux.txt) |
| Windows Python 3.12.2, 94 selected affected cases | 91 passed, three skipped, zero failed; 370.929 seconds of tests; frozen inputs unchanged | [Cases](windows-cases.json), [results](windows-cases-results.json), [command](windows-run.json), [output](windows.txt) |
| Real Linux pseudo terminal | Navigation, detach, clean exit and terminal setting/alternate-screen restoration passed | [Results](terminal-smoke.json), [reproduction script](terminal_smoke.py) |
| Native Windows pseudo terminal | Output rendered; `v`, Tab and `q` handled; supervisor view and clean detach observed, exit 0 | [Observations](windows-terminal.json) |
| Headless Microsoft Edge, widths 1280 and 390 | Session tabs, worker/supervisor switching, literal untrusted markup and no horizontal overflow; zero page errors | [Results](browser.json), [desktop](browser-1280.png), [phone](browser-390.png) |

The Windows skips are two POSIX controlling-terminal cases and a file-symlink
case requiring host permission. Linux executed those cases. Selected Windows
coverage includes the new session tests, dashboard, installer, foreground process
supervision, output capture, legacy cleanup, console, readable views and startup
cost guards. Real owned-worker tests establish that detaching preserves the same
live worker/work and that a normal stop preserves its log.

The simulation was regenerated through its generator and passed; its transcript
and companion console figures are updated. Lint, manifest and whitespace checks
also passed. These results do not establish hosted six-runtime acceptance,
macOS behavior, authenticated provider trials or a productivity improvement.
Historical reports remain tied to their original source; these results do not
retroactively change their counts or outcomes.
