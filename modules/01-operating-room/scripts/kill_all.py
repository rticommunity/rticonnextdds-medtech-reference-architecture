#!/usr/bin/env python3
"""Kill all Module 01 applications and RTI services."""

import platform
import subprocess

UNIX_TARGETS = [
    ("pkill", "ArmController"),
    ("pkill", "Orchestrator"),
    ("pkill", "PatientSensor"),
    ("pkill", "-f", "PatientMonitor.py"),
    ("pkill", "-f", "Arm.py"),
    ("pkill", "-f", "rtirecordingservice"),
    ("pkill", "-f", "rticlouddiscoveryservice"),
    ("pkill", "-f", "rtiroutingservice"),
]

WINDOWS_TARGETS = [
    "ArmController.exe",
    "Orchestrator.exe",
    "PatientSensor.exe",
    "python.exe",  # NOTE: kills all Python — narrow if needed
    "rtirecordingservice.bat",
    "rticlouddiscoveryservice.bat",
    "rtiroutingservice.bat",
]


def main() -> None:
    print("Killing all applications...")
    if platform.system() == "Windows":
        for name in WINDOWS_TARGETS:
            subprocess.run(
                ["taskkill", "/F", "/IM", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    else:
        for cmd in UNIX_TARGETS:
            subprocess.run(
                list(cmd),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    main()
