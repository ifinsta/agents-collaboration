# agents-collaboration: Resilient Engineering Workforce

**Implementation proposal · 19 October 2026 · Target: next incremental releases after v0.4.4**
**Repository:** https://github.com/ifinsta/agents-collaboration
**Status:** original proposal baseline. An unreleased implementation and selected
source-bound trials now exist; full proposal acceptance remains open. See the
[current documentation](docs/README.md), [conformance mapping](docs/workforce-conformance.md)
and [release readiness](docs/release-candidate.md). Repository facts and compatibility
plans below describe the proposal stage; the [migration guide](docs/legacy-migration.md)
records later deliberate breaking changes. Trial results establish no productivity
or cost advantage.

## 1. Product promise

**Turn an ambiguous engineering request into a small, reasoned architecture, bounded assignments, independently checked changes, and a recoverable result—even when individual agents or developers make mistakes.**

The product is a *safety net and thinking discipline*, not a chatroom or a promise of infallible autonomy. An engineer should be able to type one goal, understand the proposed plan, approve consequential decisions, see who is doing what, interrupt safely, and receive verifiable results. A solo agent must remain useful; parallel execution is optional. The software—not a prompt alone—enforces the critical boundaries.

**Design laws:** (1) architecture before implementation; (2) outcomes before tasks; (3) one accountable owner per task; (4) no unbounded debate or work; (5) conversations are not authority; (6) evidence before integration; (7) preserve work and recover; (8) easy defaults, explicit high-risk approvals.

## 2. Repository facts verified from `main`

