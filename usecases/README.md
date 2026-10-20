# Use cases

These workflow outlines show when to use local agent coordination and which records
establish the result. They assume the [current source contracts](../docs/README.md);
an installed release may differ. For a complete executable session, see the
[generated simulation](../docs/simulation.md).

`hivewire` stands for the verified Python executable followed by the **absolute** path
to the installed `hivewire.py`. Use that path from task worktrees too. Replace all
uppercase placeholders, `<...>` and `...` with actual IDs, epochs, evidence and
completed template fields. These outlines omit repository-specific implementation
commands; they are not scripts to paste and run without those steps.

Configure executable project gates before integrating work. Goal closure also
needs executable outcome checks, an approved architecture and a matching final
verification receipt. See [completion evidence](../docs/completion-evidence.md).

| # | Use case | Main actors | Features exercised |
|---|---|---|---|
| 1 | [Ship a feature with parallel agents](01-parallel-feature-delivery.md) | coordinator, workers, human | goals, architecture, task waves, merge queue |
| 2 | [Recover a crashed agent's work](02-crash-recovery-takeover.md) | coordinator, successor | orphaning, takeover, retained plans |
| 3 | [Mixed-vendor team on one machine](03-mixed-agent-team.md) | operator, different CLIs | environment, probe, spawn, console |
| 4 | [Solo agent with a safety net](04-solo-agent-safety-net.md) | one agent, human | questions, plans, steps, integration |
| 5 | [Interrupt and hand off work](05-interrupt-and-handoff.md) | operator, worker, successor | contracts, epochs, checkpoints, controls |
| 6 | [Independent review and lessons](06-incident-review-and-lessons.md) | operator, reviewer, verifier | incidents, verification, memory |

Enforcement applies to engine operations. Local names are unauthenticated, and
worktrees do not prevent arbitrary shell writes or isolate credentials. Pools are
single-machine; read the [security model](../SECURITY.md).
