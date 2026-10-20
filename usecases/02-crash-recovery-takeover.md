# 2. Recover a crashed agent's work

Ann stops responding while working on `H-api`. Bo is a joined, available successor;
the coordinator inspects retained work before authorizing recovery. See the
[outline conventions](README.md).

## Inspect before takeover

Commands and the optional monitor sweep liveness. Silence can first mark Ann
offline and later orphan the task; a closed terminal alone does not prove that
all owned descendants stopped.

```bash
swarm agents
swarm status --all
swarm explain H-api
swarm execution list
swarm allocation show H-api
```

Resolve any unknown owned execution or incomplete allocation through its documented
inspection/reconciliation path before taking over. A stored PID is not permission
to signal a process. See [process supervision](../docs/process-supervision.md).

## Resume retained work

```bash
swarm claim H-api --take-over --as bo
swarm explain H-api
swarm plan --as bo
```

Read the preserved plan, completed steps, branch, worktree and current epoch.
Resolve critical questions and replan only when needed. A retained plan returns
to planning or awaiting answers; it must pass `start` again before further steps.

```bash
swarm start --as bo
```

Continue the remaining recorded steps with real evidence, commit and follow normal
submission/integration. Takeover preserves the original deadline, remaining active
allowance and usage lineage; an expired contract needs explicit recovery rather
than an automatic fresh budget.

If Ann returns, she runs `join --resume --as ann` and inspects `whoami --as ann`.
Engine writes from an old assignment/epoch are refused. She must also stop any
old shell activity: epochs cannot prevent direct filesystem writes.

## Establish recovery

Check that Bo owns the task, Ann's completed steps and files remain, and new work
passes the normal plan, contract and integration gates. Interrupted integrations
are inspected through their retained intent; takeover is not a reason to repeat
a target update blindly.
