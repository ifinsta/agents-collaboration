# Pre-push source validation

The push includes the resilient workforce engine, standard bus contract and
dispatch, managed sessions, browser dashboard, documentation and retained
validation history. The version remains an unreleased source update after the
existing v0.4.4 tag.

## Terminal-output defect found during validation

The first complete Linux run discovered 425 cases: 424 passed and one failed.
`test_ec328_posix_terminal_drains_the_final_output_after_the_worker_exits`
captured only part of a fast-exiting worker's final PTY output. The launcher
performed only one final read, although a PTY can return less than the requested
buffer size. See [original results](linux313/results.json) and
[failing shard](linux313/shard-5.log).

The launcher now drains every available output chunk after the owned group exits,
with input forwarding disabled, before closing the terminal bridge. A deterministic
regression test uses a real PTY and limits each read to 127 bytes. Both that check
and the existing end-to-end output check passed. All nine terminal-supervision
tests passed in the [focused run](terminal-fix.txt).

The complete suite was then rerun from a frozen archive of the fixed runtime:
**425 of 426 cases passed**, with zero skips and one fixture error. The terminal
checks passed. [Rerun results](linux313-fixed/results.json) retain all discovered
cases, source hashes, coverage and unchanged-input checks.

## Liveness fixture race

The remaining error came from an older liveness test invoking `git status` in a
worktree after its instant worker had already removed it during normal cleanup.
This was a race between the test's inspection and the successful cleanup it was
testing. See [the traceback](linux313-fixed/shard-5.log). Five diagnostic repeats
passed without a fix, demonstrating why a simple retry would not prevent it.

The fixture now gates worker exit on a release file outside the worktree. It
checks the live worktree and ignored brief, releases the worker, then verifies
automatic cleanup and task reuse. All original outcome assertions remain.
The synchronized test passed [ten consecutive checks](liveness-fixed.txt).

The [publication comparison](publication.json) verifies that final staged runtime
inputs match the complete rerun. The only subsequent test-input change is this
fixture synchronization in `tests/test_swarm.py`. The final combined snapshot
has not passed another complete local discovery; hosted CI must establish that
result. Evidence files and this report are outside the runner's input inventory.

## Other checks

- Ruff and the installed skill manifest pass.
- All 284 staged relative documentation links resolved before adding this report.
- The staged source and retained evidence had no matches for the credential
  patterns checked before staging; the frozen source ZIP was checked as well.
- [Canvas acceptance](../canvas-live/report.md) retains its own source hashes,
  browser interaction checks and 57 Windows dashboard/action/installer results.
  It precedes this POSIX terminal fix; it is not relabelled as a new full-platform
  result.
- Validation artifacts retain their original bytes through `.gitattributes`,
  including logs whose hashes appear in reports.

The first failure and its source inventory remain available. Hosted CI is
configured to run the final commit on Linux, Windows and macOS with Python 3.11
and 3.13. A push starts that matrix; the local Linux run does not establish its
result or complete every acceptance item in the original design proposal.
