#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

import asyncio
import importlib
from types import SimpleNamespace

import pytest

_UNSECURED_QOS = SimpleNamespace(property=SimpleNamespace(exists=lambda _: False))


def _fail(message):
    raise RuntimeError(message)


async def _fail_stream():
    _fail("worker failed")
    yield


async def _fail_task():
    _fail("worker failed")


async def _wait():
    await asyncio.Event().wait()


class _UiApp:
    async def stop(self):
        pass


@pytest.mark.parametrize(
    ("module_name", "class_name"),
    [("Arm", "ArmApp"), ("PatientMonitor", "PatientMonitorApp")],
)
def test_participant_closed_when_final_status_write_fails(module_name, class_name, capsys):
    module = importlib.import_module(module_name)
    application = getattr(module, class_name).__new__(getattr(module, class_name))
    closed = []
    reader = SimpleNamespace(take_data_async=_fail_stream, take_async=_fail_stream)
    application.participant = SimpleNamespace(
        enable=lambda: None,
        close=lambda: closed.append(True),
        qos=_UNSECURED_QOS,
        current_time=object(),
    )
    application.status_writer = SimpleNamespace(write=lambda _: None)
    application.status_sample = object()

    def write_status(status):
        if status != module.Device.DeviceStatusKind.ON:
            _fail("final status failed")

    application.write_status = write_status
    application.write_readiness = lambda _: None
    application.rates = lambda: _fail("worker failed")
    application.vitals_reader = reader
    application.receive_vitals_stream = _fail_task
    application.command_reader = reader
    application.heartbeat_writer = object()
    application.failed = False
    application.status = module.Device.DeviceStatusKind.ON
    application.last_sample_at = None
    application.readiness = module.Device.DeviceReadinessKind.NOT_READY
    application.view = lambda **_: {}
    application.ui = SimpleNamespace(update=lambda **_: None, log=lambda *args: None)

    asyncio.run(application.run(_UiApp()))
    assert application.failed
    assert "final status failed" in capsys.readouterr().err
    assert closed == [True]


@pytest.mark.parametrize(
    ("module_name", "class_name"),
    [("Arm", "ArmApp"), ("PatientMonitor", "PatientMonitorApp")],
)
def test_participant_closed_when_enable_fails(module_name, class_name, capsys):
    module = importlib.import_module(module_name)
    application = getattr(module, class_name).__new__(getattr(module, class_name))
    closed = []
    application.failed = False
    application.participant = SimpleNamespace(
        enable=lambda: _fail("enable failed"),
        close=lambda: closed.append(True),
    )
    asyncio.run(application.run(_UiApp()))
    assert application.failed
    assert "enable failed" in capsys.readouterr().err
    assert closed == [True]


def test_arm_participant_closed_when_final_readiness_write_fails(capsys):
    module = importlib.import_module("Arm")
    application = module.ArmApp.__new__(module.ArmApp)
    closed = []
    readiness_writes = []
    reader = SimpleNamespace(take_data_async=_fail_stream)

    def write_readiness(status):
        readiness_writes.append(status)
        if status == module.Device.DeviceReadinessKind.NOT_READY and len(readiness_writes) > 1:
            _fail("final readiness failed")

    application.participant = SimpleNamespace(
        enable=lambda: None, close=lambda: closed.append(True), qos=_UNSECURED_QOS
    )
    application.status_writer = SimpleNamespace(write=lambda _: None)
    application.status_sample = object()
    application.write_status = lambda _: None
    application.write_readiness = write_readiness
    application.rates = lambda: _fail("worker failed")
    application.command_reader = reader
    application.heartbeat_writer = object()
    application.failed = False
    application.status = module.Device.DeviceStatusKind.ON
    application.readiness = module.Device.DeviceReadinessKind.NOT_READY
    application.view = lambda: {}
    application.ui = SimpleNamespace(update=lambda **_: None, log=lambda *args: None)

    asyncio.run(application.run(_UiApp()))
    assert application.failed
    assert "final readiness failed" in capsys.readouterr().err
    assert closed == [True]


