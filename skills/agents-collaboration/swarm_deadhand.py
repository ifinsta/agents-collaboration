"""Dead-hand authority: bounded, human-armed delegation of a few human-only decisions.

Off unless the human arms it, in advance and from a terminal. A ticket needs an independent deputy the
engine selects from agents the human made eligible, then the coordinator's approval, and is consumed once,
inside the gated action's own transaction, with exact arguments. Nothing is ever attributed to the human.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sys
from datetime import timedelta

import swarm_core as core

ALLOWLIST = (
    "incident.resolve",
    "usage.reconcile",
    "verification.reconcile",
    "execution.reconcile",
    "allocation.reconcile",
    "contract.extend.high_risk",
)
RECONCILES = {"usage.reconcile", "verification.reconcile", "execution.reconcile", "allocation.reconcile"}
MAX_ARM_HOURS = 72  # floors live in code, not only config
MIN_WAIT_MIN = 30
MAX_HIGH_RISK_EXTENSION_MIN = 60
TOKEN_RE = re.compile(r"^hwt_[0-9a-f]{32}$")
OPEN_TICKETS = ("waiting", "requested", "reviewed", "approved")


HumanOnly = core.HumanOnly


# ----------------------------------------------------------------------------------------- join tokens
def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def presented_token(read_stdin: bool = False) -> str | None:
    """From SWARM_TOKEN or one stdin line, never argv, so it stays out of process listings and shell history."""
    token = os.environ.get("SWARM_TOKEN", "").strip()
    if not token and read_stdin:
        token = sys.stdin.readline().strip()
    return token if TOKEN_RE.match(token or "") else None


def token_record(sw, name: str) -> dict | None:
    raw = sw.meta(f"agent_token:{name}")
    return json.loads(raw) if raw else None


def token_valid(sw, name: str, token: str | None) -> bool:
    record = token_record(sw, name)
    return bool(record and token and secrets.compare_digest(record["hash"], token_hash(token)))


def proven(sw, name: str) -> bool:
    record = token_record(sw, name)
    return bool(record and record.get("proven"))


def join_token(sw, name: str, existed: bool, token: str | None) -> tuple[str | None, bool]:
    """A fresh name gets a token; a resume presenting the current one keeps its standing. Any other resume
    rotates it, is unproven, and voids the name's dead-hand eligibility and unconsumed signatures."""
    record = token_record(sw, name)
    if existed and record and token_valid(sw, name, token):
        sw.event("agent_resume_proven", name, None, "presented its current join token")
        return None, record.get("proven", False)
    fresh = "hwt_" + secrets.token_hex(16)
    is_proven = not existed
    sw.set_meta(
        f"agent_token:{name}", json.dumps({"hash": token_hash(fresh), "proven": is_proven, "at": core.iso()})
    )
    if existed:
        sw.event("agent_resume_unproven", name, None, "no current join token: dead-hand eligibility and signatures void")
        for row in sw.db.execute(
            "SELECT id FROM deadhand_tickets WHERE state IN ('waiting','requested','reviewed','approved') "
            "AND (deputy=? OR approver=? OR requester=?)",
            (name, name, name),
        ).fetchall():
            void(sw, row["id"], f"{name} resumed without its join token")
    return fresh, is_proven


# ----------------------------------------------------------------------------------------- arming
def deadhand_config(sw) -> dict:
    cfg = sw.config.get("deadhand", {})
    return {
        "wait_min": max(MIN_WAIT_MIN, float(cfg.get("wait_min", MIN_WAIT_MIN))),
        "require_distinct_model": bool(cfg.get("require_distinct_model", False)),
    }


def guarded_config_hash(sw) -> str:
    return core.request_hash({"deadhand": sw.config.get("deadhand", {}), "generated": sw.config["merge"]["generated_paths"]})


