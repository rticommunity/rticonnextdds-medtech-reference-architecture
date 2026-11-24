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

import asyncio
import math
import signal
import subprocess
import time
from types import SimpleNamespace

import pytest
from module01_test_support import local_ui_url, wait_for_ui_data
from test_utils import (
    check_no_deadline_missed,
    wait_for_device_status,
    wait_for_reader_match,
    wait_for_samples,
    wait_for_writer_match,
)

# ---------------------------------------------------------------------------
# PatientSensor (headless) — no @gui marker needed
# ---------------------------------------------------------------------------


def test_patient_monitor_rejects_paused_and_metadata_samples():
    from MedTech import Device, Patient
    from PatientMonitor import PatientMonitorApp, VitalsStatus

    app = PatientMonitorApp.__new__(PatientMonitorApp)
    app.status = Device.DeviceStatusKind.ON
    app.status_sample = Device.Status(device=Device.DeviceType.PATIENT_MONITOR)
    app.status_writer = SimpleNamespace(write=lambda _: None)
    app.vitals_status = VitalsStatus.WAITING_FOR_VITALS
    app.vitals = None
    app.failed = False
    app.ui = SimpleNamespace(log=lambda *args: None, update=lambda **kwargs: None)
    vitals = Patient.Vitals(patient_id="ab1234", hr=60, spo2=98, etco2=40, nibp_s=120, nibp_d=80)

    async def exercise():
        app.process_vitals_sample(vitals, SimpleNamespace(valid=False))
        app.status = Device.DeviceStatusKind.PAUSED
        app.process_vitals_sample(vitals, SimpleNamespace(valid=True))
        assert app.vitals_status == VitalsStatus.WAITING_FOR_VITALS
        assert app.view()["vitals_status"] == "STREAM PAUSED"
        assert app.status_sample.readiness == Device.DeviceReadinessKind.NOT_READY
        app.status = Device.DeviceStatusKind.OFF
        assert app.view()["vitals_status"] == "MONITOR OFFLINE"
        app.status = Device.DeviceStatusKind.ON
        app.process_vitals_sample(vitals, SimpleNamespace(valid=True))
        assert app.vitals_status == VitalsStatus.LIVE_VITALS
        assert app.status_sample.readiness == Device.DeviceReadinessKind.READY
        vitals.spo2 = 101
        app.process_vitals_sample(vitals, SimpleNamespace(valid=True))
        assert app.view()["vitals_status"] == "INVALID VITALS"
        app.mark_vitals_quiet()
        assert app.view()["vitals_status"] == "DATA QUIET"

    asyncio.run(exercise())


def test_patient_monitor_processes_only_triggered_conditions(monkeypatch):
    import PatientMonitor

    calls = []
    data_condition = SimpleNamespace(close=lambda: calls.append("close"))
    deadline_condition = SimpleNamespace(enabled_statuses=None)
    stop_condition = SimpleNamespace(trigger_value=False)

    class Reader:
        @property
        def requested_deadline_missed_status(self):
            calls.append("deadline")
            return SimpleNamespace(total_count_change=1)

        def select(self):
            calls.append("take")
            return self

        def condition(self, condition):
            assert condition is data_condition
            return self

        def take(self):
            return []

    class WaitSet:
        def __init__(self):
            self.iteration = 0
            self.ready = asyncio.Event()

        def __iadd__(self, _condition):
            return self

        async def wait_async(self):
            self.iteration += 1
            if self.iteration == 1:
                return [data_condition]
            if self.iteration == 2:
                assert calls == ["take"]
                return [deadline_condition]
            assert calls == ["take", "deadline", "quiet"]
            self.ready.set()
            while not stop_condition.trigger_value:
                await asyncio.sleep(0.001)
            return [stop_condition]

        def detach_all(self):
            calls.append("detach")

    waitset = WaitSet()
    monkeypatch.setattr(PatientMonitor.dds, "ReadCondition", lambda *_: data_condition)
    monkeypatch.setattr(PatientMonitor.dds, "StatusCondition", lambda *_: deadline_condition)
    monkeypatch.setattr(PatientMonitor.dds, "GuardCondition", lambda: stop_condition)
    monkeypatch.setattr(PatientMonitor.dds, "WaitSet", lambda: waitset)
    app = PatientMonitor.PatientMonitorApp.__new__(PatientMonitor.PatientMonitorApp)
    app.vitals_reader = Reader()
    app.mark_vitals_quiet = lambda: calls.append("quiet")

    async def exercise():
        receiver = asyncio.create_task(app.receive_vitals_stream())
        await asyncio.wait_for(waitset.ready.wait(), 1)
        receiver.cancel()
        with pytest.raises(asyncio.CancelledError):
            await receiver

    asyncio.run(exercise())
    assert calls == ["take", "deadline", "quiet", "detach", "close"]


