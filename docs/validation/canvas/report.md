# Interactive team canvas validation

Validated locally on Windows with Python 3.12.2 and installed Microsoft Edge on
2026-10-20. This evidence covers the canvas changes and dashboard/installer
regressions; it does not replace the broader platform validation matrix.

The canvas follows the spacing, floating controls and card treatment in the
repository's `canvas.png` reference. It continues to draw relationships derived
from the selected board. Cards show recorded completed task steps where available.

| Check | Result | Evidence |
|---|---|---|
| Zoom, drag-pan, keyboard controls, pointer-anchored Ctrl+wheel | Passed | [Browser acceptance](browser.json) |
| Real board update preserves camera; switching boards restores separate cameras | Passed | [Browser acceptance](browser.json) |
| Search, empty results, participant focus, edge filters, relationship navigation | Passed | [Browser acceptance](browser.json) |
| Literal untrusted display text and production CSP | Passed; no browser console or page errors | [Browser acceptance](browser.json) |
| 1440, 1024, 820, 600 and 390 px layouts | No horizontal page overflow | [Desktop](canvas-1440.png), [390 px fitted view](canvas-390.png) |
| Touch-capable 390 px phone context | Starts at 100%, centres linked participant, controls accessible | [Phone](canvas-phone.png) |
| Dashboard and action regressions | 38 passed, zero skipped/failed | [Per-case results](regressions.json), [Log](regressions.txt) |
| Installer and manifest regressions | 19 passed | [Log](installer.txt) |

[Source hashes](source.json) bind this evidence to the tested files.
The browser runner independently checks that its inputs are unchanged throughout
the run. Its fixtures create disposable real Git boards, an isolated dashboard
home and a temporary server port; no provider CLI is started. The browser test
injects one hostile display string into an intercepted API response to verify text
rendering. All other graph state comes from the fixture boards.

PowerShell's redirected logs label unittest's stderr as `NativeCommandError` even
when its result is `OK`; the retained per-case dashboard report records all 38
passing outcomes. Windows also logged an idle HTTP connection reset when a client
closed a connection during validation. Browser error collection remained empty.

Reproduce from the repository root, with Playwright and an installed Edge:

```powershell
python scripts/validate_canvas.py --output canvas-check
python -m unittest discover -s tests -p test_web_dashboard.py -v
python -m unittest discover -s tests -p test_web_actions.py -v
python -m unittest discover -s tests -p test_installer.py -v
python scripts/make_manifest.py --check
python -m ruff check .
```

Playwright is optional validation tooling; the installed dashboard retains its
standard-library-only runtime. The touch check uses a browser device context,
not a physical phone, and this run does not claim Firefox, Safari or macOS testing.
