"""Open the assignment's viewers once; owned workers retain their own lifetimes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
import webbrowser


def state(sw, key):
    try:
        value = json.loads(sw.meta(key) or "{}")
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def fresh(record, seconds):
    from swarm_core import seconds_since

    try:
        return bool(record.get("at")) and seconds_since(record["at"]) < seconds
    except (ValueError, TypeError):
        return False


def viewer_alive(sw):
    from swarm_core import pid_alive

    viewer = state(sw, "workspace_viewer")
    # Input prompts may pause refreshes. A still-live viewer keeps its lease;
    # pending GUI launches without a PID expire so failures remain retryable.
    return pid_alive(viewer["pid"]) if isinstance(viewer.get("pid"), int) else fresh(viewer, 30)


def touch_viewer(sw, token, *, close=False):
    """A heartbeat, not a PID to signal: a viewer can never stop another process."""
    from swarm_core import iso

    with sw.tx():
        viewer = state(sw, "workspace_viewer")
        if viewer.get("token") != token:
            return False
        if close:
            sw.set_meta("workspace_viewer", None)
        else:
            sw.set_meta("workspace_viewer", json.dumps({"token": token, "pid": os.getpid(), "at": iso()}))
    return True


def desktop_available(os_name):
    if os.environ.get("SWARM_HEADLESS") == "1" or os.environ.get("CI", "").lower() in ("1", "true"):
        return False
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    return os_name != "linux" or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def terminal_plan(root, board, token, os_name, has=shutil.which, display=True):
    """One native window containing the manager's dynamic execution tabs."""
    from swarm_core import LAUNCHER, terminal_window

    command = [sys.executable, str(LAUNCHER), "sessions", "--workspace-id", token]
    if not display:
        return None
    if os_name == "windows":
        if has("wt"):
            # No cmd.exe or shell interpolation; WT treats semicolons as separators.
            if any(";" in value for value in [str(root), *command]):
                return {"argv": [*command, "--workspace-console"], "new_console": True}
            return {"argv": ["wt", "-w", f"hivewire-{board}", "new-tab", "-d", str(root),
                             "--title", "Hivewire sessions", *command], "new_console": False}
        return {"argv": [*command, "--workspace-console"], "new_console": True}
    wrapped = ["sh", "-c", f"cd {shlex.quote(str(root))} && exec {shlex.join(command)}"]
    window = terminal_window(os_name, has, wrapped, display)
    return {"argv": window, "new_console": False} if window else None


def launch_terminal(plan, root):
    from swarm_core import background_flags

    env = os.environ.copy()
    env.pop("SWARM_AS", None)  # the visible operator console acts as the human
    flags = ({"creationflags": 0x00000010} if plan["new_console"] else background_flags()) if os.name == "nt" else {"start_new_session": True}
    return subprocess.Popen(plan["argv"], cwd=root, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)


def ensure_dashboard(sw):
    """Reuse the shared authenticated loopback server, or start a hidden observer."""
    from swarm_core import LAUNCHER, background_flags
    import swarm_web

    quote = subprocess.list2cmdline if os.name == "nt" else shlex.join
    entry = swarm_web.register(sw, quote([sys.executable, str(LAUNCHER)]), str(LAUNCHER))
    there = swarm_web.running()
    if there:
        return entry, there
    flags = background_flags() if os.name == "nt" else {"start_new_session": True}
    child = subprocess.Popen([sys.executable, str(LAUNCHER), "dashboard", "--web", "--observe", "--no-open"],
                             cwd=sw.main_root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, **flags)
    until = time.monotonic() + 10
    while time.monotonic() < until:
        there = swarm_web.running()
        if there:
            return entry, there
        if child.poll() is not None:
            break
        time.sleep(0.1)
    raise OSError("Dashboard did not become ready; run `hivewire dashboard --web` to inspect startup.")


def open_workspace(sw, *, no_open=False, reopen=False, dry_run=False):
    from swarm_core import detect_environment, iso, redact_text
    import swarm_web

    os_name = detect_environment(sw.main_root)["os"]
    board = swarm_web.board_id(sw.dir / "swarm.db")
    token = uuid.uuid4().hex
    plan = terminal_plan(sw.main_root, board, token, os_name, display=desktop_available(os_name) and not no_open)
    if dry_run:
        return {"dry_run": True, "dashboard": "reuse or start a hidden loopback observer",
                "terminal": "open one session manager with live agent tabs" if plan else "manual: hivewire sessions",
                "browser": "open once" if desktop_available(os_name) and not no_open else "disabled"}
    # Claim before any subprocess/browser work; no SQLite lock is held while starting viewers.
    with sw.tx():
        if fresh(state(sw, "workspace_opening"), 45):
            return {"dashboard": "starting", "terminal": "starting", "browser": "starting", "warnings": []}
        sw.set_meta("workspace_opening", json.dumps({"token": token, "at": iso()}))
    result = {"dashboard": "unavailable", "terminal": "manual: hivewire sessions", "browser": "disabled", "warnings": []}
    try:
        try:
            entry, there = ensure_dashboard(sw)
            result["dashboard"] = "ready"
            # Do not expose the capability token in JSON, logs or event descriptions.
            identity = hashlib.sha256(f"{there['port']}:{there['token']}".encode()).hexdigest()
            if desktop_available(os_name) and not no_open:
                if state(sw, "workspace_browser").get("server") == identity and not reopen:
                    result["browser"] = "already opened"
                elif webbrowser.open(swarm_web.link(there["port"], there["token"], entry["id"])):
                    with sw.tx():
                        sw.set_meta("workspace_browser", json.dumps({"server": identity, "at": iso()}))
                    result["browser"] = "opened"
                else:
                    result["browser"] = "unavailable"
                    result["warnings"].append("No browser accepted the request; use `hivewire dashboard --web` for the private link.")
        except (OSError, webbrowser.Error) as exc:
            result["warnings"].append(redact_text(str(exc)))
        if not no_open and viewer_alive(sw):
            result["terminal"] = "already running"
        elif plan:
            with sw.tx():
                sw.set_meta("workspace_viewer", json.dumps({"token": token, "at": iso()}))
            try:
                child = launch_terminal(plan, sw.main_root)
                # GUI terminal launchers can return before their shell starts. The
                # actual session viewer claims the pending lease and sends heartbeats.
                code = child.poll()
                if code not in (None, 0):
                    raise OSError(f"Terminal launcher exited with code {code}; run `hivewire sessions` in your terminal.")
                result["terminal"] = "opening"
            except OSError as exc:
                touch_viewer(sw, token, close=True)
                result["warnings"].append(redact_text(str(exc)))
        with sw.tx():
            sw.event("workspace_opened", None, None, json.dumps(result))
        return result
    finally:
        with sw.tx():
            if state(sw, "workspace_opening").get("token") == token:
                sw.set_meta("workspace_opening", None)


def valid_token(value):
    return bool(re.fullmatch(r"[0-9a-f]{32}", value or ""))
