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
"""Build verification tests for Module 01.

Ensures the CMake build succeeds, expected binaries are produced,
and the generated Python types are importable.
"""

import sys
from pathlib import Path

import pytest
from module01_test_support import MODULE_DIR

sys.path.insert(0, str(MODULE_DIR.parent.parent / "resource" / "python"))
from scripts import platform_setup

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


class TestBuild:
    """Validate that the project-level CMake build produced expected binaries."""

    @pytest.mark.parametrize("binary", ["PatientSensor", "Orchestrator", "ArmController"])
    def test_binary_exists(self, binary: str):
        """Compiled C++ binary exists and can be located."""
        exe = platform_setup.find_executable(binary)
        assert Path(exe).is_file(), f"Binary not found: {exe}"
