#!/usr/bin/env python3
"""Build the Module 01 C++ applications using CMake."""

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_DIR = SCRIPT_DIR.parent
BUILD_DIR = MODULE_DIR / "build"


def main() -> None:
    BUILD_DIR.mkdir(exist_ok=True)
    subprocess.run(
        ["cmake", "-B", str(BUILD_DIR), "-S", str(MODULE_DIR)], check=True
    )
    subprocess.run(["cmake", "--build", str(BUILD_DIR)], check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
