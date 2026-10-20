# Markdown alignment review

Review date: 2026-10-20. Reviewed all 41 Markdown files present at the start,
the dashboard guide added during the review, the new documentation index and
this report: **44 Markdown files** in total. The inventory below accounts for
each document; the final machine inventory also includes this report.

## Alignment decisions

- Current contracts: unreleased 0.4.4 source, CLI protocol 2, database schema 12,
  bus/message/event versions 1. The installed release can differ from this source.
- Current instructions now distinguish executable project gates, approved outcome
  checks, task integration and goal closure receipts. All fresh claims have
  contracts; reclaim retains remaining allowances and usage lineage.
- Use cases distinguish transport receipts from interrupt acknowledgements,
  read the current epoch, preserve takeover plan/start gates and avoid a second
  handoff after completed yield/cancel. Examples identify omitted implementation,
  template fields, actual evidence and Git commits as prerequisites.
- The standard bus remains SQLite-authoritative. Wake signals and hooks are
  advisory; consumer receipts, control operations and external effects have
  different authority and retry requirements.
- The browser HTTP interface is read-only; its default server loop still sweeps
  liveness/recovery state. The module is now in the source manifest file list.
  Inclusion and file installation do not establish full browser/platform acceptance.
- The simulation was regenerated through its generator with scripted-agent and
  local-source installation wording. Its companion SVGs come from the same run.
- Proposals, transition investigations and seven historical validation reports
  explicitly identify their snapshot scope. All seven reports retain the same
  numeric tokens, hashes and metrics; published changelog sections are unchanged.
  No test count, productivity advantage or hosted CI result was invented.

## Verification and limits

[Installer/bus output](installer.txt) records **20 passing tests** on Windows,
Python 3.12.2: all 19 installer/release tests and the installed bus-schema test.
[Simulation output](simulation.txt) records successful execution of every scripted
milestone and generation of the transcript and matching console figures.
[Selected installer inputs](installer.json) and [simulation inputs](simulation.json)
were unchanged before/after their respective runs; the exact recorded file lists
are in those JSON files. Both used engine SHA-256
`cab0e158873e4fcaae69ba6b6735a0e5d31cca6f248d8be5458214ee0c1d6576`.

[Final checks and inventory](results.json) record UTF-8 document inventory,
local file/heading links, complete command examples and routine source checks.
Command checks use the current argparse parser and mirror the CLI's global
`--json` normalization **without executing board operations**. Schematic commands
are explicitly excluded, as are historical/generated transcripts. Syntax success
does not prove that an example's task state or repository-specific evidence exists.

The engine/dashboard source changed independently during the documentation review;
this task did not modify those runtime modules. A further dashboard-module edit
after the focused runs required another manifest refresh; its hash differs from
the test records. These focused checks do not validate that later edit or replace
the outstanding consolidated Windows/Linux/macOS candidate acceptance, broader
transition/adapter coverage, or representative usefulness trials. The earlier
379-case Linux run remains a separate [broad snapshot](../legacy-cleanup/report.md).
No release, remote publication or hosted CI execution is claimed here.

## File-by-file review

