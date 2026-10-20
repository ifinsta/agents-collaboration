# Hivewire naming and compatibility

Historical snapshot: the later Hivewire-only change removed the alias and installer
fallback tested here. See [current command validation](../hivewire-only/report.md).

Validated locally on Windows with Python 3.12.2 and Microsoft Edge on 2026-10-20.

Hivewire is the product name, with the tagline “Independent agents. Accountable
teamwork.” The dashboard title and masthead, project metadata, current guides,
installer presentation and preferred launcher use the new name.

`hivewire.py` is the preferred launcher; `swarm.py` remains a supported entry point
to the same engine. Both keep the launcher/core version check. Current installs
ship both and generate pointers to `hivewire.py`. For a release manifest without
that launcher, the installer selects `swarm.py`; a disposable manifest fixture
confirmed the generated pointer references the available entry point.

Existing install identifiers, environment variables, configuration sections,
repository URLs, database paths and machine protocol identifiers remain
compatible. No board migration is needed. Historical validation evidence keeps
the names and commands actually tested at the time.

[Selected regression results](results.json) record **101 passing tests**:

- [Installation and launcher compatibility](installation.txt): 21.
- [Dashboard and guarded actions](dashboard.txt): 38.
- [Joining, claims and planning](workflow.txt): 20.
- [Environment, initial workflow, console and output](environment-console.txt): 22.

Compatibility checks join and claim through the preferred launcher, release
through the existing launcher, and inspect the same `.git/swarm/swarm.db`.
Both entry points report equivalent version and protocol results. These are
selected local regressions, not a complete platform matrix.

[Browser acceptance](browser.json) passed nine interaction checks over 11 viewport
sizes with unchanged source hashes and no browser errors. A separate check of the
running dashboard confirmed the Hivewire title and masthead on desktop and phone,
with Archivo typography and the original 20 px dotted canvas grid preserved.
The shared dashboard was restarted headlessly in observation mode with its
existing address and token. Current documentation screenshots were regenerated
from the seeded demo board. Ruff, manifest verification and `git diff --check`
also passed.

- [Desktop preview](canvas-1440.png)
- [Phone preview](canvas-phone.png)
