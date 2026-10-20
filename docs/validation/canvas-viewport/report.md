# Team viewport layout

Validated on Windows with Python 3.12.2 and Microsoft Edge on 2026-10-20.

The Team page has two sections below the global header: the canvas section,
including its title and search, and the selected participant inspector. Both
extend to the bottom of the viewport on desktop. The header takes its actual
height, including wrapped navigation. On phones the sections stack within the
remaining height. Canvas and inspector scrolling stays inside their sections.

[Browser results](browser.json) record source hashes, measured section bounds
and checks at nine window sizes, plus a touch phone context. Measurements verify
that sections meet the header and viewport edges without page overflow. Checks
also cover independent inspector scrolling, route changes, retained DOM elements
and camera position through live updates, smooth connectors, search, keyboard
navigation, board switching, action form retention and literal untrusted text.
No browser console or page errors were recorded.

The [dashboard regression log](windows-web.txt) records **24 tests passed**,
zero failures, exit code 0. Windows HTTP connection-reset diagnostics occurred
when test clients disconnected; they did not fail the tests. Ruff, manifest
verification and `git diff --check` passed. These are local checks.

The running local dashboard was restarted headlessly in observation mode with
its existing address and token. A separate browser check against that dashboard
measured both desktop sections at 855 px high in a 1920 × 900 window, directly
below the 45 px header, without document overflow or browser errors.

- [Desktop preview](canvas-1440.png)
- [Phone preview](canvas-phone.png)
- [Fitted phone preview](canvas-390.png)

Reproduce with optional Playwright and installed Edge:

```powershell
python scripts/validate_canvas.py --output canvas-viewport-check
python -m unittest discover -s tests -p test_web_dashboard.py -v
```
