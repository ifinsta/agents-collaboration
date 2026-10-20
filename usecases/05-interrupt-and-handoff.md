# 5. Interrupt and hand off work

Priorities change while Ann owns `H-api`. A coordinator or human requests a safe
stop; a joined, available Bo will continue it. See the [outline conventions](README.md)
and the [bus contract](../skills/agents-collaboration/BUS.md).

## Set terms and checkpoint

Every fresh claim gets bounded terms. To negotiate custom terms **before claiming**:

```bash
swarm contract offer H-api ann --active-time-min 60 --deadline-min 90
swarm contract accept H-api --as ann
```

While working, Ann uses the current epoch printed by `explain`. Replace `EPOCH`
and the other uppercase placeholders with actual values.

```bash
swarm explain H-api
swarm checkpoint --as ann --epoch EPOCH --note "endpoint stubbed" --next "wire version string"
```

## Request and complete a stop

```bash
swarm interrupt request ann --mode yield --reason "production incident takes priority" --deadline-min 10
swarm interrupt show INTERRUPT_ID --as ann
swarm explain H-api
```

`attention` requests attention while allowing work; `pause`, `yield` and `cancel`
fence work through a new epoch. Cancel requires the human unless delegated. Ann
reads the **new** epoch, acknowledges the control, and records a fresh checkpoint:

```bash
swarm interrupt ack INTERRUPT_ID --epoch NEW_EPOCH --as ann
swarm checkpoint --epoch NEW_EPOCH --as ann --note "safe stopping state" --next "remaining work"
swarm interrupt complete INTERRUPT_ID --epoch NEW_EPOCH --checkpoint CHECKPOINT_ID --note "ready for successor" --as ann
```

A completed **yield or cancel already hands off the task**. Do not issue a second
handoff. A pause instead retains ownership for a later resume. Bo inspects the
released work and remaining terms before claiming; expired terms require explicit
contract recovery.

```bash
swarm explain H-api
swarm claim H-api --as bo
```

For a voluntary handoff without a yield/cancel control, use `handoff` with a fresh
checkpoint and current epoch. Follow the successor's printed plan/start gates.

## If Ann does not respond

After the control deadline, the operator inspects owned executions and retained
work, then uses the coordinator/human `checkpoint --task H-api` and
`handoff --task H-api` recovery path with the current epoch and checkpoint ID.
Unknown execution state must be reconciled before assuming it is safe to resume.
Ann must explicitly resume her local registration before accepting more work.

Transport receipt acknowledgement only records message delivery processing;
`interrupt ack` records the control acknowledgement. Neither substitutes for the
other. Handoff itself does not kill processes; a separately captured owned-process
termination policy may stop owned descendants after grace. Files and checkpoints
remain available. Sweeps enforce expiry on commands or while a monitor runs;
hooks and wake signals reduce polling without becoming authority themselves.
