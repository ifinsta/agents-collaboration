# Adapter relay, interrupt hooks and platform acceptance

> Historical source snapshot: commands, metrics and completion statements below
> apply only to the recorded inputs and runtimes. They do not validate later
> working-tree changes. See the [current evidence index](../../README.md).

Unreleased schema-12 engine SHA-256:
`82c788b3a63dbc5c114411c032af6015c415ba3c0e77ff97861adc722f72f9f8`.

Headless workers and supervised terminals now receive an automatic standard-bus
relay in their actual owning supervisor. Committed message/control changes send
loopback wake hints; the relay re-reads authoritative SQLite state, acquires or
renews receipts and atomically publishes `SWARM_BUS_INBOX`. A 15-second default
fallback recovers missed hints. The model does not need to run repeated inbox
commands to maintain this relay. Legacy read-once messages retain legacy inbox
semantics; reliable automatic dispatch uses typed messages.

Configured message/interrupt hooks receive `SWARM_BUS_EVENT_PATH` and run in
bounded owned command groups. Control transitions include pause and resume.
`bus hook --stage before-tool --enforce --json` exposes current permissions and
blocks on targeted control, global pause, stale epoch and stopping/unknown owned
execution. Native wrappers map that result into their vendor's deny/context
protocol and must permit recovery commands. The engine does not edit global
vendor settings or inject terminal keystrokes. Hook success is notification only;
message acknowledgement, interrupt acknowledgement and task completion remain
separate authoritative operations.

Registration and receipt cleanup is scoped to the actual relay. Rollback sends
no wake hint. Failed socket delivery cannot fail a committed message. Lost hints
fall back to durable reads. Hook timeout/failure retains pending work, and a
replacement supervisor cannot create a delayed old hook. Startup policy and
actual owned process handles continue to govern execution termination.

## Evidence

| Final-source runtime | Result | Scope |
|---|---|---|
| Linux Python 3.13.16 | 374 passed, no skips/failures | Complete discovery, four exhaustive process shards |
| Windows Python 3.11.14 | 20 passed | Bus, automatic relay/hooks and CI-gate regressions |

Both captures verified unchanged input hashes. The complete Linux run also
verified exact discovery coverage and no changed inputs, finishing in 725.147
seconds. Its normalized source fingerprint is
`f6e2e767637a996d94b9cb671bef877a44dd8c0f68472fab466743421f131a35`;
the working-tree validation inputs matched it exactly when recorded; later
changes are outside this evidence. Per-case results,
raw logs, commands, runtime details and source hashes are retained alongside
this report. This closes the consolidated final-source local Linux suite gate;
it does not establish a complete Windows/macOS matrix.

The local regression set exercises actual loopback datagrams, transaction
rollback/commit boundaries, sender failure, fallback, durable relay files,
non-acknowledging hooks, hook group timeout, replacement-owner fencing, native
tool control, schema-12 rollback, real headless worker notifications with a
30-second supervision interval, and explicit execution-stop permission fencing.
It also verifies resume notification when there are no pending messages.
No provider call or authenticated billing claim is involved in these fixtures.

The complete Linux 370-case development run passed at earlier engine
`36bbdff862f9823853b82f5ae32ff400087c418216e38fe0409a62e85af143a1`.
Later source checks added delayed-hook creation fencing, resume notification,
the complete-platform aggregator and explicit execution-stop hook refusal.
The subsequent 373-case frozen Linux run also passed at engine
`783a3c6ba971ab47b0ec70bbaa9cbfed0ff64cb7dd647b2237748bdf146233e0`.
Those earlier runs are retained separately under adapter-dispatch-development;
their results are not relabeled as the final engine. The mutable development
Windows run finished with 368 passes, two POSIX skips and no case failures, but
its inputs changed while implementation continued. Its overall result correctly
remained rejected (`ok:false`); it is diagnostic, not a stable final-source pass.

## Hosted CI

The workflow runs the complete discovery on Windows, Linux and macOS with Python
3.11 and 3.13. Every job retains per-case results, logs and before/after input
hashes. Two local process shards cover the complete suite. Failed subtests are
recorded against their parent case, and reused evidence directories are refused.

The `all-platform acceptance` job requires six successful, complete reports with
matching test IDs and one source fingerprint. Fingerprints normalize CRLF/LF so
the same checked-out source can be compared across operating systems; raw local
hashes still detect mutations during each run. Actual subprocess tests prove that
missing macOS reports, source disagreement, failed subtests and source mutation
cannot produce an accepted matrix.

At recording time, this working tree had not been pushed and the hosted matrix
had not executed. This report establishes no later hosted result.
No macOS result or all-platform pass is claimed. The acceptance gate will run on
the configured push/PR/manual-dispatch triggers once these changes are available
on the hosted repository. Earlier ZIPs and candidate reports predate schema 12.
