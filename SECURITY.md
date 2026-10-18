# Security policy

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
- The installer writing outside `.agents/` and `AGENTS.md`, or installing a file
  that does not match its release manifest.
- Secrets from a CLI's sign-in status reaching the board, a log, or the output.

## The trust model, stated plainly

- **The machine is the trust boundary.** Every agent on the machine can read and
  write the board in `.git/swarm/`. Agent names are not authenticated (EC-008 in
  `EDGE-CASES.md`). Do not run agents you do not trust in the same repository.
- `--unattended` lets spawned agents bypass their own permission prompts. It is
  off unless a person enables `[spawn] allow_unattended` in the project config.
- Notes, questions and messages are stored unencrypted in the git directory.
  They are never committed, and they are not scanned for secrets (EC-105).
