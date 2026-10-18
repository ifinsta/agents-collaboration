# Agent CLIs

Which coding agents can join a pool, how readiness is checked, and how they are
started headless. Any agent that can run a shell command can join by hand
(`swarm join`). Adapters are only needed for `probe` and `spawn`.

| Kind | Headless command | Sign-in check | Unattended flag | Status |
|---|---|---|---|---|
| `claude` (Claude Code) | `claude -p "<prompt>"` | `claude auth status` | `--dangerously-skip-permissions` | verified with 2.1.280 |
| `opencode` | `opencode run "<prompt>"` | `opencode auth list` | `--auto` | verified with 2.0.32 |
| `qodercli` (Qoder) | `qodercli -p "<prompt>" -w <dir> -q --max-turns N` | `qodercli status` | `--dangerously-skip-permissions` | verified with 0.1.46 |
| `codex` | `codex exec "<prompt>" -C <dir> --add-dir <git dir>` | `codex login status` | `--full-auto` | verified with 0.104.0 |
| `gemini` | `gemini -p "<prompt>"` | none (reported as unknown) | `--approval-mode yolo` | verified with 0.53.1 |
| `deepseek` (deepseek-tui) | `deepseek exec "<prompt>"` | `deepseek auth status` | none | **unverified**: `exec` does not document its arguments |

"Verified" means the command line was taken from that CLI version's own `--help`.
Re-verify with `swarm probe --live` before relying on an adapter.

**DeepSeek models through opencode** is the proven path today. opencode accepts
a DeepSeek API key, so:

```bash
swarm spawn opencode --name ds1 --task T1 --model deepseek/deepseek-chat
```

## Readiness

```bash
swarm probe                 # installed? version? signed in? (no requests sent)
swarm probe --live          # also asks each installed CLI to reply READY (one request each)
swarm agents                # agents already in the pool: state, OS, task, last heartbeat
swarm send ds1 "free for the API task?" --ping    # ds1 answers with `swarm ack "..."`
```

`probe` runs each CLI's own sign-in status command and reports only its exit
code. The output usually contains an account name or email, so it is never
printed or stored.

## Spawning

```bash
swarm spawn <kind> --name <name> --task <task> [--model <model>] [--unattended] [--dry-run]
```

1. The service joins `<name>` and claims `<task>` (or the best task) for it, which
   creates the worktree.
2. It writes `.swarm-brief.md` in the worktree: identity, task, the absolute tool
   command, the skill path, and the detected environment with its rules.
3. It launches the CLI in the worktree, detached, with output in
   `.git/swarm/logs/<name>.log`, and records the process id.
4. If the process exits, the agent goes offline and its task is orphaned at once,
   so another agent can take it over.

The prompt on the command line is always one safe sentence that points at the
brief. Windows `.cmd` shims pass arguments through `cmd.exe`, and anything more
could be reinterpreted.

**Unattended mode** adds each CLI's permission-bypass flag. A headless agent
without it often stops at the first tool use, because there is nobody to approve
it. With it, the agent can run any command its CLI allows. That is why
`--unattended` also needs `[spawn] allow_unattended = true` in the project
config: a person decides, once, per repository.

## Adding a CLI

```toml
[adapters.mycli]
version = ["mycli", "--version"]
auth = ["mycli", "whoami"]                 # [] if there is no status command
run = ["mycli", "--print", "{prompt}"]     # placeholders: {prompt} {cwd} {git_common} {max_turns} {model}
model = ["--model", "{model}"]
unattended = ["--yes"]
verified = false                           # true only after a real probe --live and spawn
```

If the CLI sandboxes file access to its working directory, give it the git common
directory too (as the `codex` adapter does). Commits in a worktree write objects
there.
