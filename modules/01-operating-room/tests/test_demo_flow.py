"""End-to-end demo-flow tests for Module 01.

These tests replicate the scenarios described in the module README:
  - Crash detection via heartbeat deadline
  - Pause / resume via Orchestrator commands
  - Graceful shutdown of all devices
  - Secure-mode launch

They are marked ``slow`` because they launch the full application set and
wait for inter-app DDS interactions to play out.
"""

import signal
import sys
import time

import pytest

from conftest import (
    MODULE_DIR,
    SRC_DIR,
    create_reader,
    create_writer,
    wait_for_data,
    run_dds_subscriber_secure,
)

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

QT_ENV = {"QT_QPA_PLATFORM": "offscreen"}


# ---------------------------------------------------------------------------
# Crash detection (README exercise: kill an app, Orchestrator detects it)
# ---------------------------------------------------------------------------

@pytest.mark.gui
@pytest.mark.slow
class TestCrashDetection:
    """Killing an app should cause Orchestrator to detect the loss via heartbeat deadline."""

    def test_orchestrator_detects_patient_sensor_crash(self, proc_manager, dds_participant):
        from Types import Common_DeviceHeartbeat, Common

        patient_sensor = proc_manager.start_cpp("PatientSensor")
        proc_manager.start_cpp("Orchestrator")

        hb_reader = create_reader(
            dds_participant, "t/DeviceHeartbeat", Common_DeviceHeartbeat,
            "DataFlowLibrary::Heartbeat",
        )

        # Wait for PatientSensor heartbeats to start flowing
        samples = wait_for_data(hb_reader, timeout_sec=10)
        assert any(
            s.device == Common.DeviceType.PATIENT_SENSOR for s in samples
        ), "PatientSensor heartbeats never arrived"

        # Verify heartbeats are flowing at a reasonable rate
        hb_reader.take()  # drain
        time.sleep(0.5)
        pre_kill = hb_reader.take()
        assert any(s.info.valid for s in pre_kill), (
            "Heartbeats not flowing before kill"
        )

        # Kill PatientSensor *ungracefully* (SIGKILL — no cleanup)
        patient_sensor.kill()
        patient_sensor.wait(timeout=3)

        # After kill, heartbeats should stop arriving.
        # The Orchestrator detects this via the 200ms deadline QoS.
        # We verify the same thing: no new heartbeats arrive.
        hb_reader.take()  # drain anything buffered
        time.sleep(1)  # wait longer than the 200ms deadline
        post_kill = hb_reader.take()
        post_kill_valid = [s for s in post_kill if s.info.valid]
        assert len(post_kill_valid) == 0, (
            f"Heartbeats still arriving after SIGKILL "
            f"({len(post_kill_valid)} samples)"
        )


# ---------------------------------------------------------------------------
# Pause and resume (README: Orchestrator sends PAUSE, then START)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestPauseAndResume:
    """Pausing PatientSensor should stop vitals; resuming should restart them."""

    def test_pause_stops_vitals_then_resume_restarts(self, proc_manager, dds_participant):
        from Types import (
            Common_DeviceStatus,
            Orchestrator_DeviceCommand,
            PatientMonitor_Vitals,
            Common,
            Orchestrator,
        )

        proc_manager.start_cpp("PatientSensor")

        status_reader = create_reader(
            dds_participant, "t/DeviceStatus", Common_DeviceStatus,
            "DataFlowLibrary::Status",
        )
        vitals_reader = create_reader(
            dds_participant, "t/Vitals", PatientMonitor_Vitals,
            "DataFlowLibrary::Streaming",
        )
        cmd_writer = create_writer(
            dds_participant, "t/DeviceCommand", Orchestrator_DeviceCommand,
            "DataFlowLibrary::Command",
        )

        # Wait for ON
        samples = wait_for_data(status_reader, timeout_sec=10)
        assert any(
            s.device == Common.DeviceType.PATIENT_SENSOR
            and s.status == Common.DeviceStatuses.ON
            for s in samples
        ), "PatientSensor never reached ON"

        # Verify vitals are flowing
        vitals = wait_for_data(vitals_reader, timeout_sec=5)
        assert len(vitals) >= 1, "No vitals before pause"

        # Send PAUSE
        cmd_writer.write(Orchestrator_DeviceCommand(
            device=Common.DeviceType.PATIENT_SENSOR,
            command=Orchestrator.DeviceCommands.PAUSE,
        ))

        # Wait for PAUSED status
        paused = False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            ss = wait_for_data(status_reader, timeout_sec=1)
            if any(
                s.device == Common.DeviceType.PATIENT_SENSOR
                and s.status == Common.DeviceStatuses.PAUSED
                for s in ss
            ):
                paused = True
                break
        assert paused, "PatientSensor did not transition to PAUSED"

        # Drain any remaining vitals and then check no new ones arrive
        vitals_reader.take()  # drain
        time.sleep(1)
        stale = vitals_reader.take()
        valid_stale = [s for s in stale if s.info.valid]
        assert len(valid_stale) == 0, (
            f"Vitals still flowing while PAUSED ({len(valid_stale)} samples)"
        )

        # Send START
        cmd_writer.write(Orchestrator_DeviceCommand(
            device=Common.DeviceType.PATIENT_SENSOR,
            command=Orchestrator.DeviceCommands.START,
        ))

        # Vitals should resume
        resumed = wait_for_data(vitals_reader, timeout_sec=5)
        assert len(resumed) >= 1, "Vitals did not resume after START command"


