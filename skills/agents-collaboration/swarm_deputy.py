"""Deterministic operations scout, durable attention queue and bounded deputy leases.

The scout reads the existing SQLite board and records what needs attention. It never infers misconduct from an
unread message, a missing heartbeat or an incident signal. A deputy is an ordinary live agent holding a time-bound
delegation for named subjects; the coordinator and the existing election remain the only coordination authority.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

import swarm_core as core

KINDS = (
    "event",
    "message",
    "question",
    "contract",
    "task",
    "verification",
    "execution",
    "incident",
    "merge",
    "agent",
    "interrupt",
)
SEVERITIES = ("P0", "P1", "P2", "P3")
OPEN_STATUSES = ("new", "claimed", "investigating", "proposed_action", "escalated", "reopened")
TERMINAL_STATUSES = ("resolved", "false_alarm", "expired")
CAPABILITIES = (
    "attention.claim",
    "attention.report",
    "attention.escalate",
    "incident.propose",
    "interrupt.request",
)
DEFAULT_CAPABILITIES = ("attention.claim", "attention.report", "attention.escalate")

DEFAULTS = {
    "enabled": True,
    "critical_sla_min": 5,
    "queue_sla_min": 30,
    "stale_min": 10,
    "activation_min_urgent": 2,
    "activation_min_blockers": 3,
    "lease_min": 30,
    "claim_lease_sec": 300,
    "min_active_min": 5,
    "cooldown_min": 10,
    "max_scan_items": 200,
}


class DeputyError(core.SwarmError):
    pass


class DelegationViolation(DeputyError):
    """A lease exists but does not cover this subject; the caller must revoke it outside the action transaction."""

    def __init__(self, message: str, delegation: int):
        super().__init__(message)
        self.delegation = delegation


def config(sw) -> dict:
    merged = dict(DEFAULTS)
    loaded = sw.config.get("deputy") or {}
    if isinstance(loaded, dict):
        merged.update({k: v for k, v in loaded.items() if k in DEFAULTS})
    return merged


def _settings(sw) -> dict:
    return config(sw)


def _now():
    return core.utcnow()


def _age_min(ts, now) -> float | None:
    moment = core.parse(ts)
    return None if moment is None else max(0.0, (now - moment).total_seconds() / 60.0)


def _loads(value, fallback):
    try:
        parsed = json.loads(value) if value else fallback
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (TypeError, ValueError):
        return fallback


def _severity_rank(value: str) -> int:
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(value, 9)


def _task_for(subject_ref: str) -> str | None:
    return subject_ref.split(":", 1)[1] if subject_ref.startswith("task:") else None


def _history(sw, item: int, actor: str | None, old: str | None, new: str, note: str, evidence: str = "") -> None:
    sw.db.execute(
        "INSERT INTO attention_history(attention,at,actor,old_status,new_status,note,evidence) VALUES(?,?,?,?,?,?,?)",
        (item, core.iso(), actor, old, new, core.redact_text(note), core.redact_text(evidence)),
    )


def _item(sw, item_id: int):
    row = sw.db.execute("SELECT * FROM attention_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        raise DeputyError(f"There is no attention item {item_id}. `hivewire attention list` shows the open queue.")
    return row


def _event(sw, kind: str, actor: str | None, item, detail: str) -> None:
    sw.event(kind, actor, _task_for(item["subject_ref"]), detail)


# ----------------------------------------------------------------------------------------------- the scout


class _Signals:
    def __init__(self, sw, now):
        self.sw = sw
        self.now = now
        self.settings = _settings(sw)
        self.items: list[dict] = []
        self.keys: set[str] = set()

    def add(
        self,
        kind: str,
        severity: str,
        subject_ref: str,
        evidence_ref: str,
        summary: str,
        dedupe_key: str,
        due_at: str | None = None,
        source_severity: str | None = None,
        details: dict | None = None,
    ) -> None:
        if dedupe_key in self.keys:
            return
        self.keys.add(dedupe_key)
        self.items.append(
            {
                "kind": kind,
                "severity": severity,
                "subject_ref": subject_ref,
                "evidence_ref": evidence_ref,
                "summary": core.redact_text(summary),
                "dedupe_key": dedupe_key,
                "due_at": due_at,
                "source_severity": source_severity,
                "details": core.redacted_data(details or {}),
            }
        )


def _scan_messages(signals: _Signals) -> None:
    sw, now, cfg = signals.sw, signals.now, signals.settings
    rows = sw.db.execute(
        "SELECT m.*, (SELECT COUNT(*) FROM message_recipients r WHERE r.msg=m.id AND r.acked_at IS NULL) AS waiting "
        "FROM messages m WHERE m.ack_state IN ('pending','dead_letter') ORDER BY m.id"
    ).fetchall()
    for m in rows:
        age = _age_min(m["created_at"], now) or 0.0
        if m["ack_state"] == "dead_letter":
            signals.add(
                "message",
                "P0",
                f"message:{m['id']}",
                f"sqlite:messages/{m['id']}",
                f"Message #{m['id']} from {m['sender']} expired as a critical dead letter; {m['waiting']} recipient(s) never acknowledged it.",
                f"message:{m['id']}:dead_letter",
                m["expires_at"],
                source_severity="critical",
                details={"sender": m["sender"], "recipient": m["recipient"], "waiting": m["waiting"], "age_min": round(age)},
            )
        elif m["waiting"] and m["priority"] == "critical" and age >= cfg["critical_sla_min"]:
            signals.add(
                "message",
                "P1",
                f"message:{m['id']}",
                f"sqlite:messages/{m['id']}",
                f"Critical message #{m['id']} from {m['sender']} is still unacknowledged after {round(age)} min.",
                f"message:{m['id']}:critical_unacked",
                m["expires_at"],
                source_severity="critical",
                details={"sender": m["sender"], "recipient": m["recipient"], "waiting": m["waiting"], "age_min": round(age)},
            )
        elif m["waiting"] and m["priority"] == "high" and age >= cfg["queue_sla_min"]:
            signals.add(
                "message",
                "P2",
                f"message:{m['id']}",
                f"sqlite:messages/{m['id']}",
                f"High-priority message #{m['id']} from {m['sender']} has waited {round(age)} min for acknowledgement.",
                f"message:{m['id']}:high_unacked",
                m["expires_at"],
                source_severity="high",
                details={"sender": m["sender"], "recipient": m["recipient"], "waiting": m["waiting"], "age_min": round(age)},
            )


def _scan_questions(signals: _Signals) -> None:
    sw, now, cfg = signals.sw, signals.now, signals.settings
    escalate_min = sw.config["swarm"]["question_escalate_min"]
    for q in sw.db.execute("SELECT * FROM questions WHERE answer IS NULL AND waived=0 ORDER BY id").fetchall():
        age = _age_min(q["created_at"], now) or 0.0
        due = core.iso(core.parse(q["created_at"]) + timedelta(minutes=escalate_min))
        if q["critical"] and (q["escalated"] or age >= escalate_min):
            signals.add(
                "question",
                "P1",
                f"question:{q['id']}",
                f"sqlite:questions/{q['id']}",
                f"Critical question Q{q['id']} from {q['asker']} to {q['to_whom']} is unanswered after {round(age)} min.",
                f"question:{q['id']}:critical_open",
                due,
                source_severity="critical",
                details={"task": q["task"], "asker": q["asker"], "to": q["to_whom"], "age_min": round(age)},
            )
        elif q["to_whom"] == core.HUMAN and age >= cfg["queue_sla_min"]:
            signals.add(
                "question",
                "P2",
                f"question:{q['id']}",
                f"sqlite:questions/{q['id']}",
                f"Question Q{q['id']} is waiting for a human decision after {round(age)} min.",
                f"question:{q['id']}:human_pending",
                core.iso(core.parse(q["created_at"]) + timedelta(minutes=cfg["queue_sla_min"])),
                details={"task": q["task"], "asker": q["asker"], "age_min": round(age)},
            )


def _scan_contracts(signals: _Signals) -> None:
    sw, now, cfg = signals.sw, signals.now, signals.settings
    rows = sw.db.execute(
        "SELECT c.* FROM task_contracts c WHERE c.id=(SELECT MAX(latest.id) FROM task_contracts latest WHERE latest.task=c.task) "
        "AND c.state IN ('offered','countered','accepted','active','expired') ORDER BY c.id"
    ).fetchall()
    for c in rows:
        terms = _loads(c["terms"], {})
        deadline = terms.get("deadline_at")
        if c["state"] == "active" and c["checkpoint_due"]:
            signals.add(
                "contract",
                "P1",
                f"task:{c['task']}",
                f"sqlite:task_contracts/{c['id']}",
                f"{c['task']} has an overdue contract checkpoint (owner {c['owner']}).",
                f"contract:{c['id']}:checkpoint",
                c["checkpoint_at"] or c["accepted_at"],
                details={"task": c["task"], "owner": c["owner"], "contract": c["id"]},
            )
        if c["state"] == "expired" and c["grace_until"] and now >= core.parse(c["grace_until"]) and c["recovery_notified"]:
            signals.add(
                "contract",
                "P1",
                f"task:{c['task']}",
                f"sqlite:task_contracts/{c['id']}",
                f"{c['task']} checkpoint grace elapsed; work is retained and awaits coordinator recovery.",
                f"contract:{c['id']}:recovery",
                c["grace_until"],
                details={"task": c["task"], "owner": c["owner"], "contract": c["id"]},
            )
        if c["state"] == "accepted" and c["decision_at"] and now >= core.parse(c["decision_at"]):
            signals.add(
                "contract",
                "P1",
                f"task:{c['task']}",
                f"sqlite:task_contracts/{c['id']}",
                f"{c['task']} offer to {c['owner']} was accepted but not claimed before its decision window closed.",
                f"contract:{c['id']}:unclaimed",
                c["decision_at"],
                details={"task": c["task"], "owner": c["owner"], "contract": c["id"]},
            )
        if c["state"] == "active" and c["blocked_at"] and (_age_min(c["blocked_at"], now) or 0) >= cfg["queue_sla_min"]:
            signals.add(
                "contract",
                "P2",
                f"task:{c['task']}",
                f"sqlite:task_contracts/{c['id']}",
                f"{c['task']} has been declared blocked by {c['owner']} for {round(_age_min(c['blocked_at'], now) or 0)} min.",
                f"contract:{c['id']}:blocked:{c['blocked_at']}",
                None,
                details={"task": c["task"], "owner": c["owner"], "contract": c["id"]},
            )
        if c["state"] == "active" and deadline:
            moment = core.parse(deadline)
            if moment is not None:
                left = (moment - now).total_seconds() / 60.0
                if 0 <= left <= cfg["queue_sla_min"]:
                    signals.add(
                        "contract",
                        "P2",
                        f"task:{c['task']}",
                        f"sqlite:task_contracts/{c['id']}",
                        f"{c['task']} contract deadline is {round(left)} min away (owner {c['owner']}).",
                        f"contract:{c['id']}:expiring:{deadline}",
                        deadline,
                        details={"task": c["task"], "owner": c["owner"], "contract": c["id"], "minutes_left": round(left)},
                    )
                elif left < 0:
                    signals.add(
                        "contract",
                        "P1",
                        f"task:{c['task']}",
                        f"sqlite:task_contracts/{c['id']}",
                        f"{c['task']} contract deadline passed {round(-left)} min ago.",
                        f"contract:{c['id']}:breached:{deadline}",
                        deadline,
                        details={"task": c["task"], "owner": c["owner"], "contract": c["id"]},
                    )


def _scan_tasks(signals: _Signals) -> None:
    sw, now, cfg = signals.sw, signals.now, signals.settings
    tasks = sw.db.execute("SELECT * FROM tasks WHERE removed=0 ORDER BY ord,id").fetchall()
    done = {t["id"] for t in tasks if t["state"] == "done"}
    for t in tasks:
        epoch = t["epoch"] or 0
        if t["state"] == "orphaned":
            signals.add(
                "task",
                "P1",
                f"task:{t['id']}",
                f"sqlite:tasks/{t['id']}",
                f"{t['id']} lost its holder and is orphaned; its branch and worktree are preserved.",
                f"task:{t['id']}:orphaned:{epoch}",
                None,
                details={"task": t["id"], "state": t["state"], "epoch": epoch, "assignee": t["assignee"]},
            )
        if t["state"] in ("merge_blocked", "gates_failed", "expired"):
            signals.add(
                "task",
                "P1",
                f"task:{t['id']}",
                f"sqlite:tasks/{t['id']}",
                f"{t['id']} is {t['state'].replace('_', ' ')}; verification or a coordinator decision is outstanding.",
                f"task:{t['id']}:{t['state']}:{epoch}",
                None,
                details={"task": t["id"], "state": t["state"], "epoch": epoch, "assignee": t["assignee"]},
            )
        if t["state"] == "ready_to_merge" and (_age_min(t["updated_at"], now) or 0) >= cfg["queue_sla_min"]:
            signals.add(
                "merge",
                "P2",
                f"task:{t['id']}",
                f"sqlite:tasks/{t['id']}",
                f"{t['id']} has awaited merge for {round(_age_min(t['updated_at'], now) or 0)} min.",
                f"task:{t['id']}:awaiting_merge:{epoch}:{t['updated_at']}",
                None,
                details={"task": t["id"], "state": t["state"], "epoch": epoch, "assignee": t["assignee"]},
            )
        if t["state"] == "open":
            waiting = [n for n in _loads(t["needs"], []) if n not in done]
            if waiting and (_age_min(t["updated_at"] or t["created_at"], now) or 0) >= cfg["queue_sla_min"]:
                signals.add(
                    "task",
                    "P2",
                    f"task:{t['id']}",
                    f"sqlite:tasks/{t['id']}",
                    f"{t['id']} is blocked on {', '.join(waiting)}.",
                    f"task:{t['id']}:blocked_deps:{','.join(sorted(waiting))}",
                    None,
                    details={"task": t["id"], "waiting": waiting, "state": t["state"]},
                )
        if t["state"] == "interrupted":
            signals.add(
                "task",
                "P2",
                f"task:{t['id']}",
                f"sqlite:tasks/{t['id']}",
                f"{t['id']} is interrupted; a checkpoint or handoff decision is outstanding.",
                f"task:{t['id']}:interrupted:{epoch}",
                None,
                details={"task": t["id"], "state": t["state"], "epoch": epoch, "assignee": t["assignee"]},
            )


def _scan_verifications(signals: _Signals) -> None:
    sw, now, cfg = signals.sw, signals.now, signals.settings
    for r in sw.db.execute(
        "SELECT * FROM verification_runs WHERE state IN ('failed','unknown','running') ORDER BY rowid"
    ).fetchall():
        if not r["subject"]:
            subject = f"verification:{r['id']}"
        elif r["kind"] == "goal":
            subject = f"goal:{r['subject']}"
        else:
            subject = f"task:{r['subject']}"
        owner_ref = {"goal" if r["kind"] == "goal" else "task": r["subject"]} if r["subject"] else {}
        if r["state"] == "failed":
            signals.add(
                "verification",
                "P1",
                subject,
                f"sqlite:verification_runs/{r['id']}",
                f"Verification {r['id']} failed for {r['kind']} on {r['subject']}; inspect the receipt, do not assume misconduct.",
                f"verification:{r['id']}:failed",
                r["ended_at"],
                source_severity="failed",
                details={"receipt": r["id"], **owner_ref, "kind": r["kind"], "detail": r["detail"]},
            )
        elif r["state"] == "unknown" and (_age_min(r["heartbeat_at"] or r["started_at"], now) or 0) >= cfg["stale_min"]:
            signals.add(
                "verification",
                "P1",
                subject,
                f"sqlite:verification_runs/{r['id']}",
                f"Verification {r['id']} is in state unknown; the receipt must be reconciled before its result is trusted.",
                f"verification:{r['id']}:unknown",
                r["heartbeat_at"] or r["started_at"],
                details={"receipt": r["id"], **owner_ref, "kind": r["kind"]},
            )
        elif r["state"] == "running" and (_age_min(r["heartbeat_at"] or r["started_at"], now) or 0) >= cfg["stale_min"]:
            signals.add(
                "verification",
                "P2",
                subject,
                f"sqlite:verification_runs/{r['id']}",
                f"Verification {r['id']} has not reported a heartbeat for {round(_age_min(r['heartbeat_at'] or r['started_at'], now) or 0)} min.",
                f"verification:{r['id']}:stale_running",
                None,
                details={"receipt": r["id"], **owner_ref, "kind": r["kind"]},
            )


def _scan_executions(signals: _Signals) -> None:
    sw, now, cfg = signals.sw, signals.now, signals.settings
    for r in sw.db.execute(
        "SELECT * FROM executions WHERE state NOT IN ('exited','terminated','failed','reconciled','abandoned') ORDER BY started_at,id"
    ).fetchall():
        subject = f"task:{r['task']}" if r["task"] else f"execution:{r['id']}"
        last = r["heartbeat_at"] or r["started_at"]
        if r["state"] == "unknown":
            signals.add(
                "execution",
                "P1",
                subject,
                f"sqlite:executions/{r['id']}",
                f"Execution {r['id']} owned by {r['agent']} is in state unknown; prove it stopped before reuse.",
                f"execution:{r['id']}:unknown",
                None,
                details={"execution": r["id"], "agent": r["agent"], "task": r["task"], "detail": r["detail"]},
            )
        elif (_age_min(last, now) or 0) >= cfg["stale_min"]:
            signals.add(
                "execution",
                "P1",
                subject,
                f"sqlite:executions/{r['id']}",
                f"Execution {r['id']} owned by {r['agent']} is {r['state']} with no heartbeat for {round(_age_min(last, now) or 0)} min.",
                f"execution:{r['id']}:stale:{r['state']}",
                None,
                details={"execution": r["id"], "agent": r["agent"], "task": r["task"], "state": r["state"]},
            )
    failures = sw.db.execute(
        "SELECT agent, COUNT(*) AS n FROM executions WHERE state='failed' AND started_at>=? GROUP BY agent HAVING n>=3",
        (core.iso(now - timedelta(hours=24)),),
    ).fetchall()
    for row in failures:
        signals.add(
            "agent",
            "P2",
            f"agent:{row['agent']}",
            f"sqlite:executions?agent={row['agent']}&state=failed",
            f"{row['agent']} has {row['n']} failed executions in the last 24 h; inspect the evidence before drawing conclusions.",
            f"agent:{row['agent']}:failures:{now.date().isoformat()}",
            None,
            details={"agent": row["agent"], "failures": row["n"]},
        )


def _scan_incidents(signals: _Signals) -> None:
    sw, now = signals.sw, signals.now
    for r in sw.db.execute(
        "SELECT * FROM incidents WHERE state IN ('open','reviewed','timed_out','needs_human') ORDER BY id"
    ).fetchall():
        review_due = r["deadline_at"] and now >= core.parse(r["deadline_at"])
        if r["state"] in ("timed_out", "needs_human") or (r["state"] in ("open", "reviewed") and review_due):
            signals.add(
                "incident",
                "P1",
                f"task:{r['task']}",
                f"sqlite:incidents/{r['id']}",
                f"Incident I{r['id']} on {r['task']} is {r['state']} at revision {r['revision']}; evidence is frozen and a decision is outstanding.",
                f"incident:{r['id']}:{r['state']}:{r['revision']}",
                r["deadline_at"],
                details={"incident": r["id"], "task": r["task"], "state": r["state"], "revision": r["revision"]},
            )


def _scan_agents(signals: _Signals) -> None:
    sw, now, cfg = signals.sw, signals.now, signals.settings
    for a in sw.db.execute("SELECT * FROM agents WHERE state='offline' AND offline_reason='silent' ORDER BY name").fetchall():
        age = _age_min(a["offline_at"], now) or 0
        if age <= cfg["queue_sla_min"]:
            signals.add(
                "agent",
                "P2",
                f"agent:{a['name']}",
                f"sqlite:agents/{a['name']}",
                f"{a['name']} stopped heartbeating {round(age)} min ago; this is a liveness signal, not proof of a dead process.",
                f"agent:{a['name']}:silent:{a['offline_at']}",
                a["offline_at"],
                details={"agent": a["name"], "task": a["task"], "offline_at": a["offline_at"]},
            )
    for a in sw.db.execute(
        "SELECT a.name,a.task,a.reviewing,i.state AS incident_state,r.reviewer "
        "FROM agents a LEFT JOIN incidents i ON i.id=a.reviewing "
        "LEFT JOIN incident_reviews r ON r.incident=i.id AND r.revision=i.revision "
        "WHERE a.reviewing IS NOT NULL ORDER BY a.name"
    ).fetchall():
        if a["incident_state"] == "open" and a["reviewer"] == a["name"] and not a["task"]:
            continue
        signals.add(
            "incident",
            "P2",
            f"incident:{a['reviewing']}",
            f"sqlite:agents/{a['name']}",
            f"{a['name']} holds an inconsistent review reservation for I{a['reviewing']} "
            f"({a['incident_state'] or 'missing incident'}, reviewer {a['reviewer'] or 'none'}, task {a['task'] or 'none'}); "
            "a human must settle it without inferring misconduct.",
            f"review_conflict:{a['name']}:{a['reviewing']}",
            None,
            details={"agent": a["name"], "incident": a["reviewing"], "task": a["task"], "state": a["incident_state"]},
        )


def _scan_interrupts(signals: _Signals) -> None:
    sw, now = signals.sw, signals.now
    for r in sw.db.execute(
        "SELECT * FROM interrupts WHERE state IN ('requested','acknowledged') AND deadline_at<=? ORDER BY id", (core.iso(now),)
    ).fetchall():
        signals.add(
            "interrupt",
            "P2",
            f"task:{r['task']}" if r["task"] else f"interrupt:{r['id']}",
            f"sqlite:interrupts/{r['id']}",
            f"Interrupt {r['id']} to {r['target']} missed its deadline in state {r['state']}.",
            f"interrupt:{r['id']}:deadline:{r['state']}",
            r["deadline_at"],
            details={"interrupt": r["id"], "target": r["target"], "mode": r["mode"], "state": r["state"]},
        )


def scan(sw, now=None) -> dict:
    """One deterministic pass. Repeated scans update one durable item per source signal."""
    now = now or _now()
    signals = _Signals(sw, now)
    _scan_messages(signals)
    _scan_questions(signals)
    _scan_contracts(signals)
    _scan_tasks(signals)
    _scan_verifications(signals)
    _scan_executions(signals)
    _scan_incidents(signals)
    _scan_agents(signals)
    _scan_interrupts(signals)
    limit = signals.settings["max_scan_items"]
    signals.items = signals.items[:limit]
    created, existing = [], 0
    for s in signals.items:
        cur = sw.db.execute(
            "INSERT OR IGNORE INTO attention_items(kind,severity,subject_ref,evidence_ref,detected_at,due_at,status,"
            "dedupe_key,source_severity,details,last_seen_at,last_scan_at,summary) VALUES(?,?,?,?,?,?, 'new',?,?,?,?,?,?)",
            (
                s["kind"],
                s["severity"],
                s["subject_ref"],
                s["evidence_ref"],
                core.iso(now),
                s["due_at"],
                s["dedupe_key"],
                s["source_severity"],
                json.dumps(s["details"], ensure_ascii=False),
                core.iso(now),
                core.iso(now),
                s["summary"],
            ),
        )
        if cur.rowcount:
            item_id = cur.lastrowid
            _history(sw, item_id, "scout", None, "new", s["summary"], s["evidence_ref"])
            sw.event("attention_new", "scout", _task_for(s["subject_ref"]), f"A{item_id} {s['severity']} {s['summary']}")
            created.append({"id": item_id, **s})
        else:
            existing += 1
            row = sw.db.execute(
                "SELECT id,status,summary,details,last_scan_at FROM attention_items WHERE dedupe_key=?",
                (s["dedupe_key"],),
            ).fetchone()
            details = json.dumps(s["details"], ensure_ascii=False)
            stamp = core.iso(now)
            # Repeated scans of unchanged evidence write nothing; freshness moves at most once a minute.
            if row["summary"] != s["summary"] or row["details"] != details or (row["last_scan_at"] or "")[:16] != stamp[:16]:
                sw.db.execute(
                    "UPDATE attention_items SET last_seen_at=?,last_scan_at=?,summary=?,details=? WHERE id=?",
                    (stamp, stamp, s["summary"], details, row["id"]),
                )
    reminded = _remind_overdue(sw, now)
    current = status(sw, now=now)
    result = {
        "schema": 1,
        "scanned_at": core.iso(now),
        "created": created,
        "created_count": len(created),
        "existing_count": existing,
        "reminded_count": reminded,
        "queue": queue_counts(sw),
        "status": current,
        "notice": "Deterministic signals only. An alert is not evidence of misconduct, and a deputy cannot resolve it.",
    }
    if current["candidate"]["eligible"] and not current["available"]:
        _notify_capacity(sw, result)
    return result


SLA_REMINDER = "SLA reminder sent to"


def _remind_overdue(sw, now) -> int:
    """One visible nudge per unowned P0/P1 item past its deadline or queue SLA. It assigns no owner and changes no status."""
    cfg = _settings(sw)
    since = core.iso(now - timedelta(minutes=cfg["queue_sla_min"]))
    rows = sw.db.execute(
        "SELECT * FROM attention_items WHERE status IN ('new','reopened') AND owner IS NULL "
        "AND severity IN ('P0','P1') "
        "AND ((due_at IS NOT NULL AND due_at<=?) OR (due_at IS NULL AND detected_at<=?)) "
        "ORDER BY COALESCE(due_at,detected_at),id LIMIT 10",
        (core.iso(now), since),
    ).fetchall()
    target = sw.coordinator() or core.HUMAN
    reminded = 0
    for row in rows:
        marker = f"SLA reminder (revision {row['revision']})"
        if sw.db.execute(
            "SELECT 1 FROM attention_history WHERE attention=? AND actor='scout' AND note LIKE ?",
            (row["id"], marker + "%"),
        ).fetchone():
            continue
        when = row["due_at"] or f"the {cfg['queue_sla_min']}-minute queue SLA, detected {row['detected_at']}"
        note = (
            f"{marker} sent to {target}: A{row['id']} is still unowned past its response deadline. "
            "This is a queue-health notice, not an allegation about any agent."
        )
        _history(sw, row["id"], "scout", row["status"], row["status"], note, row["evidence_ref"] or "")
        sw.message(
            "swarm",
            target,
            f"Attention A{row['id']} ({row['severity']}, {row['kind']}) passed its response deadline ({when}) "
            f"and no agent owns it. {row['summary']} This reminder assigns no blame and no owner: claim it, assign it "
            "to an available agent, or record that it is a false alarm.",
            kind="warning",
            task=_task_for(row["subject_ref"]),
            priority="normal",
            idempotency_key=f"attention:remind:{row['id']}:{row['revision']}:{row['due_at'] or row['detected_at']}",
        )
        sw.event(
            "attention_reminded",
            "scout",
            _task_for(row["subject_ref"]),
            f"A{row['id']} left its {row['severity']} response deadline unowned; one reminder sent to {target}.",
        )
        reminded += 1
    return reminded


def _notify_capacity(sw, result: dict) -> None:
    coordinator = sw.coordinator() or core.HUMAN
    key = f"deputy:capacity:{core.utcnow().date().isoformat()}"
    if sw.db.execute("SELECT 1 FROM messages WHERE sender='swarm' AND idempotency_key=?", (key,)).fetchone():
        return
    sw.message(
        "swarm",
        coordinator,
        "Attention backlog is above the deputy activation threshold, but every live agent is occupied. "
        "Deterministic scouting and escalation continue; no sixth agent is created and no worker is interrupted. "
        "Release an assignment or grant a bounded deputy shift explicitly.",
        kind="warning",
        priority="high",
        idempotency_key=key,
    )


def queue_counts(sw) -> dict:
    counts = {sev: 0 for sev in SEVERITIES}
    for row in sw.db.execute(
        "SELECT severity, COUNT(*) AS n FROM attention_items WHERE status IN ('new','claimed','investigating','proposed_action','escalated','reopened') GROUP BY severity"
    ).fetchall():
        counts[row["severity"]] = row["n"]
    counts["open"] = sum(counts[sev] for sev in SEVERITIES)
    return counts


def oldest_open_min(sw, now=None) -> float | None:
    row = sw.db.execute(
        "SELECT MIN(detected_at) AS oldest FROM attention_items WHERE status IN ('new','claimed','investigating','proposed_action','escalated','reopened')"
    ).fetchone()
    return _age_min(row["oldest"], now or _now()) if row and row["oldest"] else None


# ----------------------------------------------------------------------------------------- coordinator term and delegation


def coordinator_term(sw) -> str | None:
    name = sw.coordinator()
    if not name:
        return None
    return core.request_hash({"name": name, "since": sw.meta("coordinator_since") or "legacy"})


def current_policy_digest(sw) -> str:
    return sw.configuration_digest() or "default"


def _delegation_row(sw, delegation_id: int):
    row = sw.db.execute("SELECT * FROM deputy_delegations WHERE id=?", (delegation_id,)).fetchone()
    if not row:
        raise DeputyError(f"There is no delegation {delegation_id}.")
    return row


def active_delegation(sw):
    return sw.db.execute(
        "SELECT * FROM deputy_delegations WHERE state='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()


def _live(sw, name: str) -> bool:
    agent = sw.agent(name)
    return bool(agent and agent["state"] not in ("offline", "left"))


def scope_allows(scope: list[str], subject_ref: str) -> bool:
    if "*" in scope:
        return True
    for entry in scope:
        if entry == subject_ref:
            return True
        if entry.endswith(":*") and subject_ref.startswith(entry[:-1]):
            return True
    return False


def _parse_scope(raw: str) -> list[str]:
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if not parts:
        raise DeputyError("Give --scope with the exact subjects this deputy may touch, e.g. task:T1,incident:2 or *.")
    if len(parts) > 64 or any(len(p) > 96 for p in parts):
        raise DeputyError("Scope is limited to 64 subjects of at most 96 characters.")
    return sorted(set(parts))


def _parse_capabilities(raw: str) -> list[str]:
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if not parts:
        parts = list(DEFAULT_CAPABILITIES)
    unknown = [p for p in parts if p not in CAPABILITIES]
    if unknown:
        raise DeputyError(f"Unknown capability: {', '.join(unknown)}. Allowed: {', '.join(CAPABILITIES)}.")
    return sorted(set(parts))


def _revoke(sw, row, actor: str | None, state: str, reason: str) -> None:
    sw.db.execute(
        "UPDATE deputy_delegations SET state=?,revoked_at=?,reason=? WHERE id=? AND state='active'",
        (state, core.iso(), core.redact_text(reason), row["id"]),
    )
    sw.event("deputy_revoked", actor, None, f"delegation {row['id']} to {row['deputy']}: {reason}")
    for item in sw.db.execute(
        "SELECT * FROM attention_items WHERE owner=? AND status IN ('claimed','investigating')",
        (row["deputy"],),
    ).fetchall():
        sw.db.execute(
            "UPDATE attention_items SET status='new',owner=NULL,lease_until=NULL,revision=revision+1 "
            "WHERE id=? AND lease_epoch=?",
            (item["id"], item["lease_epoch"]),
        )
        note = f"delegation {row['id']} ended ({reason}); evidence preserved and the item is claimable again"
        _history(sw, item["id"], "swarm", item["status"], "new", note, item["evidence_ref"] or "")
        sw.event(
            "attention_released",
            "swarm",
            _task_for(item["subject_ref"]),
            f"A{item['id']} released after delegation {row['id']} ended",
        )
    if actor != row["deputy"]:
        sw.message(
            "swarm",
            row["deputy"],
            f"Your deputy delegation {row['id']} was revoked ({reason}). Stop triage actions immediately; "
            "preserve your evidence in a message or handoff.",
            kind="warning",
            priority="high",
        )


def require_delegation(sw, who: str, capability: str, subject_ref: str):
    """Human and coordinator keep their existing authority; every other actor needs a live scoped lease."""
    if who == core.HUMAN or sw.is_coordinator(who):
        return None
    row = active_delegation(sw)
    failure = None
    if not row or row["deputy"] != who:
        failure = f"{who} holds no active deputy delegation; the coordinator or human must activate one."
        row = None
    elif row["revoked_at"]:
        failure = "The deputy delegation was revoked."
    elif core.utcnow() >= core.parse(row["expires_at"]):
        failure = "The deputy delegation expired; ask the coordinator for a new bounded lease."
    elif not _live(sw, who):
        failure = "The deputy is not a live agent."
    elif row["coordinator_term"] != coordinator_term(sw):
        failure = "The coordination term changed; the old delegation is fenced out."
    elif row["policy_digest"] != current_policy_digest(sw):
        failure = "Project policy changed; the old delegation is stale."
    elif capability not in _loads(row["capabilities"], []):
        failure = f"This delegation does not include {capability}."
    elif not scope_allows(_loads(row["subject_scope"], []), subject_ref):
        failure = f"{subject_ref} is outside this delegation's scope."
    if failure:
        if row:
            raise DelegationViolation(failure, row["id"])
        raise DeputyError(failure)
    return row


def record_violation(sw, delegation_id: int, reason: str) -> None:
    """Revoked after the failed action transaction commits; a revoke inside it would be rolled back."""
    row = sw.db.execute(
        "SELECT * FROM deputy_delegations WHERE id=? AND state='active'", (delegation_id,)
    ).fetchone()
    if row:
        _revoke(sw, row, "swarm", "revoked", reason)
        sw.set_meta("deputy_cooldown_until", core.iso(_now() + timedelta(minutes=_settings(sw)["cooldown_min"])))


def _enforce_deputy_subject(sw, who: str, capability: str, subject_ref: str) -> None:
    require_delegation(sw, who, capability, subject_ref)


def status(sw, now=None) -> dict:
    now = now or _now()
    active = active_delegation(sw)
    campaign = None
    if active:
        campaign = {
            **{k: active[k] for k in ("id", "issuer", "deputy", "granted_at", "expires_at", "state", "reason")},
            "capabilities": _loads(active["capabilities"], []),
            "subject_scope": _loads(active["subject_scope"], []),
            "live": _live(sw, active["deputy"]),
            "remaining_sec": max(0, round((core.parse(active["expires_at"]) - now).total_seconds())),
        }
    coord = sw.coordinator()
    coordinator_busy = bool(coord and coord != core.HUMAN and (sw.agent(coord)["task"] if sw.agent(coord) else False))
    live = [
        a
        for a in sw.live_agents()
        if a["name"] != coord and not a["task"] and not (a["reviewing"] if "reviewing" in a.keys() else None)
        and a["state"] == "ready"
    ]
    occupied = [
        a
        for a in sw.live_agents()
        if a["name"] != coord and (a["task"] or (a["reviewing"] if "reviewing" in a.keys() else None) or a["state"] != "ready")
    ]
    queue = queue_counts(sw)
    oldest = oldest_open_min(sw, now)
    cfg = _settings(sw)
    urgent = sum(
        1
        for r in sw.db.execute(
            "SELECT id FROM attention_items WHERE status IN ('new','claimed','investigating','proposed_action','escalated','reopened') AND severity IN ('P0','P1')"
        )
    )
    blockers = sw.db.execute(
        "SELECT COUNT(DISTINCT subject_ref) AS n FROM attention_items WHERE status IN ('new','claimed','investigating','proposed_action','escalated','reopened') "
        "AND kind IN ('task','contract','execution','verification','merge') AND severity IN ('P0','P1','P2')"
    ).fetchone()["n"]
    urgent_incident = bool(
        sw.db.execute(
            "SELECT 1 FROM attention_items WHERE status IN ('new','claimed','investigating','proposed_action','escalated','reopened') "
            "AND kind='incident' AND severity IN ('P0','P1') LIMIT 1"
        ).fetchone()
    )
    coordinator_available = bool(coord and (coord == core.HUMAN or _live(sw, coord) and not coordinator_busy))
    backlog_sla = bool(oldest is not None and oldest >= cfg["queue_sla_min"])
    reasons = []
    if queue["P0"] + queue["P1"] >= cfg["activation_min_urgent"]:
        reasons.append(f"{queue['P0'] + queue['P1']} critical/high attention item(s) waiting")
    if blockers >= cfg["activation_min_blockers"]:
        reasons.append(f"{blockers} distinct operational blocker(s) across tasks")
    if urgent_incident and not coordinator_available:
        reasons.append("urgent incident while the coordinator is unavailable or occupied")
    if backlog_sla:
        reasons.append(f"oldest open item has waited {round(oldest)} min")
    eligible = cfg["enabled"] and bool(reasons) and not active
    cooldown_until = sw.meta("deputy_cooldown_until")
    in_cooldown = bool(cooldown_until and now < core.parse(cooldown_until))
    if in_cooldown:
        eligible = False
        reasons.append(f"deputy cooldown until {cooldown_until}")
    if not cfg["enabled"]:
        reasons.append("deputy activation is disabled by [deputy] enabled = false")
    return {
        "schema": 1,
        "as_of": core.iso(now),
        "enabled": cfg["enabled"],
        "deputy": campaign,
        "nominee": sw.meta("deputy_nominee"),
        "coordinator": coord,
        "coordinator_term": coordinator_term(sw),
        "policy_digest": current_policy_digest(sw),
        "queue": queue,
        "candidate": {
            "eligible": eligible,
            "reasons": reasons,
            "urgent": urgent,
            "blockers": blockers,
            "oldest_open_min": None if oldest is None else round(oldest),
            "cooldown_until": cooldown_until,
        },
        "available": [a["name"] for a in live],
        "occupied": [a["name"] for a in occupied],
        "leases": [
            {
                **{k: r[k] for k in ("id", "issuer", "deputy", "granted_at", "expires_at", "revoked_at", "state", "reason")},
                "capabilities": _loads(r["capabilities"], []),
                "subject_scope": _loads(r["subject_scope"], []),
            }
            for r in sw.db.execute("SELECT * FROM deputy_delegations ORDER BY id DESC LIMIT 20")
        ],
        "notice": "One authoritative coordinator. A deputy lease grants triage only and never coordinator authority.",
    }


# ----------------------------------------------------------------------------------------- triage workflow


def list_items(sw, severity=None, status_filter=None, kind=None, owner=None, limit=100, all_items=False):
    where, args = [], []
    if severity:
        if severity not in SEVERITIES:
            raise DeputyError(f"Severity is one of {', '.join(SEVERITIES)}.")
        where.append("severity=?")
        args.append(severity)
    if status_filter:
        where.append("status=?")
        args.append(status_filter)
    elif not all_items:
        where.append("status IN ('new','claimed','investigating','proposed_action','escalated','reopened')")
    if kind:
        if kind not in KINDS:
            raise DeputyError(f"Kind is one of {', '.join(KINDS)}.")
        where.append("kind=?")
        args.append(kind)
    if owner:
        where.append("owner=?")
        args.append(owner)
    clause = " AND ".join(where) if where else "1=1"
    if not 1 <= limit <= 1000:
        raise DeputyError("--limit is 1..1000.")
    rows = sw.db.execute(
        f"SELECT * FROM attention_items WHERE {clause} "
        "ORDER BY CASE severity WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, "
        "COALESCE(due_at,'9999'), id LIMIT ?",
        (*args, limit),
    ).fetchall()
    return [
        {
            **{k: r[k] for k in ("id", "kind", "severity", "subject_ref", "evidence_ref", "detected_at", "due_at", "status", "owner", "lease_until", "summary")},
            "details": _loads(r["details"], {}),
            "finding": r["finding"],
            "recommendation": r["recommendation"],
            "decision_owner": r["decision_owner"],
            "disposition": r["disposition"],
            "resolved_at": r["resolved_at"],
        }
        for r in rows
    ]


def show(sw, item_id: int) -> dict:
    row = _item(sw, item_id)
    history = [
        dict(r)
        for r in sw.db.execute(
            "SELECT * FROM attention_history WHERE attention=? ORDER BY id", (row["id"],)
        ).fetchall()
    ]
    return {
        "item": {**dict(row), "details": _loads(row["details"], {})},
        "history": history,
        "notice": "Findings are bounded evidence summaries, not sanctions or merge authority.",
    }


def claim(sw, item_id: int, who: str, lease_sec: int | None = None) -> dict:
    cfg = _settings(sw)
    lease_sec = lease_sec or cfg["claim_lease_sec"]
    if not 1 <= lease_sec <= 86400:
        raise DeputyError("--lease-sec is 1..86400.")
    row = _item(sw, item_id)
    _enforce_deputy_subject(sw, who, "attention.claim", row["subject_ref"])
    now = _now()
    if row["status"] in TERMINAL_STATUSES:
        raise DeputyError(f"Attention item {item_id} is already {row['status']}; reopen it explicitly if the signal returned.")
    if row["status"] in ("proposed_action",):
        raise DeputyError(f"Attention item {item_id} already has a finding and awaits a coordinator decision.")
    if row["owner"] and row["owner"] != who and row["lease_until"] and core.parse(row["lease_until"]) > now:
        raise DeputyError(f"Attention item {item_id} is claimed by {row['owner']} until {row['lease_until']}.")
    if row["owner"] == who and row["lease_until"] and core.parse(row["lease_until"]) > now:
        raise DeputyError(f"You already hold attention item {item_id}; report, escalate or let its lease expire.")
    lease_until = core.iso(now + timedelta(seconds=lease_sec))
    cur = sw.db.execute(
        "UPDATE attention_items SET status='claimed',owner=?,lease_epoch=lease_epoch+1,lease_until=?,claimed_at=?,last_seen_at=? "
        "WHERE id=? AND lease_epoch=? AND (owner IS NULL OR lease_until IS NULL OR lease_until<=?) "
        "AND status NOT IN ('proposed_action','escalated','resolved','false_alarm','expired')",
        (who, lease_until, core.iso(now), core.iso(now), item_id, row["lease_epoch"], core.iso(now)),
    )
    if cur.rowcount != 1:
        raise DeputyError(f"Attention item {item_id} was claimed concurrently; read the queue again.")
    _history(
        sw,
        item_id,
        who,
        row["status"],
        "claimed",
        f"{who} claimed with a {lease_sec}s lease" + (f" (recovered from {row['owner']})" if row["owner"] else ""),
        row["evidence_ref"] or "",
    )
    sw.event("attention_claimed", who, _task_for(row["subject_ref"]), f"A{item_id} claimed; lease {lease_until}")
    return {**show(sw, item_id), "lease_until": lease_until, "lease_epoch": row["lease_epoch"] + 1}


def investigate(sw, item_id: int, who: str, note: str = "") -> dict:
    row = _item(sw, item_id)
    _enforce_deputy_subject(sw, who, "attention.claim", row["subject_ref"])
    row = _current_owner(sw, item_id, who)
    note = core.bounded_text(sw, (note or "Investigation started; collecting evidence.").strip())
    if len(note) < core.MIN_ANSWER:
        raise DeputyError("Describe the investigation in at least 15 characters.")
    sw.db.execute(
        "UPDATE attention_items SET status='investigating',last_seen_at=? WHERE id=? AND owner=? AND lease_epoch=?",
        (core.iso(), item_id, who, row["lease_epoch"]),
    )
    _history(sw, item_id, who, row["status"], "investigating", note, row["evidence_ref"] or "")
    sw.event("attention_investigating", who, _task_for(row["subject_ref"]), f"A{item_id}: {note}")
    return show(sw, item_id)


def _current_owner(sw, item_id: int, who: str):
    row = _item(sw, item_id)
    if row["owner"] != who:
        raise DeputyError(f"{who} does not hold attention item {item_id} (owner: {row['owner'] or 'nobody'}).")
    if not row["lease_until"] or core.parse(row["lease_until"]) <= _now():
        raise DeputyError(f"{who}'s lease on attention item {item_id} expired; the evidence and history were preserved.")
    return row


def report(
    sw,
    item_id: int,
    who: str,
    finding: str,
    evidence: list[str],
    recommend: str,
    decision_owner: str = "coordinator",
) -> dict:
    row = _item(sw, item_id)
    _enforce_deputy_subject(sw, who, "attention.report", row["subject_ref"])
    row = _current_owner(sw, item_id, who)
    finding = core.bounded_text(sw, (finding or "").strip())
    recommend = core.bounded_text(sw, (recommend or "").strip())
    evidence = [e.strip() for e in (evidence or []) if e and e.strip()]
    if len(finding) < core.MIN_ANSWER:
        raise DeputyError("Give a concrete --finding of at least 15 characters.")
    if not evidence:
        raise DeputyError("Give at least one --evidence reference (event, message, receipt or file).")
    if len(recommend) < core.MIN_ANSWER:
        raise DeputyError("Give a concrete --recommend action and its owner.")
    if decision_owner == "coordinator":
        decision_owner = sw.coordinator() or core.HUMAN
    if decision_owner != core.HUMAN:
        target = sw.agent(decision_owner)
        if not target or target["state"] in ("left", "offline"):
            raise DeputyError("The decision owner must be the human or a live agent.")
    evidence_text = ", ".join(evidence[:20])
    sw.db.execute(
        "UPDATE attention_items SET status='proposed_action',finding=?,report_evidence=?,recommendation=?,decision_owner=?,reported_at=?,lease_until=NULL "
        "WHERE id=? AND owner=? AND lease_epoch=?",
        (finding, evidence_text, recommend, decision_owner, core.iso(), item_id, who, row["lease_epoch"]),
    )
    _history(sw, item_id, who, row["status"], "proposed_action", f"finding: {finding}", evidence_text)
    sw.message(
        who,
        decision_owner,
        f"A{item_id} [{row['severity']}] {row['summary']}\nFinding: {finding}\nEvidence: {evidence_text}\n"
        f"Recommended: {recommend}\nThis is a bounded recommendation; it grants no authority and is not a finding of misconduct.",
        kind="status",
        task=_task_for(row["subject_ref"]),
    )
    sw.event("attention_reported", who, _task_for(row["subject_ref"]), f"A{item_id} proposed action for {decision_owner}")
    return show(sw, item_id)


def escalate(sw, item_id: int, who: str, to: str = "coordinator", reason: str = "") -> dict:
    row = _item(sw, item_id)
    _enforce_deputy_subject(sw, who, "attention.escalate", row["subject_ref"])
    row = _current_owner(sw, item_id, who)
    reason = core.bounded_text(sw, (reason or "").strip())
    if len(reason) < core.MIN_ANSWER:
        raise DeputyError("Give a concrete --reason for escalation.")
    target = sw.coordinator() or core.HUMAN if to == "coordinator" else to
    if target != core.HUMAN:
        agent = sw.agent(target)
        if not agent or agent["state"] in ("left", "offline"):
            raise DeputyError("Escalate to the human or a live agent.")
    sw.db.execute(
        "UPDATE attention_items SET status='escalated',lease_until=NULL WHERE id=? AND owner=? AND lease_epoch=?",
        (item_id, who, row["lease_epoch"]),
    )
    _history(sw, item_id, who, row["status"], "escalated", reason, row["evidence_ref"] or "")
    sw.message(
        who,
        target,
        f"A{item_id} [{row['severity']}] escalated: {row['summary']}\nReason: {reason}\n"
        "The coordinator or human decides; this grant does not authorize consequences.",
        kind="warning",
        priority="high",
        task=_task_for(row["subject_ref"]),
    )
    sw.event("attention_escalated", who, _task_for(row["subject_ref"]), f"A{item_id} to {target}: {reason}")
    return show(sw, item_id)


def resolve(sw, item_id: int, who: str, disposition: str, reason: str) -> dict:
    if who != core.HUMAN and not sw.is_coordinator(who):
        raise DeputyError("Only the coordinator or human may resolve attention; a deputy may report or escalate.")
    if disposition not in ("resolved", "false_alarm", "expired"):
        raise DeputyError("--disposition is one of resolved, false_alarm, expired.")
    reason = core.bounded_text(sw, (reason or "").strip())
    if len(reason) < core.MIN_ANSWER:
        raise DeputyError("Give a concrete --reason for the disposition.")
    row = _item(sw, item_id)
    if row["status"] == disposition and row["disposition"] == disposition:
        if row["resolution"] != reason:
            raise DeputyError("Disposition is immutable; reopen the item if the decision must change.")
        return show(sw, item_id)
    if row["status"] in TERMINAL_STATUSES:
        raise DeputyError(f"Attention item {item_id} is already {row['status']}; reopen it first.")
    if row["owner"] and row["owner"] != who and row["lease_until"] and core.parse(row["lease_until"]) > _now():
        raise DeputyError(f"{row['owner']} is still investigating {item_id}; wait for the lease to expire or revoke it.")
    sw.db.execute(
        "UPDATE attention_items SET status=?,disposition=?,resolution=?,resolved_at=?,owner=NULL,lease_until=NULL WHERE id=?",
        (disposition, disposition, reason, core.iso(), item_id),
    )
    _history(sw, item_id, who, row["status"], disposition, reason, row["evidence_ref"] or "")
    sw.event("attention_resolved", who, _task_for(row["subject_ref"]), f"A{item_id}: {disposition}; {reason}")
    return show(sw, item_id)


def reopen(sw, item_id: int, who: str, reason: str) -> dict:
    if who != core.HUMAN and not sw.is_coordinator(who):
        raise DeputyError("Only the coordinator or human may reopen attention.")
    reason = core.bounded_text(sw, (reason or "").strip())
    if len(reason) < core.MIN_ANSWER:
        raise DeputyError("Give a concrete --reason for reopening.")
    row = _item(sw, item_id)
    if row["status"] not in TERMINAL_STATUSES:
        raise DeputyError(f"Attention item {item_id} is already open ({row['status']}).")
    sw.db.execute(
        "UPDATE attention_items SET status='reopened',owner=NULL,lease_until=NULL,disposition=NULL,resolution=NULL,resolved_at=NULL,revision=revision+1 WHERE id=?",
        (item_id,),
    )
    _history(sw, item_id, who, row["status"], "reopened", reason, row["evidence_ref"] or "")
    sw.event("attention_reopened", who, _task_for(row["subject_ref"]), f"A{item_id}: {reason}")
    return show(sw, item_id)


# ----------------------------------------------------------------------------------------- activation and continuity


def nominate(sw, agent: str, issuer: str) -> dict:
    if issuer != core.HUMAN:
        sw.require_coordinator(issuer)
    target = sw.agent(agent)
    if not target or target["state"] in ("left", "offline"):
        raise DeputyError("Nominate a live agent.")
    if agent == sw.coordinator():
        raise DeputyError("The coordinator cannot also be the deputy.")
    sw.set_meta("deputy_nominee", agent)
    sw.event("deputy_nominated", issuer, None, agent)
    return {"nominee": agent, "issuer": issuer}


def activate(
    sw,
    agent: str,
    issuer: str,
    scope: str,
    capabilities: str = "",
    minutes: float | None = None,
    reason: str = "",
    force: bool = False,
) -> dict:
    if issuer != core.HUMAN:
        sw.require_coordinator(issuer)
    cfg = _settings(sw)
    if not cfg["enabled"]:
        raise DeputyError("[deputy] enabled is false; deterministic scouting still runs.")
    target = sw.agent(agent)
    if not target or target["state"] in ("left", "offline"):
        raise DeputyError("Activate a live agent that already holds a pool slot.")
    if agent == issuer or agent == sw.coordinator():
        raise DeputyError("The issuer and the current coordinator cannot also be the deputy.")
    if active_delegation(sw):
        row = active_delegation(sw)
        raise DeputyError(f"{row['deputy']} already holds the single active deputy lease (until {row['expires_at']}).")
    if target["task"] or (target["reviewing"] if "reviewing" in target.keys() else None) or target["state"] != "ready":
        raise DeputyError(
            f"{agent} is productive right now ({target['state']}, task {target['task'] or 'none'}). "
            "Do not interrupt work to acquire a deputy; wait for an idle agent."
        )
    cooldown = sw.meta("deputy_cooldown_until")
    if cooldown and core.utcnow() < core.parse(cooldown) and not (force and issuer == core.HUMAN):
        raise DeputyError(
            f"Deputy cooldown is active until {cooldown}. Wait for demand to be sustained, or the human may --force."
        )
    minutes = minutes or cfg["lease_min"]
    if not 1 <= minutes <= 1440:
        raise DeputyError("--minutes is 1..1440.")
    subject_scope = _parse_scope(scope)
    caps = _parse_capabilities(capabilities)
    minutes = float(minutes)
    now = _now()
    try:
        cur = sw.db.execute(
            "INSERT INTO deputy_delegations(issuer,deputy,capabilities,subject_scope,policy_digest,coordinator_term,"
            "granted_at,expires_at,state,reason,minimum_active_until) VALUES(?,?,?,?,?,?,?,?, 'active',?,?)",
            (
                issuer,
                agent,
                json.dumps(caps),
                json.dumps(subject_scope),
                current_policy_digest(sw),
                coordinator_term(sw),
                core.iso(now),
                core.iso(now + timedelta(minutes=minutes)),
                core.bounded_text(sw, reason or "bounded operational deputy shift"),
                core.iso(now + timedelta(minutes=cfg["min_active_min"])),
            ),
        )
    except sqlite3.IntegrityError:
        raise DeputyError("Another deputy lease became active concurrently; there is never more than one.")
    delegation_id = cur.lastrowid
    sw.message(
        "swarm",
        agent,
        f"Deputy lease {delegation_id}: {minutes:g} min for scope {', '.join(subject_scope)}; "
        f"capabilities {', '.join(caps)}. Triage only. You may claim, investigate, report and escalate. "
        "You may not resolve your own findings, acknowledge another inbox, approve architecture, merge, or kill processes.",
        kind="decision",
        priority="high",
    )
    sw.event(
        "deputy_activated",
        issuer,
        None,
        f"{agent} lease {delegation_id} for {minutes:g} min; scope {', '.join(subject_scope)}; caps {', '.join(caps)}",
    )
    return {"delegation": delegation_id, "activated": agent, "status": status(sw)}


def release(sw, who: str, reason: str, force: bool = False) -> dict:
    row = active_delegation(sw)
    if not row:
        raise DeputyError("No deputy lease is active.")
    actor = who
    if actor not in (row["deputy"],) and actor != core.HUMAN and not sw.is_coordinator(actor):
        raise DeputyError("Only the deputy, the coordinator or the human may release this lease.")
    cfg = _settings(sw)
    minimum = row["minimum_active_until"]
    if (
        actor == row["deputy"]
        and minimum
        and core.utcnow() < core.parse(minimum)
        and not (force and actor == core.HUMAN)
    ):
        raise DeputyError(
            f"Minimum deputy active time runs until {minimum}. A coordinator or human may release with --force."
        )
    reason = core.bounded_text(sw, (reason or "").strip())
    if len(reason) < core.MIN_ANSWER:
        raise DeputyError("Give a concrete --reason for handing back the deputy role.")
    sw.db.execute(
        "UPDATE deputy_delegations SET state='released',revoked_at=?,reason=? WHERE id=? AND state='active'",
        (core.iso(), reason, row["id"]),
    )
    sw.set_meta("deputy_cooldown_until", core.iso(core.utcnow() + timedelta(minutes=cfg["cooldown_min"])))
    sw.message(
        "swarm",
        sw.coordinator() or core.HUMAN,
        f"Deputy lease {row['id']} released by {actor}: {reason}. Attention findings and history remain durable; "
        "the coordinator remains accountable.",
        kind="status",
        priority="high",
    )
    sw.event("deputy_released", actor, None, f"delegation {row['id']}: {reason}")
    return {"released": row["id"], "released_agent": row["deputy"], "reason": reason, "status": status(sw)}


def reconcile(sw) -> None:
    now = _now()
    for row in sw.db.execute("SELECT * FROM deputy_delegations WHERE state='active'").fetchall():
        failure = None
        if not _live(sw, row["deputy"]):
            failure = "the deputy is no longer live"
        elif row["expires_at"] and now >= core.parse(row["expires_at"]):
            failure = "the lease expired"
        elif row["coordinator_term"] != coordinator_term(sw):
            failure = "the coordination term changed"
        elif row["policy_digest"] != current_policy_digest(sw):
            failure = "project policy changed"
        else:
            holder = sw.agent(row["deputy"])
            if holder and (
                holder["task"] or (holder["reviewing"] if "reviewing" in holder.keys() else None)
            ):
                failure = "the deputy became productive; the triage lease ended rather than split one agent across roles"
        if failure:
            state = "expired" if "expired" in failure else "revoked"
            _revoke(sw, row, "swarm", state, failure)
            sw.set_meta("deputy_cooldown_until", core.iso(now + timedelta(minutes=_settings(sw)["cooldown_min"])))
    for row in sw.db.execute(
        "SELECT * FROM attention_items WHERE status IN ('claimed','investigating','escalated') AND lease_until IS NOT NULL AND lease_until<=?",
        (core.iso(now),),
    ).fetchall():
        note = f"lease expired for {row['owner'] or 'nobody'}; evidence preserved"
        sw.db.execute(
            "UPDATE attention_items SET owner=NULL,lease_until=NULL,status=?,revision=revision+1 WHERE id=? AND lease_epoch=?",
            ("escalated" if row["status"] == "escalated" else "new", row["id"], row["lease_epoch"]),
        )
        _history(sw, row["id"], "swarm", row["status"], "escalated" if row["status"] == "escalated" else "new", note, row["evidence_ref"] or "")
        sw.event("attention_lease_expired", row["owner"], _task_for(row["subject_ref"]), f"A{row['id']}: {note}")


def sweep(sw) -> None:
    if not _settings(sw)["enabled"]:
        return
    reconcile(sw)
    scan(sw)