| File | Purpose | Review outcome |
|---|---|---|
| [.github/ISSUE_TEMPLATE/bug_report.md](../../../.github/ISSUE_TEMPLATE/bug_report.md) | Governance/contribution guidance | Aligned |
| [.github/ISSUE_TEMPLATE/edge_case.md](../../../.github/ISSUE_TEMPLATE/edge_case.md) | Governance/contribution guidance | Reviewed; retained |
| [.github/PULL_REQUEST_TEMPLATE.md](../../../.github/PULL_REQUEST_TEMPLATE.md) | Governance/contribution guidance | Aligned |
| [agents-collaboration-resilient-workforce-design.md](../../../agents-collaboration-resilient-workforce-design.md) | Original proposal | Aligned |
| [CHANGELOG.md](../../../CHANGELOG.md) | Development/release history | Aligned |
| [CODE_OF_CONDUCT.md](../../../CODE_OF_CONDUCT.md) | Governance/contribution guidance | Reviewed; retained |
| [CONTRIBUTING.md](../../../CONTRIBUTING.md) | Governance/contribution guidance | Aligned |
| [docs/agents.md](../../../docs/agents.md) | Current guidance | Aligned |
| [docs/completion-evidence.md](../../../docs/completion-evidence.md) | Current guidance | Aligned |
| [docs/design.md](../../../docs/design.md) | Current guidance | Aligned |
| [docs/legacy-migration.md](../../../docs/legacy-migration.md) | Current guidance | Aligned |
| [docs/platform-validation.md](../../../docs/platform-validation.md) | Current guidance | Aligned |
| [docs/process-supervision.md](../../../docs/process-supervision.md) | Current guidance | Aligned |
| [docs/README.md](../../../docs/README.md) | Current guidance | New navigation |
| [docs/release-candidate.md](../../../docs/release-candidate.md) | Current guidance | Aligned |
| [docs/resilient-workforce.md](../../../docs/resilient-workforce.md) | Current guidance | Aligned |
| [docs/simulation.md](../../../docs/simulation.md) | Generated workflow | Aligned |
| [docs/transition-crash-audit.md](../../../docs/transition-crash-audit.md) | Current guidance | Aligned |
| [docs/usage-budgets.md](../../../docs/usage-budgets.md) | Current guidance | Aligned |
| [docs/validation/adapter-dispatch/report.md](../../../docs/validation/adapter-dispatch/report.md) | Historical source report | Aligned |
| [docs/validation/candidate-agent-trials/report.md](../../../docs/validation/candidate-agent-trials/report.md) | Historical source report | Aligned |
| [docs/validation/candidate-matrix/report.md](../../../docs/validation/candidate-matrix/report.md) | Historical source report | Aligned |
| [docs/validation/final-source-timebox/report.md](../../../docs/validation/final-source-timebox/report.md) | Historical source report | Aligned |
| [docs/validation/legacy-cleanup/report.md](../../../docs/validation/legacy-cleanup/report.md) | Historical source report | Aligned |
| [docs/validation/live-agent-trials/report.md](../../../docs/validation/live-agent-trials/report.md) | Historical source report | Aligned |
| [docs/validation/standard-bus/report.md](../../../docs/validation/standard-bus/report.md) | Historical source report | Aligned |
| [docs/web-dashboard.md](../../../docs/web-dashboard.md) | Current guidance | Reviewed; arrived during audit |
| [docs/workforce-benchmark.md](../../../docs/workforce-benchmark.md) | Current guidance | Aligned |
| [docs/workforce-conformance.md](../../../docs/workforce-conformance.md) | Current guidance | Aligned |
| [examples/backlog.md](../../../examples/backlog.md) | Current guidance | Aligned |
| [INSTALL.md](../../../INSTALL.md) | Current guidance | Aligned |
| [README.md](../../../README.md) | Current guidance | Aligned |
| [SECURITY.md](../../../SECURITY.md) | Governance/contribution guidance | Aligned |
| [skills/agents-collaboration/BUS.md](../../../skills/agents-collaboration/BUS.md) | Installed contract/reference | Aligned |
| [skills/agents-collaboration/EDGE-CASES.md](../../../skills/agents-collaboration/EDGE-CASES.md) | Installed contract/reference | Aligned |
| [skills/agents-collaboration/SKILL.md](../../../skills/agents-collaboration/SKILL.md) | Installed contract/reference | Aligned |
| [usecases/01-parallel-feature-delivery.md](../../../usecases/01-parallel-feature-delivery.md) | Current workflow outline | Aligned |
| [usecases/02-crash-recovery-takeover.md](../../../usecases/02-crash-recovery-takeover.md) | Current workflow outline | Aligned |
| [usecases/03-mixed-agent-team.md](../../../usecases/03-mixed-agent-team.md) | Current workflow outline | Aligned |
| [usecases/04-solo-agent-safety-net.md](../../../usecases/04-solo-agent-safety-net.md) | Current workflow outline | Aligned |
| [usecases/05-interrupt-and-handoff.md](../../../usecases/05-interrupt-and-handoff.md) | Current workflow outline | Aligned |
| [usecases/06-incident-review-and-lessons.md](../../../usecases/06-incident-review-and-lessons.md) | Current workflow outline | Aligned |
| [usecases/README.md](../../../usecases/README.md) | Current workflow outline | Aligned |
| [docs/validation/markdown-alignment/report.md](report.md) | Review evidence | Authored and checked |
