#!/usr/bin/env python3
"""Build C++ modules via CMake.

Ensures a consistent build tree at ``build/<CONNEXTDDS_ARCH>/`` and
forwards any extra arguments to ``cmake --build``.

Usage:
    python3 build.py                          # configure + build all
    python3 build.py --target ArmController   # build a specific target
    python3 build.py --target module-01       # build all Module 01 targets
"""

import platform
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(PROJECT_ROOT / "resource" / "python"))
from scripts import platform_setup

BUILD_DIR = PROJECT_ROOT / "build" / platform_setup.get_connextdds_arch()


def _windows_cmake_platform() -> str | None:
    """Map a Connext architecture string to a CMake Visual Studio platform.

    Connext Windows arch names commonly begin with ``x64`` or ``i86``.
    ``x64`` maps to the Visual Studio ``x64`` platform, while the 32-bit
    variants map to ``Win32``.
    """
    if platform.system() != "Windows":
        return None

    arch = platform_setup.get_connextdds_arch().lower()
    if arch.startswith("x64"):
        return "x64"
    if arch.startswith(("i86", "x86")):
        return "Win32"
    return None


def _configure_command() -> list[str]:
    command = ["cmake", "-S", str(PROJECT_ROOT), "-B", str(BUILD_DIR)]

    platform_arg = _windows_cmake_platform()
    if platform_arg and not any(argument in ("-A", "--platform") for argument in sys.argv[1:]):
        command.extend(["-A", platform_arg])

    return command


def _build_command() -> list[str]:
    command = ["cmake", "--build", str(BUILD_DIR)] + sys.argv[1:]

    if platform.system() == "Windows" and "--config" not in command:
        command.extend(["--config", "Release"])

    return command


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    subprocess.run(_configure_command(), check=True)
    subprocess.run(_build_command(), check=True)


if __name__ == "__main__":
    main()

