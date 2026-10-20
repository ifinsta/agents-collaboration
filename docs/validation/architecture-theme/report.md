# Architecture reference typography and palette

Validated on Windows with Python 3.12.2 and Microsoft Edge on 2026-10-20.

The dashboard uses the font families and palette inspected on
[DeepInfer's architecture page](https://deepinfer.net/architecture/).
[Reference measurements](reference.json) record the colors and typography.
Archivo provides 400-weight body text and 700-weight headings; IBM Plex Mono
provides navigation, technical labels and code. Paper, raised paper, green-black
ink, teal and rust use the reference's color values. Dashboard font sizes and
spacing preserve the existing compact layout and 33 px desktop headers.
The Team canvas retains its original 20 px dotted grid; the reference's 32 px
square grid is used for page backgrounds. [Canvas measurements](canvas-grid.json)
verify the distinction on desktop and phone while preserving the fonts and palette.

`swarm_fonts.css` embeds the unmodified Latin WOFF2 distributions of Archivo
(variable 400–700) and IBM Plex Mono (400, 500, 600), with their copyright and
SIL Open Font License notices. The release manifest and installer include it.
The existing nonced stylesheet contains these font faces. CSP permits font data
only; no external font hosts are enabled.

[Browser acceptance](browser.json) passed all nine interaction checks across
11 viewport sizes, with source hashes unchanged before and after validation.
It covers live DOM updates, draft retention, camera and search behavior, smooth
connectors, board and page navigation, short windows, wrapped headers and touch
layouts. Console and page errors were empty.

The [installer log](installer.txt) records **19 passing tests**. The dashboard
security regression also passed with checks for the bundled font faces, their
injection into the single nonced stylesheet, and `font-src data:`. Ruff, manifest
verification and `git diff --check` passed. These are local checks.

[Live browser measurements](live-browser.json) verify custom font glyphs actually
render through the browser's font inspection API, the expected weights and
palette, and both desktop header heights. No external HTTP requests or browser
errors were observed. This distinguishes loaded fonts from fallback family names.

- [Desktop preview](canvas-1440.png)
- [Phone preview](canvas-phone.png)
- [Fitted phone preview](canvas-390.png)

Reproduce browser acceptance with optional Playwright and installed Edge:

```powershell
python scripts/validate_canvas.py --output architecture-theme-check
python -m unittest discover -s tests -p test_installer.py -v
python -m unittest discover -s tests -p test_web_dashboard.py -k locked_down -v
```
