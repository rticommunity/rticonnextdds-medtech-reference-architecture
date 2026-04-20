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
"""DDS communication tests for Module 01.

These tests launch real applications and then use a test DDS participant to
verify that the expected topics carry the right data — the same data paths
described in the module README.
"""

import sys
import time

import pytest
from conftest import (
    MODULE_DIR,
    SRC_DIR,
    create_reader,
    create_writer,
    wait_for_data,
    wait_for_process_ready,
)

# Ensure generated types are importable
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ---------------------------------------------------------------------------
# PatientSensor (headless) — no @gui marker needed
# ---------------------------------------------------------------------------


class TestPatientSensorVitals:
    """PatientSensor should publish vitals on t/Vitals."""

    def test_vitals_arrive(self, proc_manager, dds_participant):
        from Types import PatientMonitor_Vitals

        proc_manager.start_app("PatientSensor")
        reader = create_reader(
            dds_participant,
            "t/Vitals",
            PatientMonitor_Vitals,
            "DataFlowLibrary::Streaming",
        )

        samples = wait_for_data(reader, timeout_sec=10)
        assert len(samples) >= 1, "No vitals received from PatientSensor"

    def test_vitals_values_in_range(self, proc_manager, dds_participant):
        from Types import PatientMonitor_Vitals

        proc_manager.start_app("PatientSensor")
        reader = create_reader(
            dds_participant,
            "t/Vitals",
            PatientMonitor_Vitals,
            "DataFlowLibrary::Streaming",
        )

        samples = wait_for_data(reader, timeout_sec=10, min_count=5)
        assert len(samples) >= 5, "Not enough vitals samples received"

        for v in samples:
            assert 40 <= v.hr <= 200, f"HR out of range: {v.hr}"
            assert 50 <= v.spo2 <= 100, f"SpO2 out of range: {v.spo2}"
            assert 20 <= v.etco2 <= 60, f"EtCO2 out of range: {v.etco2}"
            assert 60 <= v.nibp_s <= 200, f"Systolic BP out of range: {v.nibp_s}"
            assert 40 <= v.nibp_d <= 130, f"Diastolic BP out of range: {v.nibp_d}"


class TestPatientSensorHeartbeat:
    """PatientSensor should publish heartbeats at ~20 Hz on t/DeviceHeartbeat."""

    def test_heartbeat_rate(self, proc_manager, dds_participant):
        from Types import Common_DeviceHeartbeat

        proc_manager.start_app("PatientSensor")
        reader = create_reader(
            dds_participant,
            "t/DeviceHeartbeat",
            Common_DeviceHeartbeat,
            "DataFlowLibrary::Heartbeat",
        )

        # Wait for discovery
        wait_for_data(reader, timeout_sec=10, min_count=1)

        # Collect heartbeats by polling rapidly for 1 second
        count = 0
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            samples = reader.take()
            count += sum(1 for s in samples if s.info.valid)
            time.sleep(0.02)  # poll at 50 Hz

        # At 20 Hz we expect ~20 samples/sec; require at least 8 to be safe
        assert count >= 8, f"Expected ≥8 heartbeats in 1s, got {count}"


class TestPatientSensorStatus:
    """PatientSensor should publish DeviceStatus ON on startup."""

    def test_status_on(self, proc_manager, dds_participant):
        from Types import Common, Common_DeviceStatus

        proc_manager.start_app("PatientSensor")
        reader = create_reader(
            dds_participant,
            "t/DeviceStatus",
            Common_DeviceStatus,
            "DataFlowLibrary::Status",
        )

        samples = wait_for_data(reader, timeout_sec=10)
        sensor_statuses = [s for s in samples if s.device == Common.DeviceType.PATIENT_SENSOR]
        assert len(sensor_statuses) >= 1, "No DeviceStatus from PatientSensor"
        assert sensor_statuses[-1].status == Common.DeviceStatuses.ON


