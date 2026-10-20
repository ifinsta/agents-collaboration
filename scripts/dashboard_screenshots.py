#!/usr/bin/env python3
"""Regenerate the dashboard screenshots used by the README and docs/web-dashboard.md.

    python scripts/dashboard_screenshots.py [--out docs/images] [--browser PATH]

It builds the demo board (examples/dashboard_demo.py) in a temporary directory, starts the dashboard on a free port
with throw-away state, captures each page with a headless Chromium-based browser (Edge, Chrome or Chromium), and stops
everything. Nothing in your own repositories or in ~/.agents is touched. Standard library only; the browser is the one
thing it cannot supply. The images are of seeded data (see the demo script), not of live agents.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))
import dashboard_demo  # noqa: E402

# (file name, route, width, height)
SHOTS = (
    ("dashboard-overview.png", "", 1440, 900),
    ("dashboard-team.png", "team", 1440, 900),
    ("dashboard-inbox.png", "inbox/decision", 1440, 900),
    ("dashboard-task.png", "task/H-ready", 1440, 580),
    ("dashboard-phone.png", "", 500, 960),
)
CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "google-chrome", "chromium", "chromium-browser", "microsoft-edge", "msedge",
)


def find_browser(given: str | None) -> str:
    for c in ([given] if given else CANDIDATES):
        found = shutil.which(c) or (c if c and os.path.exists(c) else None)
        if found:
            return found
    raise SystemExit("No Chromium-based browser found. Pass --browser PATH (Edge, Chrome or Chromium).")


def capture(browser: str, url: str, out: Path, width: int, height: int) -> bool:
    # Headless windows narrower than about 500 px are widened by the browser and the picture is then cropped, so the narrowest shot is 500 px.
    for mode in ("--headless=new", "--headless"):
        out.unlink(missing_ok=True)
        subprocess.run(
            [browser, mode, "--disable-gpu", "--hide-scrollbars", "--no-first-run", f"--window-size={width},{height}",
             "--virtual-time-budget=9000", f"--screenshot={out}", url],
            capture_output=True, timeout=120, check=False,
        )
        if out.exists() and out.stat().st_size > 2000:
            return True
    return False


def _writable_then_retry(func, path, _exc):
    try:
        os.chmod(path, 0o700)
        func(path)
    except OSError:
        pass


def scratch_dir() -> Path:
    """A throw-away directory. The task page shows its worktree path, so prefer a root-level directory over one under a user profile."""
    try:
        return Path(tempfile.mkdtemp(prefix="swarm-demo-", dir=Path.cwd().anchor))
    except OSError:
        return Path(tempfile.mkdtemp(prefix="swarm-demo-"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default=str(ROOT / "docs" / "images"))
    parser.add_argument("--browser")
    args = parser.parse_args()
    browser = find_browser(args.browser)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = scratch_dir()
    server = None
    try:
        repo = dashboard_demo.build(work / "shop")
        env = {**os.environ, "SWARM_WEB_HOME": str(work / "web"), "PYTHONUTF8": "1"}
        env.pop("SWARM_AS", None)
        server = subprocess.Popen(
            [sys.executable, str(dashboard_demo.SWARM), "dashboard", "--web", "--no-open", "--observe", "--port", "0"],
            cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        )
        lines: list[str] = []

        def pump():
            for line in server.stdout:
                lines.append(line)

        threading.Thread(target=pump, daemon=True).start()
        deadline = time.time() + 40
        url = None
        while time.time() < deadline and not url:
            for line in lines:
                m = re.search(r"(http://127\.0\.0\.1:\d+/\?t=\S+)", line)
                if m:
                    url = m.group(1)
            time.sleep(0.2)
        if not url:
            raise SystemExit("The dashboard did not start:\n" + "".join(lines))
        failed = []
        for name, route, width, height in SHOTS:
            ok = capture(browser, f"{url}#/{route}", out / name, width, height)
            print(("wrote " if ok else "FAILED ") + str(out / name))
            if not ok:
                failed.append(name)
        if failed:
            raise SystemExit(f"Could not capture: {', '.join(failed)}")
    finally:
        if server:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
        shutil.rmtree(work, **{("onexc" if sys.version_info >= (3, 12) else "onerror"): _writable_then_retry})  # git objects are read-only on Windows


if __name__ == "__main__":
    main()
