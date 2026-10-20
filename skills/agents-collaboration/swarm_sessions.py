"""Read-only session snapshots, bounded log excerpts and a portable terminal viewer.

Execution records and their creating supervisors remain the process authority.
This module never launches a process or writes a board.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat
import sys

CAPTURE_ID = re.compile(r"[a-f0-9]{32}\Z")
MAX_READ = 65536


def clean(text) -> str:
    """Untrusted output must not execute terminal escapes, including OSC links."""
    from swarm_core import redact_text

    text = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", str(text))
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = redact_text(text)
    return "".join(c for c in text if c in "\n\t" or (c.isprintable() and c != "\x1b"))


def _data(value, default):
    try:
        parsed = json.loads(value) if value else default
        return parsed if default is None or isinstance(parsed, type(default)) else default
    except (ValueError, TypeError):
        return default


def log_tail(directory: Path, execution: str, *, stream="worker", lines=100, after_bytes=None) -> dict:
    if stream not in ("worker", "supervisor") or not 1 <= lines <= 1000 or (after_bytes is not None and after_bytes < 0):
        raise ValueError("Use worker/supervisor and 1..1000 lines.")
    result = {"available": False, "stream": stream, "text": "", "truncated": False, "bytes_retained": 0}
    if not CAPTURE_ID.fullmatch(execution):
        return {**result, "reason": "This historical execution has no supported capture ID."}
    logs = Path(directory).resolve() / "logs"
    path = logs / (execution + (".supervisor" if stream == "supervisor" else "") + ".log")
    try:
        if logs.is_symlink() or logs.resolve() != logs or path.is_symlink():
            return {**result, "reason": "A linked log path is not served."}
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as fh:
            info = os.fstat(fh.fileno())
            named = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
                return {**result, "reason": "The log is not a regular captured file."}
            start = max(0, info.st_size - MAX_READ)
            if after_bytes is not None and after_bytes <= info.st_size:
                start = max(start, after_bytes)
            fh.seek(start)
            data = fh.read(MAX_READ)
            next_offset = fh.tell()
        text = clean(data.decode("utf-8", errors="replace")).expandtabs(4)
        rows = text.splitlines()
        return {**result, "available": True, "text": "\n".join(rows[-lines:]),
                "bytes_retained": info.st_size, "next_offset": next_offset,
                "truncated": bool(start > (after_bytes or 0) or len(rows) > lines)}
    except OSError:
        return {**result, "reason": "No readable retained log yet; inspect execution state and supervisor output."}


def listing(db, *, limit=200) -> dict:
    if not 1 <= limit <= 1000:
        raise ValueError("Session limit must be 1..1000.")
    records = db.execute(
        "SELECT e.*,a.kind FROM executions e LEFT JOIN agents a ON a.name=e.agent "
        "ORDER BY CASE WHEN e.state IN ('exited','terminated','failed','reconciled') THEN 1 ELSE 0 END, "
        "e.started_at DESC,e.id DESC LIMIT ?", (limit + 1,),
    ).fetchall()
    sessions = []
    for record in records[:limit]:
        row = dict(record)
        policy = _data(row.pop("policy", None), {})
        row.pop("argv", None)  # the session view does not need provider command arguments
        row["output"] = _data(row.get("output"), None)
        row["transport"] = policy.get("transport", "headless")
        row["timeout_action"] = policy.get("timeout_action", "cooperative")
        sessions.append(row)
    return {"sessions": sessions, "has_more": len(records) > limit}


def detail(db, directory: Path, execution: str, *, lines=100) -> dict | None:
    record = db.execute("SELECT * FROM executions WHERE id=?", (execution,)).fetchone()
    if record is None:
        return None
    row = dict(record)
    row["output"] = _data(row.get("output"), None)
    row["policy"] = _data(row.get("policy"), {})
    row.pop("argv", None)
    task = db.execute("SELECT * FROM tasks WHERE id=?", (row["task"],)).fetchone()
    task = dict(task) if task else None
    if task:
        task = {key: task.get(key) for key in ("id", "title", "state", "assignee", "epoch", "branch", "worktree", "plan", "steps", "integration_evidence")}
        for key, default in (("plan", {}), ("steps", []), ("integration_evidence", None)):
            task[key] = _data(task[key], default)
    events = [dict(r) for r in db.execute(
        "SELECT id,at,kind,agent,task,detail FROM events WHERE task=? AND (at>=? OR ? IS NULL) ORDER BY id DESC LIMIT 40",
        (row["task"], row["started_at"], row["started_at"]),
    )]
    worker = log_tail(directory, execution, lines=lines)
    if row["policy"].get("transport") == "terminal" and not worker["available"]:
        worker["reason"] = "Foreground output was streamed without a retained transcript; start headlessly for auditable output tabs."
    if isinstance(row["output"], dict) and row["output"].get("truncated"):
        worker["truncated"] = True
    return {"session": row, "task": task, "events": list(reversed(events)), "worker": worker,
            "supervisor": log_tail(directory, execution, stream="supervisor", lines=lines)}


def render(snapshot, selected, details, *, width=100, height=30, view=0, scroll=0, message="") -> str:
    width, height = max(20, width), max(8, height)
    rows = ["HIVEWIRE SESSIONS | workers run headlessly; closing this viewer leaves them running"]
    sessions = snapshot["sessions"]
    tabs = [f"{'[' if i == selected else ' '}{i+1}:{s['agent']} {s['state']}{']' if i == selected else ' '}" for i, s in enumerate(sessions)]
    # Keep the selected tab visible even when the pool history exceeds the terminal width.
    start = max(0, selected - 1)
    rows.append(" | ".join(tabs[start:]))
    if details:
        s = details["session"]
        rows += [f"{s['id']}  task={s['task']}  epoch={s['epoch']}  state={s['state']}  exit={s['exit_code']}",
                 "View: " + ("Worker output", "Supervisor diagnostics", "Task / evidence / events")[view]]
        if view < 2:
            capture = details[("worker", "supervisor")[view]]
            body = capture["text"] or capture.get("reason", "Waiting for output; headless CLIs have no interactive input.")
            if capture["truncated"]:
                body = "[Bounded excerpt; capture limits do not establish completion.]\n" + body
        else:
            body = "Current task state (may be newer than this execution):\n" + json.dumps(
                {"task": details["task"], "events": details["events"]}, ensure_ascii=False, indent=2,
            )
        content = clean(body).splitlines()
        room = max(1, height - 7)
        end = max(min(len(content), room), len(content) - scroll)
        rows.extend(content[max(0, end-room):end])
    else:
        rows += ["No workers yet. Press s, pick a CLI from the list and press Enter: the defaults do the rest.",
                 "Or from any terminal: hivewire spawn CLI --name NAME --task TASK"]
    rows = rows[:height-2]
    rows += ["" for _ in range(height-2-len(rows))]
    rows += [message, "Tab/Left/Right: session | v: output/audit | PgUp/PgDn: scroll | s: start | x: stop | q: detach"]
    return "\n".join(clean(line).expandtabs(4)[:width] for line in rows)


class TerminalKeys:
    """Read keys without curses (which is not included with Windows Python)."""

    def __enter__(self):
        self.saved = None
        if os.name != "nt":
            import termios
            import tty

            self.saved = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        else:
            import ctypes

            kernel = ctypes.windll.kernel32
            kernel.GetStdHandle.restype = ctypes.c_void_p
            kernel.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            kernel.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            self.handle = kernel.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetConsoleMode(self.handle, ctypes.byref(mode)):
                self.saved = mode.value
                ctypes.windll.kernel32.SetConsoleMode(self.handle, mode.value | 4)
        sys.stdout.write("\x1b[?1049h\x1b[?25l")
        return self

    def __exit__(self, *_):
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        if self.saved is not None:
            if os.name != "nt":
                import termios

                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.saved)
            else:
                import ctypes

                ctypes.windll.kernel32.SetConsoleMode(self.handle, self.saved)

    @contextmanager
    def cooked(self):
        if os.name != "nt":
            import termios
            import tty

            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.saved)
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()
        try:
            yield
        finally:
            if os.name != "nt":
                tty.setcbreak(sys.stdin.fileno())
            sys.stdout.write("\x1b[?25l")

    def read(self):
        if os.name == "nt":
            import msvcrt

            if not msvcrt.kbhit():
                return None
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                return {"K": "previous", "M": "next", "I": "older", "Q": "newer"}.get(msvcrt.getwch(), "")
        else:
            import select

            if not select.select([sys.stdin], [], [], 0)[0]:
                return None
            key = os.read(sys.stdin.fileno(), 1).decode("utf-8", errors="replace")
            if key == "\x1b":
                while select.select([sys.stdin], [], [], 0.01)[0] and len(key) < 8:
                    key += os.read(sys.stdin.fileno(), 1).decode("utf-8", errors="replace")
                return {"\x1b[D": "previous", "\x1b[C": "next", "\x1b[Z": "previous", "\x1b[5~": "older", "\x1b[6~": "newer"}.get(key, "")
        return {"\t": "next", "\x03": "q"}.get(key, key)


def dashboard_page(page: str) -> str:
    """Keep this audit view separate from the independently maintained dashboard layout."""
    marker = "\n// ---- loop\n"
    if page.count(marker) != 1:
        raise ValueError("The dashboard needs its session-view insertion point before the refresh loop.")
    return page.replace(marker, DASHBOARD_VIEW + marker, 1)


DASHBOARD_VIEW = r"""
// ---- retained sessions (read-only; state changes use the existing CLI)
TABS.splice(2, 0, ['sessions', 'Sessions', null]);
VIEWS.sessions = {
  async load(p) {
    const d = await get('/api/sessions');
    const id = p[1] || (d.sessions[0] && d.sessions[0].id);
    d.detail = id ? await get('/api/sessions/' + encodeURIComponent(id)) : null;
    d.stream = p[2] === 'supervisor' ? 'supervisor' : 'worker';
    return d;
  },
  render(d) {
    const selected = d.detail && d.detail.session;
    const tabs = h('nav', { class: 'row', 'aria-label': 'Worker sessions', style: { 'overflow-x': 'auto', 'max-width': '100%', 'white-space': 'nowrap', padding: '4px 0' } },
      d.sessions.map((s) => link('#/sessions/' + s.id, { class: 'btn' + (selected && s.id === selected.id ? ' on' : ''), 'aria-current': selected && s.id === selected.id ? 'page' : null },
        s.agent + ' (' + (s.kind || '?') + ') / ' + s.state + ' / ' + s.id.slice(-6))));
    const top = [h('div', { class: 'row wrap', style: { gap: '10px', 'align-items': 'baseline' } }, h('h1', null, 'Sessions'),
      h('span', { class: 'muted small' }, 'Headless workers under their supervisors. Closing this viewer leaves them running; failed and finished sessions stay here.')), tabs];
    if (!selected) return [...top, panel(h('div', { class: 'item' }, h('span', { class: 'm' }, 'No owned sessions yet'), h('span', { class: 'muted small' }, 'Start a worker on a task, or open every session in one terminal with tabs and start/stop controls:'), cmd('spawn CLI --name NAME --task TASK'), cmd('sessions')))];
    const capture = d.detail[d.stream];
    const excerpt = (text) => h('pre', { class: 'mono', style: { 'white-space': 'pre-wrap', 'overflow-wrap': 'anywhere', 'max-height': '60vh', overflow: 'auto', padding: '10px', margin: '0' } }, text);
    const streams = h('div', { class: 'row wrap' }, ...['worker', 'supervisor'].map((s) => link('#/sessions/' + selected.id + '/' + s, { class: 'btn' + (d.stream === s ? ' on' : ''), 'aria-current': d.stream === s ? 'page' : null }, s === 'worker' ? 'Worker output' : 'Supervisor diagnostics')));
    const t = d.detail.task;
    const audit = t ? panel(h('div', { class: 'item col' },
      h('b', { class: 'b' }, t.title + ' / ' + t.state),
      h('span', { class: 'muted' }, 'Current holder: ' + (t.assignee || 'unassigned')),
      t.epoch !== selected.epoch ? h('p', { class: 'note' }, 'This task has a newer or different assignment. Current evidence is shown below; this session ran at epoch ' + selected.epoch + '.') : null,
      t.branch ? h('span', { class: 'mono break' }, 'Branch: ' + t.branch) : null,
      t.worktree ? h('span', { class: 'mono break' }, 'Worktree: ' + t.worktree) : null,
      t.steps.length ? h('ol', null, t.steps.map((s) => h('li', { class: 'item col' }, h('b', null, (s.done ? 'Done: ' : 'Planned: ') + s.text), s.evidence ? h('span', { class: 'muted break' }, s.evidence) : null))) : h('p', { class: 'muted' }, 'No recorded plan steps yet.'),
      h('details', null, h('summary', { class: 'small' }, 'Integration evidence'), excerpt(JSON.stringify(t.integration_evidence, null, 2))),
      h('h2', null, 'Recent task events'),
      d.detail.events.length ? h('ol', null, d.detail.events.slice().reverse().map((e) => h('li', { class: 'item break' }, e.at + ' / ' + e.kind + ' / ' + (e.agent || '') + ': ' + (e.detail || '')))) : h('p', { class: 'muted' }, 'No task events for this session.'))) : empty('No retained task record.');
    return [...top,
      panel(h('div', { class: 'item col' }, h('b', { class: 'b' }, selected.agent + ' / ' + selected.state),
        h('span', { class: 'mono break' }, selected.id),
        h('div', { class: 'row wrap' }, taskLink(selected.task), h('span', null, 'epoch ' + selected.epoch), h('span', null, 'exit ' + (selected.exit_code == null ? 'not observed' : selected.exit_code))),
        selected.detail ? h('p', { class: 'muted break' }, selected.detail) : null,
        ['exited', 'terminated', 'failed', 'reconciled'].includes(selected.state) ? h('span', { class: 'muted' }, 'Session ended. Retained evidence remains available.') : cmd('execution stop ' + selected.id + ' --reason "reason for stop"', 'A policy-bound request, never a signal to a stored PID.'))),
      section('Captured output', streams, panel(capture.truncated ? h('div', { class: 'item muted' }, 'Bounded excerpt. Capture limits do not establish completion.') : null,
        excerpt(capture.text || capture.reason || 'Waiting for output. Headless sessions have no interactive input.'))),
      cmd('execution logs ' + selected.id + ' --stream ' + d.stream + ' --follow', 'Follow output; captured logs remain after exit.'),
      section('Audit: current task and recent task events', selected.task ? link('#/task/' + selected.task, { class: 'btn' }, 'Open task') : null,
        audit)];
  },
};
"""
