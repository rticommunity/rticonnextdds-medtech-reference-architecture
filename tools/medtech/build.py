#!/usr/bin/env python3
#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

"""Configure and build C++ modules for ``medtech.py build``."""

from __future__ import annotations

import platform
import subprocess

from . import module_runner, platform_setup

PROJECT_ROOT = module_runner.PROJECT_ROOT


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


def configure_command(args: list[str] | None = None) -> list[str]:
    args = args or []
    command = [
        "cmake",
        "-S",
        str(PROJECT_ROOT),
        "-B",
        str(PROJECT_ROOT / platform_setup.build_path()),
    ] + args

    platform_arg = _windows_cmake_platform()
    if platform_arg and not any(argument in ("-A", "--platform") for argument in args):
        command.extend(["-A", platform_arg])

    return command


def build_command(args: list[str] | None = None) -> list[str]:
    args = args or []
    command = ["cmake", "--build", str(PROJECT_ROOT / platform_setup.build_path())] + args

    if platform.system() == "Windows" and "--config" not in command:
        command.extend(["--config", "Release"])

    return command


def run_build(args: list[str]) -> None:
    idx = args.index("--") if "--" in args else len(args)
    for command in (configure_command(args[:idx]), build_command(args[idx + 1 :])):
        module_runner.print_command(command, PROJECT_ROOT)
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)
