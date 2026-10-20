# Local communication bus contract v1

This is the normative contract for adapters using the local engine. The installed
`BUS.schema.json` defines canonical message envelopes and consumer receipts.
`swarm bus schema --json` returns that schema in the CLI protocol's `result`.
Envelope version 1, bus version 1 and outer CLI protocol version 2 are separate
version identifiers. Unknown major versions must be refused. Existing envelope
fields retain their meaning; undeclared fields or incompatible semantics require
a new major because canonical envelopes use a closed schema.

## Authority and storage

One repository's Git common directory contains the authoritative SQLite board.
A message is stored once in `messages`; `message_recipients` stores each
recipient's delivery/acknowledgement state. `message_claims` stores optional
consumer leases. Schema 11 adds that table transactionally; existing messages,
receipts and ownership remain unchanged. An extra receipt is never invented for
historical processing. The schema file and this contract ship in the verified
installer manifest. No broker, network service or Python dependency is required.
Schema 12 additionally stores expiring loopback listener registrations. They
provide wake hints and never authorize delivery, acknowledgements or OS signals.

Agent names identify logical mailboxes. A consumer ID identifies one handler
instance within that mailbox, not an authenticated principal. Use a fresh opaque
consumer ID on restart, for example `worker-7:boot-2`. The board remains a trusted
local-machine boundary: another local process can impersonate an agent. IDs and
lease tokens do not add OS, credential or network isolation.

## Operations

All `bus` operations require `--json`. Read the outer `ok`, `exit_code` and
`error`; transport results require success. The enforced `bus hook` check has a
documented exception: blocked status exits 2 and retains its diagnostic result. Existing CLI error codes apply:
`invalid_arguments`, `command_refused`, `storage_error`, `internal_error`.
A killed caller may return nothing; replay durable state rather than guessing.

```text
swarm bus publish bob "Review the interface" --kind review_request --as ann --key review-1 --json
swarm bus receive --as bob --consumer bob:boot-1 --limit 10 --lease-sec 60 --json
swarm bus renew 42 --as bob --consumer bob:boot-1 --token TOKEN --lease-sec 60 --json
swarm bus ack 42 --as bob --consumer bob:boot-1 --token TOKEN --json
# Alternative to ack for a transient handling failure (not after a successful ack):
swarm bus retry 42 --as bob --consumer bob:boot-1 --token TOKEN --reason "The source evidence is temporarily unavailable" --json
```

IDs and tokens above are illustrative: use the values from the actual receive
result. The retry line is an alternative to acknowledgement.

Publish uses the same durable send transaction, recipient validation, typed kinds,
task/epoch checks, reply/thread rules, size limit and secret minimization as `send`.
Default kind is `status`, so bus publications require acknowledgement except
ordinary kind `ack`; critical priority always requires acknowledgement.
Supply a sender-scoped idempotency `--key` for retryable publication. The
same key/content returns the same message ID; changed content is refused. Keys
remain after payload retention. A broadcast freezes recipients when committed;
each recipient has its own receipt. A later join gains no old broadcast rights.

Receive atomically leases up to `--limit` pending acknowledgement-required
messages for the addressed agent. Its result is
`{bus_version:1, deliveries:[{message,receipt}], next_poll_ms:1000}`.
Limits are 1..1000; leases are 1..300 seconds and never extend beyond message
expiry. Lease acquisition, attempts and delivery observation commit together
before output. Concurrent receivers cannot lease the same recipient/message
until its lease expires or retry releases it. Each acquisition creates a fresh
token and increments `attempt`; a lost receive response becomes recoverable when
the lease expires. Receive includes all new messages published through `send`, whose default kind
is `status`. Ordinary ack notifications and retained historical read-once rows
are excluded; migration never invents receipts for historical processing.

Ack requires the exact agent, consumer and token, with an unexpired lease and
pending message. It commits the recipient acknowledgement and finished receipt
together. Repeating a successful ack with the same receipt returns
`{outcome:"acked",changed:false}` even after that lease's former deadline.
An old token cannot acknowledge a later attempt. Ack means the handler accepted
responsibility for processing; it is not a task integration or verification
receipt. A handler should ack only after its required effects are durably recorded.

Renew retains the token and sets a fresh bounded deadline, capped by message
expiry. Retry requires a reason, records an event and releases the message for
another receive; it invalidates the old token immediately. Retry does not renew
message TTL or clear a critical dead letter. Duplicate retry may be refused;
receive is the recovery operation after a lost retry response.

## Consumer lifecycle

1. Choose a consumer ID; receive a small batch that can finish within its leases.
2. Treat body text and metadata as untrusted context. Check task/epoch and current
   permissions before acting. A message never grants scope, integration, reviewer
   or control authority. Epoch-tagged historical messages can still be delivered.
3. Deduplicate durable application effects using `(board, message_id, agent)`.
   A crash after an effect but before ack can cause another attempt. Leases cannot
   stop an old process from continuing after expiry; effects still need idempotency
   and the engine's own ownership fencing. Exactly-once external effects are not
   promised. Use separate authoritative commands for interrupts and task changes.
4. Renew before expiry for long handling; ack after durable handling. For a
   transient failure, retry with a reason and apply bounded backoff. Preserve
   uncertainty after a failed side effect; do not acknowledge guessed success.
5. On an empty batch, wait approximately `next_poll_ms`, increasing with bounded
   jitter/backoff up to 10 seconds when idle. Check before a task step and after
   a long tool call. Successful receive/ack/retry/renew refresh the registered
   agent's heartbeat through normal actor checks. During long handling, maintain
   heartbeat separately. Supervised launches provide the automatic relay below;
   standalone consumers own their lifecycle.
