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

import math
import time

import pytest
from scripts.test_utils import (
    check_no_deadline_missed,
    wait_for_device_status,
    wait_for_reader_match,
    wait_for_samples,
    wait_for_writer_match,
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
        from MedTech import Device

        status_reader = nonsecure_utility_app.device_status.reader

        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )


class TestPatientSensorCommands:
    """PatientSensor should respond to DeviceCommand messages."""

    def test_responds_to_pause(self, proc_manager, nonsecure_utility_app):
        from MedTech import Device

        proc_manager.start_app("PatientSensor")

        status_reader = nonsecure_utility_app.device_status.reader
        cmd_writer = nonsecure_utility_app.device_command.writer

        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )

        # Send PAUSE command
        assert wait_for_writer_match(cmd_writer), "Command writer never matched a reader"
        cmd = Device.Command(
            device=Device.DeviceType.PATIENT_SENSOR,
            command=Device.DeviceCommands.PAUSE,
        )
        cmd_writer.write(cmd)

        # Wait for status to change to PAUSED
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatuses.PAUSED],
            timeout_sec=2,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not transition to PAUSED"
        )

    def test_responds_to_shutdown(self, proc_manager, nonsecure_utility_app):
        from MedTech import Device

        proc = proc_manager.start_app("PatientSensor")

        status_reader = nonsecure_utility_app.device_status.reader
        cmd_writer = nonsecure_utility_app.device_command.writer

        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )

        # Send SHUTDOWN command
        assert wait_for_writer_match(cmd_writer), "Command writer never matched a reader"
        cmd = Device.Command(
            device=Device.DeviceType.PATIENT_SENSOR,
            command=Device.DeviceCommands.SHUTDOWN,
        )
        cmd_writer.write(cmd)

        # PatientSensor should exit within 5s
        try:
            proc.wait(timeout=5)
        except Exception:
            pytest.fail("PatientSensor did not exit after SHUTDOWN command")


# ---------------------------------------------------------------------------
# Arm browser frontend and DDS behavior
# ---------------------------------------------------------------------------


