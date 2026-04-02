#!/usr/bin/env python3
"""Launch Operating Room apps (used by Module 03 — Remote Teleoperation)."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / ".." / ".." / ".." / "system_arch" / "scripts"))
import platform_setup
import xml_setup

if __name__ == "__main__":
    env = xml_setup.setup_env()

    processes = [
        platform_setup.find_executable("Orchestrator"),
        platform_setup.find_executable("PatientSensor"),
        [sys.executable, "src/Arm.py"],
        [sys.executable, "src/PatientMonitor.py"],
    ]

    children = []
    for cmd in processes:
        if isinstance(cmd, str):
            cmd = [cmd]
        children.append(subprocess.Popen(cmd, env=env))

    for child in children:
        child.wait()
