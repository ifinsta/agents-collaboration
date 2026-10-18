# Changelog

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
