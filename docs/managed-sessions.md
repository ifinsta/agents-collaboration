# Managed headless sessions

At assignment startup, the coordinator runs:

```text
hivewire workspace --as COORDINATOR
```

This finite command starts or reuses the hidden loopback dashboard, opens it in
the browser once per board/server, and opens one visible session manager. Its
agent tabs follow owned executions as they start; no provider agents are started
by opening the workspace. Later calls reuse a live manager. Closing it leaves
workers running, and the next call can reopen it. Use `workspace --reopen` to open
the browser again after closing its tab. There is no browser-tab closure detector.

Windows uses a named Windows Terminal window when available, otherwise a single
new console. macOS uses Terminal; Linux uses an installed desktop terminal.
SSH, CI, `SWARM_HEADLESS=1`, and Linux without a display skip desktop viewers.
`workspace --no-open` explicitly starts only the hidden dashboard. If no terminal
or browser can open, the command reports a fallback and never restarts workers.
Concurrent startup requests share a short lease so they do not open duplicate
viewers. `workspace --dry-run --json` previews startup without launching anything;
`workspace --json` returns finite startup status without revealing the URL token.
The dashboard starts as an observer (`--observe`); the session manager and normal
engine commands continue their existing recovery sweeps.

Use one terminal to inspect workers instead of opening a window for each CLI:

```text
hivewire sessions
# Equivalent console entry point, in the terminal you already opened:
hivewire console --managed
```

`hivewire` abbreviates your verified Python executable and the absolute installed
launcher path. From this source checkout, use
`python skills/agents-collaboration/hivewire.py sessions`.

Each owned execution appears as a tab with its agent, task, assignment epoch,
state and observed exit code. Failed and completed sessions remain listed.
Workers run under their independent existing supervisors; closing the viewer or
pressing `q` detaches observation and leaves those workers running. Reopen the
viewer from another terminal to inspect the same records and retained output.
It opens no additional terminal windows and needs neither Windows Terminal nor tmux.

## Start and manage workers

Start a task-bound worker through the normal headless path, then inspect it:

```text
hivewire spawn opencode --name ola --task API-1
hivewire sessions
```

Replace the kind, agent name and task ID with actual configured/eligible values.
Normal architecture, contracts, routing and permission checks still apply.
Alternatively, start the requested kinds on eligible tasks from the manager:

```text
hivewire sessions --agents opencode,claude
```

Existing active or uncertain sessions count toward the requested number of each
kind. Reopening this command does not implicitly restart those workers. Repeat
a kind to request another worker of that kind. Partial startup failures retain
already-started workers and report errors; they are not rolled back or hidden.

| Key | Action |
|---|---|
| Tab, Left, Right | Select a session |
| `v` | Cycle worker output, supervisor diagnostics, task/evidence/events |
| Page Up / Page Down | Scroll within the bounded excerpt |
| `s` | Start a headless worker after entering its kind, task and name |
| `x` | Request a policy-bound stop with a concrete reason; blank cancels |
| `q`, Ctrl+C | Detach the viewer and keep workers running |

Start/stop operations use the existing engine checks. A reserved independent
reviewer can observe sessions but cannot start or stop workers through the viewer.
Termination follows the execution's captured cooperative/terminate policy; a stop
request does not establish observed exit. Unknown supervision requires inspection.

## Headless inspection and log following

```text
hivewire sessions --once --json
hivewire sessions --agents opencode,claude --once --json
hivewire execution logs EXECUTION_ID --lines 100 --json
hivewire execution logs EXECUTION_ID --stream supervisor --follow
```

Use an actual execution ID from the session list. `--once` is the finite machine
interface; interactive sessions and `logs --follow` are refused in JSON mode.
The session list defaults to 200 records, with `has_more` and a configurable
`--limit` up to 1,000. CLI log excerpts support 1..1,000 lines, with at most 64 KiB
read per refresh. Following uses byte cursors so an unchanged log is not repeated.

The viewer and follow command do local reads; models do not need to poll for
their output. The viewer sweeps normal board recovery once per refresh. Worker
message delivery continues through the existing bus relay and advisory wake hints.

Windows captured helper commands (including Git/probe calls through the engine's
runner) use `CREATE_NO_WINDOW`; owned headless workers already use hidden/detached
process creation. Explicit interactive `launch` and the native multi-pane console
remain available when a person wants a CLI's full interactive interface.

## Dashboard and audit scope

The [web dashboard](web-dashboard.md) also has a **Sessions** page with a tab per
execution, worker/supervisor output and links to task evidence. Session reads use
the selected board, existing token and loopback checks, and read-only connections.
Session endpoints expose no HTTP start/stop operation; displayed control commands
run through the CLI. Other dashboard actions retain their own existing policy.

These tabs display captured headless output, not an input-capable terminal or a
reconstructed native CLI conversation. Externally started terminals cannot gain
past output retroactively. Foreground `launch` records can appear, but their
streamed output has no retained transcript. Use `spawn` or the manager for new
workers whose output must remain auditable.

Task/evidence views show **current** task state alongside the execution's epoch;
another assignment may have updated the task since that execution ran. Output,
exit codes and agent assertions do not substitute for integration/verification
receipts. Existing capture limits still apply: overflow can retain only a prefix,
and a view can show only a bounded excerpt of that prefix.

Log reads use only execution-ID-derived regular files in the board's log directory,
refuse linked paths and ignore a forged stored output path. Terminal controls are
removed before display; common credentials are redacted on a best-effort basis.
[Source-bound validation](validation/managed-sessions/report.md) records the Linux,
Windows, browser and real-terminal checks. Raw logs remain local, unencrypted and potentially sensitive. Local names are
still unauthenticated; see [SECURITY.md](../SECURITY.md).
