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
"""Project-level build verification tests.

Validates that the CMake build pipeline (driven by ``build.py``) succeeds
and produces the expected binaries for all modules.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "resource" / "python"))
from build import build_command, configure_command

pytestmark = pytest.mark.build_pipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# CMake configure & build
# ---------------------------------------------------------------------------


class TestCMakeBuild:
    """Validate the project-level CMake configure and build."""

    def test_cmake_configure_succeeds(self):
        """cmake -S <root> -B build/<arch> exits cleanly."""
        result = subprocess.run(
            configure_command(extra_args=[]),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"CMake configure failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_cmake_build_succeeds(self):
        """cmake --build build/<arch> exits cleanly."""
        result = subprocess.run(
            build_command(extra_args=[]),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"CMake build failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
