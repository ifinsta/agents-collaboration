# Canvas updates in place and smooth connections

Validated on Windows with Python 3.12.2 and installed Microsoft Edge on
2026-10-20. [Browser results](browser.json) include source hashes checked before
and after the run. [Regression results](results.json) and
[per-case outcomes](regressions.json) cover the dashboard, actions and installer:
**57 passed**, zero skipped or failed, exit code 0, with the recorded source
unchanged throughout the regression run.

The earlier refresh path called `shell()` and rebuilt the dashboard DOM on a
changed response. The Team view now has an incremental update path. Cards are
matched by participant ID; text and attributes change only when their rendered
values differ. Inspector sections retain their elements when their inputs are
unchanged, including the steward's action form. The canvas stage, navigation
controls, search field and header stay mounted across data updates and participant
selection. Switching boards or pages mounts the appropriate view.

The browser test retains references to the header, main element, canvas, stage,
plane, navigation controls, search, inspector, cards and connectors. It changes
fixture task state and inspects mutations during a live update. Bob and the
integration gate receive visible changes; the other cards receive no mutations.
Existing card roots and surviving connector elements retain their identity.

Every factual relationship uses an SVG path: cubic curves for direct links and
rounded quadratic bends where a route must pass around another card. The browser
checks each path's endpoints against its cards' boundaries and verifies arrowheads
for directional relationships. Peer collaboration remains undirected. Solid,
dotted and dashed styles continue to distinguish relationship types.

Additional checks cover search and selection, filters, camera retention, keyboard
and pointer zoom, board switching, literal hostile display text under the
production CSP, and layouts at 390, 600, 820, 1024 and 1440 px without horizontal
page overflow. A touch-capable browser context starts at readable 100% zoom. The
steward form retains its draft and chosen CLI through a live update and a successful
local inbox-review action; no provider CLI is launched. Browser console and page
error collection are empty.

- [Desktop preview](canvas-1440.png)
- [Phone preview](canvas-phone.png)
- [390 px fitted preview](canvas-390.png)
- [Regression log](regressions.txt)
- [Recorded regression inputs](source.json)
- [Earlier canvas snapshot](../canvas/report.md)

Reproduce the browser acceptance with Playwright and an installed Edge:

```powershell
python scripts/validate_canvas.py --output canvas-live-check
```

Playwright remains optional validation tooling. The dashboard adds no runtime
dependency. These are local browser and regression checks, not a new full-platform
CI run or physical-phone acceptance.
