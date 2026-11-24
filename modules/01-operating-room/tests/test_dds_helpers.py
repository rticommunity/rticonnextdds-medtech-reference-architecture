#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

import asyncio
import importlib
import threading
import time
from types import SimpleNamespace

import pytest
import test_utils
from MedTech import Device, Robot
from test_utils import wait_for_device_status, wait_for_samples, wait_for_writer_match


def _status(device):
    return Device.Status(device=device, status=Device.DeviceStatusKind.ON)


def test_security_probe_unexpected_failure_is_not_a_skip(monkeypatch):
    monkeypatch.delattr(test_utils.security_plugin_available, "_cached", raising=False)
    monkeypatch.setattr(
        test_utils.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2, stderr="probe crashed", stdout=""),
    )
    with pytest.raises(RuntimeError, match="probe crashed"):
        test_utils.security_plugin_available()


def test_read_samples_counts_each_cached_sample_once(nonsecure_utility_app):
    reader = nonsecure_utility_app.device_status.reader
    writer = nonsecure_utility_app.device_status.writer
    assert wait_for_writer_match(writer)
    writer.write(_status(Device.DeviceType.ARM))

    assert len(wait_for_samples(reader, n=1, read=True)) == 1
    assert len(wait_for_samples(reader, n=2, timeout_sec=0.25, read=True)) == 1

    timer = threading.Timer(0.1, writer.write, args=[_status(Device.DeviceType.PATIENT_SENSOR)])
    timer.start()
    try:
        samples = wait_for_samples(reader, n=2, timeout_sec=2, read=True)
    finally:
        timer.join()
    assert {sample.device for sample in samples} == {
        Device.DeviceType.ARM,
        Device.DeviceType.PATIENT_SENSOR,
    }


def test_status_wait_accepts_cached_and_unexpected_devices(nonsecure_utility_app):
    reader = nonsecure_utility_app.device_status.reader
    writer = nonsecure_utility_app.device_status.writer
    assert wait_for_writer_match(writer)
    writer.write(_status(Device.DeviceType.ARM))
    writer.write(_status(Device.DeviceType.PATIENT_SENSOR))
    assert len(wait_for_samples(reader, n=2, read=True)) == 2

    start = time.monotonic()
    seen = wait_for_device_status(reader, {Device.DeviceType.ARM}, timeout_sec=2)
    assert Device.DeviceType.ARM in seen
    assert time.monotonic() - start < 1

    timer = threading.Timer(0.1, writer.write, args=[_status(Device.DeviceType.PATIENT_MONITOR)])
    timer.start()
    try:
        seen = wait_for_device_status(
            reader, {Device.DeviceType.ARM, Device.DeviceType.PATIENT_MONITOR}, timeout_sec=2
        )
    finally:
        timer.join()
    assert {Device.DeviceType.ARM, Device.DeviceType.PATIENT_MONITOR}.issubset(seen)


def test_arm_readiness_cache_tracks_successful_publication():
    from Arm import ArmApp

    app = ArmApp.__new__(ArmApp)
    app._last_published_readiness = None
    app.status_sample = Device.Status(device=Device.DeviceType.ARM)
    written = []

    def write(sample):
        if not written:
            written.append("failed")
            raise RuntimeError("write failed")
        written.append(sample.readiness.name)

    app.status_writer = SimpleNamespace(write=write)
    with pytest.raises(RuntimeError, match="write failed"):
        app.write_readiness(Device.DeviceReadinessKind.READY)
    app.write_readiness(Device.DeviceReadinessKind.READY)
    app.write_readiness(Device.DeviceReadinessKind.READY)
    assert written == ["failed", "READY"]
    app.write_readiness(Device.DeviceReadinessKind.FAULTED)
    assert app.status_sample.readiness == Device.DeviceReadinessKind.FAULTED
    assert written[-1] == "FAULTED"


