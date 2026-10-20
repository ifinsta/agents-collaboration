import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "skills/agents-collaboration"))
import swarm_core as core  # noqa: E402


def check(kind):
    ad = core.DEFAULTS["adapters"][kind]
    result = {"kind": kind, "installed": bool(shutil.which(ad["run"][0])), "live_provider_call": False}
    if result["installed"]:
        try:
            version = core.run(core.resolve_bin(ad["version"]), check=False, timeout=20)
            result["version"] = (version.stdout or version.stderr).strip().splitlines()[0][:100]
            result["headless_missing_options"] = core.missing_options([*ad["run"], *ad["model"], *ad["unattended"]], ad.get("help") or [ad["run"][0], "--help"])
            result["option_compatibility_pass"] = not result["headless_missing_options"]
        except Exception as exc:
            result["error"] = str(exc)[:400]
    return result


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(check, ("claude", "codex", "opencode", "qodercli")))
report = {"core_sha256": hashlib.sha256((root / "skills/agents-collaboration/swarm_core.py").read_bytes()).hexdigest(), "scope": "Installed headless CLI version/help compatibility; no authentication output or live provider request", "adapters": results}
Path(__file__).with_name("adapters.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
