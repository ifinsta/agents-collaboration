import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

base = Path(__file__).resolve().parent
root = Path('C:/Users/user/CascadeProjects/agents-collaboration')
name, runtime, *modules = sys.argv[1:]
paths = [root / 'install.py', root / 'scripts/make_manifest.py', root / 'examples/simulate.py', root / 'docs/simulation.md']
paths += [p for folder in ('skills', 'tests') for p in (root / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]

def hashes():
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

before = hashes()
command = [runtime, '-m', 'unittest', *modules, '-v']
start = time.monotonic()
with (base / (name + '.log')).open('wb') as log:
    result = subprocess.run(command, cwd=root / 'tests', stdout=log, stderr=subprocess.STDOUT, check=False)
after = hashes()
report = {'exit_code': result.returncode, 'command': command, 'elapsed_seconds': round(time.monotonic() - start, 3), 'runtime': subprocess.check_output([runtime, '--version'], text=True).strip(), 'source_unchanged': before == after, 'inputs': before, 'core_sha256': before['skills\\agents-collaboration\\swarm_core.py'], 'log_sha256': hashlib.sha256((base / (name + '.log')).read_bytes()).hexdigest()}
(base / (name + '.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'inputs'}))
sys.exit(result.returncode)
