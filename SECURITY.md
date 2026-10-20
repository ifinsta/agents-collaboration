# Security policy

Unreleased headless supervision uses private Windows jobs or anchored POSIX
groups; only the creating supervisor holds termination authority. Execution
records/PIDs are status, never a way to kill an arbitrary existing process.
Termination after timeout needs captured `[spawn] timeout_action = "terminate"`;
the default is cooperative. Unknown supervision blocks automatic cleanup/restart
until inspected. See [process supervision](docs/process-supervision.md).
This is not credential or OS isolation: code can deliberately leave an inherited
POSIX group or request allowed Windows breakaway. Independently supervised workers
start outside their coordinator's private job; inherited process context must be
preserved. Local names/database access remain unauthenticated.
Foreground `launch` uses the same owned job/group stop policy. Terminal output
streams without the retained headless capture receipt. No-task launches and the
unsupervised launch path have been removed.

New headless worker output is retained under a per-execution byte cap; earlier
logs are preserved separately. Raw worker logs remain local and unencrypted,
with no arbitrary-secret-removal promise. Metadata tails use best-effort
redaction. A lost reader may break the worker's output pipe; unknown state is
preserved rather than claiming observed termination. See the output section in
[process supervision](docs/process-supervision.md).

Unreleased usage allowances fence coordination permissions. Numeric usage reports
retain hashes and minimized facts, but are not authenticated provider bills.
Human conservative settlement is an attestation, not measured usage or observed
process termination. Calls outside recorded commands/report paths are not
automatically metered or constrained by a provider billing quota. See
[usage budgets](docs/usage-budgets.md).

The unreleased `dashboard --web` view listens on 127.0.0.1 only. Every data request needs a
token (in the printed link) and a checked loopback `Host` header,
which mitigate cross-site access and DNS rebinding. One dashboard serves every board a person starts it from;
its token is stored in `~/.agents/swarm-web/` and reused so the link is stable, and `--reset-link` replaces it.
Views open each board through read-only SQLite connections, and only paths that are a real `swarm/swarm.db`.
The page can also act **as the human**: answer or waive a question, reply to or acknowledge a message addressed
to the human, approve a brief, run the inbox steward, start a reviewer agent. Actions are one `POST /api/act`
that requires the token header and the dashboard's own `Origin`, takes a fixed list of actions with checked
inputs, and runs the real `hivewire` command with an argument list (free text after `--`), so the engine's rules
apply. **Anyone holding the link can therefore act as the human** on every listed board: keep it private,
`--reset-link` if it leaked, and `--read-only` to turn actions off. The inbox steward never acknowledges a
message on anyone's behalf. Board text is written by agents and is untrusted: the page sets only text content and
its Content-Security-Policy restricts scripts/styles to per-run nonces and
connections to the same origin. It adds no way to
authenticate agents. The server itself performs normal recovery/liveness sweeps
unless `--observe` is supplied, and its actions run `swarm` commands as the human unless
`--read-only` is supplied; reading the board does not make the default process observational. See [web dashboard](docs/web-dashboard.md).

## Reporting a vulnerability

Please report security issues privately through GitHub's
[private vulnerability reporting](https://github.com/ifinsta/agents-collaboration/security/advisories/new),
not in a public issue. We aim to acknowledge reports within three working days.

## What is in scope

- A way for one agent to make another agent, or the human, run a command it did
  not choose (prompt or argument injection through briefs, messages, task fields
  or spawned command lines).
- Anything that moves work into the target branch without passing the merge
  queue and its gates.
- Anything that overwrites a person's uncommitted work.
- The installer writing outside its explicitly selected project/user paths and
  pointer files (`.agents/`, `.claude/`, `AGENTS.md`), or installing a file
  that does not match its release manifest.
- Secrets from a CLI's sign-in status reaching the board, a log, or the output.

## The trust model, stated plainly

- **The machine is the trust boundary.** Every agent on the machine can read and
  write the board in `.git/swarm/`. Agent names are not authenticated (EC-008 in
  `EDGE-CASES.md`). Do not run agents you do not trust in the same repository.
- `--unattended` lets spawned agents bypass their own permission prompts. It is
  off unless a person enables `[spawn] allow_unattended` in the project config.
- Notes, questions and messages are stored unencrypted in the git directory.
  They are never committed. Unreleased versions apply best-effort redaction of
  common credential forms to new message bodies, checkpoint notes and event
  details, and reject credential-like envelope keys (EC-105). This does not
  recognize arbitrary sensitive prose, scrub old records, or cover every stored
  field (for example, question text). Avoid putting secrets on the board.
- Typed messages and message acknowledgements carry information. Only the
  separately checked interrupt control record changes coordination permissions;
  forged `interrupt`/`review_result` text cannot approve an action. Human and
  coordinator names remain unauthenticated roles within the local trust boundary.
- Targeted pause/cancellation fence coordination commands and retain worktrees.
  They do not sandbox filesystem access, revoke credentials, or terminate
  unrelated processes.
- Unreleased incident reviews reserve a different available reviewer and freeze
  source commits, policy, checks and diff evidence. Agent reviewers and subjects
  cannot resolve their own findings. A cleared finding never skips the merge
  gates; changed evidence invalidates it. Read-only is a CLI coordination role,
  not an OS filesystem sandbox.
- Memory is scoped contextual data, never policy or permission. Promotion needs
  a different verifier and local event/commit provenance. Cross-repository files
  require explicit opt-in and import as provisional candidates; exported verified
  labels and verifier names do not grant local authority. Evidence refs preserve
  inspected commits; registry data is still local, readable and unencrypted.
