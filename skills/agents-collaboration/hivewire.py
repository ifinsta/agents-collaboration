#!/usr/bin/env python3
"""Hivewire: independent agents, accountable teamwork (https://github.com/ifinsta/hivewire).

Run it as:  python hivewire.py <command> --as <your-name>      (or: python hivewire.py -h)

This file is deliberately tiny. The tool is swarm_core.py. Python compiles a script it is RUN AS from source on every
start, but caches the bytecode of a module it IMPORTS, so keeping the code in a module saves most of a second per
command. Everything is re-exported here, so `import hivewire` gives the whole API.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path[:1]:
    sys.path.insert(0, HERE)

EXPECTED = "0.4.4"  # the swarm_core.py this launcher was released with

import swarm_core  # noqa: E402
from swarm_core import *  # noqa: E402,F401,F403

if __name__ == "__main__":
    if swarm_core.__version__ != EXPECTED:
        sys.stderr.write(
            f"hivewire: hivewire.py is v{EXPECTED} but swarm_core.py is v{swarm_core.__version__}: the install is "
            "half-updated. Reinstall:\n  curl -fsSL https://raw.githubusercontent.com/ifinsta/hivewire/"
            "main/install.py | python - --all\n"
        )
        sys.exit(2)
    sys.exit(swarm_core.main())
