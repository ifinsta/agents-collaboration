# Candidate real-agent trials

> Historical source snapshot: commands, metrics and completion statements below
> apply only to the recorded inputs and runtimes. They do not validate later
> working-tree changes. See the [current evidence index](../../README.md).

| Trial | Model | Mode | Verified | Full acceptance | Rework | Reported USD |
|---|---|---|---:|---|---:|---:|
| benchmark1 | minimax-m3.1-flash-free | solo | 2/2 | True | 0 | 0 |
| benchmark1 | minimax-m3.1-flash-free | uncoordinated | 2/2 | True | 0 | 0 |
| benchmark1 | minimax-m3.1-flash-free | coordinated | 0/2 | False | unknown | unknown |
| benchmark2 | minimax-m3.1-flash-free | solo | 1/2 | False | 0 | unknown |
| benchmark2 | minimax-m3.1-flash-free | uncoordinated | 1/2 | False | 0 | unknown |
| benchmark2 | minimax-m3.1-flash-free | coordinated | 0/2 | False | unknown | unknown |
| glm1 | glm-5.3-flash-free | solo | 2/2 | True | 0 | 0 |
| glm1 | glm-5.3-flash-free | uncoordinated | 2/2 | True | 0 | 0 |
| glm1 | glm-5.3-flash-free | coordinated | 2/2 | True | 0 | 0 |
| glm2 | glm-5.3-flash-free | solo | 2/2 | True | 0 | 0 |
| glm2 | glm-5.3-flash-free | uncoordinated | 2/2 | True | 0 | 0 |
| glm2 | glm-5.3-flash-free | coordinated | 1/2 | False | 0 | 0 |

GLM trial 1 passed all six outcomes. In trial 2, the coordinated formatter failed its independent negative-input check: it did not reject -1. T2 stayed in progress and was not integrated. MiniMax trials had runner timeouts; the retained assignment/lock prevented a dependent claim from pretending to proceed.

These are mixed outcomes. Provider-reported completed free-model usage was USD zero; missing cost/tokens/interventions stay unknown. No productivity improvement follows from this sample. Every trial, native output hash and failed check remains inspectable in [results.json](results.json). Earlier setup failures and passing trials are retained separately in [the prior live-trial report](../live-agent-trials/report.md).
