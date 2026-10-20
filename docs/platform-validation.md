# Reproducing platform checks

Runtime evidence belongs to a specific source and scope. The latest recorded broad
runtime snapshot is [managed sessions](validation/managed-sessions/report.md):
425 passing Linux Python 3.13 cases, plus 91 passing selected Windows Python 3.12
checks and three skips (two POSIX cases and host file-symlink permission). The engine was
`b0c475f2b31f1ed2104b8445f9d6ffa31be2e0fa727aae8f73e6255c4e00f9a6`.
Both used the same frozen ZIP and retained unchanged inputs during their runs.
Subsequent working-tree edits require fresh acceptance; these records contain
no executed hosted matrix or macOS result.

## Complete candidate run

Regenerate the manifest after skill changes, then use a fresh empty output path:

```text
python -m ruff check .
python scripts/make_manifest.py --check
python scripts/validate_candidate.py --workers 2 --output PATH_TO_NEW_EVIDENCE_DIRECTORY
```

The runner requires unique discovery, disjoint exhaustive shards, terminal
per-case results and unchanged inputs. It records failed subtests against their
parent cases and retains log hashes. A partially written log, running process
or stale result directory cannot establish a pass. Documentation-only checks
and focused tests must be reported separately from a full candidate run.

## Hosted acceptance

[CI](../.github/workflows/ci.yml) is configured for Windows, Linux and macOS on
Python 3.11 and 3.13. Each job runs full discovery with two local process shards,
a 45-minute bound, lint and manifest checks. It uploads evidence even on failure.
Push/PR/manual-dispatch configuration does not prove that a workflow executed.

The `all-platform acceptance` job uses `scripts/validate_matrix.py` to require
six successful, complete reports with matching case IDs and one normalized
source fingerprint. CRLF/LF normalization permits comparison across operating
systems; raw per-run hashes still detect local mutations. Missing macOS reports,
source disagreement, cancellation and failed cases prevent acceptance.

## Local Linux container

The test image supplies Python, Git and `ps`. It introduces no production
container requirement. From PowerShell at the source root:

```powershell
docker build --build-arg PYTHON_VERSION=3.13 -f scripts/Dockerfile.validation -t workforce-validation .
docker run --rm --init --mount "type=bind,source=$PWD,target=/workspace,readonly" workforce-validation python -m unittest discover -s tests -v
```

Fixtures, installs and Git repositories live in temporary container directories.
`--init` reaps orphaned fixture children during deliberate supervisor kills.
A frozen ZIP extracted onto container-local storage is another supported test
setup; retain its hash and exact command. Mounting many source files from Windows
can be substantially slower. An ordinary unittest run does not produce the
source-bound evidence bundle; use the candidate runner when that proof is needed.
A Linux container cannot establish macOS or native Windows behavior.

## Retained history

| Snapshot | What its own record establishes |
|---|---|
| [Managed sessions](validation/managed-sessions/report.md) | Complete 425-case Linux run; 94 selected Windows cases with three skips; browser and terminal checks |
| [Documentation alignment](validation/markdown-alignment/report.md) | Later Windows installer/bus checks and a regenerated scripted session; focused scope only |
| [Legacy cleanup](validation/legacy-cleanup/report.md) | Complete 379-case Linux run; 48 selected Windows cases with two skips |
| [Adapter dispatch](validation/adapter-dispatch/report.md) | Earlier complete 374-case Linux run and 20 focused Windows checks |
| [Standard bus](validation/standard-bus/report.md) | Overlapping focused bus/communication/installer scopes at schema 11 |
| [Candidate matrix](validation/candidate-matrix/report.md) | Staged schema-10 coverage across five runtimes; not one complete command at its final source |
| [Acceptance timebox](validation/final-source-timebox/report.md) | Additional memory crash and installed-option checks; incomplete broad runs retained |
| [Candidate agent trials](validation/candidate-agent-trials/report.md) | Mixed real-agent outcomes, including failed acceptance and timeouts |
| [Earlier live trials](validation/live-agent-trials/report.md) | Small matched real-agent sample; no productivity conclusion |

Earlier startup, claim, allocation and takeover artifacts are referenced by the
[implementation history](resilient-workforce.md#verification-history) and
[transition audit](transition-crash-audit.md). Historical failures remain failures;
a later targeted repair neither erases them nor upgrades an unexecuted platform
into a pass. See [release readiness](release-candidate.md) for the remaining gates.