class TestArmTeleopControl:
    """Arm should receive operator-level teleoperation commands."""

    @pytest.mark.parametrize("lost_stream", ["arm", "tool"])
    def test_arm_receives_teleop_control(self, proc_manager, nonsecure_utility_app, lost_stream):
        from MedTech import Device, Geometry, Robot

        proc_manager.start_app("Arm")

        status_reader = nonsecure_utility_app.device_status.reader
        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.ARM},
            device_statuses=[Device.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Device.DeviceType.ARM in seen, (
            "Arm did not report DeviceStatus ON within the timeout"
        )

        teleop_writer = nonsecure_utility_app.teleop_control.writer
        tool_writer = nonsecure_utility_app.tool_control.writer
        telemetry = nonsecure_utility_app.arm_telemetry.reader
        readiness = nonsecure_utility_app.arm_status.reader
        teleop_command = Robot.Arm.TeleopControl(
            arm_id="arm-1",
            linear_velocity=Geometry.Vector3(x=0.01),
        )
        tool_command = Robot.Tool.ParallelJawControl(arm_id="arm-1", opening_rate=0.01)
        assert wait_for_writer_match(teleop_writer), "TeleopControl writer never matched a reader"
        assert wait_for_writer_match(tool_writer)
        assert wait_for_reader_match(telemetry)
        initial = wait_for_samples(telemetry, n=1, timeout_sec=2)[-1]
        assert initial.tcp_pose is not None
        assert initial.parallel_jaw is not None

        until = time.monotonic() + 0.2
        while time.monotonic() < until:
            teleop_writer.write(teleop_command)
            tool_writer.write(tool_command)
            time.sleep(0.02)
        moved = wait_for_samples(telemetry, n=1, timeout_sec=2)[-1]

        def position(sample):
            point = sample.tcp_pose.position
            return (point.x, point.y, point.z)

        assert position(moved)[0] - position(initial)[0] > 0.0005
        assert position(moved)[1:] == pytest.approx(position(initial)[1:], abs=1e-8)
        assert moved.parallel_jaw.opening_width > initial.parallel_jaw.opening_width

        remaining_writer, remaining_command = (
            (tool_writer, tool_command) if lost_stream == "arm" else (teleop_writer, teleop_command)
        )
        until = time.monotonic() + 0.7
        settled = None
        while time.monotonic() < until:
            remaining_writer.write(remaining_command)
            if until - time.monotonic() < 0.2 and settled is None:
                settled = wait_for_samples(telemetry, n=1, timeout_sec=2)[-1]
            time.sleep(0.02)
        held = wait_for_samples(telemetry, n=1, timeout_sec=2)[-1]
        assert settled is not None
        assert held.parallel_jaw.opening_width == pytest.approx(
            settled.parallel_jaw.opening_width, abs=1e-8
        )
        if lost_stream == "arm":
            assert position(held) == pytest.approx(position(settled), abs=1e-8)
            assert wait_for_samples(readiness, n=1, timeout_sec=2)[-1].readiness == (
                Robot.Arm.Readiness.NOT_READY
            )
        else:
            assert math.dist(position(held), position(settled)) > 0.0005

        until = time.monotonic() + 0.2
        tool_command.opening_rate = -0.01
        while time.monotonic() < until:
            teleop_writer.write(teleop_command)
            tool_writer.write(tool_command)
            time.sleep(0.02)
        recovered = wait_for_samples(telemetry, n=1, timeout_sec=2)[-1]
        assert math.dist(position(held), position(recovered)) > 0.0005
        assert recovered.parallel_jaw.opening_width < held.parallel_jaw.opening_width


# ---------------------------------------------------------------------------
# All apps — status reporting
# ---------------------------------------------------------------------------


class TestAllAppsStatus:
    """All five apps should report DeviceStatus ON when running."""

    def test_all_apps_report_status_on(self, proc_manager, nonsecure_utility_app):
        from MedTech import Device

        proc_manager.start_app("PatientSensor")
        proc_manager.start_app("Orchestrator")
        proc_manager.start_app("ArmController")
        proc_manager.start_app("PatientMonitor")
        proc_manager.start_app("Arm")

        status_reader = nonsecure_utility_app.device_status.reader

        # Wait for discovery
        assert wait_for_reader_match(status_reader, timeout_sec=8, count=4), (
            "Status reader never matched writers"
        )

        # Wait for device status
        expected_devices = {
            Device.DeviceType.PATIENT_SENSOR,
            Device.DeviceType.ARM_CONTROLLER,
            Device.DeviceType.ARM,
            Device.DeviceType.PATIENT_MONITOR,
        }
        seen = wait_for_device_status(
            status_reader,
            expected_devices=expected_devices,
            device_statuses=[Device.DeviceStatuses.ON],
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
        from MedTech import Device

        proc_manager.start_app("PatientSensor")

        status_reader = nonsecure_utility_app.device_status.reader
        cmd_writer = nonsecure_utility_app.device_command.writer

        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )

        # Send PAUSE addressed to PATIENT_SENSOR
        cmd = Device.Command(
            device=Device.DeviceType.PATIENT_SENSOR,
            command=Device.DeviceCommands.PAUSE,
        )
        cmd_writer.write(cmd)

        # Verify PatientSensor transitioned to PAUSED
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatuses.PAUSED],
            timeout_sec=2,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not receive its own PAUSE command"
        )

        # Send START command
        cmd = Device.Command(
            device=Device.DeviceType.PATIENT_SENSOR,
            command=Device.DeviceCommands.START,
        )
        cmd_writer.write(cmd)

        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatuses.ON],
            timeout_sec=2,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, "PatientSensor did not publish ON status"

    def test_patient_sensor_ignores_arm_command(self, proc_manager, nonsecure_utility_app):
        """PatientSensor should NOT react to a command addressed to ARM."""
        from MedTech import Device

        proc_manager.start_app("PatientSensor")

        status_reader = nonsecure_utility_app.device_status.reader
        vitals_reader = nonsecure_utility_app.vitals.reader
        cmd_writer = nonsecure_utility_app.device_command.writer

        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatuses.ON],
            timeout_sec=10,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )

        assert wait_for_reader_match(vitals_reader), "Vitals reader never matched a writer"
        samples = wait_for_samples(vitals_reader, timeout_sec=4)
        assert len(samples) >= 1, "No vitals received from PatientSensor"

        # Send PAUSE addressed to ARM — PatientSensor should ignore it
        cmd = Device.Command(
            device=Device.DeviceType.ARM,
            command=Device.DeviceCommands.PAUSE,
        )
        cmd_writer.write(cmd)
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatuses.PAUSED],
            timeout_sec=2,
        )
        assert Device.DeviceType.PATIENT_SENSOR not in seen, (
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
