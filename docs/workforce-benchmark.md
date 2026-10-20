# Fixed-task workforce trials

`scripts/workforce_bench.py` runs the same small duration-utility coding workload
with one worker, two uncoordinated workers, and two workers using the engine.
Every trial creates a fresh Git repository and installs the current local source
through the real installer, including manifest verification. The accepted
artifact must pass fixed Python checks; agent declarations do not count as
verification. This harness is separate from `scripts/bench.py`, which measures
CLI startup latency.

```powershell
python scripts/make_manifest.py
python scripts/workforce_bench.py --output .git/workforce-trial --fault after_target_moved
```

Choose a new output directory each time. `--mode solo|uncoordinated|coordinated`
runs one mode; the default is all three. `--deadline-seconds 300` sets each
assignment's runner timeout and the dispatch-to-integration deadline. Installation
is outside measured trial time; planning, worktree preparation and integration
are included in trial wall time. Assignment elapsed time starts after preparation
and includes verification/integration. Deadline misses are recorded even when
checks eventually pass.

The workload has two operations in `durations.py`: parse nonnegative seconds or
minutes, and format nonnegative whole seconds. The fixed verifier covers valid
and invalid inputs, including type errors and Unicode digit lookalikes. The
harness hashes the verifier and rejects changes outside the implementation file.
It independently reruns each task's checks and full acceptance on the target.
The default runner applies deterministic implementations; it is a mechanics
check, **not an LLM benchmark or evidence of productivity improvement**.

| Mode | Scheduling and integration |
|---|---|
| Solo | One worker identity receives tasks serially; Git rebase and checks precede integration |
| Uncoordinated | Two workers start from the same baseline, independently; Git rebase/checks integrate their results |
| Coordinated | Two registered workers use claim, plan, start, step, submit and merge; the shared-file hotspot serializes their assignments |

Uncoordinated integration conflicts get one fresh-worktree retry from the
integrated target, preserving the original branch. Retries count as rework.
Coordinated execution follows the engine's rules and records a refused/failed
integration rather than silently patching it. All original and retry artifacts
remain available for inspection. Shared-file serialization is conservative;
these tiny tasks do not establish how a larger independent workload behaves.

`--fault after_target_moved` kills the coordinated T1 merge subprocess at the
actual Git/SQLite crash boundary (exit 97, no cleanup handlers). A subsequent
status command must recover the completed integration, preserve check proof and
emit exactly one completion event. `fault.json` records the observed result.
The other modes run normally, allowing their outcomes to be inspected alongside
the controlled failure. This fault trial measures recovery, not comparative speed.

Each mode writes `results.json`, per-task runner logs, check logs, assignments,
Git branches/worktrees and optional usage sidecars. `comparison.json` aggregates
verified completion, rework, deadline misses, wall time, human interventions and
cost. Missing cost, token usage or external interventions remain `null`. Scripted
interventions are zero because the script makes all trial decisions. Unknown
cost is never interpreted as free. A failed setup/runner/trial is recorded as a
failure; it cannot disappear from the comparison.

For a real agent, pass `--runner runner.json`, where the file contains an argv
array with `{assignment}`, `{result}` and `{worktree}` placeholders. The program
runs with its working directory set to the worktree; it reads the assignment
JSON and edits only the permitted implementation. It can write this optional
usage JSON to `{result}`:

```json
{"cost": null, "currency": null, "tokens": null, "human_interventions": null}
```

Known cost must include its currency; costs in different currencies are not
summed. Usage is labeled runner-reported, not independently metered. External
programs inherit the user's permissions. Runner timeout/error cleanup uses the
engine's [owned jobs/groups](process-supervision.md), including inherited group
descendants; this is not an OS sandbox. Logs retain bounded stdout/stderr tails,
and output beyond the monitored 1 MiB limit is refused. Unknown usage stays owed.

Run matched repeated trials with the same model/settings/workload and record
machine conditions before drawing comparisons. A successful scripted trial
shows the fixture and integration path work locally. It provides no causal
claim about coordination, model quality, spend or real-team performance.

## Executed live trials and default runner

[Two matched real-agent trials](validation/live-agent-trials/report.md) now record
12 independently verified task outcomes, one uncoordinated retry, no deadline
misses and zero human interventions during the trials. Their free provider
reported USD zero; aggregate tokens stay unknown. Earlier quota/model/output-cap
setup failures are retained. These observations establish neither productivity
improvement nor scaling, and final-source candidate trials have separate evidence.

`scripts/agent_bench_runner.py` provides bounded CLI adapters for this harness.
Claude defaults to Haiku with a USD 0.25/session CLI cap and eight turns. Codex
uses an explicit model and short timeout; its CLI has no dollar-cap accounting
here, so unknown cost stays null. OpenCode defaults to an explicitly free model
and rejects non-free models in this runner. All use the engine's actual owned
process handles and a 120-second command timeout. Original native output is
retained with a monitored 1 MiB limit. Provider/account availability can still
refuse execution, which is a failed attempt rather than a benchmark pass.

A runner JSON for the tested free path is an argv array containing the Python
executable, absolute `scripts/agent_bench_runner.py` path, `{assignment}`,
`{result}`, `--provider`, `opencode`. Select the same explicit model/settings for
each matched trial. The [official CLI reference](https://opencode.ai/docs/cli/)
describes JSON run output; native result hashes/counters remain inspectable in
the trial report.

The [candidate-baseline trials](validation/candidate-agent-trials/report.md)
include both failures and successes. GLM's pair verified 11 of 12 outcomes; one
formatter failed the independent negative-input check and stayed unintegrated.
MiniMax trials timed out and retained their assignment/lock. These later results
must be considered alongside the earlier passing pair. The JSON-receipt follow-up
recorded in that report had separate focused verification. Those source-bound
results do not validate subsequent engine or adapter changes.
