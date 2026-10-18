#!/usr/bin/env python3
"""Install the agents-collaboration skill.

Into the current repository, with every pointer agents look for (bash, zsh, Git Bash):
    curl -fsSL https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --all

The same from PowerShell:
    irm https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --all

Once for every repository on this machine (your home folder):
    curl -fsSL https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --user --claude

From a local checkout:
    python install.py --source path/to/agents-collaboration --project path/to/repo --all

What it does, and nothing else:
  1. downloads the skill files of one release (default: the tag below) and checks
     each against the SHA-256 in that release's MANIFEST.json;
  2. writes them to <repo>/.agents/skills/agents-collaboration/ (or, with --user,
     ~/.agents/skills/agents-collaboration/), refusing to overwrite files you
     edited since the last install unless --force;
  3. with --scaffold, in a repository: creates .agents/swarm/config.toml and
     backlog.md from the examples, only if they do not exist. Nothing about the
     project is assumed otherwise: the tool runs on defaults, and work is broken
     down with `swarm goal` rather than a pre-written backlog;
  4. --agents-md: adds a short marked section to AGENTS.md, read by opencode,
     Codex, Qoder, DeepSeek-TUI and others;
  5. --claude: adds .claude/skills/agents-collaboration/SKILL.md, a pointer that
     makes Claude Code list the skill;
  6. --all: both pointers.
Files it edits keep their own line endings and byte-order mark.

This file is ASCII on purpose: Windows PowerShell 5.1 pipes text to native
programs as ASCII, and any other character would arrive as '?'.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = "ifinsta/agents-collaboration"
DEFAULT_REF = "v0.3.1"
SKILL = "agents-collaboration"
SKILL_DIR = f"skills/{SKILL}"
MARK_START = "<!-- agents-collaboration:start -->"
MARK_END = "<!-- agents-collaboration:end -->"
STUB_MARK = "<!-- agents-collaboration:pointer -->"
AGENTS_SECTION = """{start}
## Working alongside other agents

This repository may have several coding agents working at once. Before changing
anything, read `{skill}` and follow it. In short: run `python {tool} environment`,
then `join`, take one task, answer the critical questions, plan in order, and
merge your work through the queue before taking another.
{end}"""
CLAUDE_STUB = """---
name: agents-collaboration
description: {description}
---

{mark}
# agents-collaboration