class TestPatientSensorCommands:
    """PatientSensor should respond to DeviceCommand messages."""

    def test_responds_to_pause(self, proc_manager, dds_participant):
        from Types import (
            Common,
            Common_DeviceStatus,
            Orchestrator,
            Orchestrator_DeviceCommand,
        )

        proc_manager.start_app("PatientSensor")

        status_reader = create_reader(
            dds_participant,
            "t/DeviceStatus",
            Common_DeviceStatus,
            "DataFlowLibrary::Status",
        )
        cmd_writer = create_writer(
            dds_participant,
            "t/DeviceCommand",
            Orchestrator_DeviceCommand,
            "DataFlowLibrary::Command",
        )

        # Wait for PatientSensor to come online (status = ON)
        samples = wait_for_data(status_reader, timeout_sec=10)
        sensor_on = any(
            s.device == Common.DeviceType.PATIENT_SENSOR and s.status == Common.DeviceStatuses.ON for s in samples
        )
        assert sensor_on, "PatientSensor did not publish ON status"

        # Send PAUSE command
        cmd = Orchestrator_DeviceCommand(
            device=Common.DeviceType.PATIENT_SENSOR,
            command=Orchestrator.DeviceCommands.PAUSE,
        )
        cmd_writer.write(cmd)

        # Wait for status to change to PAUSED
        paused_samples = wait_for_data(status_reader, timeout_sec=10)
        paused = any(
            s.device == Common.DeviceType.PATIENT_SENSOR and s.status == Common.DeviceStatuses.PAUSED
            for s in paused_samples
        )
        assert paused, "PatientSensor did not transition to PAUSED"

    def test_responds_to_shutdown(self, proc_manager, dds_participant):
        from Types import (
            Common,
            Common_DeviceStatus,
            Orchestrator,
            Orchestrator_DeviceCommand,
        )

        proc = proc_manager.start_app("PatientSensor")

        status_reader = create_reader(
            dds_participant,
            "t/DeviceStatus",
            Common_DeviceStatus,
            "DataFlowLibrary::Status",
        )
        cmd_writer = create_writer(
            dds_participant,
            "t/DeviceCommand",
            Orchestrator_DeviceCommand,
            "DataFlowLibrary::Command",
        )

        # Wait for PatientSensor to come online
        wait_for_data(status_reader, timeout_sec=10)

        # Send SHUTDOWN command
        cmd = Orchestrator_DeviceCommand(
            device=Common.DeviceType.PATIENT_SENSOR,
            command=Orchestrator.DeviceCommands.SHUTDOWN,
        )
        cmd_writer.write(cmd)

        # PatientSensor should exit within 5s
        try:
            proc.wait(timeout=5)
        except Exception:
            pytest.fail("PatientSensor did not exit after SHUTDOWN command")


# ---------------------------------------------------------------------------
# Arm (Qt GUI) — needs display
# ---------------------------------------------------------------------------


@pytest.mark.gui
class TestArmMotorControl:
    """Arm should receive MotorControl commands and stay alive."""

    QT_ENV = {"QT_QPA_PLATFORM": "offscreen"}

    def test_arm_receives_motor_control(self, proc_manager, dds_participant):
        from Types import SurgicalRobot, SurgicalRobot_MotorControl

        proc = proc_manager.start_app("Arm", extra_env=self.QT_ENV)
        wait_for_process_ready(proc, timeout_sec=10)
        assert proc.poll() is None, f"Arm exited early with code {proc.returncode}"

        writer = create_writer(
            dds_participant,
            "t/MotorControl",
            SurgicalRobot_MotorControl,
            "DataFlowLibrary::Command",
        )

        # Send INCREMENT command for BASE motor
        cmd = SurgicalRobot_MotorControl(
            id=SurgicalRobot.Motors.BASE,
            direction=SurgicalRobot.MotorDirections.INCREMENT,
        )
        writer.write(cmd)
        time.sleep(1)

        assert proc.poll() is None, "Arm crashed after receiving MotorControl"


# ---------------------------------------------------------------------------
# All apps — status reporting
# ---------------------------------------------------------------------------


@pytest.mark.gui
class TestAllAppsStatus:
    """All five apps should report DeviceStatus ON when running."""

    QT_ENV = {"QT_QPA_PLATFORM": "offscreen"}
    GTK_ENV = {"GDK_BACKEND": "x11"}

    EXPECTED_DEVICES = {
        "PATIENT_SENSOR",
        "ARM",
        "ARM_CONTROLLER",
        "PATIENT_MONITOR",
        # Note: Orchestrator publishes commands but doesn't write its own
        # DeviceStatus in the current implementation — adjust if it does.
    }

    def test_all_apps_report_status_on(self, proc_manager, dds_participant):
        from Types import Common, Common_DeviceStatus

        proc_manager.start_app("PatientSensor")
        proc_manager.start_app("Orchestrator", extra_env=self.GTK_ENV)
        proc_manager.start_app("ArmController", extra_env=self.GTK_ENV)
        proc_manager.start_app("PatientMonitor", extra_env=self.QT_ENV)
        proc_manager.start_app("Arm", extra_env=self.QT_ENV)

        reader = create_reader(
            dds_participant,
            "t/DeviceStatus",
            Common_DeviceStatus,
            "DataFlowLibrary::Status",
        )

        # Collect statuses for up to 15 seconds
        devices_on: set[str] = set()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            samples = reader.take()
            for s in samples:
                if s.info.valid and s.data.status == Common.DeviceStatuses.ON:
                    devices_on.add(s.data.device.name)
            # We expect at least 4 devices to report ON
            # (Orchestrator may or may not report its own status)
            if len(devices_on) >= 4:
                break
            time.sleep(0.2)

        assert len(devices_on) >= 4, f"Only {len(devices_on)} devices reported ON: {devices_on}. Expected at least 4."


