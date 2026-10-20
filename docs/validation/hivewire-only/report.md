# Hivewire-only command entry point

Validated locally on Windows with Python 3.12.2 and Microsoft Edge on 2026-10-20.

`hivewire.py` is the only shipped command launcher. The old launcher was deleted
and removed from the release manifest. Installer pointers, CI, examples, test
fixtures, benchmark command labels, dashboard defaults and dashboard log prefixes
use Hivewire. The dashboard action allowlist accepts only `hivewire.py`.

The installer selects current `main` by default. It refuses a manifest without
`hivewire.py` or with an obsolete launcher instead of falling back to old commands.
Reinstalling removes retired managed files. Edited or unmanaged obsolete files
require the existing explicit `--force` option before removal; dry runs leave files
alone. Cleanup validates retired paths before deletion and does not remove board
configuration or data. Tests cover these cases, including an attempted path outside
the install directory.

Historical validation records retain the commands and behavior tested at their
recorded snapshots. They are not alternate supported versions or executable aliases.

[Selected regression results](results.json) record **107 passing tests**:

- [Installation and command naming](installation.txt): 27.
- [Dashboard and guarded actions](dashboard.txt): 38.
- [Joining, claims and planning](workflow.txt): 20.
- [Environment, initial workflow, console and output](environment-console.txt): 22.

The final naming and dashboard groups include the last command-default cleanup.
Workflow and environment groups cover the same final engine source. These are
selected local checks, not a complete platform matrix.

[Browser acceptance](browser.json) passed nine interaction checks across 11
viewport sizes with unchanged recorded application-source hashes and no browser
errors. The live dashboard was restarted headlessly with `hivewire.py` in
observation mode, preserving its existing address and token. Its Hivewire title
and rendered canvas were checked in the running browser. Fonts, compact headers
and the original dotted canvas remain intact. Ruff, manifest verification and
`git diff --check` passed.

- [Desktop preview](canvas-1440.png)
- [Phone preview](canvas-phone.png)
