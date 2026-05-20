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
"""Launch / smoke tests for Module 01 applications.

Verifies that each application starts without crashing.
GUI applications are marked so they can be skipped on headless systems.
"""

import pytest
from scripts.test_utils import (
    GTK_ENV,
    QT_ENV,
    wait_for_device_status,
)


class TestPatientSensor:
    """PatientSensor is a headless C++ app — no display needed."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc_manager.start_app_ready("PatientSensor")

    def test_prints_launch_message(self, proc_manager):
        proc = proc_manager.start_app_ready("PatientSensor")
        # Read whatever is available, non-blocking
        out = (
            proc.stdout.read1(4096).decode(errors="replace")
            if hasattr(proc.stdout, "read1")
            else b""
        )
        # Fallback: terminate and capture
        if not out:
            proc.terminate()
            stdout, _ = proc.communicate(timeout=5)
            out = stdout.decode(errors="replace")
        assert "Launching Patient Sensor" in out


@pytest.mark.gui
class TestOrchestrator:
    """Orchestrator is a C++ GTK application."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc_manager.start_app_ready("Orchestrator", extra_env=GTK_ENV)


@pytest.mark.gui
class TestArmController:
    """ArmController is a C++ GTK application."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc_manager.start_app_ready("ArmController", extra_env=GTK_ENV)


@pytest.mark.gui
class TestPatientMonitor:
    """PatientMonitor is a Python/Qt application — use offscreen platform."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc_manager.start_app_ready("PatientMonitor", extra_env=QT_ENV)


@pytest.mark.gui
class TestArm:
    """Arm is a Python/Qt application — use offscreen platform."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc_manager.start_app_ready("Arm", extra_env=QT_ENV)


@pytest.mark.gui
class TestAllApps:
    """Launch all five applications simultaneously."""

    def test_all_apps_launch_together(self, proc_manager, nonsecure_utility_app):
        from Types import Common

        proc_manager.start_apps_ready(
            [
                "PatientSensor",
                ("Orchestrator", GTK_ENV),
                ("ArmController", GTK_ENV),
                ("PatientMonitor", QT_ENV),
                ("Arm", QT_ENV),
            ]
        )

        # Wait for all 4 device-type apps to report DeviceStatus
        # (Orchestrator doesn't publish DeviceStatus — it's the controller)
        status_reader = nonsecure_utility_app.device_status.reader
        expected = {
            Common.DeviceType.PATIENT_SENSOR,
            Common.DeviceType.ARM_CONTROLLER,
            Common.DeviceType.ARM,
            Common.DeviceType.PATIENT_MONITOR,
        }
        seen = wait_for_device_status(
            status_reader,
            expected,
            device_statuses=[Common.DeviceStatuses.ON],
            timeout_sec=30,
        )
        assert seen == expected, (
            f"Not all apps came online. Missing: {set(d.name for d in expected - seen)}"
        )
