#!/usr/bin/env python3
"""Kill all Module 04 threat application processes."""

import platform
import subprocess

UNIX_TARGETS = [
    ("pkill", "-f", "ThreatInjector.py"),
    ("pkill", "-f", "ThreatExfiltrator.py"),
    ("pkill", "-f", "threat_headless.py"),
]


def main() -> None:
    if platform.system() == "Windows":
        # On Windows, kill Python processes by window title or image name.
        # This is a broad approach; narrow as needed.
        subprocess.run(
            ["taskkill", "/F", "/IM", "python.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        for cmd in UNIX_TARGETS:
            result = subprocess.run(
                list(cmd),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            name = cmd[-1]
            if result.returncode == 0:
                print(f"Stopped {name}")

    print("All module 04 processes stopped.")


if __name__ == "__main__":
    main()
