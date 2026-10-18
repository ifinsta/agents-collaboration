# Installing agents-collaboration (for agents)

If a person asked you to install agents-collaboration, follow these steps in
order. Every command is complete; do not adapt it to an operating system you
assume. Check the facts first.

## 1. Find out where you are

- Run `git rev-parse --show-toplevel`. If it prints a path, you are in a
  repository: install there (steps 2 to 4). If it fails, ask the person whether to
  install for every repository instead (step 5).
- Find Python 3.11 or newer: try `python --version`, then `py -3 --version`. On
  Windows, never use `python3`: it is often the Microsoft Store stub. Use whichever
  command printed 3.11 or newer as `PY` below.
- Find your shell: if `$PSVersionTable` means something to it, it is PowerShell;
  otherwise use the bash form.

## 2. Install into the repository

From the repository's root:

```bash
# bash, zsh, Git Bash
curl -fsSL https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | PY - --all
```

```powershell
# PowerShell
irm https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | PY - --all
```

`--all` adds the pointers that agent CLIs read: a marked section in `AGENTS.md`
(opencode, Codex, Qoder, DeepSeek-TUI and others) and `.claude/skills/agents-collaboration/SKILL.md`
(Claude Code). The installer verifies every file against the release manifest,
never overwrites edits you made to installed files, and keeps the line endings of
the files it edits.

## 3. Verify

```bash
PY .agents/skills/agents-collaboration/swarm.py version
PY .agents/skills/agents-collaboration/swarm.py environment
```

`environment` lists the facts and rules for this machine. Read them before your
next command.

## 4. Start

1. Read `.agents/skills/agents-collaboration/SKILL.md` and follow it from section 1.
2. Do not create project settings by guessing. If the person wants to state the
   project's own facts (gates, target branch, shared files), they add `--scaffold`
   to the install, or write `.agents/swarm/config.toml` themselves.
3. Turn the work you were given into tasks with `swarm goal` (SKILL.md, section 1.5).

## 5. Install once for every repository

```bash
curl -fsSL https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | PY - --user --claude
```

The tool is then `PY ~/.agents/skills/agents-collaboration/swarm.py`, and works
in any repository. A repository still keeps its own `.agents/swarm/config.toml`.

## Updating

```bash
PY .agents/skills/agents-collaboration/swarm.py update
```

It reinstalls the latest release the same way it was installed, keeping the
pointers already present.
