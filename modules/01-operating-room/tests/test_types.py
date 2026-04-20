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
"""Type verification tests for Module 01.

Ensures the generated Python types are importable and have the expected
fields and enum members that this module's applications depend on.
"""

import sys
from pathlib import Path

import pytest
from conftest import SRC_DIR

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
            Common_DeviceHeartbeat,
            Common_DeviceStatus,
            Orchestrator_DeviceCommand,
            PatientMonitor_Vitals,
            SurgicalRobot_MotorControl,
        )

        # Smoke-check that we can instantiate them
        status = Common_DeviceStatus()
        assert hasattr(status, "device")
        assert hasattr(status, "status")

        vitals = PatientMonitor_Vitals()
        assert hasattr(vitals, "hr")
        assert hasattr(vitals, "spo2")


# ---------------------------------------------------------------------------
# Type instantiation and enum validation
# ---------------------------------------------------------------------------


class TestTypeInstantiation:
    """All generated DDS types should be instantiable with default values."""

    @pytest.fixture(autouse=True)
    def _setup_path(self):
        if str(SRC_DIR) not in sys.path:
            sys.path.insert(0, str(SRC_DIR))

    def test_device_status_fields(self):
        from Types import Common_DeviceStatus

        s = Common_DeviceStatus()
        assert hasattr(s, "device")
        assert hasattr(s, "status")

    def test_device_heartbeat_fields(self):
        from Types import Common_DeviceHeartbeat

        h = Common_DeviceHeartbeat()
        assert hasattr(h, "device")

    def test_motor_control_fields(self):
        from Types import SurgicalRobot_MotorControl

        m = SurgicalRobot_MotorControl()
        assert hasattr(m, "id")
        assert hasattr(m, "direction")

    def test_device_command_fields(self):
        from Types import Orchestrator_DeviceCommand

        c = Orchestrator_DeviceCommand()
        assert hasattr(c, "device")
        assert hasattr(c, "command")

    def test_vitals_fields(self):
        from Types import PatientMonitor_Vitals

        v = PatientMonitor_Vitals()
        for field in ("patient_id", "hr", "spo2", "etco2", "nibp_s", "nibp_d"):
            assert hasattr(v, field), f"Vitals missing field: {field}"


class TestEnumMembers:
    """Generated enum types should have the expected members."""

    @pytest.fixture(autouse=True)
    def _setup_path(self):
        if str(SRC_DIR) not in sys.path:
            sys.path.insert(0, str(SRC_DIR))

    def test_device_type_enum(self):
        from Types import Common

        expected = {"ARM_CONTROLLER", "ARM", "VIDEO_PUB", "VIDEO_SUB", "PATIENT_MONITOR", "PATIENT_SENSOR"}
        actual = {e.name for e in Common.DeviceType}
        assert expected <= actual

    def test_device_statuses_enum(self):
        from Types import Common

        expected = {"ON", "OFF", "PAUSED", "ERROR"}
        actual = {e.name for e in Common.DeviceStatuses}
        assert expected == actual

    def test_device_commands_enum(self):
        from Types import Orchestrator

        expected = {"START", "SHUTDOWN", "PAUSE"}
        actual = {e.name for e in Orchestrator.DeviceCommands}
        assert expected == actual

    def test_motors_enum(self):
        from Types import SurgicalRobot

        expected = {"BASE", "SHOULDER", "ELBOW", "WRIST", "HAND"}
        actual = {e.name for e in SurgicalRobot.Motors}
        assert expected == actual

    def test_motor_directions_enum(self):
        from Types import SurgicalRobot

        expected = {"STATIONARY", "INCREMENT", "DECREMENT"}
        actual = {e.name for e in SurgicalRobot.MotorDirections}
        assert expected == actual
