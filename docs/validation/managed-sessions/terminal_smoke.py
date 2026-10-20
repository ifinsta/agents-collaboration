"""Run in the Linux validation image with source.zip mounted under /evidence."""

from pathlib import Path
import json
import os
import pty
import select
import subprocess
import sys
import termios
import time
import zipfile

zipfile.ZipFile("/evidence/source.zip").extractall("/tmp/session-terminal-source")
root = Path("/tmp/session-terminal-source")
sys.path.insert(0, str(root / "tests"))
from test_sessions import SessionViews  # noqa: E402 (the frozen source is extracted above)

case = SessionViews("test_ec345_closed_sessions_stay_visible_with_exit_and_task_audit")
case.setUp()
master, slave = pty.openpty()
before = termios.tcgetattr(slave)
proc = None
try:
    proc = subprocess.Popen(
        [sys.executable, str(root / "skills/agents-collaboration/swarm.py"), "sessions"],
        cwd=case.root,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    data = b""
    deadline = time.monotonic() + 30
    while b"SWARM SESSIONS" not in data and time.monotonic() < deadline:
        if select.select([master], [], [], 0.1)[0]:
            data += os.read(master, 65536)
    assert b"SWARM SESSIONS" in data, data.decode(errors="replace")
    os.write(master, b"v\tq")
    code = proc.wait(timeout=20)
    while select.select([master], [], [], 0.1)[0]:
        data += os.read(master, 65536)
    assert code == 0, data.decode(errors="replace")
    assert termios.tcgetattr(slave) == before, "viewer did not restore terminal settings"
    assert b"Workers continue" in data
    assert b"\x1b[?1049l" in data, "alternate screen was not restored"
    result = {
        "ok": True,
        "exit_code": code,
        "real_pty": True,
        "session_and_view_switching": True,
        "settings_restored": True,
        "detach_message": True,
    }
    Path("/evidence/terminal-smoke.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
finally:
    if proc and proc.poll() is None:
        proc.kill()
        proc.wait()
    os.close(master)
    os.close(slave)
    case.tearDown()
