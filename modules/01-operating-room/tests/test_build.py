"""Build verification tests for Module 01.

Ensures the CMake build succeeds, expected binaries are produced,
and the generated Python types are importable.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import MODULE_DIR, SRC_DIR


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

class TestBuild:
    """Validate the CMake build pipeline."""

    def test_cmake_configure_succeeds(self):
        """cmake -B build -S . exits cleanly."""
        result = subprocess.run(
            ["cmake", "-B", str(MODULE_DIR / "build"), "-S", str(MODULE_DIR)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"CMake configure failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_cmake_build_succeeds(self):
        """cmake --build build exits cleanly."""
        result = subprocess.run(
            ["cmake", "--build", str(MODULE_DIR / "build")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"CMake build failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    @pytest.mark.parametrize("binary", ["PatientSensor", "Orchestrator", "ArmController"])
    def test_binary_exists(self, binary: str):
        """Compiled C++ binary exists and is a file."""
        path = MODULE_DIR / "build" / binary
        assert path.is_file(), f"Binary not found: {path}"


# ---------------------------------------------------------------------------
# Generated types
# ---------------------------------------------------------------------------

class TestPythonTypes:
    """Validate that rtiddsgen-generated Python types are importable."""

    def test_types_file_exists(self):
        assert (SRC_DIR / "Types.py").is_file()

    def test_import_types(self):
        """Core DDS types can be imported from the generated module."""
        # Add src/ to path so the import works like it does for the apps
        if str(SRC_DIR) not in sys.path:
            sys.path.insert(0, str(SRC_DIR))

        from Types import (
            Common_DeviceStatus,
            Common_DeviceHeartbeat,
            SurgicalRobot_MotorControl,
            Orchestrator_DeviceCommand,
            PatientMonitor_Vitals,
        )

        # Smoke-check that we can instantiate them
        status = Common_DeviceStatus()
        assert hasattr(status, "device")
        assert hasattr(status, "status")

        vitals = PatientMonitor_Vitals()
        assert hasattr(vitals, "hr")
        assert hasattr(vitals, "spo2")