@pytest.mark.parametrize(
    "module_name, class_name", [("Arm", "ArmApp"), ("ArmKortex", "ArmKortexApp")]
)
def test_control_deadline_dispatch_and_shutdown(nonsecure_utility_app, module_name, class_name):
    from PhysicalMotionGate import MotionConditions, PhysicalMotionGate

    cls = getattr(importlib.import_module(module_name), class_name)
    app = cls.__new__(cls)
    app._motion_cancelled = threading.Event()
    arm = nonsecure_utility_app.teleop_control
    tool = nonsecure_utility_app.tool_control
    app.teleop_reader = arm.reader
    app.tool_reader = tool.reader
    app.motion_gate = PhysicalMotionGate()
    app.motion_gate.update(MotionConditions(True, True, True, True))
    assert app.motion_gate.rearm()
    app.commands_fresh = True
    app.command_rates_neutral = True
    app._control_wake = asyncio.Event()
    assert wait_for_writer_match(arm.writer)
    assert wait_for_writer_match(tool.writer)

    async def exercise():
        event = asyncio.Event()
        messages = []
        loop_thread = threading.get_ident()

        def diagnostic(message):
            assert threading.get_ident() == loop_thread
            messages.append(message)
            if len(messages) >= (2 if module_name == "Arm" else 1):
                event.set()

        app._diagnostic = diagnostic
        task = asyncio.create_task(app.monitor_control_health())
        await asyncio.sleep(0)
        arm.writer.write(Robot.Arm.TeleopControl(arm_id="arm-1"))
        tool.writer.write(Robot.Tool.ParallelJawControl(arm_id="arm-1"))
        try:
            await asyncio.wait_for(event.wait(), timeout=3)
            assert any(message.startswith("Arm ") for message in messages)
            if module_name == "Arm":
                assert any(message.startswith("Jaw ") for message in messages)
            else:
                assert not any(message.startswith("Jaw ") for message in messages)
            assert not app.motion_gate.armed
            assert not app.commands_fresh
            assert not app.command_rates_neutral
            assert app._control_wake.is_set()
            assert app._command(arm.reader) is None
            if module_name == "Arm":
                assert app._command(tool.reader) is None
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "module_name, class_name, lost_stream",
    [("Arm", "ArmApp", "Arm"), ("Arm", "ArmApp", "Jaw"), ("ArmKortex", "ArmKortexApp", "Arm")],
)
def test_control_deadline_requires_new_neutral_samples_and_rearm(
    nonsecure_utility_app, module_name, class_name, lost_stream
):
    from PhysicalMotionGate import PhysicalMotionGate

    cls = getattr(importlib.import_module(module_name), class_name)
    app = cls.__new__(cls)
    app._motion_cancelled = threading.Event()
    arm = nonsecure_utility_app.teleop_control
    tool = nonsecure_utility_app.tool_control
    app.teleop_reader = arm.reader
    app.tool_reader = tool.reader
    app.motion_gate = PhysicalMotionGate()
    app.status = Device.DeviceStatusKind.ON
    app.commands_fresh = False
    app.command_rates_neutral = False
    app._control_wake = asyncio.Event()
    assert wait_for_writer_match(arm.writer)
    assert wait_for_writer_match(tool.writer)

    async def exercise():
        event = asyncio.Event()
        enabled = {"Arm": True, "Jaw": True}
        arm_command = Robot.Arm.TeleopControl(arm_id="arm-1")
        tool_command = Robot.Tool.ParallelJawControl(arm_id="arm-1")

        def diagnostic(message):
            if message.startswith(lost_stream + " "):
                event.set()

        def update():
            app.rates()
            if module_name == "ArmKortex":
                app._health_observed_at = time.monotonic()
            app.update_motion_gate(connected=True, healthy=True)

        async def publish():
            while True:
                if enabled["Arm"]:
                    arm.writer.write(arm_command)
                if enabled["Jaw"]:
                    tool.writer.write(tool_command)
                await asyncio.sleep(0.01)

        async def wait_for_rearm():
            async with asyncio.timeout(3):
                while True:
                    update()
                    if app.motion_gate.can_rearm:
                        return
                    await asyncio.sleep(0.01)

        app._diagnostic = diagnostic
        update()
        assert not app.motion_gate.can_rearm
        monitor = asyncio.create_task(app.monitor_control_health())
        publisher = asyncio.create_task(publish())
        try:
            await wait_for_rearm()
            assert app.motion_gate.rearm()
            app._control_deadline_missed("Arm", arm.reader)
            assert not app.motion_gate.armed
            assert app._command(arm.reader) is None
            if module_name == "Arm":
                assert app._command(tool.reader) is None
            await wait_for_rearm()
            assert app.motion_gate.rearm()
            event.clear()
            enabled[lost_stream] = False
            await asyncio.wait_for(event.wait(), timeout=3)
            assert not app.motion_gate.armed
            update()
            assert not app.motion_gate.can_rearm

            arm_command.linear_velocity.x = 0.01
            enabled[lost_stream] = True
            async with asyncio.timeout(3):
                while True:
                    update()
                    if app.commands_fresh and not app.command_rates_neutral:
                        break
                    await asyncio.sleep(0.01)
            assert not app.motion_gate.can_rearm
            arm_command.linear_velocity.x = 0.0
            await wait_for_rearm()
            assert not app.motion_gate.armed
            assert app.motion_gate.rearm()
            await asyncio.sleep(0.15)
            assert app.motion_gate.armed
        finally:
            publisher.cancel()
            monitor.cancel()
            with pytest.raises(asyncio.CancelledError):
                await publisher
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(monitor, timeout=3)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "module_name, class_name", [("Arm", "ArmApp"), ("ArmKortex", "ArmKortexApp")]
)
def test_control_deadline_dispatch_cancels_when_idle(
    nonsecure_utility_app, module_name, class_name
):
    cls = getattr(importlib.import_module(module_name), class_name)
    app = cls.__new__(cls)
    app.teleop_reader = nonsecure_utility_app.teleop_control.reader
    app.tool_reader = nonsecure_utility_app.tool_control.reader

    async def exercise():
        app._diagnostic = lambda _: pytest.fail("No samples were written")
        for _ in range(5):
            task = asyncio.create_task(app.monitor_control_health())
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "module_name, class_name", [("Arm", "ArmApp"), ("ArmKortex", "ArmKortexApp")]
)
def test_control_deadline_repeated_cancellation_joins_dispatch(
    nonsecure_utility_app, monkeypatch, module_name, class_name
):
    module = importlib.import_module(module_name)
    app = getattr(module, class_name).__new__(getattr(module, class_name))
    app.teleop_reader = nonsecure_utility_app.teleop_control.reader
    app.tool_reader = nonsecure_utility_app.tool_control.reader
    original_dds = module.dds

    async def exercise():
        released = asyncio.Event()
        dispatch_woken = asyncio.Event()
        detached = False

        class DelayedWaitSet:
            def __init__(self):
                self.waitset = original_dds.WaitSet()

            def attach_condition(self, condition):
                self.waitset.attach_condition(condition)

            async def wait_async(self):
                result = await self.waitset.wait_async()
                dispatch_woken.set()
                await released.wait()
                return result

            def detach_all(self):
                nonlocal detached
                detached = True
                self.waitset.detach_all()

        monkeypatch.setattr(
            module,
            "dds",
            SimpleNamespace(
                WaitSet=DelayedWaitSet,
                GuardCondition=original_dds.GuardCondition,
                StatusCondition=original_dds.StatusCondition,
                StatusMask=original_dds.StatusMask,
            ),
        )
        task = asyncio.create_task(app.monitor_control_health())
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await asyncio.wait_for(dispatch_woken.wait(), timeout=3)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            assert not detached
        finally:
            released.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3)
        assert detached

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "module_name, class_name", [("Arm", "ArmApp"), ("ArmKortex", "ArmKortexApp")]
)
@pytest.mark.parametrize(
    "command, expected_remaining", [("START", 1), ("PAUSE", 0), ("SHUTDOWN", 0)]
)
def test_lifecycle_command_drains_cached_dds_rates(
    nonsecure_utility_app, module_name, class_name, command, expected_remaining
):
    from PhysicalMotionGate import PhysicalMotionGate

    cls = getattr(importlib.import_module(module_name), class_name)
    app = cls.__new__(cls)
    app._motion_cancelled = threading.Event()
    app.status = Device.DeviceStatusKind.ON
    app.readiness = Device.DeviceReadinessKind.NOT_READY
    app.motion_gate = PhysicalMotionGate()
    arm = nonsecure_utility_app.teleop_control
    tool = nonsecure_utility_app.tool_control
    app.teleop_reader = arm.reader
    app.tool_reader = tool.reader
    assert wait_for_writer_match(arm.writer)
    assert wait_for_writer_match(tool.writer)
    arm.writer.write(Robot.Arm.TeleopControl(arm_id="arm-1"))
    tool.writer.write(Robot.Tool.ParallelJawControl(arm_id="arm-1"))
    assert wait_for_samples(arm.reader, n=1, read=True)
    assert wait_for_samples(tool.reader, n=1, read=True)

    app.apply_command(getattr(Device.DeviceCommandKind, command))

    assert len(arm.reader.read()) == expected_remaining
    assert len(tool.reader.read()) == (expected_remaining if module_name == "Arm" else 1)