# ---------------------------------------------------------------------------
# Content filter verification
# ---------------------------------------------------------------------------


class TestContentFilter:
    """DeviceCommand content filters should route commands only to the targeted device."""

    def test_patient_sensor_receives_own_command(self, proc_manager, dds_participant):
        """PatientSensor should receive a command addressed to PATIENT_SENSOR."""
        from Types import (
            Common,
            Common_DeviceStatus,
            Orchestrator,
            Orchestrator_DeviceCommand,
        )

        proc_manager.start_app("PatientSensor")

        status_reader = create_reader(
            dds_participant,
            "t/DeviceStatus",
            Common_DeviceStatus,
            "DataFlowLibrary::Status",
        )
        cmd_writer = create_writer(
            dds_participant,
            "t/DeviceCommand",
            Orchestrator_DeviceCommand,
            "DataFlowLibrary::Command",
        )

        # Wait for PatientSensor to come online
        samples = wait_for_data(status_reader, timeout_sec=10)
        assert any(
            s.device == Common.DeviceType.PATIENT_SENSOR and s.status == Common.DeviceStatuses.ON for s in samples
        ), "PatientSensor never reached ON"

        # Send PAUSE addressed to PATIENT_SENSOR
        cmd_writer.write(
            Orchestrator_DeviceCommand(
                device=Common.DeviceType.PATIENT_SENSOR,
                command=Orchestrator.DeviceCommands.PAUSE,
            )
        )

        # Verify PatientSensor transitioned to PAUSED
        paused = False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not paused:
            for s in wait_for_data(status_reader, timeout_sec=1):
                if s.device == Common.DeviceType.PATIENT_SENSOR and s.status == Common.DeviceStatuses.PAUSED:
                    paused = True
                    break
        assert paused, "PatientSensor did not receive its own PAUSE command"

    def test_patient_sensor_ignores_arm_command(self, proc_manager, dds_participant):
        """PatientSensor should NOT react to a command addressed to ARM."""
        from Types import (
            Common,
            Common_DeviceStatus,
            Orchestrator,
            Orchestrator_DeviceCommand,
            PatientMonitor_Vitals,
        )

        proc_manager.start_app("PatientSensor")

        status_reader = create_reader(
            dds_participant,
            "t/DeviceStatus",
            Common_DeviceStatus,
            "DataFlowLibrary::Status",
        )
        vitals_reader = create_reader(
            dds_participant,
            "t/Vitals",
            PatientMonitor_Vitals,
            "DataFlowLibrary::Streaming",
        )
        cmd_writer = create_writer(
            dds_participant,
            "t/DeviceCommand",
            Orchestrator_DeviceCommand,
            "DataFlowLibrary::Command",
        )

        # Wait for ON status and verify vitals are flowing
        samples = wait_for_data(status_reader, timeout_sec=10)
        assert any(
            s.device == Common.DeviceType.PATIENT_SENSOR and s.status == Common.DeviceStatuses.ON for s in samples
        )
        wait_for_data(vitals_reader, timeout_sec=5, min_count=1)

        # Send PAUSE addressed to ARM — PatientSensor should ignore it
        cmd_writer.write(
            Orchestrator_DeviceCommand(
                device=Common.DeviceType.ARM,
                command=Orchestrator.DeviceCommands.PAUSE,
            )
        )

        # Give time for any reaction and drain vitals
        vitals_reader.take()
        time.sleep(1.5)

        # PatientSensor should still be publishing vitals (not paused)
        fresh = wait_for_data(vitals_reader, timeout_sec=3.0, min_count=1)
        assert len(fresh) >= 1, (
            "PatientSensor stopped publishing vitals after a command addressed to ARM — content filter may be broken"
        )
