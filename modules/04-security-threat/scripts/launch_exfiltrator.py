#!/usr/bin/env python3
"""Launch the Threat Exfiltrator GUI application.

Run from the modules/04-security-threat/ directory.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xml_setup

if __name__ == "__main__":
    env = xml_setup.setup_env()
    subprocess.run([sys.executable, "src/ThreatExfiltrator.py"], env=env, check=True)
