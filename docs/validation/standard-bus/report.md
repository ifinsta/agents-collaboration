# Standard local bus validation

> Historical source snapshot: commands, metrics and completion statements below
> apply only to the recorded inputs and runtimes. They do not validate later
> working-tree changes. See the [current evidence index](../../README.md).

The unreleased engine now exposes the installed [bus contract](../../../skills/agents-collaboration/BUS.md)
and [JSON Schema](../../../skills/agents-collaboration/BUS.schema.json), plus
`bus publish/receive/ack/retry/renew/schema --json`. SQLite remains authoritative;
schema 11 adds per-recipient consumer receipts without changing historical
message acknowledgements. The production engine remains one standard-library module.

Engine SHA-256:
`8a0c4c8731f637685dc3357b2c66350122b1872f0092fa00f4623d09cd8408fe`.

| Final-engine run | Result | Scope |
|---|---|---|
| Windows Python 3.11.14 | 7 passed | Bus conformance |
| Windows Python 3.12.2 | 37 passed | Bus, installer, JSON protocol, legacy messages and command-cost regressions |
| Linux Python 3.13.16 | 42 passed | Bus, communication/interrupts, input payloads, JSON protocol, legacy messages and command-cost regressions |

Commands, runtime details, logs and hashes are retained alongside this report.
Both Windows captures verified unchanged input hashes during their runs. Linux
ran the frozen source ZIP extracted onto the container's local disk; its engine
hash matches both Windows captures. These scopes overlap and are not 86 distinct
tests or a full 361-case suite. All 361 discovered test IDs are unique.

The seven new tests cover canonical envelopes and retry keys; concurrent
consumers; rejection of unclaimed/stale receipts and legacy acknowledgement
bypass; expired leases, renewal and retry; independent broadcast acknowledgements;
critical expiry; FIFO eligible IDs; bounded consumer inputs; schema-10 migration;
and four actual process kills before/after receive and acknowledgement commits.
Draft 2020-12 schema validation additionally checked actual message and receipt
output with the already-installed test-only `jsonschema` package. It is not a
production or required test-suite dependency.

A broader development regression invocation passed 58 tests, including actual
Git allocation/migration and the published simulation. It began before the final
bus edits, so it is not frozen final-source evidence. No transcript regeneration
was needed: the existing simulation still passed unchanged.

After frozen captures, the contract clarified heartbeat refresh and critical ack
notifications; the manifest was regenerated and clean installation checked again.
This documentation-only correction did not alter the engine hash. Final lint,
manifest and whitespace checks passed. The wrong-directory manifest invocation
initially caused an expected installer hash refusal; running regeneration from
the repository root repaired it and the installation smoke then passed.

Consumer loops must still be integrated by each adapter using the documented
poll/renew/ack lifecycle. This change does not introduce an automatic dispatcher,
push/network transport, remote authentication, exactly-once external effects or
task completion through a message acknowledgement. Leases fence receipts; handlers
still need idempotent effects and current task permissions.

Full final-source multi-platform CI, macOS and wider proposal acceptance remain
separate gates. Earlier candidate hashes and source ZIPs predate this bus change;
they do not describe schema 11. No publication or release was performed.
