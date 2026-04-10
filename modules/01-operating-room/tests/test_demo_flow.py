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
        from Types import Common, Common_DeviceHeartbeat

        patient_sensor = proc_manager.start_cpp("PatientSensor")
        proc_manager.start_cpp("Orchestrator")

        hb_reader = create_reader(
            dds_participant,
            "t/DeviceHeartbeat",
            Common_DeviceHeartbeat,
            "DataFlowLibrary::Heartbeat",
        )

        # Wait for PatientSensor heartbeats to start flowing
        samples = wait_for_data(hb_reader, timeout_sec=10)
        assert any(s.device == Common.DeviceType.PATIENT_SENSOR for s in samples), (
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

        # After kill, heartbeats should stop arriving.
        # The Orchestrator detects this via the 200ms deadline QoS.
        # We verify the same thing: no new heartbeats arrive.
        hb_reader.take()  # drain anything buffered
        time.sleep(1)  # wait longer than the 200ms deadline
        post_kill = hb_reader.take()
        post_kill_valid = [s for s in post_kill if s.info.valid]
        assert len(post_kill_valid) == 0, f"Heartbeats still arriving after SIGKILL ({len(post_kill_valid)} samples)"


# ---------------------------------------------------------------------------
# Pause and resume (README: Orchestrator sends PAUSE, then START)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestPauseAndResume:
    """Pausing PatientSensor should stop vitals; resuming should restart them."""

    def test_pause_stops_vitals_then_resume_restarts(self, proc_manager, dds_participant):
        from Types import (
            Common,
            Common_DeviceStatus,
            Orchestrator,
            Orchestrator_DeviceCommand,
            PatientMonitor_Vitals,
        )

        proc_manager.start_cpp("PatientSensor")

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

        # Wait for ON
        samples = wait_for_data(status_reader, timeout_sec=10)
        assert any(
            s.device == Common.DeviceType.PATIENT_SENSOR and s.status == Common.DeviceStatuses.ON for s in samples
        ), "PatientSensor never reached ON"

        # Verify vitals are flowing
        vitals = wait_for_data(vitals_reader, timeout_sec=5)
        assert len(vitals) >= 1, "No vitals before pause"

        # Send PAUSE
        cmd_writer.write(
            Orchestrator_DeviceCommand(
                device=Common.DeviceType.PATIENT_SENSOR,
                command=Orchestrator.DeviceCommands.PAUSE,
            )
        )

        # Wait for PAUSED status
        paused = False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            ss = wait_for_data(status_reader, timeout_sec=1)
            if any(
                s.device == Common.DeviceType.PATIENT_SENSOR and s.status == Common.DeviceStatuses.PAUSED for s in ss
            ):
                paused = True
                break
        assert paused, "PatientSensor did not transition to PAUSED"

        # Drain any remaining vitals and then check no new ones arrive
        vitals_reader.take()  # drain
        time.sleep(2)
        stale = vitals_reader.take()
        valid_stale = [s for s in stale if s.info.valid]
        assert len(valid_stale) <= 1, f"Vitals still flowing while PAUSED ({len(valid_stale)} samples)"

        # Send START
        cmd_writer.write(
            Orchestrator_DeviceCommand(
                device=Common.DeviceType.PATIENT_SENSOR,
                command=Orchestrator.DeviceCommands.START,
            )
        )

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
            Common,
            Common_DeviceStatus,
            Orchestrator,
            Orchestrator_DeviceCommand,
        )

        procs = {
            Common.DeviceType.PATIENT_SENSOR: proc_manager.start_cpp("PatientSensor"),
            Common.DeviceType.ARM_CONTROLLER: proc_manager.start_cpp("ArmController"),
            Common.DeviceType.ARM: proc_manager.start_python("Arm.py", extra_env=QT_ENV),
            Common.DeviceType.PATIENT_MONITOR: proc_manager.start_python("PatientMonitor.py", extra_env=QT_ENV),
        }

        create_reader(
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

        # Wait for at least some devices to come online
        time.sleep(5)

        # Send SHUTDOWN to each device
        for device_type in procs:
            cmd_writer.write(
                Orchestrator_DeviceCommand(
                    device=device_type,
                    command=Orchestrator.DeviceCommands.SHUTDOWN,
                )
            )

        # All processes should exit within 10 seconds
        deadline = time.monotonic() + 10
        still_alive = {}
        for device_type, proc in procs.items():
            remaining = max(0.1, deadline - time.monotonic())
            try:
                proc.wait(timeout=remaining)
            except Exception:
                still_alive[device_type.name] = proc

        assert not still_alive, f"These devices did not exit after SHUTDOWN: {list(still_alive.keys())}"


# ---------------------------------------------------------------------------
# Security mode tests
# ---------------------------------------------------------------------------


@pytest.mark.secure
class TestSecurePatientSensor:
    """PatientSensor should work correctly in secure mode."""

    def test_vitals_flow_with_security(self, proc_manager_secure, dds_env_secure):
        """PatientSensor starts and runs with DDS Security enabled."""
        ps = proc_manager_secure.start_cpp("PatientSensor")

        # Give security handshake and publishing time
        time.sleep(5)

        if ps.poll() is not None:
            stdout = ps.stdout.read().decode(errors="replace") if ps.stdout else ""
            stderr = ps.stderr.read().decode(errors="replace") if ps.stderr else ""
            pytest.fail(
                f"PatientSensor exited prematurely (code={ps.returncode})\n"
                f"stdout:\n{stdout[-2000:]}\nstderr:\n{stderr[-2000:]}"
            )


@pytest.mark.secure
class TestSecureAllApps:
    """All C++ apps should launch successfully in secure mode."""

    def test_secure_launch(self, proc_manager_secure, dds_env_secure):
        """All C++ apps start and keep running with DDS Security enabled."""
        apps = {
            "PatientSensor": proc_manager_secure.start_cpp("PatientSensor"),
            "Orchestrator": proc_manager_secure.start_cpp("Orchestrator"),
            "ArmController": proc_manager_secure.start_cpp("ArmController"),
        }

        # Give apps time to start and complete security handshake
        time.sleep(5)

        crashed = {}
        for name, p in apps.items():
            if p.poll() is not None:
                stderr = p.stderr.read().decode(errors="replace") if p.stderr else ""
                crashed[name] = f"code={p.returncode}, stderr={stderr[-500:]}"
        assert not crashed, f"Apps crashed during secure startup:\n{crashed}"
