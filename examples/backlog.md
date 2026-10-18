<!-- agents-collaboration:example - never imported as work -->
# Backlog (example)

This file only shows the format. The tool refuses to import it; write your own
table, or let agents create the tasks with `swarm goal`.

The coordinator keeps this table; `swarm sync` imports it. One row is one task an
agent can finish, verify and merge on its own.

- **Id**: letters, digits and `-`. It becomes the branch name.
- **Title**: what will exist when the task is done.
- **Scope**: a hint at the paths it touches (the agent declares the real scope when planning).
- **Needs**: ids that must be merged first.
- **Locks**: hotspot locks the task holds from claim to merge (see `[hotspots]` in config.toml).
- **Caps**: capabilities the agent's machine must have, for example `linux`, `docker`, `linux-docker`, `windows`, `postgres-client`.

Row order is priority order.

| Id | Title | Scope | Needs | Locks | Caps |
|---|---|---|---|---|---|
| EX-docs | Write the contributor quick start | `docs/` | — | — | |
| EX-api | Add the health endpoint | `src/api/` | — | — | |
| EX-api-tests | Cover the health endpoint with tests | `tests/api/` | EX-api | — | |
| EX-deploy | Container healthcheck for the API | `deploy/` | EX-api | — | linux-docker |
