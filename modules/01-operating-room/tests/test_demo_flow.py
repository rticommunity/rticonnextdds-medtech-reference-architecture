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
"""End-to-end demo-flow tests for Module 01.

These tests replicate the scenarios described in the module README:
  - Crash detection via heartbeat deadline
  - Pause / resume via Orchestrator commands
  - Graceful shutdown of all devices
  - Secure-mode launch

They are marked ``slow`` because they launch the full application set and
wait for inter-app DDS interactions to play out.
"""

import importlib
import subprocess
import sys
import time
from pathlib import Path

import pytest
import rti.connextdds as dds

TESTS_DIR = Path(__file__).resolve().parent

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

module01_test_support = importlib.import_module("module01_test_support")

SRC_DIR = module01_test_support.SRC_DIR

from scripts.test_utils import (  # noqa: E402
    PROCESS_WAIT_TIMEOUT,
    UtilityApp,
    disable_monitoring,
    wait_for_device_status,
    wait_for_process_ready,
    wait_for_reader_match,
    wait_for_samples,
)

# ---------------------------------------------------------------------------
# Heartbeat cessation after a crash
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestCrashDetection:
    """Observe heartbeat cessation after a sensor crashes."""

    def test_patient_sensor_heartbeats_stop_after_crash(self, proc_manager, nonsecure_utility_app):
        from MedTech import Device

        patient_sensor = proc_manager.start_app_ready("PatientSensor")
        hb_reader = nonsecure_utility_app.device_heartbeat.reader

        # Wait for PatientSensor heartbeats to start flowing
        assert wait_for_reader_match(hb_reader), "Reader never matched a writer"
        samples = wait_for_samples(hb_reader, timeout_sec=5)
        assert any(s.device == Device.DeviceType.PATIENT_SENSOR for s in samples), (
            "PatientSensor heartbeats never arrived"
        )

        # Verify heartbeats are flowing at a reasonable rate
        hb_reader.take()  # drain
        time.sleep(0.5)
        pre_kill = hb_reader.take()
        assert any(s.info.valid for s in pre_kill), "Heartbeats not flowing before kill"

        # Kill PatientSensor *ungracefully* (SIGKILL — no cleanup)
        patient_sensor.kill()
        patient_sensor.wait(timeout=3)

        # Observe cessation independently; this does not test the Orchestrator UI.
        hb_reader.take()  # drain anything buffered
        time.sleep(1)  # wait longer than the 200ms deadline
        post_kill = hb_reader.take()
        post_kill_valid = [s for s in post_kill if s.info.valid]
        assert len(post_kill_valid) == 0, (
            f"Heartbeats still arriving after SIGKILL ({len(post_kill_valid)} samples)"
        )


# ---------------------------------------------------------------------------
# Pause and resume (README: Orchestrator sends PAUSE, then START)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestPauseAndResume:
    """Pausing PatientSensor should stop vitals; resuming should restart them."""

    def test_pause_stops_vitals_then_resume_restarts(self, proc_manager, nonsecure_utility_app):
        from MedTech import (
            Device,
        )

        proc_manager.start_app_ready("PatientSensor")

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

        # Verify vitals are flowing
        assert wait_for_reader_match(vitals_reader), "Reader never matched a writer"
        vitals = wait_for_samples(vitals_reader, timeout_sec=5)
        assert len(vitals) >= 1, "No vitals before pause"

        # Send PAUSE
        cmd_writer.write(
            Device.Command(
                device=Device.DeviceType.PATIENT_SENSOR,
                command=Device.DeviceCommands.PAUSE,
            )
        )

        # Wait for PAUSED status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatuses.PAUSED],
            timeout_sec=5,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not transition to PAUSED"
        )

        # Allow in-flight samples to settle, then observe several publish periods.
        time.sleep(0.5)
        vitals_reader.take()  # drain
        time.sleep(1)
        stale = vitals_reader.take()
        valid_stale = [s for s in stale if s.info.valid]
        assert len(valid_stale) == 0, (
            f"Vitals still flowing while PAUSED ({len(valid_stale)} samples)"
        )

        # Send START
        cmd_writer.write(
            Device.Command(
                device=Device.DeviceType.PATIENT_SENSOR,
                command=Device.DeviceCommands.START,
            )
        )

        # Vitals should resume
        resumed = wait_for_samples(vitals_reader, timeout_sec=5)
        assert len(resumed) >= 1, "Vitals did not resume after START command"


