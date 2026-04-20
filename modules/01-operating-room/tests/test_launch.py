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

import time

import pytest
from conftest import (
    create_reader,
    wait_for_data,
    wait_for_device_status,
    wait_for_process_ready,
)


class TestPatientSensor:
    """PatientSensor is a headless C++ app — no display needed."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc = proc_manager.start_app("PatientSensor")
        wait_for_process_ready(proc)
        assert proc.poll() is None, f"PatientSensor exited early with code {proc.returncode}"

    def test_prints_launch_message(self, proc_manager):
        proc = proc_manager.start_app("PatientSensor")
        wait_for_process_ready(proc)
        # Read whatever is available, non-blocking
        out = proc.stdout.read1(4096).decode(errors="replace") if hasattr(proc.stdout, "read1") else b""
        # Fallback: terminate and capture
        if not out:
            proc.terminate()
            stdout, _ = proc.communicate(timeout=5)
            out = stdout.decode(errors="replace")
        assert "Launching Patient Sensor" in out


@pytest.mark.gui
class TestOrchestrator:
    """Orchestrator is a C++ GTK application."""

    GTK_ENV = {"GDK_BACKEND": "x11"}

    def test_starts_and_stays_alive(self, proc_manager):
        proc = proc_manager.start_app("Orchestrator", extra_env=self.GTK_ENV)
        wait_for_process_ready(proc)
        assert proc.poll() is None, f"Orchestrator exited early with code {proc.returncode}"


@pytest.mark.gui
class TestArmController:
    """ArmController is a C++ GTK application."""

    GTK_ENV = {"GDK_BACKEND": "x11"}

    def test_starts_and_stays_alive(self, proc_manager):
        proc = proc_manager.start_app("ArmController", extra_env=self.GTK_ENV)
        wait_for_process_ready(proc)
        assert proc.poll() is None, f"ArmController exited early with code {proc.returncode}"


@pytest.mark.gui
class TestPatientMonitor:
    """PatientMonitor is a Python/Qt application — use offscreen platform."""

    QT_ENV = {"QT_QPA_PLATFORM": "offscreen"}

    def test_starts_and_stays_alive(self, proc_manager):
        proc = proc_manager.start_app("PatientMonitor", extra_env=self.QT_ENV)
        wait_for_process_ready(proc, timeout_sec=10)
        assert proc.poll() is None, f"PatientMonitor exited early with code {proc.returncode}"


@pytest.mark.gui
class TestArm:
    """Arm is a Python/Qt application — use offscreen platform."""

    QT_ENV = {"QT_QPA_PLATFORM": "offscreen"}

    def test_starts_and_stays_alive(self, proc_manager):
        proc = proc_manager.start_app("Arm", extra_env=self.QT_ENV)
        wait_for_process_ready(proc, timeout_sec=10)
        assert proc.poll() is None, f"Arm exited early with code {proc.returncode}"


@pytest.mark.gui
class TestAllApps:
    """Launch all five applications simultaneously."""

    QT_ENV = {"QT_QPA_PLATFORM": "offscreen"}
    GTK_ENV = {"GDK_BACKEND": "x11"}

    def test_all_apps_launch_together(self, proc_manager, dds_participant):
        from Types import Common, Common_DeviceStatus

        procs = {}
        procs["PatientSensor"] = proc_manager.start_app("PatientSensor")
        procs["Orchestrator"] = proc_manager.start_app("Orchestrator", extra_env=self.GTK_ENV)
        procs["ArmController"] = proc_manager.start_app("ArmController", extra_env=self.GTK_ENV)
        procs["PatientMonitor"] = proc_manager.start_app("PatientMonitor", extra_env=self.QT_ENV)
        procs["Arm"] = proc_manager.start_app("Arm", extra_env=self.QT_ENV)

        # Wait for all 4 device-type apps to report DeviceStatus
        # (Orchestrator doesn't publish DeviceStatus — it's the controller)
        status_reader = create_reader(
            dds_participant,
            "t/DeviceStatus",
            Common_DeviceStatus,
            "DataFlowLibrary::Status",
        )
        expected = {
            Common.DeviceType.PATIENT_SENSOR,
            Common.DeviceType.ARM_CONTROLLER,
            Common.DeviceType.ARM,
            Common.DeviceType.PATIENT_MONITOR,
        }
        seen = wait_for_device_status(status_reader, expected, timeout_sec=30)
        assert seen == expected, f"Not all apps came online. Missing: {set(d.name for d in expected - seen)}"

        for name, proc in procs.items():
            assert proc.poll() is None, f"{name} crashed on startup (exit code {proc.returncode})"