def active_arm(sw):
    row = sw.db.execute("SELECT * FROM deadhand_arms WHERE disarmed_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    if core.utcnow() >= core.parse(row["until"]):
        disarm(sw, row, "the armed window ended")
        return None
    if row["config_hash"] != guarded_config_hash(sw):
        disarm(sw, row, "[deadhand] or [merge] generated_paths changed in config.toml")
        return None
    return row


def disarm(sw, row, reason: str) -> None:
    sw.db.execute("UPDATE deadhand_arms SET disarmed_at=?, disarm_reason=? WHERE id=?", (core.iso(), reason, row["id"]))
    for t in sw.db.execute(
        "SELECT id FROM deadhand_tickets WHERE arm=? AND state IN ('waiting','requested','reviewed','approved')", (row["id"],)
    ).fetchall():
        void(sw, t["id"], "dead hand disarmed: " + reason)
    sw.event("deadhand_disarmed", "engine", None, reason)


def msys_pty() -> bool:
    """Git Bash's mintty: isatty() is false for a real person, but stdin is an MSYS pty pipe."""
    if os.name != "nt" or not os.environ.get("MSYSTEM"):
        return False
    try:
        import ctypes
        import msvcrt

        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        size = 1024
        buf = ctypes.create_string_buffer(size)
        ok = ctypes.windll.kernel32.GetFileInformationByHandleEx(ctypes.c_void_p(handle), 2, buf, size)  # FileNameInfo
        if not ok:
            return False
        length = int.from_bytes(buf.raw[:4], "little")
        name = buf.raw[4 : 4 + length].decode("utf-16-le", "replace")
    except (OSError, ValueError, AttributeError):
        return False
    return bool(re.search(r"msys-[0-9a-f]+-pty\d+-from-master", name))


def person_at_terminal(phrase: str) -> None:
    """Stops accidents, not deliberate typing: a headless agent without a terminal cannot arm by mistake."""
    if not (sys.stdin.isatty() or msys_pty()):
        raise core.SwarmError(
            "This needs a person at a terminal (stdin is not one). Run it yourself in a terminal; under mintty use `winpty`."
        )
    print(f"Type exactly: {phrase}")
    if sys.stdin.readline().strip() != phrase:
        raise core.SwarmError("The confirmation phrase did not match; nothing changed.")


def eligible_default(sw) -> list[str]:
    spawned = {r[0] for r in sw.db.execute("SELECT DISTINCT agent FROM executions WHERE agent IS NOT NULL")}
    return [a["name"] for a in sw.live_agents() if a["name"] not in spawned]


def cmd_arm(sw, a) -> None:
    if (a.as_ or core.HUMAN) != core.HUMAN:
        raise core.SwarmError("Only the human arms dead hand.")
    until = core.parse(a.until)
    if until <= core.utcnow() or until - core.utcnow() > timedelta(hours=MAX_ARM_HOURS):
        raise core.SwarmError(f"--until must be in the future and at most {MAX_ARM_HOURS} hours away.")
    allow = core.split_list(a.allow) if a.allow else list(ALLOWLIST)
    if any(x not in ALLOWLIST for x in allow):
        raise core.SwarmError("Dead hand delegates only: " + ", ".join(ALLOWLIST))
    person_at_terminal(f"arm dead hand until {core.iso(until)}")
    with sw.tx():
        sw.sweep()
        deputies = core.split_list(a.deputies) if a.deputies else eligible_default(sw)
        old = active_arm(sw)
        if old:
            disarm(sw, old, "re-armed")
        sw.db.execute(
            "INSERT INTO deadhand_arms(armed_at,until,allow,deputies,config_hash) VALUES(?,?,?,?,?)",
            (core.iso(), core.iso(until), json.dumps(allow), json.dumps(sorted(deputies)), guarded_config_hash(sw)),
        )
        sw.event("deadhand_armed", core.HUMAN, None, f"until {core.iso(until)}; {', '.join(allow)}; deputies {', '.join(deputies) or 'none'}")
    print(f"dead hand armed until {core.iso(until)}; eligible deputies: {', '.join(deputies) or 'none'}")


def cmd_disarm(sw, a) -> None:
    if (a.as_ or core.HUMAN) != core.HUMAN:
        raise core.SwarmError("Only the human disarms dead hand.")
    with sw.tx():
        row = active_arm(sw)
        if row:
            disarm(sw, row, "disarmed by the human")
    print("dead hand is off")


def cmd_verify_agent(sw, a) -> None:
    if (a.as_ or core.HUMAN) != core.HUMAN:
        raise core.SwarmError("Only the human re-verifies an agent.")
    person_at_terminal(f"verify {a.name}")
    with sw.tx():
        record = token_record(sw, a.name)
        if not record:
            raise core.SwarmError(f"{a.name} has no join token yet; it gets one at its next join.")
        sw.set_meta(f"agent_token:{a.name}", json.dumps({**record, "proven": True, "verified_at": core.iso()}))
        sw.event("agent_verified", core.HUMAN, None, a.name)
    print(f"{a.name} verified for dead-hand eligibility")


# ----------------------------------------------------------------------------------------- waiting decisions
def note_waiting(sw, action: str, subject: str, command: str, who: str | None) -> None:
    key = f"human_waiting:{action}:{subject}"
    if not sw.meta(key):
        sw.set_meta(key, json.dumps({"action": action, "subject": subject, "command": command, "by": who, "since": core.iso()}))
        sw.event("human_decision_waiting", who or "engine", None, f"{action} {subject}: {command}")


def waiting(sw, action: str, subject: str) -> dict | None:
    raw = sw.meta(f"human_waiting:{action}:{subject}")
    return json.loads(raw) if raw else None


def cmd_human_pending(sw, a) -> None:
    rows = []
    for r in sw.db.execute("SELECT key, value FROM meta WHERE key LIKE 'human_waiting:%' ORDER BY key"):
        item = json.loads(r["value"])
        rows.append(f"{item['action']} {item['subject']} (waiting since {item['since']}): {item['command']}")
    for r in sw.db.execute("SELECT * FROM incidents WHERE state IN ('timed_out','needs_human') ORDER BY id"):
        rows.append(f"incident I{r['id']} needs the human: `hivewire incident brief {r['id']}`, then resolve it")
    for r in sw.db.execute("SELECT * FROM questions WHERE to_whom=? AND answer IS NULL AND waived=0", (core.HUMAN,)):
        rows.append(f"question Q{r['id']} for the human: `hivewire answer {r['id']} \"...\"`")
    for r in sw.db.execute("SELECT key FROM meta WHERE key LIKE 'agent_token:%'"):
        name = r["key"].split(":", 1)[1]
        if not proven(sw, name) and sw.agent(name) and sw.agent(name)["state"] not in ("offline", "left"):
            rows.append(f"{name} resumed without its token: `hivewire deadhand verify-agent {name}` to restore eligibility")
    for t in sw.db.execute("SELECT * FROM deadhand_tickets WHERE state IN ('approved','reviewed') ORDER BY id"):
        rows.append(f"dead-hand ticket D{t['id']} {t['action']} {t['subject']} is {t['state']}: `hivewire deadhand veto {t['id']}` cancels it")
    print("\n".join(rows) if rows else "Nothing is waiting on the human.")


# ----------------------------------------------------------------------------------------- tickets
def subject_revision(sw, action: str, subject: str) -> str:
    if action == "incident.resolve":
        r = sw.db.execute("SELECT * FROM incidents WHERE id=?", (int(subject),)).fetchone()
        if not r:
            raise core.SwarmError("No such incident.")
        return f"{r['revision']}:{r['state']}"
    if action == "usage.reconcile":
        r = core.usage_row(sw, subject)
        return f"{r['state']}:{r['source_hash'] or ''}"
    if action == "verification.reconcile":
        r = sw.db.execute("SELECT state FROM verification_runs WHERE id=?", (subject,)).fetchone()
    elif action == "execution.reconcile":
        r = sw.db.execute("SELECT state FROM executions WHERE id=?", (subject,)).fetchone()
    elif action == "allocation.reconcile":
        r = sw.db.execute("SELECT state FROM allocations WHERE task=? ORDER BY rowid DESC LIMIT 1", (subject,)).fetchone()
    elif action == "contract.extend.high_risk":
        c = core.current_contract(sw, subject)
        r = {"state": f"{c['id']}:{c['state']}:{c['extension_count']}"} if c else None
    else:
        r = None
    if not r:
        raise core.SwarmError(f"No such subject for {action}: {subject}.")
    return str(r["state"])


def subject_parties(sw, action: str, subject: str) -> set[str]:
    """Who may not review or approve: the subject task's owner and author, an incident's subject and reviewer."""
    parties, task = set(), None
    if action == "incident.resolve":
        r = sw.db.execute("SELECT * FROM incidents WHERE id=?", (int(subject),)).fetchone()
        review = core.incident_review(sw, r)
        parties |= {r["subject"], review["reviewer"], r["opened_by"]}
        task = r["task"]
    elif action == "usage.reconcile":
        task = core.usage_row(sw, subject)["task"]
    elif action == "contract.extend.high_risk" or action == "allocation.reconcile":
        task = subject
    elif action == "execution.reconcile":
        r = sw.db.execute("SELECT task, agent FROM executions WHERE id=?", (subject,)).fetchone()
        task, parties = (r["task"], {r["agent"]}) if r else (None, set())
    if task:
        t = sw.db.execute("SELECT assignee FROM tasks WHERE id=?", (task,)).fetchone()
        if t:
            parties.add(t["assignee"])
        parties |= {r[0] for r in sw.db.execute("SELECT DISTINCT owner FROM task_contracts WHERE task=?", (task,))}
    return {p for p in parties if p}


def recorded_namespace(sw, action: str, subject: str) -> str | None:
    if action == "usage.reconcile":
        raw = sw.meta(f"usage_supervisor:{subject}")
        return json.loads(raw).get("ns") if raw else None
    return sw.meta(f"supervisor_ns:{action}:{subject}")


def check_request(sw, arm, who: str, action: str, subject: str, args: dict) -> None:
    if action not in json.loads(arm["allow"]):
        raise core.SwarmError(f"{action} is not delegated by the current arm.")
    if who == core.HUMAN or sw.is_coordinator(who):
        raise core.SwarmError("The requester must be an agent other than the coordinator.")
    wait = waiting(sw, action, subject)
    minimum = deadhand_config(sw)["wait_min"]
    if not wait or core.minutes_since(wait["since"]) < minimum:
        raise core.SwarmError(
            f"The decision must have waited on the human for {minimum:g} min first (it starts when an agent is refused). "
            "`hivewire human pending` lists what is waiting."
        )
    if action in RECONCILES and recorded_namespace(sw, action, subject) != core.namespace_id():
        raise core.SwarmError("A reconcile is delegable only on the supervisor's own host and boot.")
    if action == "contract.extend.high_risk":
        if not 0 < float(args.get("minutes", 0)) <= MAX_HIGH_RISK_EXTENSION_MIN:
            raise core.SwarmError(f"A dead-hand high-risk extension is at most {MAX_HIGH_RISK_EXTENSION_MIN} minutes.")
        if sw.db.execute(
            "SELECT 1 FROM deadhand_tickets WHERE action=? AND subject=? AND state='consumed'", (action, subject)
        ).fetchone():
            raise core.SwarmError("Dead hand extends a high-risk contract once per task.")


def select_deputy(sw, arm, ticket) -> str | None:
    """The engine chooses; the coordinator never does. Longest-idle eligible live agent with standing."""
    eligible = set(json.loads(arm["deputies"]))
    excluded = subject_parties(sw, ticket["action"], ticket["subject"]) | {ticket["requester"], sw.coordinator()}
    pool = [
        a
        for a in sw.live_agents()
        if a["name"] in eligible
        and a["name"] not in excluded
        and proven(sw, a["name"])
        and not core.incident_subject(sw, a["name"])
        and not a["reviewing"]
    ]
    pool.sort(key=lambda a: (bool(a["task"]), a["heartbeat_at"] or ""))
    return pool[0]["name"] if pool else None


def assign_waiting(sw) -> None:
    arm = active_arm(sw)
    if not arm:
        return
    for t in sw.db.execute("SELECT * FROM deadhand_tickets WHERE state='waiting' AND arm=?", (arm["id"],)).fetchall():
        deputy = select_deputy(sw, arm, t)
        if deputy:
            cur = sw.db.execute(
                "INSERT INTO deadhand_delegations(ticket,deputy,capability,created_at,expires_at) VALUES(?,?,'deadhand.review',?,?)",
                (t["id"], deputy, core.iso(), t["expires_at"]),
            )
            sw.db.execute(
                "UPDATE deadhand_tickets SET state='requested', deputy=?, delegation=? WHERE id=?", (deputy, cur.lastrowid, t["id"])
            )
            sw.message(
                "swarm",
                deputy,
                f"Dead-hand ticket D{t['id']}: review {t['action']} {t['subject']} independently, then "
                f"`hivewire deadhand review {t['id']} --verdict approve|reject --evidence ...` with SWARM_TOKEN set.",
                kind="review_request",
                priority="critical",
            )
            sw.event("deadhand_deputy_selected", "engine", None, f"D{t['id']}: {deputy}")


def ticket_row(sw, ident: int):
    row = sw.db.execute("SELECT * FROM deadhand_tickets WHERE id=?", (ident,)).fetchone()
    if not row:
        raise core.SwarmError("No such dead-hand ticket; `hivewire deadhand status` lists them.")
    return row


def void(sw, ident: int, reason: str) -> None:
    sw.db.execute("UPDATE deadhand_tickets SET state='void', void_reason=? WHERE id=?", (reason, ident))
    sw.db.execute("UPDATE deadhand_delegations SET revoked_at=? WHERE ticket=? AND revoked_at IS NULL", (core.iso(), ident))
    sw.event("deadhand_ticket_void", "engine", None, f"D{ident}: {reason}")


def still_bound(sw, ticket) -> None:
    import swarm_deputy

    if ticket["coordinator_term"] != swarm_deputy.coordinator_term(sw):
        raise core.SwarmError("The coordination term changed since the request; request again.")
    if subject_revision(sw, ticket["action"], ticket["subject"]) != ticket["subject_rev"]:
        raise core.SwarmError("The subject changed since the request; request again.")
    if core.utcnow() >= core.parse(ticket["expires_at"]):
        raise core.SwarmError("The ticket expired with its arm.")


def parse_args(pairs: list[str]) -> dict:
    out = {}
    for item in pairs or []:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise core.SwarmError("--arg takes key=value.")
        out[key] = value
    return out


def canonical(action: str, args: dict) -> dict:
    """The gated arguments a ticket binds; the consuming command must present exactly these."""
    keys = {
        "incident.resolve": ("outcome", "reason"),
        "contract.extend.high_risk": ("minutes", "reason"),
    }.get(action, ("reason",))
    missing = [k for k in keys if not str(args.get(k, "")).strip()]
    if missing:
        raise core.SwarmError(f"{action} binds --arg {' --arg '.join(k + '=...' for k in missing)}.")
    out = {k: str(args[k]) for k in keys}
    if "minutes" in out:
        out["minutes"] = f"{float(out['minutes']):g}"
    return out


def cmd_deadhand(sw, a) -> None:
    action = a.deadhand_action
    if action == "arm":
        return cmd_arm(sw, a)
    if action == "disarm":
        return cmd_disarm(sw, a)
    if action == "verify-agent":
        return cmd_verify_agent(sw, a)
    who = a.as_ or core.HUMAN
    import swarm_deputy

    with sw.tx():
        sw.sweep()
        assign_waiting(sw)
        if action == "status":
            arm = active_arm(sw)
            print(f"armed until {arm['until']}" if arm else "dead hand is off")
            for t in sw.db.execute("SELECT * FROM deadhand_tickets ORDER BY id DESC LIMIT 20"):
                print(f"D{t['id']} {t['action']} {t['subject']}: {t['state']}, deputy {t['deputy'] or '-'}, approver {t['approver'] or '-'}")
            return
        if action == "veto":
            if who != core.HUMAN:
                raise core.SwarmError("Only the human vetoes a dead-hand ticket.")
            t = ticket_row(sw, a.ticket)
            if t["state"] not in OPEN_TICKETS:
                raise core.SwarmError(f"D{t['id']} is {t['state']}; only an unconsumed ticket can be vetoed.")
            sw.db.execute("UPDATE deadhand_tickets SET state='vetoed', void_reason=? WHERE id=?", (core.bounded_text(sw, a.reason), t["id"]))
            sw.event("deadhand_vetoed", core.HUMAN, None, f"D{t['id']}: {a.reason}")
            print(f"D{t['id']} vetoed")
            return
        arm = active_arm(sw)
        if not arm:
            raise core.SwarmError("Dead hand is not armed. Only the human arms it: `hivewire deadhand arm --until T`.")
        if action == "request":
            sw.require_agent(who)
            args = canonical(a.action, parse_args(a.arg))
            check_request(sw, arm, who, a.action, a.subject, args)
            if len(a.reason.strip()) < core.MIN_ANSWER:
                raise core.SwarmError("--reason: why this cannot wait for the human.")
            cur = sw.db.execute(
                "INSERT INTO deadhand_tickets(action,subject,args,args_hash,subject_rev,coordinator_term,requester,arm,state,reason,created_at,expires_at) "
                "VALUES(?,?,?,?,?,?,?,?,'waiting',?,?,?)",
                (
                    a.action,
                    a.subject,
                    json.dumps(args),
                    core.request_hash(args),
                    subject_revision(sw, a.action, a.subject),
                    swarm_deputy.coordinator_term(sw),
                    who,
                    arm["id"],
                    core.bounded_text(sw, a.reason),
                    core.iso(),
                    arm["until"],
                ),
            )
            sw.event("deadhand_requested", who, None, f"D{cur.lastrowid}: {a.action} {a.subject}")
            assign_waiting(sw)
            t = ticket_row(sw, cur.lastrowid)
            print(f"D{t['id']} " + (f"goes to deputy {t['deputy']} for review" if t["deputy"] else "waits for an eligible deputy"))
            return
        t = ticket_row(sw, a.ticket)
        token = presented_token(getattr(a, "token_stdin", False))
        if not token_valid(sw, who, token) or not proven(sw, who):
            raise core.SwarmError("Present your current join token (SWARM_TOKEN or --token-stdin); an unproven name cannot sign.")
        still_bound(sw, t)
        if action == "review":
            if t["state"] != "requested" or t["deputy"] != who:
                raise core.SwarmError(f"D{t['id']} is not waiting for your review.")
            d = sw.db.execute("SELECT * FROM deadhand_delegations WHERE id=?", (t["delegation"],)).fetchone()
            if not d or d["revoked_at"] or d["deputy"] != who:
                raise core.SwarmError("Your dead-hand delegation for this ticket is not valid.")
            if len(a.evidence.strip()) < core.MIN_ANSWER:
                raise core.SwarmError("--evidence: what you checked, independently.")
            state = "reviewed" if a.verdict == "approve" else "rejected"
            sw.db.execute(
                "UPDATE deadhand_tickets SET state=?, verdict=?, evidence=?, reviewed_at=? WHERE id=?",
                (state, a.verdict, core.bounded_text(sw, a.evidence), core.iso(), t["id"]),
            )
            sw.event("deadhand_reviewed", who, None, f"D{t['id']}: {a.verdict}")
            if state == "reviewed":
                sw.notify_coordinator(f"Dead-hand ticket D{t['id']} was reviewed by {who}; `hivewire deadhand approve {t['id']} --reason ...`.")
            print(f"D{t['id']} {state}")
            return
        if action == "approve":
            if t["state"] != "reviewed" or not sw.is_coordinator(who):
                raise core.SwarmError(f"D{t['id']} needs a deputy's approval first, and only the coordinator approves it.")
            conflicted = subject_parties(sw, t["action"], t["subject"]) | {t["deputy"], t["requester"]}
            if who in conflicted or core.incident_subject(sw, who):
                raise core.SwarmError("The approver must not be the deputy, the requester or a party to the subject.")
            if deadhand_config(sw)["require_distinct_model"] and (sw.agent(who)["model"] or "") == (sw.agent(t["deputy"])["model"] or ""):
                raise core.SwarmError("[deadhand] require_distinct_model: the deputy and the coordinator run the same model.")
            if len(a.reason.strip()) < core.MIN_ANSWER:
                raise core.SwarmError("--reason: why you approve.")
            sw.db.execute(
                "UPDATE deadhand_tickets SET state='approved', approver=?, approval_reason=?, approved_at=? WHERE id=?",
                (who, core.bounded_text(sw, a.reason), core.iso(), t["id"]),
            )
            sw.event("deadhand_approved", who, None, f"D{t['id']}")
            print(f"D{t['id']} approved; run the gated command with `--deadhand {t['id']}` and SWARM_TOKEN set")
            return


def consume(sw, who: str, ticket_id: int, action: str, subject: str, args: dict) -> str:
    """Called inside the gated action's own transaction, so the action and its single use commit together."""
    arm = active_arm(sw)
    if not arm:
        raise core.SwarmError("Dead hand is not armed; this decision needs the human.")
    t = ticket_row(sw, ticket_id)
    if t["state"] != "approved" or t["approver"] != who:
        raise core.SwarmError(f"D{ticket_id} is {t['state']}; only its approver may use an approved ticket, once.")
    if t["action"] != action or t["subject"] != str(subject) or t["args_hash"] != core.request_hash(canonical(action, args)):
        raise core.SwarmError(f"D{ticket_id} authorises different arguments; request a new ticket.")
    if not token_valid(sw, who, presented_token()) or not proven(sw, who):
        raise core.SwarmError("Present your current join token in SWARM_TOKEN to use a dead-hand ticket.")
    still_bound(sw, t)
    sw.db.execute("UPDATE deadhand_tickets SET state='consumed', consumed_at=? WHERE id=?", (core.iso(), ticket_id))
    sw.db.execute("UPDATE deadhand_delegations SET revoked_at=? WHERE ticket=? AND revoked_at IS NULL", (core.iso(), ticket_id))
    sw.set_meta(f"human_waiting:{action}:{subject}", None)
    attribution = f"dead-hand authority D{ticket_id}: reviewed by {t['deputy']}, approved by {who}, armed by the human until {arm['until']}"
    sw.event("deadhand_consumed", who, None, attribution)
    return attribution


def blocks_coordinator_return(sw, name: str) -> str | None:
    if sw.db.execute("SELECT 1 FROM deadhand_tickets WHERE state='approved' LIMIT 1").fetchone():
        return "a dead-hand ticket is approved but not yet used"
    if sw.db.execute(
        "SELECT 1 FROM deadhand_tickets WHERE state IN ('waiting','requested','reviewed','approved') "
        "AND (deputy=? OR requester=? OR approver=?) LIMIT 1",
        (name, name, name),
    ).fetchone():
        return "an open dead-hand ticket names you"
    return None


def add_parser(add) -> None:
    import argparse

    dp = add("deadhand", cmd_deadhand, "human-armed delegation of a few human-only decisions")
    dsub = dp.add_subparsers(dest="deadhand_action", required=True)

    def sub(name, help_):
        p = dsub.add_parser(name, help=help_)
        p.add_argument("--as", dest="as_", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return p

    p = sub("arm", "human, at a terminal: arm until a time")
    p.add_argument("--until", required=True)
    p.add_argument("--allow", default="", help="comma-separated subset of: " + ", ".join(ALLOWLIST))
    p.add_argument("--deputies", default="", help="eligible reviewers; default: agents live now that were not spawned")
    sub("disarm", "human: turn it off")
    p = sub("verify-agent", "human, at a terminal: restore an unproven name's eligibility")
    p.add_argument("name")
    sub("status", "the arm and recent tickets")
    p = sub("request", "an agent other than the coordinator: ask for one bounded decision")
    p.add_argument("action", choices=ALLOWLIST)
    p.add_argument("subject")
    p.add_argument("--arg", action="append", default=[], help="a gated argument, key=value")
    p.add_argument("--reason", required=True)
    for name in ("review", "approve"):
        p = sub(name, "the selected deputy reviews; then the coordinator approves")
        p.add_argument("ticket", type=lambda v: int(str(v).lstrip("Dd")))
        p.add_argument("--token-stdin", action="store_true", help="read the join token from stdin")
        if name == "review":
            p.add_argument("--verdict", choices=("approve", "reject"), required=True)
            p.add_argument("--evidence", required=True)
        else:
            p.add_argument("--reason", required=True)
    p = sub("veto", "human: cancel an unconsumed ticket")
    p.add_argument("ticket", type=lambda v: int(str(v).lstrip("Dd")))
    p.add_argument("--reason", required=True)
    hp = add("human", lambda sw, a: cmd_human_pending(sw, a), "decisions waiting on the human")
    hsub = hp.add_subparsers(dest="human_action", required=True)
    h = hsub.add_parser("pending", help="every decision waiting on the human, with the exact command")
    h.add_argument("--as", dest="as_", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