def test_patient_monitor_reports_lifecycle_and_vitals_readiness(
    proc_manager, nonsecure_utility_app
):
    from MedTech import Device, Patient

    status_reader = nonsecure_utility_app.device_status.reader
    command_writer = nonsecure_utility_app.device_command.writer
    vitals_writer = nonsecure_utility_app.vitals.writer
    monitor = proc_manager.start_app_ready("PatientMonitor")
    ui_url = local_ui_url(monitor, "Patient Monitor listening on")
    assert wait_for_writer_match(command_writer)
    assert wait_for_writer_match(vitals_writer)

    def wait_for_monitor_status(status, readiness):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            for sample in status_reader.take_data():
                if (
                    sample.device == Device.DeviceType.PATIENT_MONITOR
                    and sample.status == status
                    and sample.readiness == readiness
                ):
                    return
            time.sleep(0.05)
        pytest.fail(f"Patient Monitor did not publish {status.name}/{readiness.name}")

    def command(value):
        command_writer.write(
            Device.Command(device=Device.DeviceType.PATIENT_MONITOR, command=value)
        )

    vitals = Patient.Vitals(patient_id="ab1234", hr=60, spo2=98, etco2=40, nibp_s=120, nibp_d=80)
    wait_for_monitor_status(Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.NOT_READY)
    vitals_writer.write(
        Patient.Vitals(patient_id="other", hr=60, spo2=98, etco2=40, nibp_s=120, nibp_d=80)
    )
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        assert all(
            sample.readiness != Device.DeviceReadinessKind.READY
            for sample in status_reader.take_data()
            if sample.device == Device.DeviceType.PATIENT_MONITOR
        )
        time.sleep(0.05)

    vitals_writer.write(vitals)
    wait_for_monitor_status(Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.READY)
    vitals_writer.write(
        Patient.Vitals(patient_id="ab1234", hr=60, spo2=101, etco2=40, nibp_s=120, nibp_d=80)
    )
    wait_for_monitor_status(Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.NOT_READY)
    wait_for_ui_data(ui_url, lambda data: data["vitals_status"] == "INVALID VITALS")
    vitals_writer.write(vitals)
    wait_for_monitor_status(Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.READY)
    command(Device.DeviceCommandKind.PAUSE)
    wait_for_monitor_status(Device.DeviceStatusKind.PAUSED, Device.DeviceReadinessKind.NOT_READY)
    command(Device.DeviceCommandKind.START)
    wait_for_monitor_status(Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.NOT_READY)

    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        assert all(
            sample.readiness != Device.DeviceReadinessKind.READY
            for sample in status_reader.take_data()
            if sample.device == Device.DeviceType.PATIENT_MONITOR
        )
        time.sleep(0.05)

    vitals_writer.write(vitals)
    wait_for_monitor_status(Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.READY)
    wait_for_monitor_status(Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.NOT_READY)
    wait_for_ui_data(ui_url, lambda data: data["vitals_status"] == "DATA QUIET")
    vitals_writer.write(vitals)
    wait_for_monitor_status(Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.READY)
    vitals_writer.close()
    wait_for_monitor_status(Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.NOT_READY)
    wait_for_ui_data(ui_url, lambda data: data["vitals_status"] == "DATA QUIET")