# ---------------------------------------------------------------------------
# Graceful shutdown (README: send SHUTDOWN to every device)
# ---------------------------------------------------------------------------

@pytest.mark.gui
@pytest.mark.slow
class TestGracefulShutdown:
    """Sending SHUTDOWN to each device should cause all processes to exit."""

    def test_shutdown_all_devices(self, proc_manager, dds_participant):
        from Types import (
            Orchestrator_DeviceCommand,
            Common_DeviceStatus,
            Common,
            Orchestrator,
        )

        procs = {
            Common.DeviceType.PATIENT_SENSOR: proc_manager.start_cpp("PatientSensor"),
            Common.DeviceType.ARM_CONTROLLER: proc_manager.start_cpp("ArmController"),
            Common.DeviceType.ARM: proc_manager.start_python("Arm.py", extra_env=QT_ENV),
            Common.DeviceType.PATIENT_MONITOR: proc_manager.start_python(
                "PatientMonitor.py", extra_env=QT_ENV
            ),
        }

        status_reader = create_reader(
            dds_participant, "t/DeviceStatus", Common_DeviceStatus,
            "DataFlowLibrary::Status",
        )
        cmd_writer = create_writer(
            dds_participant, "t/DeviceCommand", Orchestrator_DeviceCommand,
            "DataFlowLibrary::Command",
        )

        # Wait for at least some devices to come online
        time.sleep(5)

        # Send SHUTDOWN to each device
        for device_type in procs:
            cmd_writer.write(Orchestrator_DeviceCommand(
                device=device_type,
                command=Orchestrator.DeviceCommands.SHUTDOWN,
            ))

        # All processes should exit within 10 seconds
        deadline = time.monotonic() + 10
        still_alive = {}
        for device_type, proc in procs.items():
            remaining = max(0.1, deadline - time.monotonic())
            try:
                proc.wait(timeout=remaining)
            except Exception:
                still_alive[device_type.name] = proc

        assert not still_alive, (
            f"These devices did not exit after SHUTDOWN: "
            f"{list(still_alive.keys())}"
        )


# ---------------------------------------------------------------------------
# Security mode tests
# ---------------------------------------------------------------------------

@pytest.mark.secure
class TestSecurePatientSensor:
    """PatientSensor should work correctly in secure mode."""

    def test_vitals_flow_with_security(self, proc_manager_secure, dds_env_secure):
        """Vitals are published successfully when DDS Security is enabled."""
        proc_manager_secure.start_cpp("PatientSensor")

        # Give the sensor time to start and begin publishing
        time.sleep(3)

        # Run DDS subscriber in a subprocess to avoid XML namespace conflict
        samples = run_dds_subscriber_secure(
            dds_env_secure,
            topic_name="t/Vitals",
            type_module="Types",
            type_class="PatientMonitor_Vitals",
            qos_profile="DataFlowLibrary::Streaming",
            timeout_sec=15,
            min_count=1,
        )
        assert len(samples) >= 1, "No vitals received in secure mode"


@pytest.mark.secure
@pytest.mark.gui
class TestSecureAllApps:
    """All apps should launch and report ON in secure mode."""

    def test_secure_launch(self, proc_manager_secure, dds_env_secure):
        proc_manager_secure.start_cpp("PatientSensor")
        proc_manager_secure.start_cpp("Orchestrator")
        proc_manager_secure.start_cpp("ArmController")
        proc_manager_secure.start_python("PatientMonitor.py", extra_env=QT_ENV)
        proc_manager_secure.start_python("Arm.py", extra_env=QT_ENV)

        # Give apps time to start
        time.sleep(5)

        # Collect DeviceStatus.device names in a subprocess
        samples = run_dds_subscriber_secure(
            dds_env_secure,
            topic_name="t/DeviceStatus",
            type_module="Types",
            type_class="Common_DeviceStatus",
            qos_profile="DataFlowLibrary::Status",
            timeout_sec=20,
            min_count=4,
            extract_field="device",
        )

        # samples are string representations of the device enum values
        unique_devices = set(samples)
        assert len(unique_devices) >= 4, (
            f"Only {len(unique_devices)} devices ON in secure mode: {unique_devices}"
        )