The full skill is installed at `{skill}`. Read that file now and follow it
exactly. The coordination tool is `python {tool}`.
"""


def fail(message: str) -> None:
    print(f"install: {message}", file=sys.stderr)
    sys.exit(2)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Source:
    def __init__(self, ref: str, local: Path | None):
        self.ref = ref
        self.local = local

    def label(self) -> str:
        return str(self.local) if self.local else f"github.com/{REPO}@{self.ref}"

    def read(self, rel: str) -> bytes:
        if self.local:
            path = self.local / rel
            if not path.is_file():
                fail(f"{path} does not exist")
            return path.read_bytes()
        url = f"https://raw.githubusercontent.com/{REPO}/{self.ref}/{rel}"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed https URL
                return response.read()
        except Exception as exc:  # noqa: BLE001 - every network failure means the same thing here
            fail(f"could not download {url}: {exc}")
        return b""


def read_keep_style(path: Path) -> tuple[str, str, bool]:
    """Text, its line ending and whether it had a BOM. Python's text mode would turn every
    line ending into CRLF on Windows, rewriting the whole file in the diff."""
    raw = path.read_bytes() if path.exists() else b""
    bom = raw.startswith(b"\xef\xbb\xbf")
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    return text, newline, bom


def write_keep_style(path: Path, text: str, newline: str, bom: bool) -> None:
    data = text.replace("\n", newline).encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)


def project_root(path: Path) -> Path:
    done = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=path, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        fail(f"{path} is not inside a git repository (use --user to install for every repository instead)")
    return Path(done.stdout.strip()).resolve()


def description_of(skill_md: bytes) -> str:
    match = re.search(r"^description:\s*(.+)$", skill_md.decode("utf-8"), re.M)
    return match.group(1).strip() if match else "Coordinate several coding agents in one repository."


def install(args: argparse.Namespace) -> None:
    if sys.version_info < (3, 11):  # noqa: UP036 - the installer may be piped into an older python
        fail("Python 3.11 or newer is required (the skill uses tomllib)")
    if args.all:
        args.agents_md = args.claude = True
    source = Source(args.ref, Path(args.source).resolve() if args.source else None)
    root = None if args.user and args.project is None else project_root(Path(args.project or ".").resolve())
    base = Path.home() if args.user else root
    if args.agents_md and root is None:
        fail("--agents-md needs a repository: add --project <path>")
    manifest = json.loads(source.read(f"{SKILL_DIR}/MANIFEST.json").decode("utf-8"))
    files = {}
    for name, digest in manifest["files"].items():
        data = source.read(f"{SKILL_DIR}/{name}").replace(b"\r\n", b"\n")  # a CRLF checkout is still the same file
        if sha256(data) != digest:
            fail(f"{name} does not match the release manifest; refusing to install a damaged file")
        files[name] = data

    dest = base / ".agents" / "skills" / SKILL
    record_path = dest / "INSTALLED.json"
    if dest.exists() and not args.force:
        if not record_path.exists():
            fail(f"{dest} exists but was not installed by this installer; use --force to replace it")
        previous = json.loads(record_path.read_text(encoding="utf-8"))
        edited = [
            name
            for name, digest in previous.get("files", {}).items()
            if (dest / name).exists() and sha256((dest / name).read_bytes()) != digest
        ]
        if edited:
            fail(
                "these installed files were edited locally: "
                + ", ".join(edited)
                + ". Move your changes upstream, or use --force to discard them"
            )

    shown = "~" if args.user else "."
    actions = []
    if not args.dry_run:
        dest.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        actions.append(f"write {shown}/.agents/skills/{SKILL}/{name}")
        if not args.dry_run:
            (dest / name).write_bytes(data)
    record = {
        "source": source.label(),
        "ref": args.ref if not args.source else "local",
        "version": manifest.get("version", ""),
        "scope": "user" if args.user else "project",
        "installed_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "files": {name: sha256(data) for name, data in files.items()},
    }
    if not args.dry_run:
        record_path.write_bytes((json.dumps(record, indent=2) + "\n").encode("utf-8"))

    if args.user:
        skill_ref = (dest / "SKILL.md").as_posix()
        tool_ref = (dest / "swarm.py").as_posix()
    else:
        skill_ref = f".agents/skills/{SKILL}/SKILL.md"
        tool_ref = f".agents/skills/{SKILL}/swarm.py"

    if root is not None and args.scaffold:
        swarm_dir = root / ".agents" / "swarm"
        for example, target in (("examples/config.toml", "config.toml"), ("examples/backlog.md", "backlog.md")):
            path = swarm_dir / target
            if path.exists():
                actions.append(f"keep  .agents/swarm/{target} (exists)")
                continue
            actions.append(f"create .agents/swarm/{target} from {example}")
            if not args.dry_run:
                swarm_dir.mkdir(parents=True, exist_ok=True)
                path.write_bytes(source.read(example))

    if args.agents_md:
        agents = root / "AGENTS.md"
        text, newline, bom = read_keep_style(agents)
        section = AGENTS_SECTION.format(start=MARK_START, end=MARK_END, skill=skill_ref, tool=tool_ref)
        if MARK_START in text and MARK_END in text:
            head, rest = text.split(MARK_START, 1)
            new = head + section + rest.split(MARK_END, 1)[1]
        else:
            new = text.rstrip("\n") + ("\n\n" if text else "") + section + "\n"
        if new != text:
            actions.append("update AGENTS.md (marked section)")
            if not args.dry_run:
                write_keep_style(agents, new, newline, bom)

    if args.claude:
        stub = base / ".claude" / "skills" / SKILL / "SKILL.md"
        if stub.exists() and STUB_MARK not in stub.read_text(encoding="utf-8", errors="replace"):
            fail(f"{stub} exists and is not this installer's pointer; move it, or install without --claude")
        content = CLAUDE_STUB.format(
            description=description_of(files["SKILL.md"]), mark=STUB_MARK, skill=skill_ref, tool=tool_ref
        )
        actions.append(f"write {shown}/.claude/skills/{SKILL}/SKILL.md (Claude Code pointer)")
        if not args.dry_run:
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.write_bytes(content.encode("utf-8"))

    where = str(dest) if args.user else str(root)
    print(f"agents-collaboration {manifest.get('version', '')} from {source.label()} into {where}")
    for line in actions:
        print(f"  {'(dry run) ' if args.dry_run else ''}{line}")
    tool = f"python {tool_ref}"
    print("\nVerify, then start:")
    print(f"  {tool} version")
    print(f"  {tool} environment          # what this machine is, and the rules for it")
    print(f"  {tool} join --as <name> --kind <cli>")
    print(f'  {tool} goal new <id> "what you want to achieve"   # break a piece of work down')


def main() -> None:
    parser = argparse.ArgumentParser(description="Install the agents-collaboration skill.")
    parser.add_argument("--project", default=None, help="a path inside the target repository (default: here)")
    parser.add_argument("--user", action="store_true", help="install once into your home folder, for every repository")
    parser.add_argument("--ref", default=DEFAULT_REF, help=f"release tag or branch on GitHub (default {DEFAULT_REF})")
    parser.add_argument("--source", default="", help="install from a local checkout instead of GitHub")
    parser.add_argument("--agents-md", action="store_true", help="add a pointer section to AGENTS.md")
    parser.add_argument("--claude", action="store_true", help="add a Claude Code skill pointer in .claude/skills/")
    parser.add_argument("--all", action="store_true", help="--agents-md and --claude (in a repository)")
    parser.add_argument("--scaffold", action="store_true", help="create .agents/swarm/config.toml and backlog.md")
    parser.add_argument("--force", action="store_true", help="overwrite local edits to installed files")
    parser.add_argument("--dry-run", action="store_true", help="show what would change")
    args = parser.parse_args()
    if args.user and args.all and args.project is None:
        args.all, args.claude = False, True  # no repository to put AGENTS.md in
    install(args)


if __name__ == "__main__":
    main()
