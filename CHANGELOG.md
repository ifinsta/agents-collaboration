# Changelog

## v0.4.1 - 2026-10-18

### Added

- **Pictures of the console**, at the top of the README. `docs/console.svg` loops
  through six moments of the simulated session:
  - the goal committed;
  - three agents working at once;
  - the merge queue catching a conflict;
  - a silent agent's task taken over;
  - the gate catching a wrong test;
  - the goal closed on evidence.

  `docs/console-three-agents.svg` is a still of the three agents working. The
  simulation draws both from the tool's own board and monitor views, and CI
  builds them on every change.
- The simulated goal gains a third task (a changelog entry), so the first wave
  really runs three agents in parallel.

- **Kilo Code** (`kilocode`, verified with `@kilocode/cli` 0.18.0) is a supported
  agent CLI. It works with `probe`, `spawn` (`--auto`, `--yolo` when unattended,
  `-mo` for the model) and the console's `launch`. The adapter never uses Kilo's
  own `--parallel` branching, and a test keeps every adapter away from a CLI's
  own branching modes (EC-181).

### Fixed: work never leaves the pool

Found when two Qoder agents in a real project each took a task, received no
instructions, and were closed, which left both tasks orphaned and out of reach.

- **Untouched tasks return to the pool.** If an agent exits before planning,
  stepping, committing or changing anything, its task goes straight back to the
  pool and its empty worktree is removed. Existing boards are cleaned on the next
  command (EC-184).
- **Work left behind is offered.** When nothing is open, `next` offers an
  orphaned task as a take-over. The board lists it as "needs a new owner"
  (EC-185).
- **Every agent receives its instructions.** Qoder now starts with its first
  message (`-i`, new in Qoder 1.1.73). For a CLI that cannot take one, the
  message goes to the clipboard and the launch waits for Enter, instead of
  printing it behind the CLI's screen (EC-183).
- **CLIs that change are caught.** Qoder updated itself mid-session and dropped
  `-q` and `--max-turns`. Before `spawn`, `launch` or `probe` uses a CLI, every
  option is checked against its own `--help` (EC-182). The Qoder adapter is
  updated for 1.1.73.
- **An uncommitted skill is named.** `doctor`, and the coordinator's `join`, warn
  when the skill is installed but not committed, because then agents in
  worktrees cannot see it (EC-186).
- A launched agent's exit is recorded with its exit code and how long it ran.
- Events no longer show internals: no Python lists (`needs ['H-api']`), no claim
  epochs, and no list of every answered key. Goal outcomes and answers read as
  sentences.

## v0.4.0 - 2026-10-18

A console people can read, shaped by using the v0.2.0 console for real.

### Changed

- **Layout:** the board takes the left half at full height, and the event monitor
  and the launcher share the right. Agent panes asked for with `--agents` get
  their own tab (EC-180).
- **Fit:** every console view fits its pane. The board shows the most important
  lines first and fills the rest with recent events; lines are clipped or
  wrapped to the width (EC-174).
- **Readable events:** events read as sentences in local time, coloured by kind
  ("opencode joined: opencode / DeepSeek V4.1 Flash Free; caps bash, windows"),
  with no UTC stamps or Python lists. `NO_COLOR` turns colour off (EC-175).
- **The launcher:**
  - it starts each agent in a new tab of the same terminal (Windows Terminal or
    tmux) instead of inside its own small pane;
  - it offers the next open task, a chosen task (EC-179), or no task yet (EC-178);
  - leaving it explains how to reopen it (EC-177).

### Added

- `swarm launch <cli> --no-task`: join in the main checkout and ask for work.
- The monitor and the board restart themselves when `swarm.py` is updated
  (EC-176).

## v0.3.3 - 2026-10-18

### Added

- **[A simulated session](docs/simulation.md)** shows what to expect before you
  install. [`examples/simulate.py`](examples/simulate.py) runs it with the real
  installer, tool and git, and `--check` verifies every milestone in CI on every OS.
  Three agents and a human take one goal from a sentence to merged, verified work.
  On the way they meet hard questions, a refused gap, an overlap, a merge conflict,
  a silent agent taken over, and a failing gate.

### Fixed

- `goal answer` no longer counts an `unknown` as answered. It says which questions
  wait, which question each became, and who it went to (EC-173). Found by the
  simulation.
- The merge message has no trailing space when nothing was pushed.

## v0.3.2 - 2026-10-18

### Fixed

- **`--scaffold` no longer puts example tasks on the board.** In v0.3.1 the example
  config pointed at the example backlog, so the first command imported
  "EX-docs" and "EX-api" as real, claimable work. Now `--scaffold` creates only a
  config that explains every setting and names no backlog. The example backlog is marked, and the
  tool never imports it (EC-171).
- **A backlog file named in the config but missing** is reported instead of
  crashing the command (EC-172).

### If you used `--scaffold` with v0.3.1

Run `swarm update`, then `swarm sync`. It withdraws EX- tasks nobody has
touched. Delete `.agents/swarm/backlog.md` if it is the copied example.

## v0.3.1 - 2026-10-18

- The tool's output is UTF-8 on every OS. Through a pipe, which is how agents
  read it, Windows had used cp1252: "§" arrived garbled and a note containing
  "→" crashed the command (EC-170). Found by running v0.3.0 in a real project.

## v0.3.0 - 2026-10-18

Nothing about a project is assumed any more. A piece of work becomes tasks
through hard questions, backward and forward reasoning, and a review that attacks
the plan.

