# Workforce proposal conformance

This maps the [original proposal](../agents-collaboration-resilient-workforce-design.md)
to the current source. It is an evidence map, not a claim that every acceptance
gate passed. Source remains unreleased. See the [documentation index](README.md),
[latest recorded broad runtime snapshot](validation/managed-sessions/report.md) and
[release readiness](release-candidate.md). Later working-tree changes require
fresh acceptance.

| Requirement | Implementation / evidence | Limit or remaining gate |
|---|---|---|
| Goal -> outcomes -> architecture -> tasks -> verification | Goal commands, architecture/contract tests, generated simulation | Real-team usefulness and ease of use need broader trials |
| Local engine; solo useful; parallel optional | Standard-library core, Git/SQLite, installer and solo/multi-worker harness | One machine; POSIX ownership requires system ps |
| Source-backed architecture and approval | Revision-bound brief/evidence checks in test_contracts.py | High-risk approval is a local human role, not authenticated identity |
| One accountable assignment and scope | Atomic claims, epochs, contracts and checked plan/submit/merge paths | Arbitrary filesystem edits remain outside engine enforcement |
| Bounded contracts and negotiation | Every fresh claim has terms; explicit offer/accept/one counter/extension | Configured defaults are heuristics; new terms do not prove useful deadlines |
| Retained deadlines and usage on recovery | Reclaim/takeover tests; clock and ledger lineage checks | Further clock/control and failure interleavings remain to audit |
| Recoverable expiry and handoff | Checkpoints, fenced interrupts and retained branches/worktrees | Recovery can require human inspection; no guessed cessation |
| Owned process escalation | Headless and foreground owned jobs/groups, terminal/startup crash tests | Cooperative by default; deliberate group escape is not sandboxed |
| Durable communication and replay | Bus v1, leases, receipt-only ack, retries, idempotency keys, dead letters | At-least-once attempts require consumers; external effects need deduplication |
| Timely local notification | Supervisor relay, loopback wake hints, fallback, bounded configured hooks | Vendor-specific context injection needs a bridge; no universal request preemption |
| Independent incident review | Frozen revisions, different reviewer, citations and separate decision | Read-only reviewer is a coordination role, not filesystem isolation |
| Scoped lessons and provenance | Independent verification, source refs, expiry, search, provisional imports | Utility observations are self-reported; causal learning gains are unproven |
| Data minimization and no authority from chat | Credential-form filters; message/memory/control tests | Arbitrary secrets are not comprehensively detected; storage is unencrypted |
| Checked integration | Rebase, final-commit gates, policy/ownership/CAS checks and retained intent | Weak configured checks cannot prove semantic completeness |
| Receipt-bound completion and goal closure | Executable approved checks, retained checkouts, owed-resolution history | Historical closures stay unverified; foreign-platform checks need actual evidence |
| Harness-neutral status | CLI protocol 2, result-only typed JSON, version-1 events, diagnostics | Interactive views have JSON restrictions; old protocol clients must migrate |
| Bounded accounting | Contract time, measured owned-command time, numeric/native usage imports | Uninstrumented calls and authenticated provider billing are not observed |
| Safe uncertainty and cleanup | Unknown states, source pins, allocation/verification reconciliation | Human attestation is distinct from observed process termination |
| Every transition's crash branches | Named transaction hooks, selected real CLI/OS kills and seeded races | Full external-effect/branch enumeration remains incomplete |
| Cross-platform acceptance | Recorded 425-case Linux run and 94 selected Windows cases; six-job CI configuration | Latest records have no hosted matrix/macOS result; later source edits are unaccepted |
| Fixed comparative real-agent trials | Retained solo/uncoordinated/coordinated trials and immutable verifier | Mixed outcomes; no established productivity or cost improvement |
| Clear incremental delivery | Schemas through 12, forward migration, CLI v2 cleanup guide | Runtime compatibility was intentionally revised; publication remains pending |

## Acceptance still open

1. Execute consolidated Windows/Linux/macOS acceptance on the actual candidate
   source and packaging. A configured matrix does not establish execution.
2. Extend the [transition audit](transition-crash-audit.md) beyond selected
   commits to remaining Git, filesystem, clock, SQLite and process branches.
3. Broaden real native-adapter/hook and usage coverage where promised. Preserve
   missing accounting and unavailable providers as unknown/failed outcomes.
4. Demonstrate usefulness on representative real projects, measuring verified
   completion, rework and developer intervention against suitable alternatives.
5. Complete installed-browser/native-platform acceptance. The module is in the
   manifest and latest local source checks, with desktop/phone session-view
   coverage; this does not establish the complete required platform matrix.
6. Review the requirement/evidence mapping and prepare publication after required
   checks. No local trial or raw test count completes the original goal alone.

## Resilience claims and their boundaries

The engine checks ownership, preserves durable coordination records, binds
integration to observed checks and retains uncertain work. Those claims apply to
its checked operations under the trusted-local model. They do not establish
infallible storage, authenticated identity, OS isolation, comprehensive secret
scanning or freedom from all agent mistakes.

The [latest recorded broad snapshot](validation/managed-sessions/report.md) retains
passing runs at its own source. Earlier failed development attempts remain in the
source-specific history. Older source-specific reports and
counterexamples remain linked from the [platform guide](platform-validation.md)
and [implementation history](resilient-workforce.md#verification-history). Historical
unconfigured merges and closures without proof stay labeled; new integration
requires executable gates.
