# Unreleased source and acceptance

The working source identifies itself as **0.4.4**. It uses CLI protocol **2**,
database schema **13**, and bus/message/event versions **1**. It has not been
published as a release by this implementation work. The default remote installer
selects its configured release ref; it does not install an unpublished working tree.

Current behavior is documented in the [skill](../skills/agents-collaboration/SKILL.md),
[implementation guide](resilient-workforce.md) and [migration guide](legacy-migration.md).
Fresh claims receive contracts, engine launches are supervised, message delivery
requires bus receipts, and new merges require configured executable gates.

## Recorded validation

The subsequent [pre-push checks](validation/github-push/report.md) found and
fixed a POSIX terminal-output defect and an older liveness-fixture race. They
retain both complete-run failures and the passing focused regressions. Final
combined-source platform acceptance remains pending hosted CI.

The [latest recorded broad runtime snapshot](validation/managed-sessions/report.md) has:

- 425 passing Linux Python 3.13 cases from one complete discovery;
- 91 passing selected Windows Python 3.12 cases, two POSIX-only skips and one
  host-permission skip for creating a file symlink;
- one frozen source ZIP, unchanged inputs within both runs and retained per-case
  coverage; the Linux runner verified exact discovery coverage;
- separate desktop/phone browser and real Windows/Linux terminal checks.

Its engine SHA-256 is
`b0c475f2b31f1ed2104b8445f9d6ffa31be2e0fa727aae8f73e6255c4e00f9a6`.
These results establish that snapshot's local scope. Later edits require fresh
acceptance. Older reports retain their original failures, case counts and hashes;
counts from different snapshots cannot be added to claim a complete current pass.

## Acceptance still needed

- Execute the full Windows/Linux/macOS matrix against the candidate being
  published. Hosted configuration is not an executed result.
- Finish the proposal's transition/branch audit beyond selected crash windows.
- Validate native adapters on actual installed/authenticated CLIs where claimed;
  recorded help compatibility does not establish successful live work.
- Validate the newly included browser dashboard from a real source installation
  and the required platforms. Its manifest inclusion is separate from acceptance.
- Keep unmeasured usage unknown and preserve benchmark failures. Real-team
  productivity, authenticated billing and comprehensive external-call metering
  remain unestablished.
- Review the [conformance mapping](workforce-conformance.md) before declaring the
  original proposal complete. Distributed identity and OS sandboxing remain out
  of scope for this local implementation.

## Reproduce and publish

Use a disposable checkout/repository and a fresh evidence directory:

```text
python -m ruff check .
python scripts/make_manifest.py --check
python scripts/validate_candidate.py --workers 2 --output PATH_TO_NEW_EVIDENCE_DIRECTORY
```

For a local-source installation, replace both paths with reviewed source and
an existing target repository:

```text
python install.py --source PATH_TO_SOURCE --project PATH_TO_PROJECT --all
```

Keep source unchanged during validation and report each result's actual scope.
The [platform guide](platform-validation.md) describes the six-report CI gate.
Publication follows [CONTRIBUTING.md](../CONTRIBUTING.md): settle required checks,
prepare the version/ref and manifest, then publish through the authorized release
workflow. No release or hosted pass follows from these local records alone.
