#!/usr/bin/env python3
"""Install the agents-collaboration skill into a git repository.

From GitHub (bash, zsh, Git Bash):
    curl -fsSL https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --agents-md

From GitHub (PowerShell):
    irm https://raw.githubusercontent.com/ifinsta/agents-collaboration/main/install.py | python - --agents-md

From a local checkout:
    python install.py --source path/to/agents-collaboration --project path/to/repo

What it does, and nothing else:
  1. downloads the skill files of one release (default: the tag below) and checks
     each against the SHA-256 in that release's MANIFEST.json;
  2. writes them to <repo>/.agents/skills/agents-collaboration/, refusing to
     overwrite files you edited since the last install (unless --force);
  3. creates .agents/swarm/config.toml and .agents/swarm/backlog.md from the
     examples, only if they do not exist;
  4. with --agents-md, adds (or refreshes) a short marked section in AGENTS.md so
     every agent CLI that reads AGENTS.md finds the skill.

This file is ASCII on purpose: Windows PowerShell 5.1 pipes text to native
programs as ASCII, and any other character would arrive as '?'.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = "ifinsta/agents-collaboration"
DEFAULT_REF = "v0.1.1"
SKILL = "agents-collaboration"
SKILL_DIR = f"skills/{SKILL}"
MARK_START = "<!-- agents-collaboration:start -->"
MARK_END = "<!-- agents-collaboration:end -->"
AGENTS_SECTION = """{start}
## Working alongside other agents

This repository may have several coding agents working at once. Before changing
anything, read `.agents/skills/agents-collaboration/SKILL.md` and follow it. In short:
run `python .agents/skills/agents-collaboration/swarm.py environment`, then `join`,
take one task, answer the critical questions, plan in order, and merge your work
through the queue before taking another.
{end}"""


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


def project_root(path: Path) -> Path:
    done = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=path, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        fail(f"{path} is not inside a git repository")
    return Path(done.stdout.strip()).resolve()


def install(args: argparse.Namespace) -> None:
    if sys.version_info < (3, 11):  # noqa: UP036 - the installer may be piped into an older python
        fail("Python 3.11 or newer is required (the skill uses tomllib)")
    source = Source(args.ref, Path(args.source).resolve() if args.source else None)
    root = project_root(Path(args.project).resolve())
    manifest = json.loads(source.read(f"{SKILL_DIR}/MANIFEST.json").decode("utf-8"))
    files = {}
    for name, digest in manifest["files"].items():
        data = source.read(f"{SKILL_DIR}/{name}").replace(b"\r\n", b"\n")  # a CRLF checkout is still the same file
        if sha256(data) != digest:
            fail(f"{name} does not match the release manifest; refusing to install a damaged file")
        files[name] = data

    dest = root / ".agents" / "skills" / SKILL
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

    actions = []
    if not args.dry_run:
        dest.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        actions.append(f"write .agents/skills/{SKILL}/{name}")
        if not args.dry_run:
            (dest / name).write_bytes(data)
    record = {
        "source": source.label(),
        "ref": args.ref if not args.source else "local",
        "version": manifest.get("version", ""),
        "installed_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "files": {name: sha256(data) for name, data in files.items()},
    }
    if not args.dry_run:
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

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
        text = agents.read_text(encoding="utf-8") if agents.exists() else ""
        section = AGENTS_SECTION.format(start=MARK_START, end=MARK_END)
        if MARK_START in text and MARK_END in text:
            head, rest = text.split(MARK_START, 1)
            tail = rest.split(MARK_END, 1)[1]
            new = head + section + tail
        else:
            new = text.rstrip("\n") + ("\n\n" if text else "") + section + "\n"
        if new != text:
            actions.append("update AGENTS.md (marked section)")
            if not args.dry_run:
                agents.write_text(new, encoding="utf-8")

    print(f"agents-collaboration {manifest.get('version', '')} from {source.label()} into {root}")
    for line in actions:
        print(f"  {'(dry run) ' if args.dry_run else ''}{line}")
    tool = f"python .agents/skills/{SKILL}/swarm.py"
    print("\nNext:")
    print(f"  {tool} environment          # what this machine is, and the rules for it")
    print("  edit .agents/swarm/config.toml and .agents/swarm/backlog.md for this project")
    print(f"  {tool} init                 # import the backlog")
    print(f"  {tool} join --as <name> --kind <cli>")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install the agents-collaboration skill into a git repository.")
    parser.add_argument("--project", default=".", help="a path inside the target repository (default: here)")
    parser.add_argument("--ref", default=DEFAULT_REF, help=f"release tag or branch on GitHub (default {DEFAULT_REF})")
    parser.add_argument("--source", default="", help="install from a local checkout instead of GitHub")
    parser.add_argument("--agents-md", action="store_true", help="add a pointer section to AGENTS.md")
    parser.add_argument("--force", action="store_true", help="overwrite local edits to installed files")
    parser.add_argument("--dry-run", action="store_true", help="show what would change")
    install(parser.parse_args())


if __name__ == "__main__":
    main()
