# Usage allowances and evidence (unreleased)

Native evidence can be imported with `usage report RUN --source FILE --format
claude` (final JSON result) or `--format codex` (exec JSONL). The original bytes
remain SHA-256 bound to the report. Claude cache input is counted once; Codex
cached input is already included in its input total. Missing token/cost counters
stay unknown, and malformed/negative counters are refused. These imports remain
provider-reported evidence, not authenticated billing or a provider quota.
See the [Claude CLI reference](https://code.claude.com/docs/en/cli-reference) and
[official Codex JSONL example](https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable).

Schema 8 adds a durable usage ledger alongside contract running/blocked time.
It separates four quantities:

| Quantity | Source | Meaning |
|---|---|---|
| Running and blocked time | Contract state transitions | Time between start, block and settlement; independent of actual command activity |
| Tool seconds | Creating supervisor's monotonic clock | Duration of a recorded owned command, including cleanup |
| Tokens and currency cost | Explicit numeric report with source hash | Reported consumption; provider billing is not independently authenticated |
| Conservative policy debit | Human cessation attestation | Full reserved allowance charged when exact usage is unavailable; actual usage stays unknown |

An absent report is `null`, never evidence of zero cost. Reservations hold
allowance until settled. Concurrent allocation uses SQLite transactions; retries
cannot double-reserve or launch a tool twice. Actual reported overruns remain in
the ledger even when they exceed the reservation. Exhaustion or unknown usage
fences new coordination permissions and preserves recoverable work.

These are coordination limits. They do not enforce a provider billing quota or
observe calls made outside the recorded command/report paths. Explicit native Claude/Codex imports exist. Automatic collection, comprehensive
external-command coverage, authenticated billing and broader real-provider trials
remain outstanding proposal work. Local role names are not authenticated users.

For an open backlog task, a human can offer explicit allowances:

```text
hivewire contract offer T1 ann --token-limit 10000 --cost-limit 0.50 --currency USD --tool-time-min 5
hivewire contract accept T1 --as ann
hivewire claim T1 --as ann
hivewire usage reserve T1 --as ann --tokens 2000 --cost 0.10 --key window-1
```

The reservation authorizes the next bounded external-usage window. Plan/start
as usual, then run an owned command with a JSON argument array:

```text
hivewire tool run --as ann --command '["python","check.py"]' --timeout-seconds 60 --key check-1
```

Use the current shell's rules when quoting JSON. `--purpose check` also permits
checks after submission. The creating supervisor caps the timeout at the
remaining tool allowance and owns descendant cleanup. Failure settles measured
time without claiming the task passed. A repeated tool key always refuses a
second launch; inspect its receipt instead.

External usage is reported from a UTF-8 JSON file, at most 64 KiB:

```json
{"tokens": 1234, "cost": "0.02468", "currency": "USD"}
```

```text
hivewire usage report RUN_ID --as ann --source usage.json
hivewire usage show T1 --json
hivewire usage inspect RUN_ID --json
```

Only normalized numeric fields and the SHA-256 source hash are retained; prompt
or arbitrary extra fields are discarded. Cost is stored in millionths of the
declared currency. Limits round down and consumption rounds up. Currencies are
never converted. Missing reserved dimensions leave the run unknown; reports
cannot decrease prior consumption. Complete reports are immutable, with exact
byte-identical retries replayed. A closed report does not authorize another
window: reserve the next one explicitly.

Submission, integration, external completion and goal verification require
settled usage. A dead command supervisor or expired report window becomes
unknown; the engine does not assume the process stopped or usage was free.
After confirming cessation, a human can conservatively settle it:

```text
hivewire usage reconcile RUN_ID --confirm-stopped --charge-reserved --reason "Evidence establishing cessation and why exact usage is unavailable."
```

This retains unknown actuals and charges at least the reservation against policy.
Later factual reports can increase that debit but cannot refund it. Reconciliation
does not invent an operating-system observation, success, or task ownership.
Pending/unknown usage also prevents cleanup and prevents its owner from taking
another task. `doctor` reports unknown usage; JSON status includes task summaries.
Ledger pages use `--limit 1..200` and the returned `next_cursor` with `--after`.

Humans own budget increases. `[budgets]` can define `token_limit`, `cost_limit`,
`currency` and `tool_time_min` ceilings for coordinator offers; absent limits
mean no engine cap for that dimension. A coordinator cannot add an unconfigured
cap or increase/remove an earlier cap. Replacement offers and takeovers retain
the original budget origin and consumption.
Owner loss or an observed worker exit also settles accounted running time at
observation, with blocked time retained separately. A takeover carries remaining
active allowance and the original wall deadline; an existing plan must pass
`start` again before steps/submission resume. That gate checks critical questions
and required replanning and restarts the clock without resetting prior usage.
Replacement offers must keep that lineage's currency; a new currency needs a
separate task, rather than relabeling earlier consumption.

A time-only extension cannot restore exhausted usage. The one justified contract
extension may include human `--token-limit`, `--cost-limit` and/or
`--tool-time-min`; pending/unknown usage must first be settled. Revised allowances
must leave headroom above retained consumption. Prior/revised policy, actor,
reason and timestamp remain in contract history. This consumes the existing one
extension allowance and does not reset spend, ownership fences or interrupts.

`tests/test_budget.py` exercises migration rollback, policy validation,
reservations/retries, minimized hashed reports, overruns, conservative recovery,
owned command failure/timeout, commit crashes, lost supervision, integration,
concurrent allocation and replacement offers against real temporary Git repos.
Late usage facts also invalidate earlier goal receipts before closure.
The timeout test advances a controlled monotonic clock after real child work;
its asserted duration is deliberately simulated, not a wall-time benchmark.