Reviewed: [`README.md`](https://github.com/ifinsta/agents-collaboration/blob/main/README.md), [`docs/design.md`](https://github.com/ifinsta/agents-collaboration/blob/main/docs/design.md), [`SKILL.md`](https://github.com/ifinsta/agents-collaboration/blob/main/skills/agents-collaboration/SKILL.md), [`swarm_core.py`](https://github.com/ifinsta/agents-collaboration/blob/main/skills/agents-collaboration/swarm_core.py), [`SECURITY.md`](https://github.com/ifinsta/agents-collaboration/blob/main/SECURITY.md), [`docs/agents.md`](https://github.com/ifinsta/agents-collaboration/blob/main/docs/agents.md), [`pyproject.toml`](https://github.com/ifinsta/agents-collaboration/blob/main/pyproject.toml), [CI workflow](https://github.com/ifinsta/agents-collaboration/blob/main/.github/workflows/ci.yml), and [installer](https://github.com/ifinsta/agents-collaboration/blob/main/install.py).

| Already exists in v0.4.4 | What remains to build or strengthen |
|---|---|
| Python 3.11+ standard-library core, `swarm.py` launcher, SQLite WAL in Git common directory; commands perform a sweep; optional monitor | Versioned machine-readable protocol/events; migrations and schema compatibility tests |
| Goal interrogation in **understand → backward → forward → challenge** stages; outcomes and task waves; mandatory task plans, sequential evidenced steps | Explicit lightweight architecture decision artifact and approval policy before assignment; better quality checks without ceremonial answers |
| Atomic task ownership and epochs; slots, per-task branches/worktrees, locks; single rebase/gate/CAS merge queue with crash-intent recovery | Stronger enforcement of agent privilege boundaries and evidence bound to exact commit/policy; recoverable cancellation and interventions |
| `send`, `inbox`, `ack`, questions, escalations, events, `pause`/`resume`, coordinator promotion | Typed/reliable messages, interrupt acknowledgements, reviewer dispatch, scoped memory registry, debate limits |
| `task_budget_min` with `budget_exceeded` notification; agent timeout/orphan takeover | Per-assignment **enforced** time/cost contracts, checkpoints, expiry/handoff policies; budgets currently flag but do not stop execution |
| Headless `spawn`, interactive launch/console; heterogeneous CLI adapters | Structured status/protocol for harness-neutral integrations; supervised agent restart/termination semantics |

**Limits, not assumptions:** README labels v0.4.4 *experimental*, up to five agents and one machine per pool. `SECURITY.md` states agent names are **not authenticated**, agents on that machine can access the board, stored messages are **unencrypted and not secret-scanned**, and `--unattended` can bypass CLI permission prompts when explicitly enabled. Worktrees isolate Git changes, **not credentials or operating-system processes**. The README claims 200 documented edge cases and 115 tested; CI config runs unit tests on Windows, macOS, and Linux. **This review inspected source/configuration; it did not execute the suite or verify CI outcomes independently.**

## 3. Target architecture: extend, do not rewrite

```text
Human / engineering CLI / IDE
           |
     GOAL + POLICY
           v
 Architecture & Reasoning Gate
 (context -> options -> ADR -> outcomes -> risks -> DAG)
           |
           v
 Coordinator / Scheduler -----> Time Contracts & Decision Deadlines
   |       |       |
   |       |       +---------> Incident / Independent Review
   |       +-----------------> Typed Inbox / Interrupts / Event Log
   +-------------------------> Scoped Memory Registry (verified lessons)
           |
  Worker / Reviewer Agents (adapters: CLI first)
           |
  isolated worktrees + task leases + evidence checkpoints
           |
  Git integration gate: rebase -> tests -> policy -> compare-and-swap
           |
  verified result -> retrospective -> memory candidate

SOURCE OF TRUTH: existing local SQLite/Git engine
OPTIONAL LATER: local event push / authenticated remote transport
```

**Architectural discipline:** Make the architecture brief a *small required artifact* for nontrivial goals, not a novel every-task bureaucracy. It records current system, constraints, two credible approaches where warranted, chosen approach, boundaries/interfaces, failure modes, rollout/rollback, acceptance checks, and unresolved human decisions. For a trivial fix, a short structured note is enough. Goal review should reject missing evidence and contradictory dependencies, not just empty fields.

**Authority model:** Humans own objectives, budgets and irreversible approvals. Coordinator may propose plans, assign bounded tasks, flag incidents, dispatch read-only reviewers and pause the pool. Workers act only within claimed scope. Reviewers inspect evidence but cannot self-authorize merges or sanctions. The core engine enforces task/merge rules. **Until agents have authenticated identities and isolated execution, treat these as coordination roles, not security principals.**

## 4. Single assignment lifecycle and contract

```text
GOAL_DRAFT -> ARCHITECTURE_REVIEW -> GOAL_APPROVED
     -> ASSIGNMENT_OFFERED -> ACCEPTED -> PLANNING -> RUNNING
     -> CHECKPOINTED -> SUBMITTED -> INDEPENDENT_CHECK -> MERGED -> CLOSED
                              |             |
                              +-- BLOCKED / INTERRUPTED / EXPIRED
                                      -> REPLAN / HANDOFF / HUMAN_DECISION
```

A proposed `TaskContract` includes: `id`, `goal_id`, `goal_revision`, `owner`, `epoch`, `architecture_ref`, `scope`, `dependencies`, `acceptance_checks`, `risk_level`, `deadline_at`, `active_time_limit`, `debate_limit`, `review_reserve`, optional `token/cost_limit`, `checkpoint_interval`, `extension_count`, `interrupt_policy`, `approval_requirements`, and `version`.

**Negotiation:** The coordinator offers; agent may `accept`, `counter` once with evidence, or `blocked`. After a bounded decision window, coordinator decides, splits the task, or asks the human. No silent endless renegotiation. High-risk or irreversible actions require a human-approved policy regardless of time remaining.

**Time-boxing:** Default *configurable pilot values* for medium work: 30-minute active target, 5-minute deliberation cap, 5-minute review reserve, checkpoint every 5 minutes, one justified extension. These are **initial heuristics, not performance claims**; tune using verified task history. Separate elapsed wall time, active tool time, monetary limit, and time spent blocked. A deadline requires a defined outcome—**verified**, **partially completed with handoff**, or **escalated**—not a forced claim of success.

**Enforcement:** Budget expiry stops **new coordination permissions** (claims, new integration requests), issues a cooperative interrupt, and gives a short grace period to checkpoint. A spawned process still running after a timeout requires explicit configured escalation: signal/terminate only the owned process group when safe, then mark task recoverable; never delete worktrees, uncommitted changes or unrelated processes. The current flag-only `task_budget_min` is insufficient for this contract.

## 5. Communication: inbox first, optional RTC later

Enhance the existing `messages` table with versioned typed envelopes: `message_id`, `thread_id`, `kind`, `sender`, `recipient`, `task_id`, `epoch`, `priority`, `created_at`, `expires_at`, `reply_to`, `correlation_id`, `body_ref`, `ack_state`. Kinds: `question`, `decision`, `status`, `warning`, `experience`, `review_request`, `review_result`, `interrupt`, `ack`, `handoff`.

**Reliability rules:** durable commit before delivery; ordered per-thread IDs; at-least-once notification with idempotent handling; unread cursor and acknowledgement; replay after restart; bounded payloads and retention; dead-letter/escalation for critical messages. Messages and shared memories are *untrusted inputs*, never new authority. Minimize and redact secrets before persistence.

**Interrupt protocol** (a control-plane operation, not just a chat message): `interrupt.request(target, reason, mode, deadline)` -> agent `interrupt.ack` -> persist task checkpoint, current commit/diff, locks, blockers, next step -> `interrupt.completed` or timeout -> eligible recovery/takeover. Modes: `attention` (answer question), `yield` (safe handoff), `pause` (stop new work at checkpoint), `cancel` (authorized abort). Fencing epochs must invalidate stale task claims. `pause` remains global; targeted interrupts are a proposed new capability.

**RTC:** If live push is needed, begin with local polling or an optional Unix socket/Windows-compatible local IPC that wakes clients; SQLite stays authoritative. WebSockets/WebRTC and cross-machine coordination are **out of scope for the first implementation**: low-latency conversations are not a substitute for durable delivery, replay, or authorization.

## 6. Independent oversight and the memory register

**Incident workflow:** rule-based detector or coordinator opens an incident with a specific signal; dispatch a *different* available agent to review a frozen task/commit snapshot; reviewer sees scope, policy, events, diff, checks and provenance; reviewer returns `confirmed | not_confirmed | inconclusive`, citations to evidence, and remediation suggestion. Engine may block integration when an objective gate fails; stronger interventions follow configured authorization. Suspected misconduct is not proof. Reviewer cannot modify the accused worktree or decide its own sanctions. A coordinator is reviewable too.

**Memory workflow:** Inbox conversation/retrospective -> candidate lesson -> evidence and scope review -> `verified | provisional | contradicted | stale | retired` memory -> relevant retrieval in future architecture/planning -> effectiveness measurement. Registry entry holds `id`, `scope` (task/repo; cross-repo opt-in), `claim`, `source_events`, evidence refs and commit SHAs, author, verifier, applicability, confidence, expiry, supersedes, sensitivity and version. Unverified chat never becomes a policy or instruction. Full-text search and SQLite first; embedding/vector infrastructure is deferred.

**One integrated learning loop:** When several tasks repeatedly stall on a missing fixture, agents file experience reports; the system groups evidence and proposes a preflight check; a maintainer approves a testable change; the next release measures whether it reduces recurrence. No automated self-modification of policy or code from chat alone.

## 7. Implementation plan: four small releases

| Stage | Smallest useful deliverable | Acceptance gate |
|---|---|---|
| **A. Reasoned contracts** | Schema migration; `goal architecture` brief/decision; contract offer/accept; absolute deadline, checkpoints, budgets, debate cutoff; readable `swarm explain` | Existing flows remain compatible; no indefinite negotiation; deadline produces recoverable status; Windows/Linux/macOS tests |
| **B. Reliable communication & interrupts** | Typed inbox envelopes, acknowledgement/replay/idempotency; targeted `interrupt`, `checkpoint`, `handoff`; optional local notifications | Crash/restart loses no committed critical message; stale epoch rejected; safe targeted pause does not lose edits |
| **C. Oversight & memory** | `incident open/review/resolve`, read-only reviewer brief, evidence report; `memory propose/verify/search/retire` | Forged review cannot bypass merge gate; every promoted lesson has provenance; secrets filtered; false alarms supported |
| **D. Hardening & indispensability** | JSON CLI (`--json`), protocol versioning, `swarm doctor`, operator-facing status and next-action hints, conformance/crash suite, benchmark harness | Fresh clone gets useful solo workflow; controlled multi-agent trial survives failures; no verified regression in merge safety |

Suggested delivery order is **A → B → C → D**, with each stage shippable and a backward-compatible migration. No microservice split, browser dashboard, external message broker, distributed consensus, cross-machine identity federation, or autonomous policy rewrites in the initial sequence. Integrate thin CLI adapters first; MCP can become an additional adapter later, not the source of truth.

**Developer experience:** One clear entry path—`swarm goal new`, `swarm goal review`, `swarm goal commit --assign`, `swarm console`, `swarm doctor`. Output should explain *why* a step is blocked and show a safe next command. Defaults must protect careless usage: dry-run for destructive actions, least privilege, clear diff previews, separate human approval for production-impacting steps, and visible incomplete/owed checks. Never silently convert “tests could not run” into “passed.”

## 8. Resilience invariants and tests (non-negotiable)

1. **No double ownership:** one valid claim/epoch per task; stale clients cannot alter a reassigned task.
2. **No silent loss:** committed messages, checkpoints, refs and evidence survive coordinator/agent crashes and restarts.
3. **No unsafe integration:** target ref advances only after current-head rebase, configured gates and compare-and-swap; human uncommitted changes remain untouched.
4. **No infinite loops:** every open deliberation and assignment has an expiry/escalation path; bounded retries and extensions.
5. **No false authority:** inbox/memory/reviewer output cannot override policies, approvals or role enforcement; **full security isolation requires future authenticated execution**.
6. **No fabricated success:** task close/goal close require evidenced checks; blockers and environment-specific owed checks stay visible.
7. **No blind self-healing:** recovery is idempotent, preserves artifacts and reports what changed.

**Test matrix:** concurrent claim/takeover races; SIGKILL at every state transition; DB busy/rollback; crash before/after Git ref move; message duplicate/out-of-order/replay; interrupt during gate/rebase; expired contract with live subprocess; coordinator disappearance; adversarial messages and poisoned memory; secret leakage checks; Windows PowerShell and Linux shell differences. CI should run deterministic fault injection and property/state-machine tests; report pass/fail, not just raw edge-case counts. Benchmark one agent, uncoordinated agents and coordinated agents on fixed real tasks, measuring verified completion, rework, deadline misses, human interventions, and cost. **No benchmark outcomes are claimed yet.**

## 9. Definition of done and ownership

The new architecture succeeds when an engineer can submit an ambiguous task and receive: (a) a concise, challengeable architecture plan; (b) independently owned, bounded assignments; (c) dependable communication and interrupts; (d) recoverable execution; (e) Git integration that passes evidence checks; and (f) a usable post-task learning record. A stopped, failed, or rogue agent must not destroy the team's work or silently mark it complete.

**Decision:** Build a **local-first, architecture-led, contract-bound, auditable coordination layer** on the existing engine. Keep the rigor that teaches sequential reasoning, but remove friction through good defaults, focused questions, typed communication, and automatic recovery. Resilience—not agent count or conversation volume—is the feature that will make engineers rely on it daily.
