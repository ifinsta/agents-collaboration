# Installing Hivewire

Use a verified Python 3.11+ executable and Git. POSIX process supervision also
uses `ps`. Provider CLIs and their authentication are separate prerequisites.
`PY` below is a placeholder for your verified Python command, such as `python`
or `py -3`; replace it before running a command.

## Select the destination and Python

Run `git rev-parse --show-toplevel` to identify the project root. Use the project
already requested by the person. For an explicitly requested user installation,
use `--user` instead. If neither destination is known, clarify that scope.

Check `python --version` or `py -3 --version`. A Windows `python3` command may be
a Store stub; use the executable that actually reports 3.11 or newer. Read the
shell's facts before choosing PowerShell or POSIX syntax.

## Install current Hivewire source

Run from the destination repository root. These download the installer from
`main`; the default payload ref is also `main`. A selected source must ship
`hivewire.py` as its only launcher. Use `--ref REF` for a reviewed Hivewire ref.

```bash
# bash, zsh, Git Bash
curl -fsSL https://raw.githubusercontent.com/ifinsta/hivewire/main/install.py | PY - --all
```

```powershell
# PowerShell
irm https://raw.githubusercontent.com/ifinsta/hivewire/main/install.py | PY - --all
```

`--all` adds the pointers read by agent CLIs: a marked section in `AGENTS.md`
and `.claude/skills/agents-collaboration/SKILL.md`. The installer verifies payload
hashes against the selected ref's manifest. It refuses to overwrite edited
installed files unless explicitly given `--force`, and preserves pointer-file
line endings. `--scaffold` separately creates an explained project configuration;
installation does not import the example backlog.

## Install reviewed local source

To evaluate the unreleased changes described in the [current documentation](docs/README.md),
install from that checkout instead of assuming the published tag contains them.
Replace the paths with actual source and destination directories:

```text
PY PATH_TO_SOURCE/scripts/make_manifest.py --check
PY PATH_TO_SOURCE/install.py --source PATH_TO_SOURCE --project PATH_TO_PROJECT --all
```

A source maintainer regenerates the manifest after intentional payload edits.
Manifest agreement verifies file integrity; it does not establish runtime test
coverage or release readiness.

## Verify and start

`hivewire.py` is the only supported launcher. The installer rejects payloads
without it or with an obsolete command alias. It removes retired files recorded
by a prior managed installation, using the same edited-file protection as other
installed files. Board configuration and state are not removed.

```text
PY .agents/skills/agents-collaboration/hivewire.py version
PY .agents/skills/agents-collaboration/hivewire.py --json protocol
PY .agents/skills/agents-collaboration/hivewire.py environment
```

The reviewed current source uses CLI protocol **2**, database schema **13** and
bus/message/event versions **1**. Inspect the installed protocol and skill before using protocol-dependent automation. Read `environment`
and the installed `SKILL.md`, then follow its join and goal workflow. Configure
real executable project gates before integrating tasks, and approved executable
outcome checks before verifying and closing a goal.

From task worktrees, use the verified Python executable and the **absolute** path
to the installed launcher printed by the tool.

## User installation

An explicitly requested installation for all repositories uses `--user`:

```bash
curl -fsSL https://raw.githubusercontent.com/ifinsta/hivewire/main/install.py | PY - --user --claude
```

The launcher is under the user's `.agents/skills/agents-collaboration/` directory.
Use its absolute path; shell expansion of `~` differs across shells. Each project
still owns its own `.agents/swarm/config.toml` and board.

## Updating

```text
PY .agents/skills/agents-collaboration/hivewire.py update
```

`update` downloads the installer and uses its default release ref, or the explicit
`--ref` supplied to the command, while preserving installed pointer choices. It
does not reproduce unpublished local edits. To keep evaluating local source,
repeat the reviewed `install.py --source ...` installation. Read the
[migration guide](docs/legacy-migration.md) before changing protocol/schema versions;
forward database migration is supported, downgrade is not.