def test_patient_monitor_does_not_restore_stale_queued_vitals(nonsecure_utility_app):
    import rti.connextdds as dds
    from MedTech import DdsEntities, Device, Patient
    from PatientMonitor import PatientMonitorApp, VitalsStatus
    from test_utils import register_type

    for data_type in (Device.Status, Device.Heartbeat, Device.Command, Patient.Vitals):
        register_type(data_type)
    participant = nonsecure_utility_app.qos_provider.create_participant_from_config(
        DdsEntities.Constants.PATIENT_MONITOR_DP
    )
    try:
        participant.enable()
        app = PatientMonitorApp.__new__(PatientMonitorApp)
        app.participant = participant
        app.vitals_reader = dds.DataReader(
            participant.find_datareader(DdsEntities.Constants.VITALS_DR)
        )
        app.status = Device.DeviceStatusKind.ON
        app.status_sample = Device.Status(device=Device.DeviceType.PATIENT_MONITOR)
        app.status_writer = SimpleNamespace(write=lambda _: None)
        app.vitals = None
        app.vitals_status = VitalsStatus.WAITING_FOR_VITALS
        app.failed = False
        app.ui = SimpleNamespace(log=lambda *args: None, update=lambda **kwargs: None)
        writer = nonsecure_utility_app.vitals.writer
        assert wait_for_writer_match(writer)
        vitals = Patient.Vitals(
            patient_id="ab1234", hr=60, spo2=98, etco2=40, nibp_s=120, nibp_d=80
        )

        async def exercise():
            app.status = Device.DeviceStatusKind.PAUSED
            data_condition = dds.ReadCondition(
                app.vitals_reader, dds.DataState(dds.SampleState.NOT_READ)
            )
            try:
                writer.write(vitals)
                for _ in range(100):
                    if data_condition.trigger_value:
                        break
                    await asyncio.sleep(0.01)
                assert data_condition.trigger_value, "Paused sample was not queued"
                app.apply_command(Device.DeviceCommandKind.START)
                assert not data_condition.trigger_value
                assert app.vitals_status == VitalsStatus.WAITING_FOR_VITALS
            finally:
                data_condition.close()
            receiver = asyncio.create_task(app.receive_vitals_stream())
            try:
                await asyncio.sleep(0.1)
                writer.write(vitals)
                time.sleep(2.6)
                await asyncio.sleep(0.3)
                assert app.vitals_status == VitalsStatus.WAITING_FOR_VITALS
                assert app.status_sample.readiness == Device.DeviceReadinessKind.NOT_READY
                writer.write(vitals)
                await asyncio.sleep(0.3)
                assert app.vitals_status == VitalsStatus.LIVE_VITALS
                assert app.status_sample.readiness == Device.DeviceReadinessKind.READY
                writer.write(vitals)
                time.sleep(2.6)
                await asyncio.sleep(0.3)
                assert app.vitals_status == VitalsStatus.DATA_QUIET
                assert app.status_sample.readiness == Device.DeviceReadinessKind.NOT_READY
                writer.write(vitals)
                await asyncio.sleep(0.3)
                assert app.vitals_status == VitalsStatus.LIVE_VITALS
                assert app.status_sample.readiness == Device.DeviceReadinessKind.READY
                time.sleep(2.4)
                writer.write(vitals)
                time.sleep(0.2)
                await asyncio.sleep(0.3)
                assert app.vitals_status == VitalsStatus.LIVE_VITALS
                assert app.status_sample.readiness == Device.DeviceReadinessKind.READY
            finally:
                receiver.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await receiver

        asyncio.run(exercise())
    finally:
        participant.close()