### Added

- **`swarm goal`:** `new`, `answer`, `ask`, `outcome`, `task`, `review`,
  `commit [--assign]`, `show`, `list` and `close`.
  - Questions come in four stages: understand, backward, forward, challenge. Thin
    answers are refused, and `unknown` becomes a blocking question (EC-159).
  - Every task serves an outcome (EC-160) and carries a done-check (EC-162).
  - Review refuses outcomes without work (EC-161), oversized tasks (EC-163) and
    dependencies on work that does not exist (EC-164).
  - Review shows the backward chain and the forward waves.
  - `commit --assign` gives the first wave to machines that can verify it
    (EC-167).
  - `close` needs evidence for every outcome (EC-169).
- **`swarm context`:** previous and next for a task. It shows what the tasks it
  builds on produced (evidence, files, commit, owed checks), and what each task
  waiting on it must achieve (EC-165, EC-166). The claim output and spawned
  agents' briefs include it.

### Changed

- The installer creates `.agents/swarm/config.toml` and `backlog.md` only with
  `--scaffold`. The tool runs on defaults; a backlog file is optional (EC-168).

## v0.2.0 - 2026-10-18

See the pool, and drive it, from a terminal. Agents can install the skill
themselves.

### Added

- **`swarm console`** opens a visible terminal in the project, split into at least
  three panes:
  - an event monitor;
  - the live board;
  - an agent launcher;
  - one interactive pane per agent asked for with `--agents`.

  On Windows it uses Windows Terminal split panes; on Linux and macOS, tmux in a
  new window. Without either it uses separate windows, and on a machine with no
  display it prints what to run (EC-152).
- **The console question.** The coordinator is told to ask the human once per
  board whether to open the console; `--decline` records a no (EC-149).
- **`swarm launch <cli>`** starts an agent CLI interactively in the current
  terminal, already joined and holding a task, inside its worktree with its brief
  (EC-153). If the CLI cannot take a first message, it prints the one to paste
  (EC-155).
- **`swarm launcher`** (a menu), **`swarm dashboard`** (the live board) and
  **`swarm monitor --observe`** (follow events beside a running monitor, EC-150).
- **`[worktree] copy`** copies git-ignored local files such as `.env` into each new
  worktree (EC-148).
- **`swarm version`** and **`swarm update`** (EC-158).
- **Installer:**
  - `--claude` adds a Claude Code pointer skill (EC-156);
  - `--user` installs once for every repository (EC-157);
  - `--all` adds every pointer.
- **INSTALL.md**, an install guide written for agents.

### Changed

- `spawn` and `launch` share one preparation step: join, claim, brief.

## v0.1.2 - 2026-10-18

- The installer keeps the line endings and byte-order mark of the files it edits.
  On Windows it rewrote `AGENTS.md` with CRLF throughout, so a ten-line section
  showed as a whole-file change (EC-146).
- `swarm record <task> --commit <sha>` marks a task done when its work reached the
  target outside the board. It is for migrating from an earlier board, or for
  work a person merged. It checks the commit is in the target's history, frees the
  holder and cleans up the worktree (EC-147).

## v0.1.1 - 2026-10-18

Fixes from the first real run, in a repository where five agents were already
working through an earlier board.

- `claim` refuses a task whose branch already exists (work started outside the
  board). `--adopt` continues it and tells the coordinator, and `next` never
  hands such a task out (EC-042, EC-141).
- Gates that name their program by relative path now resolve it from the task's
  worktree on every OS. Windows had resolved it from the caller's directory, so
  the gate failed (EC-144). `doctor` checks gates the same way.
- `spawn --dry-run` changes nothing; it used to join the agent and claim the
  task (EC-145).
- Finishing every step within two minutes of `start` is flagged to the
  coordinator (EC-142).
- Only whoever set a pause, or a human, can lift it (EC-143). `pause` and
  `resume` now run the sweep like every other command.
- Broadcasts are matched to agents by message id, not by a one-second timestamp,
  so an agent joining in the same second never sees an earlier broadcast
  (EC-103). Boards created by v0.1.0 are upgraded in place.

## v0.1.0 - 2026-10-18

First public release.

- `swarm.py`: a coordination service for up to five coding agents on one git
  repository. It is one standard-library Python file, and its state lives in
  SQLite inside the git directory.
  - Pool: join and solo detection, readiness, roles, and an elected coordinator.
  - Tasks: one task per agent, claims with fencing, a worktree, branch and slot
    per task.
  - Planning: critical questions that block work until answered, ordered plans,
    and step evidence.
  - Conflicts: scope overlap checks, and hotspot locks with leases.
  - Merging: a single merge queue that rebases, runs gates on the rebased tree,
    advances the target with compare-and-swap, and never overwrites a person's
    work.
  - Operation: a background monitor, and `doctor` for drift.
- Environment intelligence: the service detects the OS, shell, Python command,
  tools, encoding and git settings. It turns them into rules for agents and
  capabilities for task routing, and gates can differ by OS.
- Agent CLIs: readiness probing and headless spawning for Claude Code, opencode,
  Qoder, Codex and Gemini. DeepSeek's adapter is included but unverified.
- `SKILL.md`: the protocol, written for any agent CLI.
- `EDGE-CASES.md`: 140 collaboration edge cases with their handling and status.
- `install.py`: one-line install from GitHub, verified against the release
  manifest.
