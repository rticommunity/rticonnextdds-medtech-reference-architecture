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

import pytest
from scripts.test_utils import (
    GTK_ENV,
    QT_ENV,
    check_no_deadline_missed,
    wait_for_device_status,
    wait_for_reader_match,
    wait_for_samples,
    wait_for_writer_match,
    write_and_wait_for_ack,
)

# ---------------------------------------------------------------------------
# PatientSensor (headless) — no @gui marker needed
# ---------------------------------------------------------------------------


class TestPatientSensorReadOnly:
    """Read-only PatientSensor tests: vitals, heartbeats, and status.

    Uses a class-scoped ProcessManager so PatientSensor is launched once
    and shared across all tests in this class.
    """

    @pytest.fixture(scope="class", autouse=True)
    @classmethod
    def start_apps(cls, class_proc_manager):
        """PatientSensor should launch and stay alive for the duration of the tests."""
        class_proc_manager.start_app_ready("PatientSensor")
        yield

    def test_vitals_values_in_range(self, nonsecure_utility_app):
        vitals_reader = nonsecure_utility_app.vitals.reader

        assert wait_for_reader_match(vitals_reader), "Vitals reader never matched a writer"

        # Vitals should be published at >= 1Hz
        samples = wait_for_samples(vitals_reader, n=5, timeout_sec=7)
        assert len(samples) >= 5, "Not enough vitals samples received"

        for v in samples:
            assert 40 <= v.hr <= 200, f"HR out of range: {v.hr}"
            assert 50 <= v.spo2 <= 100, f"SpO2 out of range: {v.spo2}"
            assert 20 <= v.etco2 <= 60, f"EtCO2 out of range: {v.etco2}"
            assert 60 <= v.nibp_s <= 200, f"Systolic BP out of range: {v.nibp_s}"
            assert 40 <= v.nibp_d <= 130, f"Diastolic BP out of range: {v.nibp_d}"

    def test_heartbeat_rate(self, nonsecure_utility_app):
        heartbeat_reader = nonsecure_utility_app.device_heartbeat.reader

        # Wait for discovery
        assert wait_for_reader_match(heartbeat_reader), "Heartbeat reader never matched a writer"

        # The Heartbeat profile has a deadline QoS; verify it is not being missed
        assert check_no_deadline_missed(heartbeat_reader), "Deadline missed on Heartbeat reader"

    def test_status_on(self, nonsecure_utility_app):
        from Types import Common

        status_reader = nonsecure_utility_app.device_status.reader

        seen = wait_for_device_status(
            status_reader,
            expected_devices={Common.DeviceType.PATIENT_SENSOR},
            device_statuses=[Common.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Common.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )


class TestPatientSensorCommands:
    """PatientSensor should respond to DeviceCommand messages."""

    def test_responds_to_pause(self, proc_manager, nonsecure_utility_app):
        from Types import Common, Orchestrator

        proc_manager.start_app("PatientSensor")

        status_reader = nonsecure_utility_app.device_status.reader
        cmd_writer = nonsecure_utility_app.device_command.writer

        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Common.DeviceType.PATIENT_SENSOR},
            device_statuses=[Common.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Common.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )

        # Send PAUSE command
        assert wait_for_writer_match(cmd_writer), "Command writer never matched a reader"
        cmd = Orchestrator.DeviceCommand(
            device=Common.DeviceType.PATIENT_SENSOR,
            command=Orchestrator.DeviceCommands.PAUSE,
        )
        cmd_writer.write(cmd)

        # Wait for status to change to PAUSED
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Common.DeviceType.PATIENT_SENSOR},
            device_statuses=[Common.DeviceStatuses.PAUSED],
            timeout_sec=2,
        )
        assert Common.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not transition to PAUSED"
        )

    def test_responds_to_shutdown(self, proc_manager, nonsecure_utility_app):
        from Types import Common, Orchestrator

        proc = proc_manager.start_app("PatientSensor")

        status_reader = nonsecure_utility_app.device_status.reader
        cmd_writer = nonsecure_utility_app.device_command.writer

        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Common.DeviceType.PATIENT_SENSOR},
            device_statuses=[Common.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Common.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )

        # Send SHUTDOWN command
        assert wait_for_writer_match(cmd_writer), "Command writer never matched a reader"
        cmd = Orchestrator.DeviceCommand(
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

    def test_arm_receives_motor_control(self, proc_manager, nonsecure_utility_app):
        from Types import Common, SurgicalRobot

        proc_manager.start_app("Arm", extra_env=QT_ENV)

        status_reader = nonsecure_utility_app.device_status.reader
        control_writer = nonsecure_utility_app.motor_control.writer

        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Common.DeviceType.ARM},
            device_statuses=[Common.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Common.DeviceType.ARM in seen, (
            "Arm did not report DeviceStatus ON within the timeout"
        )

        # Send INCREMENT command for BASE motor
        control = SurgicalRobot.MotorControl(
            id=SurgicalRobot.Motors.BASE,
            direction=SurgicalRobot.MotorDirections.INCREMENT,
        )
        assert wait_for_writer_match(control_writer), "MotorControl writer never matched a reader"
        assert write_and_wait_for_ack(control_writer, control, timeout_sec=2), (
            "Arm did not ack MotorControl command"
        )


# ---------------------------------------------------------------------------
# All apps — status reporting
# ---------------------------------------------------------------------------


@pytest.mark.gui
class TestAllAppsStatus:
    """All five apps should report DeviceStatus ON when running."""

    def test_all_apps_report_status_on(self, proc_manager, nonsecure_utility_app):
        from Types import Common

        proc_manager.start_app("PatientSensor")
        proc_manager.start_app("Orchestrator", extra_env=GTK_ENV)
        proc_manager.start_app("ArmController", extra_env=GTK_ENV)
        proc_manager.start_app("PatientMonitor", extra_env=QT_ENV)
        proc_manager.start_app("Arm", extra_env=QT_ENV)

        status_reader = nonsecure_utility_app.device_status.reader

        # Wait for discovery
        assert wait_for_reader_match(status_reader, timeout_sec=8, count=4), (
            "Status reader never matched writers"
        )

        # Wait for device status
        expected_devices = {
            Common.DeviceType.PATIENT_SENSOR,
            Common.DeviceType.ARM_CONTROLLER,
            Common.DeviceType.ARM,
            Common.DeviceType.PATIENT_MONITOR,
        }
        seen = wait_for_device_status(
            status_reader,
            expected_devices=expected_devices,
            device_statuses=[Common.DeviceStatuses.ON],
            timeout_sec=10,
        )
        for device in expected_devices:
            assert device in seen, (
                f"{device.name} did not report DeviceStatus ON within the timeout"
            )


# ---------------------------------------------------------------------------
# Content filter verification
# ---------------------------------------------------------------------------


class TestContentFilter:
    """DeviceCommand content filters should route commands only to the targeted device."""

    def test_patient_sensor_receives_own_command(self, proc_manager, nonsecure_utility_app):
        """PatientSensor should receive a command addressed to PATIENT_SENSOR."""
        from Types import Common, Orchestrator

        proc_manager.start_app("PatientSensor")

        status_reader = nonsecure_utility_app.device_status.reader
        cmd_writer = nonsecure_utility_app.device_command.writer

        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Common.DeviceType.PATIENT_SENSOR},
            device_statuses=[Common.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Common.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )

        # Send PAUSE addressed to PATIENT_SENSOR
        cmd = Orchestrator.DeviceCommand(
            device=Common.DeviceType.PATIENT_SENSOR,
            command=Orchestrator.DeviceCommands.PAUSE,
        )
        cmd_writer.write(cmd)

        # Verify PatientSensor transitioned to PAUSED
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Common.DeviceType.PATIENT_SENSOR},
            device_statuses=[Common.DeviceStatuses.PAUSED],
            timeout_sec=2,
        )
        assert Common.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not receive its own PAUSE command"
        )

        # Send START command
        cmd = Orchestrator.DeviceCommand(
            device=Common.DeviceType.PATIENT_SENSOR,
            command=Orchestrator.DeviceCommands.START,
        )
        cmd_writer.write(cmd)

        seen = wait_for_device_status(
            status_reader,
            expected_devices={Common.DeviceType.PATIENT_SENSOR},
            device_statuses=[Common.DeviceStatuses.ON],
            timeout_sec=2,
        )
        assert Common.DeviceType.PATIENT_SENSOR in seen, "PatientSensor did not publish ON status"

    def test_patient_sensor_ignores_arm_command(self, proc_manager, nonsecure_utility_app):
        """PatientSensor should NOT react to a command addressed to ARM."""
        from Types import Common, Orchestrator

        proc_manager.start_app("PatientSensor")

        status_reader = nonsecure_utility_app.device_status.reader
        vitals_reader = nonsecure_utility_app.vitals.reader
        cmd_writer = nonsecure_utility_app.device_command.writer

        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Common.DeviceType.PATIENT_SENSOR},
            device_statuses=[Common.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Common.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )

        assert wait_for_reader_match(vitals_reader), "Vitals reader never matched a writer"
        samples = wait_for_samples(vitals_reader, timeout_sec=4)
        assert len(samples) >= 1, "No vitals received from PatientSensor"

        # Send PAUSE addressed to ARM — PatientSensor should ignore it
        cmd = Orchestrator.DeviceCommand(
            device=Common.DeviceType.ARM,
            command=Orchestrator.DeviceCommands.PAUSE,
        )
        cmd_writer.write(cmd)
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Common.DeviceType.PATIENT_SENSOR},
            device_statuses=[Common.DeviceStatuses.PAUSED],
            timeout_sec=2,
        )
        assert Common.DeviceType.PATIENT_SENSOR not in seen, (
            "PatientSensor changed status in response to a command addressed to ARM"
            " — content filter may be broken"
        )

        # Give time for any reaction and drain vitals
        vitals_reader.take()

        # PatientSensor should still be publishing vitals (not paused)
        samples = wait_for_samples(vitals_reader, timeout_sec=3)
        assert len(samples) >= 1, (
            "PatientSensor stopped publishing vitals after a command addressed to ARM"
            " — content filter may be broken"
        )
