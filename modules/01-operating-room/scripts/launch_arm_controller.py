#!/usr/bin/env python3
"""Launch ArmController only (used by Module 03 — Remote Teleoperation)."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / ".." / ".." / ".." / "system_arch" / "scripts"))
import platform_setup
import xml_setup

if __name__ == "__main__":
    env = xml_setup.setup_env()

    child = subprocess.Popen([platform_setup.find_executable("ArmController")], env=env)
    child.wait()
