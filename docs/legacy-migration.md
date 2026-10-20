# Removing runtime compatibility paths

The unreleased 0.4.4 source uses one current execution and communication path.
These changes describe the [reviewed source](README.md), not a claim that the
published tag already contains them; use a verified local-source installation.
This is a breaking cleanup. CLI result protocol is **2**; message envelopes,
bus receipts and stored event records remain version **1**. Database schema
remains **12**, with forward migrations retained.

| Earlier behavior | Current behavior / upgrade |
|---|---|
| Plain `send` produces a read-once notification | Defaults to typed `status`, requiring receipt-based acknowledgement. Internal assignments, answers and reminders also use canonical typed kinds. |
| `send --ping`, plain `ack` | Use `send --kind question`, acquire a receipt with `bus receive --json`, and acknowledge with `bus ack --consumer ... --token ... --json`. Reply with `send --kind decision --reply-to ID`. |
| Reading, replying or acknowledging an interrupt can acknowledge its transport message | Observation, replies, transport acknowledgements and control acknowledgements are separate. Only a valid bus receipt acknowledges transport delivery. |
| Optional foreground supervision | Every `launch` uses owned process supervision and automatic inbox relay. Remove the redundant `--supervised` option. |
| `launch --no-task` / launcher waiting in the shared checkout | Removed. Add or release an eligible task before launching. Independently started clients can still explicitly join and use `bus listen`; that does not grant process ownership. |
| Uncontracted fresh claims | Every fresh claim accepts visible configured terms unless an offer already exists. Reclaim keeps the prior deadline, scope, remaining active time and usage ledger. Expired terms require an explicit replacement offer. |
| Already-held work without a contract | Preserve work, checkpoint, release and reclaim. No contract or acceptance history is invented by migration. |
| Open workflow-v1 goals bypass architecture approval | Record a source-backed architecture brief and approve it before further work. The stored workflow version remains provenance, not an exemption. |
| `[swarm] task_budget_min` | Refused, rather than silently dropping its limit. Remove it and configure `[contracts] active_time_min` and `deadline_min`; inspect new terms before claiming. |
| Merging without verification gates | Integration refuses until executable `[gates] commands` are configured. |
| Inbox/environment fields duplicated at JSON top level | Read only `result.messages`, `result.rules`, etc. Request `--protocol-version 2` before the command; version 1 is refused. |

Manual delivery example:

```text
swarm --protocol-version 2 --json bus receive --as bob --consumer bob:boot-1
swarm --protocol-version 2 --json bus ack 42 --as bob --consumer bob:boot-1 --token TOKEN
swarm send ann "Reviewed the interface" --as bob --kind decision --reply-to 42
```

Supervised workers receive the same consumer receipts in `SWARM_BUS_INBOX`.
Use that receipt instead of acquiring a second consumer's lease. Acknowledgement
follows durable handling; hook exit and file visibility never acknowledge work.

Forward database migrations, old kind mappings when reading stored records,
historical read timestamps and evidence remain. Historical ungated integrations
stay `unconfigured`; old closures without retained proof stay
`legacy/unverified`. No records, branches or worktrees are deleted by this cleanup.
Vendor-specific native context injection still requires its configured bridge;
local wake hints do not preempt an unsupported model request.

Validation evidence (removed from the tree; kept in git history) recorded the complete
Linux suite and focused Windows checks at one unchanged source fingerprint.
