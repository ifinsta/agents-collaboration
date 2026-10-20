# Assignment workspace startup

Validated locally on Windows, Python 3.12.2, on 2026-10-20.

`hivewire workspace` opens one managed session terminal and the selected board's
browser dashboard. The coordinator skill now runs this at assignment startup,
replacing the previous question about manually opening a console. Engine join
and identity responses remind the coordinator to open a missing workspace.
Opening viewers does not start provider agents; their owned executions supply
the manager's dynamic audit tabs through the existing session view.

The live Windows Terminal launch acquired its viewer lease and continued sending
heartbeats. The browser accepted the open request. A subsequent startup returned
`dashboard: ready`, `terminal: already running`, `browser: already opened`, with
no warnings. These checks used the existing dashboard without changing its token.

[Results and source hashes](results.json) retain **94 selected tests: 93 passed,
one skipped** because this host cannot create file symlinks:

- [Workspace, session lifetime and console checks](startup.txt): 29 run, 28 passed.
- [Installation and command naming](installation.txt): 27 passed, including the new module in the installed payload.
- [Dashboard and guarded actions](dashboard.txt): 38 passed.

Workspace checks cover simultaneous startup against separate SQLite connections,
duplicate suppression, detach/reopen without stopping workers, failed viewer
retries, stale launch leases, headless behavior, finite JSON/dry-run output,
coordinator permissions, token omission, and platform command construction.
An isolated integration test starts a real hidden dashboard, authenticates its
loopback endpoint, reuses it, and stops only the test-owned subprocess.
Ruff, manifest verification and `git diff --check` also passed.

These are selected local regressions, not full-platform acceptance. Native
macOS/Linux viewers and the Windows console fallback were checked as command
plans, not launched here. Browser closure is not detected: use `workspace --reopen`
to open that view again. A pending terminal launch expires after 30 seconds if no
viewer claims it; explicit detach releases the lease immediately. The automatic
dashboard is an observer; the session manager retains its existing recovery sweeps.