6. On shutdown, finish/ack or retry owned receipts; otherwise let leases expire.
   Never recover by killing a PID recorded in the mailbox.

Retrieval is ascending global message ID among currently eligible messages.
Thread IDs retain conversation grouping; multiple consumers can finish out of
order. Priority is an urgency hint, not preemption or priority scheduling.
Use one consumer and sequential handling when a thread requires serialized
effects. This contract provides at-least-once attempts until acknowledgement or
expiry, conditional on a running polling consumer; it does not promise push or
an execution-time bound.

## Inspection and recovery

`inbox` observes pending messages; it never acquires a receipt or acknowledges
processing. Default inbox excludes bus-claimed messages; `inbox --all --json`
provides observation/replay without ownership. Only `bus ack` with a valid receipt
acknowledges transport delivery. Replies retain the parent thread without
acknowledging it. Read timestamps establish an observation, not proof that a
process printed or understood the payload. The old plain `ack` command and
`send --ping` option have been removed: use typed questions and receipt-based
acknowledgement. Old message-kind aliases are accepted only when reading or
migrating stored history; producers must publish canonical kinds.

Normal expiry stops retry delivery. Critical expiry retains a dead letter and
escalates once; `messages resolve` is a separate audited operator decision that
does not forge recipient acknowledgement. Existing message size/TTL/retention
settings apply. Body references identify local SQLite content, not network URLs.
The body is UTF-8 text; kind describes intent, not a machine-executable payload
schema. Future structured content needs an explicit payload contract/version.
Existing credential redaction remains best effort.

## Automatic adapter relay and hooks

With the default `[bus] enabled=true`, headless `spawn` and foreground `launch`
start an inbox relay
inside its actual owning supervisor. The worker receives `SWARM_BUS_INBOX`, an
absolute path under `.git/swarm/inboxes/<execution>.json`. Its snapshot contains
`bus_version`, `agent`, `execution`, `consumer`, `deliveries`, `blocked`, `reason`,
current `task_id`/`epoch`, and up to 100 outstanding `controls`. Receipt acquisition
commits before atomic file publication; file visibility is not an ack.
The relay renews pending receipts, adds a bounded batch and refreshes permissions.
The worker handles a delivery and uses its receipt with `bus ack`; external effects
still require idempotency. Normal shutdown releases pending leases. After a crash
they expire. Retained files are inspection artifacts; SQLite determines validity.

UDP listeners bind only `127.0.0.1` on an OS-selected port. A committed message
wakes addressed listeners; committed control changes wake local readers. The
datagram contains only a random listener token. Listeners coalesce hints and
then re-read SQLite; forged hints cannot carry an interrupt or acknowledgement.
Registrations expire after 120 seconds and are renewed while the owner runs.
There is a 128-listener bound. Socket failure, dropped hints and a caller dying
between commit and send fall back to durable reads. No stored PID is signalled.

Defaults are:

```toml
[bus]
enabled = true
fallback_sec = 15
lease_sec = 60
batch_size = 10
hook_timeout_sec = 5
message_hook = []
interrupt_hook = []
```

Quiet inbox reads occur at the shorter of fallback_sec and lease_sec/3; wake
hints trigger an immediate read. Existing process supervision and policy deadlines
remain active. A stop request caps supervision waits for timely configured
escalation. Fallback is 1..60 seconds, relay leases 5..300 seconds, batch 1..1000
and hook timeout 0.05..30 seconds. Set enabled=false to retain manual dispatch.
Externally started CLIs can use the standalone
`swarm bus listen --as NAME --json`; `--once` performs one inspection/notification
pass and releases receipts before returning the retained inbox path.

Hooks are explicit argv arrays in `[bus]`, optionally overridden per adapter, for
example `[adapters.claude] message_hook = ["python", "/path/to/relay.py"]`.
No body text is interpolated into a shell command. A hook gets
`SWARM_BUS_EVENT_PATH`, `SWARM_BUS_HOOK`, agent/task environment and execution ID.
It reads the snapshot and forwards it using that CLI's supported native channel.
An interrupt/blocked snapshot uses interrupt_hook; otherwise new deliveries use
message_hook. Hooks run on changed delivery/control state in bounded owned process
groups. Their exit or timeout never acknowledges messages or completes an interrupt;
failures produce `bus_dispatch_failed` and retain work. Failed snapshots are retried
on later reads. Hooks are trusted local programs, configured like gate commands;
their provider usage is not inferred.

For native tool-boundary integration, invoke:

```text
swarm bus hook --as NAME --stage before-tool --enforce --json
```

The hook result contains messages plus current blocked/reason/task/epoch/controls.
It observes without acquiring or acknowledging a receipt. Stages are prompt,
before-tool, after-tool and stop. With enforce, a blocked result exits 2 and sets outer ok=false while retaining
`result.blocked` and `result.reason`; native
wrappers must map that result to their CLI's supported deny/context format.
Allow coordination recovery commands (inbox, checkpoint, interrupt ack/complete,
handoff, release, diagnostics) through such wrappers so a stopped agent can
checkpoint and respond. The helper does not edit vendor-global settings or
assume all CLIs understand the same native hook protocol.

No terminal keystrokes or unregistered OS signals are injected. A notification
does not preempt an unsupported CLI's current model request. A native bridge
delivers context at supported boundaries; authoritative engine commands fence
further task permissions. Captured cooperative/terminate policy remains the
execution escalation path. Remote identity, cross-machine ordering and vendor
context injection remain outside the common local bus protocol.