# ---------------------------------------------------------------------------
# Graceful shutdown (README: send SHUTDOWN to every device)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestGracefulShutdown:
    """Sending SHUTDOWN to each device should cause all processes to exit."""

    def test_shutdown_all_devices(self, proc_manager, nonsecure_utility_app):
        from MedTech import (
            Device,
        )

        procs = {
            Device.DeviceType.PATIENT_SENSOR: proc_manager.start_app("PatientSensor"),
            Device.DeviceType.ARM_CONTROLLER: proc_manager.start_app("ArmController"),
            Device.DeviceType.ARM: proc_manager.start_app("Arm"),
            Device.DeviceType.PATIENT_MONITOR: proc_manager.start_app("PatientMonitor"),
        }

        status_reader = nonsecure_utility_app.device_status.reader
        cmd_writer = nonsecure_utility_app.device_command.writer

        # Wait until all devices have published DeviceStatus ON (up to 30s)
        expected = set(procs.keys())
        seen = wait_for_device_status(
            status_reader,
            expected,
            device_statuses=[Device.DeviceStatuses.ON],
            timeout_sec=30,
        )
        assert seen == expected, (
            f"Timed out waiting for devices. Missing: {set(d.name for d in expected - seen)}"
        )

        # Send SHUTDOWN to each device
        for device_type in procs:
            cmd_writer.write(
                Device.Command(
                    device=device_type,
                    command=Device.DeviceCommands.SHUTDOWN,
                )
            )

        # All processes should exit within 10 seconds
        deadline = time.monotonic() + 10
        still_alive = {}
        for device_type, proc in procs.items():
            remaining = max(0.1, deadline - time.monotonic())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                still_alive[device_type.name] = proc

        assert not still_alive, (
            f"These devices did not exit after SHUTDOWN: {list(still_alive.keys())}"
        )


# ---------------------------------------------------------------------------
# Security mode tests
# ---------------------------------------------------------------------------


@pytest.mark.secure
class TestSecurePatientSensor:
    """PatientSensor should work correctly in secure mode."""

    def test_vitals_flow_with_security(self, proc_manager_secure, dds_env_secure):
        """PatientSensor starts and runs with DDS Security enabled."""
        ps = proc_manager_secure.start_app("PatientSensor")

        # Wait for security handshake and DDS initialization
        wait_for_process_ready(ps, timeout_sec=PROCESS_WAIT_TIMEOUT)

        if ps.poll() is not None:
            stdout = ps.stdout.read().decode(errors="replace") if ps.stdout else ""
            stderr = ps.stderr.read().decode(errors="replace") if ps.stderr else ""
            pytest.fail(
                f"PatientSensor exited prematurely (code={ps.returncode})\n"
                f"stdout:\n{stdout[-2000:]}\nstderr:\n{stderr[-2000:]}"
            )


@pytest.mark.secure
class TestSecureAllApps:
    """The core operating-room apps should launch successfully in secure mode."""

    def test_secure_launch(self, proc_manager_secure, dds_env_secure, monkeypatch):
        """C++ and Python devices publish status with DDS Security enabled."""
        from MedTech import Device

        env, _ = dds_env_secure
        monkeypatch.setenv("RTI_SECURITY_ARTIFACTS_DIR", env["RTI_SECURITY_ARTIFACTS_DIR"])
        factory_qos = dds.DomainParticipant.participant_factory_qos
        try:
            disable_monitoring()
            with UtilityApp.make_secure() as observer:
                proc_manager_secure.start_apps_ready(
                    [
                        "PatientSensor",
                        "Orchestrator",
                        "ArmController",
                        "Arm",
                        "PatientMonitor",
                    ]
                )
                expected = {
                    Device.DeviceType.ARM,
                    Device.DeviceType.ARM_CONTROLLER,
                    Device.DeviceType.PATIENT_SENSOR,
                    Device.DeviceType.PATIENT_MONITOR,
                }
                seen = wait_for_device_status(
                    observer.device_status.reader,
                    expected_devices=expected,
                    device_statuses=[Device.DeviceStatuses.ON],
                    timeout_sec=15,
                )
        finally:
            dds.DomainParticipant.participant_factory_qos = factory_qos
        assert expected.issubset(seen), f"Secure device statuses not received: {expected - seen}"