@pytest.mark.parametrize("patient_id", ["xy9876", "a-b_1", "é12"])
def test_patient_monitor_selects_configured_patient(
    proc_manager, nonsecure_utility_app, patient_id
):
    from MedTech import Patient

    writer = nonsecure_utility_app.vitals.writer
    monitor = proc_manager.start_app_ready(
        "PatientMonitor", extra_env={"MEDTECH_PATIENT_ID": patient_id}
    )
    ui_url = local_ui_url(monitor, "Patient Monitor listening on")
    assert wait_for_writer_match(writer)
    writer.write(
        Patient.Vitals(patient_id="ab1234", hr=60, spo2=98, etco2=40, nibp_s=120, nibp_d=80)
    )
    time.sleep(0.3)
    wait_for_ui_data(ui_url, lambda data: data["vitals_status"] == "WAITING FOR VITALS")
    writer.write(
        Patient.Vitals(patient_id=patient_id, hr=70, spo2=98, etco2=40, nibp_s=120, nibp_d=80)
    )
    wait_for_ui_data(ui_url, lambda data: data["vitals_status"] == "LIVE VITALS")


@pytest.mark.parametrize("patient_id", ["", "123456789", "x\0y", "a'b"])
def test_patient_monitor_rejects_invalid_patient_id(patient_id):
    from PatientMonitor import patient_filter_parameter

    with pytest.raises(ValueError, match="MEDTECH_PATIENT_ID"):
        patient_filter_parameter(patient_id)


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
        from MedTech import Device

        heartbeat_reader = nonsecure_utility_app.device_heartbeat.reader
        assert wait_for_reader_match(heartbeat_reader), "Heartbeat reader never matched a writer"
        samples = wait_for_samples(
            heartbeat_reader,
            n=3,
            timeout_sec=3,
            filter_fn=lambda sample: sample.device == Device.DeviceType.PATIENT_SENSOR,
        )
        assert len(samples) >= 3, "PatientSensor did not publish repeated heartbeats"
        assert check_no_deadline_missed(heartbeat_reader), "Deadline missed on Heartbeat reader"

    def test_status_on(self, nonsecure_utility_app):
        from MedTech import Device

        status_reader = nonsecure_utility_app.device_status.reader

        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatusKind.ON],
            timeout_sec=10,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )


@pytest.mark.parametrize(
    ("application", "device"),
    [
        ("ArmController", "ARM_CONTROLLER"),
        ("Arm", "ARM"),
        ("PatientMonitor", "PATIENT_MONITOR"),
    ],
)
def test_device_repeatedly_asserts_heartbeat(
    proc_manager, nonsecure_utility_app, application, device
):
    from MedTech import Device

    heartbeat_reader = nonsecure_utility_app.device_heartbeat.reader
    proc_manager.start_app_ready(application)
    assert wait_for_reader_match(heartbeat_reader)
    expected = getattr(Device.DeviceType, device)
    samples = wait_for_samples(
        heartbeat_reader,
        n=3,
        timeout_sec=5,
        filter_fn=lambda sample: sample.device == expected,
    )
    assert len(samples) >= 3, f"{application} did not publish repeated heartbeats"
    assert check_no_deadline_missed(heartbeat_reader), f"{application} missed its deadline"


