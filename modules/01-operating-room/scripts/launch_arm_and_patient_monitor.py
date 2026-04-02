#!/usr/bin/env python3
"""Launch Arm and PatientMonitor (used by Module 03 — Remote Teleoperation)."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xml_setup

if __name__ == "__main__":
    env = xml_setup.setup_env()

    processes = [
        [sys.executable, "src/Arm.py"],
        [sys.executable, "src/PatientMonitor.py"],
    ]

    children = []
    for cmd in processes:
        children.append(subprocess.Popen(cmd, env=env))

    for child in children:
        child.wait()
