# Web dashboard

This unreleased source feature is included in the current manifest file list.
Use a matching source installation; an older published tag may not contain it.
The [evidence index](README.md#evidence-and-release-readiness) distinguishes recorded
runtime snapshots from later dashboard changes.

At assignment startup the coordinator runs `hivewire workspace`. It starts the
dashboard as a hidden observer, opens the selected board in the browser once,
and opens the managed terminal alongside it. Repeat calls reuse both views;
`workspace --reopen` opens the browser again. See [managed sessions](managed-sessions.md)
for desktop detection, headless operation and worker lifetime guarantees.
The direct commands below remain useful for foreground server diagnostics.

```bash
hivewire dashboard --web                  # prints the link and opens it in your browser
hivewire dashboard --web --no-open        # print the link only
hivewire dashboard --web --port 9000      # another port (default: the saved one, else 8787)
hivewire dashboard --web --observe        # do not sweep; another `monitor` does
hivewire dashboard --web --reset-link     # make a new link; old links stop working
hivewire dashboard --web --read-only      # the page only shows; it cannot act as you
hivewire steward                          # the inbox steward, reviewing every minute (--once for one review)
```

## See it with the demo board

The pictures below are of a **seeded demo board**, not live agents.
[examples/dashboard_demo.py](../examples/dashboard_demo.py) builds it in a throw-away Git
repository with real `hivewire` commands: five agents (claude, opencode, qodercli, codex, gemini), a goal
awaiting approval, one task in the merge queue, one agent gone silent, an open incident under independent
review, questions, messages of several kinds and a few steward reminders. The silent agent, the incident and the
two merged tasks are written straight into the database, because producing them legitimately takes real commits
and a long wait.

```bash
python examples/dashboard_demo.py       # prints the new directory and the command to run there
cd <that directory>
python <path to>/hivewire.py dashboard --web
```

Heartbeats expire after 20 minutes, so a demo left alone turns into a board of silent agents; build it again to
see it live. Nothing here touches your repositories or `~/.agents`.

![Overview](images/dashboard-overview.png)

![Team canvas](images/dashboard-team.png)

| Inbox | Task |
|---|---|
| ![Inbox](images/dashboard-inbox.png) | ![Task](images/dashboard-task.png) |

![The overview in a 500 px wide window](images/dashboard-phone.png)

Regenerate the pictures with `python scripts/dashboard_screenshots.py [--out DIR] [--browser PATH]`. It builds
the demo in a temporary directory, runs the dashboard on a free port with throw-away state, photographs each page with
a headless Edge, Chrome or Chromium, and deletes everything it made. The narrowest shot is 500 px because headless
browsers widen narrower windows and crop the picture.

## One dashboard for every board

There is one dashboard per user, not one per run. It lives at a fixed address, `http://127.0.0.1:8787/` unless
that port is taken (then the next free one, which is saved and reused), and its link keeps the same token every
time. A bookmark of it keeps working across restarts.

- The first `hivewire dashboard --web` starts it and stays in the foreground until Ctrl+C.
- Every later run, from any repository or session, **adds its board to the running dashboard**, prints the same
  link with that board selected, and returns at once. It does not start a second server.
- A board switcher appears in the top bar once more than one board is listed. The address carries the board
  (`?b=ID`), so a link opens the board it names.
- If the terminal that started it is closed, run the command again: it comes back at the same address with the
  same link.

The shared state is in `~/.agents/swarm-web/` (set `SWARM_WEB_HOME` to move it): `server.json` holds the port and
token, `boards/` one small file per board. Only the terminal that started the dashboard sweeps its own board;
other listed boards are only read, so run `hivewire monitor` for them (or rely on their agents' own commands, which
sweep).

A link without its token, or with an old one, shows a short explanation instead of data.

The terminal board (`hivewire dashboard`) is unchanged. This is the same board, drawn for a person who wants
more room: who is working on what, what needs a human, what the agents said to each other, and why a
task is where it is. It refreshes every three seconds and stops with Ctrl+C.

## Acting from the page

The page is a tool, not only a view. These actions run as **you** (the human), from the item they concern:

| Where | Action | What runs |
|---|---|---|
| Overview, Decisions | Answer or waive a question | `hivewire answer` / `hivewire waive` |
| Overview, Decisions | Approve an architecture brief (after a confirmation) | `hivewire goal architecture GOAL --approve` |
| Inbox | Reply to a message, with its kind | `hivewire send AGENT TEXT --kind KIND --reply-to ID` |
| Inbox | Acknowledge a message addressed to you | `hivewire bus receive` then `hivewire bus ack`, with its receipt |
| Team, Inbox | Review inboxes now | `hivewire steward --once` |
| Team, steward inspector | Start an LLM reviewer (after a confirmation) | `hivewire add INBOX-n ...` then `hivewire spawn CLI --name NAME --task INBOX-n` |

Each action runs the real `hivewire` command in that board's repository, so the engine's own checks, refusals and
events apply exactly as in a terminal; a refusal is shown under the button. Everything else (interrupts,
take-overs, incident decisions, dead letters) still shows the command to copy. A reply never acknowledges a
message, and you can acknowledge only messages addressed to you. While you type, the live refresh pauses so your
text is never redrawn away; drafts survive a refresh. `--read-only` turns all actions off and the top bar then
says "Read-only" instead of "Acting as you".

## The inbox steward

Coordination stalls when messages sit unread. The steward is a built-in participant (not an LLM, and it takes no
agent slot) that reviews every inbox:

- A message an agent has left unacknowledged for 10 minutes (`--remind-after-min`) gets one reminder to that agent,
  listing the message numbers and how to acknowledge them. It repeats only after three such periods.
- If the recipient is offline, the steward tells the coordinator (or you, without one) instead.
- A critical message left waiting is also escalated to the coordinator, before it becomes a dead letter.
- Dead letters are reported to you once.

It **never acknowledges a message for anyone**: a receipt must come from its recipient. Its reminders expire on
their own, so they do not pile up in the inboxes they are about, and the human's own inbox is left to the page.
Run it with `hivewire steward` in a terminal or console pane, or press **Review inboxes now**. On the team canvas it
sits beside the orchestrator, with dotted lines to the agents it reminded.

For judgement calls (reading threads, drafting replies), start an **LLM reviewer** from the steward's inspector: it
creates a task `INBOX-n` ("Review every inbox: answer or escalate what is waiting, acknowledge what is addressed to
you") and spawns the CLI you pick on it. It uses that CLI's account and tokens, and works like any other agent:
one task, its own worktree, and its own acknowledgements.

## What it shows

The **Sessions** page adds a tab per owned execution, retained worker/supervisor
output, observed exit status and current task evidence. Its GET endpoints are
observational and board-scoped; start/stop controls use the existing CLI. For one
terminal with headless workers, use `hivewire sessions` or `hivewire console --managed`.
See [managed sessions](managed-sessions.md) for lifetime and capture limits.

| Page | Contents |
|---|---|
| Overview | A summary strip (agents online, tasks merged, waiting on you, blocked), a team table (status, task, step, contract clock, last seen), a work table, a "waiting on you" list (answer or waive a question, approve a brief, in place) and a plain-language activity log |
| Team | A canvas of the team in lanes (Governance, Orchestration, Execution, Assurance, Integration) with solid, dotted and dashed lines between agents, and an inspector for the selected one. See [the team canvas](#the-team-canvas) |
| Inbox | Every message with its kind, priority and acknowledgement state; filters for questions, decisions, warnings, reviews and dead letters; a thread view; per-recipient delivery, receipt lease and envelope fields |
| Decisions | Open questions, architecture briefs awaiting approval, contracts being negotiated with their decision window, incident reviews, interrupts, and what was recently settled |
| Tasks, Task | A table of every task, and per task: the plan as an ordered timeline with the evidence for each step, scope and locks, contract clock against its terms, checkpoints, the holder, open questions and the task's own events |

There is no free-form "debate" page. The tool has no such concept: disagreement is bounded and typed
(one contract counter, a timed decision window, evidence-backed incident reviews, decision messages), and
the Decisions page shows those.

## The team canvas

Agents are shown as `Alex (claude) – Orchestrator`: a display name, the CLI kind in brackets and a role.
The board stores a name and a kind, not a job title, so **roles are derived**, never configured:

| Role | Shown when |
|---|---|
| Owner | The human (the "You" node) |
| Orchestrator | The agent is the current coordinator |
| Implementer | Any other agent |
| Independent reviewer | The agent is assigned to review an open incident |
| Steward | The built-in inbox steward (always shown; "Not started" until it first runs) |

Each agent has an icon: a small line drawing of a bot (a different body for each kind of CLI, such as
`claude`, `opencode` or `codex`, and one picked consistently for kinds it does not know), with a badge for
its role. The icons are original drawings, not vendor logos.

The smooth connectors are facts read from the board. Curved SVG paths meet the
card edges; arrowheads indicate directional relationships:

| Line | Meaning | Comes from |
|---|---|---|
| Solid arrow | Accountability: the human approves, the orchestrator assigns, an implementer submits to the integration gate | The coordinator, task holders, tasks in the merge queue |
| Dotted | Collaboration between peers: a review request, a shared lesson, or the number of messages; and the steward's reminders | Messages between two non-coordinator agents, and from the steward, in the last 24 hours |
| Dashed teal arrow | Independent review | An open incident, its reviewer and its subject |

The line buttons hide a group of lines. A silent or offline agent is marked with a diamond and a red icon
(status is always a shape and a word, never colour alone), and its inspector offers the take-over command.

### Moving around

The canvas uses compact cards, the original dotted grid on a warm paper background, and a floating navigation bar. Task progress bars count
completed plan steps; a task without recorded steps has no progress bar.

| Control | Behaviour |
|---|---|
| Drag the background | Pan the workspace; touch screens use native scrolling |
| **− / +**, or Ctrl/⌘ + scroll | Zoom between 25% and 200%; scroll zoom stays anchored to the pointer |
| **Fit** | Fit the team into the available frame, adjusting when the window changes size |
| **Reset** | Return to 100% zoom and centre the selected participant |
| **Find** | Highlight names, roles, CLI kinds, statuses and task IDs; Enter selects and centres the next match; Escape clears the search |
| **Focus** | Dim cards outside the selected participant's direct relationships, respecting the visible line groups |
| Card or relationship link | Select that participant and open its inspector; the task link opens its evidence |

Focus the canvas with Tab to use **+ / −**, **F** (fit), **0** (100%), and the arrow keys (pan).
Canvas shortcuts apply only while the canvas itself has focus. Live refresh preserves zoom, position,
search and focus mode, and waits during a drag or while an input is active. Live updates patch changed
card text and attributes by participant ID, and update connectors and inspector sections in place.
The canvas, navigation controls and unchanged cards stay mounted; selecting another participant also
updates the existing workspace. Each board keeps its own
camera and search in memory until the page reloads. Wide screens initially fit the team; phones initially
use 100% zoom so cards remain readable.

Navigation is a browser view of the board; moving the view does not change assignments or relationships.
For reproducible browser checks, viewport measurements and screenshots, see
[canvas validation](validation/canvas-viewport/report.md).

## Screen sizes

Desktop navigation and the canvas toolbar are each 33 px high when they fit on
one row. Pages use compact section gaps, table rows, cards and inspector padding;
body text remains readable and phone controls keep their larger touch targets.

The page adapts from a phone to a wide monitor. It was measured in a browser at 390, 600, 820, 1024,
1280 and 1440 px wide with no horizontal page scroll on the original pages. The
new Sessions page was separately checked at 390 and 1280 px; see its validation report.

- **Phone (up to 760 px).** The top bar becomes two rows with the tabs underneath. Tables turn into stacked
  rows that keep their column names. Touch targets are at least 44 px. In an inbox the open message comes
  first, then the list.
- **Tablet (up to 860 px for tables, 1000 px for the inbox).** Tables stack and the inbox puts the thread
  before the list.
- **Team page.** Two sections fill the window below the main header, accounting for wrapped navigation.
  Wide screens place the canvas section beside the inspector. The title and search belong to the canvas
  section; the canvas and inspector scroll independently, without scrolling the page. The workspace has a
  dotted grid, a vertical tool rail on its right with the three line filters (icon buttons with labels),
  a legend in its top-right and navigation at the bottom. On a phone the two sections stack within the
  available height, with a scrollable inspector below and the line buttons beside the canvas.
  The Inbox works the same way on wide screens: list and thread fill the window and scroll separately, the
  reply box stays in view, and scroll positions survive the live refresh.

## Look and accessibility

The interface follows the typography and palette of [DeepInfer's architecture page](https://deepinfer.net/architecture/):
Archivo body text and bold headings, IBM Plex Mono navigation and technical labels, green-black ink,
teal accents, rust active indicators, warm paper and raised-paper card surfaces. Page backgrounds use a faint
32 px square grid; the Team canvas retains its original 20 px dotted grid. Both patterns are drawn with
local CSS gradients. Archivo (400–700) and IBM Plex Mono (400, 500, 600) are bundled as Latin WOFF2 data in
`swarm_fonts.css`, including their SIL Open Font License notices; other scripts use the system fallback stack.
There are no runtime requests to Google Fonts or other external hosts. Compact spacing, small corner radii,
thin focus indicators, and status shown as a shape plus a word remain consistent.
See [theme validation and previews](validation/architecture-theme/report.md) for measured fonts, colors and browser checks.
On wide screens the Overview, Decisions and task pages
fill the window and their two columns scroll independently, and the live refresh keeps each scroll position.

## Security model

- Listens on `127.0.0.1` only. There is no option to bind another address.
- Every data request must carry the link's token (in the link, then a header) and a `Host` of
  `127.0.0.1:PORT` or `localhost:PORT`. These checks mitigate cross-site access and DNS rebinding. The token is
  random, kept in `~/.agents/swarm-web/server.json` and reused so the link is stable; `--reset-link` replaces it.
  The page itself carries no board data and loads without the token, so a missing token gets an explanation.
- The list of boards is a file a person can edit. The server serves only paths that are a real
  `.../swarm/swarm.db` and a board id of eight hex digits, and opens each read-only.
- On Windows the port is taken exclusively, so another program cannot share it.
- Views are `GET` requests that open the board with a read-only SQLite connection (`mode=ro`, `query_only`).
- Actions are one endpoint, `POST /api/act`, which needs the token header, an `Origin` that is the dashboard's
  own address, a JSON body of at most 16 KB and an action from a fixed list. Inputs are checked first (ids are
  numbers, names match the agent-name pattern, text is 1 to 4000 characters). The server then runs `hivewire` with
  an argument list, never a shell, and puts free text after `--` so it can never be read as an option. It runs
  the `hivewire.py` that registered the board (a `hivewire.py` with `swarm_core.py` beside it), in that repository.
- **Anyone with the link can act as you** on the boards it lists. Keep the link private, use `--reset-link` if
  it was shared, and `--read-only` when you only want to watch.
- Board text is written by agents and is untrusted. The page builds its interface from text nodes only
  (never `innerHTML`), and its Content-Security-Policy is `default-src 'none'` with a single
  nonce-protected script and style, `connect-src 'self'`, `font-src data:` for the bundled fonts, and no external
  fonts, scripts or images.
- Anyone with the link can read every listed board and, while page actions are
  enabled, submit permitted human actions. This remains a trusted-local interface. Do not forward the link; use `--reset-link` if it has been shared. Stop the server
  when you are done.
- Unless `--observe` is given, the server runs the same sweep every `hivewire` command runs (marking silent
  agents offline, expiring contracts, escalating unanswered critical messages) every few seconds, as the
  terminal dashboard does. These sweeps can update liveness and recovery records
  through the normal engine; use `--observe` for an observational server loop.

## Files and endpoints

`swarm_web.py` sits next to `swarm_core.py` and uses the standard library only. The page is one string in
that file. JSON endpoints, all `GET` and all requiring the token header: `/api/overview`,
`/api/inbox?tab=`, `/api/message/ID`, `/api/team`, `/api/decisions`, `/api/task/ID` (each takes `b=BOARD`),
`/api/boards`, `/api/ping`, `/api/sessions` and `/api/sessions/EXECUTION_ID`; and one `POST`, `/api/act`. They are
for the page; the supported machine interface remains `--json` (protocol v2).