def test_gamepad_and_participant_closed_when_stop_motion_fails(monkeypatch, capsys):
    module = pytest.importorskip("ArmControllerGamepad")
    application = module.ArmControllerGamepadApp.__new__(module.ArmControllerGamepadApp)
    closed = []
    application.participant = SimpleNamespace(
        enable=lambda: None,
        close=lambda: closed.append("dds"),
        qos=_UNSECURED_QOS,
    )
    application.status_writer = SimpleNamespace(write=lambda _: None)
    application.status_sample = SimpleNamespace(status=module.Device.DeviceStatusKind.ON)
    application.heartbeat_writer = object()
    application.failed = False
    application.status = module.Device.DeviceStatusKind.ON
    application.gamepad = SimpleNamespace(quit=lambda: closed.append("gamepad"))
    application.ui = SimpleNamespace(update=lambda **_: None, log=lambda *args: None)
    application.view = lambda: {}
    application.running = True
    application.receive_commands = _wait
    application.receive_arm_status = _wait
    application.receive_arm_telemetry = _wait
    application.process_events = lambda: _fail("worker failed")
    application.stop_motion = lambda: _fail("stop motion failed")
    monkeypatch.setattr(module, "initialize_gamepad_input", lambda: None)
    monkeypatch.setattr(module.pygame.display, "set_mode", lambda *args: None)
    monkeypatch.setattr(module.controller, "get_count", lambda: 0)
    monkeypatch.setattr(module.pygame, "quit", lambda: closed.append("pygame"))

    asyncio.run(application.run(_UiApp()))
    assert application.failed
    assert "stop motion failed" in capsys.readouterr().err
    assert closed == ["gamepad", "pygame", "dds"]


def test_gamepad_participant_closed_when_enable_fails(monkeypatch, capsys):
    module = pytest.importorskip("ArmControllerGamepad")
    application = module.ArmControllerGamepadApp.__new__(module.ArmControllerGamepadApp)
    closed = []
    application.participant = SimpleNamespace(
        enable=lambda: _fail("enable failed"),
        close=lambda: closed.append("dds"),
    )
    application.failed = False
    application.gamepad = None
    monkeypatch.setattr(module.pygame, "quit", lambda: closed.append("pygame"))

    asyncio.run(application.run(_UiApp()))
    assert application.failed
    assert "enable failed" in capsys.readouterr().err
    assert closed == ["pygame", "dds"]


def test_patient_monitor_handles_vitals_task_failure_locally(capsys):
    module = importlib.import_module("PatientMonitor")
    application = module.PatientMonitorApp.__new__(module.PatientMonitorApp)
    closed = []
    application.participant = SimpleNamespace(
        enable=lambda: None,
        close=lambda: closed.append(True),
        qos=_UNSECURED_QOS,
        current_time=object(),
    )
    application.status_writer = SimpleNamespace(write=lambda _: None)
    application.status_sample = module.Device.Status(
        device=module.Device.DeviceType.PATIENT_MONITOR,
        status=module.Device.DeviceStatusKind.ON,
    )
    application.receive_vitals_stream = _fail_task
    application.command_reader = SimpleNamespace(take_data_async=_fail_stream)
    application.heartbeat_writer = object()
    application.failed = False
    application.status = module.Device.DeviceStatusKind.ON
    application.last_sample_at = None
    application.view = lambda **_: {}
    application.ui = SimpleNamespace(update=lambda **_: None, log=lambda *args: None)

    asyncio.run(application.run(_UiApp()))
    assert application.failed
    assert "Patient Monitor vitals failed: worker failed" in capsys.readouterr().err
    assert closed == [True]


@pytest.mark.parametrize(
    ("module_name", "class_name"),
    [
        ("Arm", "ArmApp"),
        ("PatientMonitor", "PatientMonitorApp"),
        ("ArmControllerGamepad", "ArmControllerGamepadApp"),
    ],
)
def test_main_closes_participant_if_ui_fails_before_run(monkeypatch, module_name, class_name):
    module = importlib.import_module(module_name)
    closed = []
    participant = SimpleNamespace(closed=False, close=lambda: closed.append(True))
    application = SimpleNamespace(participant=participant, run=lambda _: None, failed=False)
    monkeypatch.setattr(module, "create_demo_ui", lambda _: object())
    monkeypatch.setattr(module, class_name, lambda *args: application)
    if module_name == "Arm":
        monkeypatch.setattr(module, "ArmModel", lambda: object())
        monkeypatch.setattr(module, "add_arm_scene", lambda *_: object())
    monkeypatch.setattr(module, "configure_ui", lambda *_: object())

    def fail_ui(*_args):
        raise SystemExit(1)

    monkeypatch.setattr(module, "run_demo_ui", fail_ui)
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 1
    assert closed == [True]