class TestPatientSensorCommands:
    """PatientSensor should respond to DeviceCommand messages."""

    def test_sigterm_stops_heartbeat_and_exits_cleanly(self, proc_manager, nonsecure_utility_app):
        from MedTech import Device

        status_reader = nonsecure_utility_app.device_status.reader
        proc = proc_manager.start_app("PatientSensor")
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatusKind.ON],
            timeout_sec=10,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen

        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        assert proc.returncode == 0
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatusKind.OFF],
            timeout_sec=2,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen

    def test_startup_error_exits_with_failure_status(self, proc_manager, tmp_path):
        proc = proc_manager.start_app(
            "PatientSensor",
            extra_env={"NDDS_QOS_PROFILES": str(tmp_path / "missing-qos.xml")},
        )
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("PatientSensor did not exit after its QoS configuration failed")

        assert proc.returncode != 0
        assert proc.stderr is not None
        assert b"Patient Sensor failed" in proc.stderr.read()

    def test_responds_to_shutdown(self, proc_manager, nonsecure_utility_app):
        from MedTech import Device

        proc = proc_manager.start_app("PatientSensor")

        status_reader = nonsecure_utility_app.device_status.reader
        cmd_writer = nonsecure_utility_app.device_command.writer

        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatusKind.ON],
            timeout_sec=10,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )

        # Send SHUTDOWN command
        assert wait_for_writer_match(cmd_writer), "Command writer never matched a reader"
        cmd = Device.Command(
            device=Device.DeviceType.PATIENT_SENSOR,
            command=Device.DeviceCommandKind.SHUTDOWN,
        )
        cmd_writer.write(cmd)

        # PatientSensor should exit within 5s
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pytest.fail("PatientSensor did not exit after SHUTDOWN command")
        assert proc.returncode == 0


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
            device_statuses=[Device.DeviceStatusKind.ON],
            timeout_sec=10,
        )
        assert Device.DeviceType.ARM in seen, (
            "Arm did not report DeviceStatus ON within the timeout"
        )

        teleop_writer = nonsecure_utility_app.teleop_control.writer
        tool_writer = nonsecure_utility_app.tool_control.writer
        telemetry = nonsecure_utility_app.arm_telemetry.reader
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
        assert any(
            sample.device == Device.DeviceType.ARM
            and sample.readiness == Device.DeviceReadinessKind.READY
            for sample in status_reader.read_data()
        )

        def position(sample):
            point = sample.tcp_pose.position
            return (point.x, point.y, point.z)

        assert position(moved)[0] - position(initial)[0] > 0.0005
        assert position(moved)[1:] == pytest.approx(position(initial)[1:], abs=1e-4)
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
            assert any(
                sample.device == Device.DeviceType.ARM
                and sample.readiness == Device.DeviceReadinessKind.NOT_READY
                for sample in status_reader.read_data()
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
# Content filter verification
# ---------------------------------------------------------------------------


class TestContentFilter:
    """DeviceCommand content filters should route commands only to the targeted device."""

    def test_patient_sensor_filters_commands_by_device(self, proc_manager, nonsecure_utility_app):
        """PatientSensor ignores ARM commands and accepts its own commands."""
        from MedTech import Device

        proc_manager.start_app("PatientSensor")

        status_reader = nonsecure_utility_app.device_status.reader
        vitals_reader = nonsecure_utility_app.vitals.reader
        cmd_writer = nonsecure_utility_app.device_command.writer

        # Wait for device status
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatusKind.ON],
            timeout_sec=10,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, (
            "PatientSensor did not report DeviceStatus ON within the timeout"
        )

        assert wait_for_reader_match(vitals_reader), "Vitals reader never matched a writer"
        samples = wait_for_samples(vitals_reader, timeout_sec=4)
        assert len(samples) >= 1, "No vitals received from PatientSensor"
        assert wait_for_writer_match(cmd_writer), "Command writer never matched a reader"

        # Send PAUSE addressed to ARM — PatientSensor should ignore it
        cmd = Device.Command(
            device=Device.DeviceType.ARM,
            command=Device.DeviceCommandKind.PAUSE,
        )
        cmd_writer.write(cmd)
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatusKind.PAUSED],
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

        cmd_writer.write(
            Device.Command(
                device=Device.DeviceType.PATIENT_SENSOR,
                command=Device.DeviceCommandKind.PAUSE,
            )
        )
        seen = wait_for_device_status(
            status_reader,
            expected_devices={Device.DeviceType.PATIENT_SENSOR},
            device_statuses=[Device.DeviceStatusKind.PAUSED],
            timeout_sec=2,
        )
        assert Device.DeviceType.PATIENT_SENSOR in seen, "PatientSensor did not accept PAUSE"
