"""Accept only six complete, matching-source Windows/Linux/macOS CI reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED = {(system, version) for system in ("Windows", "Linux", "Darwin") for version in ("3.11", "3.13")}


def validate(directory):
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in Path(directory).rglob("results.json")]
    seen, fingerprints, suites = set(), set(), set()
    for report in reports:
        key = (report.get("system"), ".".join(report.get("python_version", "").split(".")[:2]))
        if key in seen or key not in EXPECTED:
            raise ValueError(f"Duplicate or unexpected runtime: {key}")
        seen.add(key)
        if not report.get("ok") or not report.get("source_unchanged") or not report.get("exact_discovery_coverage"):
            raise ValueError(f"Incomplete, failed or changing-source result: {key}")
        cases = report.get("cases", [])
        ids = [c["id"] for c in cases]
        if not ids or len(ids) != len(set(ids)) or len(ids) != report.get("discovered"):
            raise ValueError(f"Incomplete test IDs: {key}")
        if any(c.get("outcome") not in ("passed", "skipped") for c in cases):
            raise ValueError(f"Failed test case: {key}")
        suites.add(tuple(sorted(ids)))
        fingerprint = report.get("source_fingerprint")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError(f"Missing source fingerprint: {key}")
        fingerprints.add(fingerprint)
    if seen != EXPECTED:
        raise ValueError(f"Missing platform reports: {sorted(EXPECTED - seen)}")
    if len(fingerprints) != 1 or len(suites) != 1:
        raise ValueError("Platform reports used different source inputs or test suites")
    return {"ok": True, "runtimes": sorted(seen), "source_fingerprint": next(iter(fingerprints)),
            "tests_per_runtime": len(next(iter(suites)))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.directory)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
