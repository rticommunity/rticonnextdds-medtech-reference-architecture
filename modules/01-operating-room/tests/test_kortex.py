#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

import asyncio
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from module01_test_support import MODULE_DIR

from tools.medtech import module_runner

sys.path.insert(0, str(module_runner.platform_setup.generated_system_path() / "python"))
sys.path.insert(0, str(MODULE_DIR / "src"))
sys.path.insert(0, str(MODULE_DIR.parents[1] / "resources" / "ui" / "support"))

import ArmKortex as motion  # noqa: E402
import KortexDevice as kinova  # noqa: E402
from MedTech import Device  # noqa: E402
from PhysicalMotionGate import PhysicalMotionGate  # noqa: E402


def _fake_api(events, *, fault_banks=None, fail_udp_connect=False, limits=None, limit_error=None):
    fault_banks = {"a": 0, "b": 0} if fault_banks is None else fault_banks

    class Transport:
        def __init__(self, label):
            self.label = label

        def connect(self, ip, port):
            events.append(f"{self.label}.connect:{port}")
            if self.label == "udp" and fail_udp_connect:
                raise OSError("udp connect failed")

        def disconnect(self):
            events.append(f"{self.label}.disconnect")

    class Router:
        basicErrorCallback = object()

        def __init__(self, transport, _callback=None):
            self.transport = transport

    class Options:
        timeout_ms = 10000

    class SessionManager:
        def __init__(self, router):
            self.router = router

        def CreateSession(self, _info):
            events.append(f"{self.router.transport.label}.session.open")

        def CloseSession(self):
            events.append(f"{self.router.transport.label}.session.close")

    class Base:
        SINGLE_LEVEL_SERVOING = 2

        @staticmethod
        def Twist(**kwargs):
            return SimpleNamespace(**kwargs)

        @staticmethod
        def TwistCommand(**kwargs):
            return SimpleNamespace(**kwargs)

    class Common:
        ARMSTATE_IN_FAULT = 4
        ARMSTATE_SERVOING_READY = 7
        CARTESIAN_REFERENCE_FRAME_BASE = 3

    class Session:
        @staticmethod
        def CreateSessionInfo():
            return SimpleNamespace()

    class BaseClient:
        def __init__(self, _router):
            self.commands = []

        def GetArmState(self, *, options):
            assert options.timeout_ms == kinova.RPC_TIMEOUT_MS
            return SimpleNamespace(active_state=Common.ARMSTATE_SERVOING_READY)

        def GetServoingMode(self, *, options):
            assert options.timeout_ms == kinova.RPC_TIMEOUT_MS
            return SimpleNamespace(servoing_mode=Base.SINGLE_LEVEL_SERVOING)

        def SendTwistCommand(self, command, *, options):
            self.commands.append((command, options.timeout_ms))

        def Stop(self, *, options):
            self.stop_calls = getattr(self, "stop_calls", 0) + 1
            assert options.timeout_ms == kinova.RPC_TIMEOUT_MS

    class BaseCyclicClient:
        def __init__(self, _router):
            pass

        def RefreshFeedback(self, *, options):
            assert options.timeout_ms == kinova.RPC_TIMEOUT_MS
            return SimpleNamespace(
                base=SimpleNamespace(
                    fault_bank_a=fault_banks["a"],
                    fault_bank_b=fault_banks["b"],
                )
            )

    class ControlConfigClient:
        def __init__(self, router):
            assert router.transport.label == "tcp"

        def GetKinematicHardLimits(self, *, options):
            assert options.timeout_ms == kinova.RPC_TIMEOUT_MS
            events.append("hard_limits.read")
            if limit_error is not None:
                raise limit_error
            return limits or SimpleNamespace(twist_linear=0.1, twist_angular=10.0)

    return SimpleNamespace(
        RouterClient=Router,
        RouterClientSendOptions=Options,
        SessionManager=SessionManager,
        TCPTransport=lambda: Transport("tcp"),
        UDPTransport=lambda: Transport("udp"),
        BaseClient=BaseClient,
        BaseCyclicClient=BaseCyclicClient,
        ControlConfigClient=ControlConfigClient,
        Base=Base,
        Common=Common,
        Session=Session,
    )


def test_driver_uses_local_kortex_api_and_closes_sessions(monkeypatch):
    events = []
    api = _fake_api(events)
    monkeypatch.setattr(kinova, "_load_kortex_api", lambda: api)
    monkeypatch.setattr(motion, "_load_control_config_client", lambda: api.ControlConfigClient)
    monkeypatch.setenv("KORTEX_IP", "192.0.2.10")
    monkeypatch.setenv("KORTEX_USERNAME", "operator")
    monkeypatch.setenv("KORTEX_PASSWORD", "test-only")
    monkeypatch.setenv(motion.LIVE_WATCHDOG_ACK_ENV, motion.LIVE_WATCHDOG_ACK_VALUE)

    driver = motion.KortexDriver()
    driver.open()
    assert driver.connected
    assert "hard_limits.read" in events
    assert driver.read_health().ready
    driver._base.GetArmState = lambda **_kwargs: SimpleNamespace(
        active_state=api.Common.ARMSTATE_IN_FAULT
    )
    fault = driver.read_health()
    assert fault.faulted and not fault.ready
    driver._base.GetArmState = lambda **_kwargs: SimpleNamespace(
        active_state=api.Common.ARMSTATE_SERVOING_READY
    )
    driver._base.GetServoingMode = lambda **_kwargs: SimpleNamespace(servoing_mode=0)
    assert not driver.read_health().ready
    driver._base.GetServoingMode = lambda **_kwargs: SimpleNamespace(
        servoing_mode=api.Base.SINGLE_LEVEL_SERVOING
    )
    driver.stop()
    driver.send_twist((0.01, 0.0, 0.0), (0.0, math.radians(1), 0.0))
    command, timeout = driver._base.commands[-1]
    assert command.reference_frame == api.Common.CARTESIAN_REFERENCE_FRAME_BASE
    assert command.twist.linear_x == pytest.approx(0.01)
    assert command.twist.angular_y == pytest.approx(1.0)
    assert timeout == kinova.RPC_TIMEOUT_MS
    assert driver._base.stop_calls == 1
    driver.send_twist((0.02, 0.0, 0.0), (0.0, math.radians(10), 0.0))
    command, _ = driver._base.commands[-1]
    assert command.twist.linear_x == pytest.approx(0.02)
    assert command.twist.angular_y == pytest.approx(10.0)
    driver.send_twist((0.05, -0.05, 0), (0.5, -0.5, 0))
    command, _ = driver._base.commands[-1]
    assert (command.twist.linear_x, command.twist.linear_y) == pytest.approx(
        (0.05 / math.sqrt(2), -0.05 / math.sqrt(2))
    )
    assert (command.twist.angular_x, command.twist.angular_y) == pytest.approx(
        (10 / math.sqrt(2), -10 / math.sqrt(2))
    )
    with pytest.raises(ValueError, match="non-finite"):
        driver.send_twist((float("nan"), 0, 0), (0, 0, 0))

    driver.close()
    assert not driver.connected
    assert events[-4:] == [
        "udp.session.close",
        "udp.disconnect",
        "tcp.session.close",
        "tcp.disconnect",
    ]


def test_driver_cleans_tcp_session_when_udp_setup_fails(monkeypatch):
    events = []
    monkeypatch.setattr(
        kinova, "_load_kortex_api", lambda: _fake_api(events, fail_udp_connect=True)
    )
    monkeypatch.setenv("KORTEX_IP", "192.0.2.10")
    monkeypatch.setenv("KORTEX_USERNAME", "operator")
    monkeypatch.setenv("KORTEX_PASSWORD", "test-only")
    monkeypatch.setenv(motion.LIVE_WATCHDOG_ACK_ENV, motion.LIVE_WATCHDOG_ACK_VALUE)

    driver = motion.KortexDriver()
    with pytest.raises(OSError, match="udp connect failed"):
        driver.open()
    assert events[-2:] == ["tcp.session.close", "tcp.disconnect"]
    assert not driver.connected


def test_fault_bank_disarms_gate_even_when_arm_state_is_ready(monkeypatch):
    events = []
    fault_banks = {"a": 0, "b": 0}
    api = _fake_api(events, fault_banks=fault_banks)
    monkeypatch.setattr(kinova, "_load_kortex_api", lambda: api)
    monkeypatch.setattr(motion, "_load_control_config_client", lambda: api.ControlConfigClient)
    monkeypatch.setenv("KORTEX_IP", "192.0.2.10")
    monkeypatch.setenv("KORTEX_USERNAME", "operator")
    monkeypatch.setenv("KORTEX_PASSWORD", "test-only")
    monkeypatch.setenv(motion.LIVE_WATCHDOG_ACK_ENV, motion.LIVE_WATCHDOG_ACK_VALUE)

    driver = motion.KortexDriver()
    driver.open()
    app = _make_app()
    assert app.request_motion_rearm({}) == {"armed": True}
    fault_banks["b"] = 0x20
    health = driver.read_health()
    assert health.arm_state == api.Common.ARMSTATE_SERVOING_READY
    assert health.faulted and not health.ready

    app.apply_health(health)

    assert app.status == Device.DeviceStatusKind.ERROR
    assert app.readiness == Device.DeviceReadinessKind.FAULTED
    assert not app.motion_gate.armed
    driver.close()


@pytest.mark.parametrize(
    ("linear", "angular", "expected_linear", "expected_angular"),
    [
        (0.1, 60.0, 0.05, math.degrees(0.5)),
        (0.02, 10.0, 0.02, 10.0),
        (0.02, 60.0, 0.02, math.degrees(0.5)),
        (0.005, 4.0, 0.005, 4.0),
    ],
)
def test_motion_driver_caps_commands_to_demo_and_device_limits(
    monkeypatch, linear, angular, expected_linear, expected_angular
):
    events = []
    api = _fake_api(events, limits=SimpleNamespace(twist_linear=linear, twist_angular=angular))
    monkeypatch.setattr(kinova, "_load_kortex_api", lambda: api)
    monkeypatch.setattr(motion, "_load_control_config_client", lambda: api.ControlConfigClient)
    monkeypatch.setenv("KORTEX_IP", "192.0.2.10")
    monkeypatch.setenv("KORTEX_USERNAME", "operator")
    monkeypatch.setenv("KORTEX_PASSWORD", "test-only")
    monkeypatch.setenv(motion.LIVE_WATCHDOG_ACK_ENV, motion.LIVE_WATCHDOG_ACK_VALUE)
    driver = motion.KortexDriver()
    driver.open()
    driver.send_twist(
        (0.03, 0.04, 0.0),
        (0.3, 0.4, 0.0),
    )
    command, _ = driver._base.commands[-1]
    assert math.hypot(command.twist.linear_x, command.twist.linear_y) == pytest.approx(
        expected_linear
    )
    assert math.hypot(command.twist.angular_x, command.twist.angular_y) == pytest.approx(
        expected_angular
    )
    assert command.twist.linear_x / command.twist.linear_y == pytest.approx(0.75)
    assert command.twist.angular_x / command.twist.angular_y == pytest.approx(0.75)
    driver.close()
    with pytest.raises(RuntimeError, match="not connected"):
        driver.send_twist((0.01, 0, 0), (0, 0, 0))
    assert events[-4:] == [
        "udp.session.close",
        "udp.disconnect",
        "tcp.session.close",
        "tcp.disconnect",
    ]


@pytest.mark.parametrize("failure", ["rpc", "demo-limit", "zero", "nan", "infinity"])
def test_motion_driver_cleans_up_on_limit_rpc_or_invalid_limit(monkeypatch, failure):
    events = []
    limit_error = OSError("hard limit RPC failed") if failure == "rpc" else None
    limits = SimpleNamespace(
        twist_linear={"zero": 0.0, "infinity": float("inf")}.get(failure, 0.1),
        twist_angular=float("nan") if failure == "nan" else 60.0,
    )
    api = _fake_api(events, limits=limits, limit_error=limit_error)
    monkeypatch.setattr(kinova, "_load_kortex_api", lambda: api)
    monkeypatch.setattr(motion, "_load_control_config_client", lambda: api.ControlConfigClient)
    monkeypatch.setenv("KORTEX_IP", "192.0.2.10")
    monkeypatch.setenv("KORTEX_USERNAME", "operator")
    monkeypatch.setenv("KORTEX_PASSWORD", "test-only")
    monkeypatch.setenv(motion.LIVE_WATCHDOG_ACK_ENV, motion.LIVE_WATCHDOG_ACK_VALUE)
    if failure == "demo-limit":
        monkeypatch.setattr(motion, "MAX_LINEAR_SPEED", float("nan"))
    driver = motion.KortexDriver()
    with pytest.raises((OSError, ValueError), match="hard limit RPC failed|limit"):
        driver.open()
    assert not driver.connected
    assert events[-4:] == [
        "udp.session.close",
        "udp.disconnect",
        "tcp.session.close",
        "tcp.disconnect",
    ]


def test_watchdog_acknowledgement_is_required_before_driver_open(monkeypatch):
    monkeypatch.delenv(motion.LIVE_WATCHDOG_ACK_ENV, raising=False)
    monkeypatch.setattr(
        kinova,
        "_load_kortex_api",
        lambda: pytest.fail("Kortex SDK must not load before acknowledgement"),
    )
    driver = motion.KortexDriver()
    with pytest.raises(RuntimeError, match=motion.LIVE_WATCHDOG_ACK_ENV):
        driver.open()


def test_invalid_watchdog_acknowledgement_is_a_startup_error(monkeypatch):
    monkeypatch.setenv(motion.LIVE_WATCHDOG_ACK_ENV, "invalid")
    monkeypatch.setattr(
        motion,
        "register_type",
        lambda *_args: pytest.fail("DDS types must not be registered before acknowledgement"),
    )
    with pytest.raises(RuntimeError, match=motion.LIVE_WATCHDOG_ACK_ENV):
        motion.ArmKortexApp(None)


class _FakeDriver:
    def __init__(self):
        self.twists = []
        self.stops = 0
        self.fail_nonzero_once = False
        self.fail_stop = False

    def stop(self):
        self.stops += 1
        if self.fail_stop:
            raise OSError("Base.Stop RPC failed")

    def read_health(self):
        return motion.KortexHealth(7, 2, 0, 0, True, False)

    def send_twist(self, linear, angular):
        if self.fail_nonzero_once and any((*linear, *angular)):
            self.fail_nonzero_once = False
            raise OSError("RPC connection lost")
        self.twists.append((tuple(linear), tuple(angular)))


def _make_app():
    app = motion.ArmKortexApp.__new__(motion.ArmKortexApp)
    app.preview = False
    app.title = motion.TITLE
    app.backend_label = motion.BACKEND_LABEL
    app.status = Device.DeviceStatusKind.ON
    app.readiness = Device.DeviceReadinessKind.NOT_READY
    app.controller_connected = False
    app.failed = False
    app.motion_gate = PhysicalMotionGate()
    app._motion_cancelled = threading.Event()
    app.arm_connected = True
    app.arm_healthy = True
    app._health_observed_at = time.monotonic()
    app._arm_faulted = False
    app._stop_required = False
    app._twist_active = False
    app._last_health = None
    app._last_published_readiness = None
    app._last_diagnostic_at = {}
    app._control_wake = asyncio.Event()
    app.telemetry_sequence = 0
    app.observed_pose = None
    app.driver = _FakeDriver()
    app.status_sample = Device.Status(device=Device.DeviceType.ARM, status=app.status)
    app.status_writer = SimpleNamespace(write=lambda _sample: None)
    app.teleop_reader = SimpleNamespace(
        subscription_matched_status=SimpleNamespace(current_count=1), take=lambda: None
    )
    app.ui = SimpleNamespace(
        log=lambda *_args, **_kwargs: None,
        update=lambda **_kwargs: None,
    )
    state = {
        "fresh": True,
        "neutral": True,
        "linear": (0.0, 0.0, 0.0),
        "opening_rate": 0.0,
    }

    def rates():
        app.commands_fresh = state["fresh"]
        app.command_rates_neutral = state["neutral"]
        return (
            state["linear"],
            (0.0, 0.0, 0.0),
            state["opening_rate"],
            state["fresh"],
        )

    async def rpc(function, *args):
        return function(*args)

    app.rates = rates
    app._rpc = rpc
    app._test_state = state
    return app


def test_neutral_rearm_reports_ready_without_nonzero_motion():
    app = _make_app()

    assert app.request_motion_rearm({}) == {"armed": True}
    asyncio.run(app.control_step())

    assert app.readiness == Device.DeviceReadinessKind.READY
    assert app.driver.twists == [((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))]


@pytest.mark.parametrize("writer_count", [0, 2])
def test_motion_gate_does_not_depend_on_writer_count(writer_count):
    app = _make_app()
    app.teleop_reader.subscription_matched_status.current_count = writer_count

    assert app.request_motion_rearm({}) == {"armed": True}
    app._test_state.update(linear=(0.01, 0.0, 0.0), neutral=False)
    asyncio.run(app.control_step())
    assert app.motion_gate.armed
    assert app.driver.twists[-1][0] == (0.01, 0.0, 0.0)


def test_stale_health_prevents_rearm_until_new_health_arrives(monkeypatch):
    app = _make_app()
    now = app._health_observed_at + motion.HEALTH_MAX_AGE_SECONDS + 0.01
    monkeypatch.setattr(motion.time, "monotonic", lambda: now)
    assert app.request_motion_rearm({}) == {"armed": False}
    app.apply_health(motion.KortexHealth(7, 2, 0, 0, True, False))
    assert app.request_motion_rearm({}) == {"armed": True}


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("health-age", "health observation 0.260 s old"),
        ("command", "arm command unavailable or invalid"),
        ("unhealthy", "arm health not ready (ARMSTATE=0, servoing mode=2)"),
    ],
)
def test_armed_gate_reports_disarm_reason(monkeypatch, failure, message):
    app = _make_app()
    messages = []
    app.ui.log = lambda text, level: messages.append((text, level))
    assert app.request_motion_rearm({}) == {"armed": True}
    messages.clear()
    if failure == "unhealthy":
        app.apply_health(motion.KortexHealth(0, 2, 0, 0, False, False))
    else:
        if failure == "health-age":
            monkeypatch.setattr(motion.time, "monotonic", lambda: app._health_observed_at + 0.26)
        else:
            app.commands_fresh = False
        app.update_motion_gate(connected=True, healthy=True)
        app.update_motion_gate(connected=True, healthy=True)
    assert not app.motion_gate.armed
    assert len(messages) == 1
    assert message in messages[0][0]
    assert messages[0][1] == "warn"


@pytest.mark.parametrize("command", ["START", "PAUSE", "SHUTDOWN"])
def test_armed_gate_reports_lifecycle_disarm(command):
    app = _make_app()
    messages = []
    app.ui.log = lambda text, level: messages.append((text, level))
    assert app.request_motion_rearm({}) == {"armed": True}
    app.apply_command(getattr(Device.DeviceCommandKind, command))
    assert (f"Software motion gate disarmed: received {command} command", "warn") in messages


def test_deadline_disarm_is_reported_even_after_recent_deadline_warning():
    app = _make_app()
    messages = []
    app.ui.log = lambda text, level: messages.append((text, level))

    async def exercise():
        app._control_deadline_missed("Arm", app.teleop_reader)
        assert app.request_motion_rearm({}) == {"armed": True}
        app._control_deadline_missed("Arm", app.teleop_reader)

    asyncio.run(exercise())
    warning = ("Arm command deadline missed; cached commands discarded", "warn")
    assert messages.count(warning) == 2
    assert not app.motion_gate.armed


def test_health_expiring_during_twist_disarms_and_attempts_stop(monkeypatch):
    app = _make_app()
    now = [app._health_observed_at]
    monkeypatch.setattr(motion.time, "monotonic", lambda: now[0])
    assert app.request_motion_rearm({}) == {"armed": True}
    app._test_state.update(linear=(0.01, 0.0, 0.0), neutral=False)

    async def delayed_rpc(function, *args):
        result = function(*args)
        if function == app._send_twist and any((*args[0], *args[1])):
            now[0] += motion.HEALTH_MAX_AGE_SECONDS + 0.01
        return result

    app._rpc = delayed_rpc
    asyncio.run(app.control_step())
    assert not app.motion_gate.armed
    assert app.driver.stops == 1
    assert app.driver.twists[-1] == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def test_deadline_miss_during_twist_disarms_and_attempts_stop():
    app = _make_app()
    assert app.request_motion_rearm({}) == {"armed": True}
    app._test_state.update(linear=(0.01, 0.0, 0.0), neutral=False)

    async def delayed_rpc(function, *args):
        result = function(*args)
        if function == app._send_twist and any((*args[0], *args[1])):
            app._control_deadline_missed("Arm", app.teleop_reader)
        return result

    app._rpc = delayed_rpc
    asyncio.run(app.control_step())
    assert not app.motion_gate.armed
    assert app._control_wake.is_set()
    assert app.driver.stops == 1
    assert app.driver.twists[-1] == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


@pytest.mark.parametrize(
    "invalidation", ["START", "PAUSE", "SHUTDOWN", "deadline", "unhealthy", "fault", "health-age"]
)
def test_queued_twist_is_not_sent_after_motion_permission_changes(monkeypatch, invalidation):
    app = _make_app()
    messages = []
    app.ui.log = lambda text, level: messages.append((text, level))
    now = [app._health_observed_at]
    monkeypatch.setattr(motion, "time", SimpleNamespace(monotonic=lambda: now[0]))
    assert app.request_motion_rearm({}) == {"armed": True}
    app._test_state.update(linear=(0.01, 0.0, 0.0), neutral=False)
    occupied = threading.Event()
    release = threading.Event()
    app._rpc_executor = ThreadPoolExecutor(max_workers=1)

    def occupy_executor():
        occupied.set()
        if not release.wait(5):
            raise TimeoutError("Test did not release the occupied Kortex executor")

    blocker = app._rpc_executor.submit(occupy_executor)

    async def exercise():
        queued = asyncio.Event()

        async def rpc(function, *args):
            queued.set()
            return await motion.ArmKortexApp._rpc(app, function, *args)

        app._rpc = rpc
        assert await asyncio.to_thread(occupied.wait, 2)
        task = asyncio.create_task(app.control_step())
        try:
            await asyncio.wait_for(queued.wait(), 2)
            if invalidation in ("START", "PAUSE", "SHUTDOWN"):
                app.apply_command(getattr(Device.DeviceCommandKind, invalidation))
            elif invalidation == "deadline":
                app._control_deadline_missed("Arm", app.teleop_reader)
            elif invalidation == "unhealthy":
                app.apply_health(motion.KortexHealth(0, 2, 0, 0, False, False))
            elif invalidation == "fault":
                app.apply_health(motion.KortexHealth(4, 2, 1, 0, False, True))
            else:
                now[0] += motion.HEALTH_MAX_AGE_SECONDS + 0.01
            if invalidation in ("PAUSE", "deadline", "unhealthy"):
                app.apply_command(Device.DeviceCommandKind.START)
                app.apply_health(motion.KortexHealth(7, 2, 0, 0, True, False))
                app._test_state.update(linear=(0.0, 0.0, 0.0), neutral=True)
                assert app.request_motion_rearm({}) == {"armed": True}
                app._test_state.update(linear=(0.01, 0.0, 0.0), neutral=False)
            release.set()
            await asyncio.wait_for(task, 2)
        finally:
            release.set()
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

    try:
        asyncio.run(exercise())
        blocker.result()
    finally:
        release.set()
        app._rpc_executor.shutdown(wait=True, cancel_futures=True)

    assert app.driver.twists
    assert all(not any((*linear, *angular)) for linear, angular in app.driver.twists)
    assert not app.motion_gate.armed
    assert app.readiness != Device.DeviceReadinessKind.READY
    discarded = [text for text, _level in messages if "Queued arm command discarded" in text]
    assert len(discarded) == 1
    if invalidation == "health-age":
        assert "cancelled=False, health observation 0.260 s old" in discarded[0]
    else:
        assert "cancelled=True" in discarded[0]


def test_active_to_neutral_uses_base_stop_and_keeps_neutral_readiness():
    app = _make_app()
    app.request_motion_rearm({})
    app._test_state.update(linear=(0.01, 0.0, 0.0), neutral=False)
    asyncio.run(app.control_step())
    assert app._twist_active

    app._test_state.update(linear=(0.0, 0.0, 0.0), neutral=True)
    asyncio.run(app.control_step())

    assert app.driver.stops == 1
    assert app.driver.twists[-1] == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    assert app.readiness == Device.DeviceReadinessKind.READY
    assert app.motion_gate.armed


def test_stale_commands_disarm_and_send_zero_after_motion():
    app = _make_app()
    app.request_motion_rearm({})
    app._test_state.update(linear=(0.01, 0.0, 0.0), neutral=False)
    asyncio.run(app.control_step())
    assert app._twist_active

    app._test_state.update(fresh=False, linear=(0.0, 0.0, 0.0), neutral=False)
    asyncio.run(app.control_step())

    assert not app.motion_gate.armed
    assert app.driver.stops == 1
    assert app.driver.twists[-1] == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    assert not app._twist_active


def test_invalid_rates_are_not_sent_to_kinova():
    app = _make_app()
    app._twist_active = True
    app._test_state.update(fresh=False, linear=(0.0, 0.0, 0.0), neutral=False)

    asyncio.run(app.control_step())

    assert app.driver.twists == [((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))]
    assert not app.motion_gate.armed
    assert not app._twist_active


@pytest.mark.parametrize(
    ("status", "healthy"),
    [
        (Device.DeviceStatusKind.PAUSED, True),
        (Device.DeviceStatusKind.ON, False),
        (Device.DeviceStatusKind.ERROR, False),
    ],
)
def test_pause_or_unhealthy_arm_sends_best_effort_zero(status, healthy):
    app = _make_app()
    app._twist_active = True
    app.status = status
    app.arm_healthy = healthy

    asyncio.run(app.control_step())

    assert app.driver.stops == 1
    assert app.driver.twists == [((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))]
    assert not app._twist_active


def test_shutdown_lifecycle_sends_zero_before_reporting_off():
    app = _make_app()
    app._twist_active = True
    status_writes = []
    app.status_writer.write = lambda sample: status_writes.append(
        (sample.status, app.driver.stops, list(app.driver.twists))
    )

    shutdown = asyncio.run(app.handle_lifecycle_command(Device.DeviceCommandKind.SHUTDOWN))

    assert shutdown
    assert app.status == Device.DeviceStatusKind.OFF
    assert app.driver.stops == 1
    assert app.driver.twists == [((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))]
    assert status_writes == [(Device.DeviceStatusKind.OFF, 1, app.driver.twists)]


def test_shutdown_preserves_latched_fault_readiness():
    app = _make_app()
    app._publish_fault("Kinova fault")
    app.apply_health(motion.KortexHealth(7, 2, 0, 0, True, False))
    written = []
    app.status_writer.write = lambda sample: written.append((sample.status, sample.readiness))

    assert asyncio.run(app.handle_lifecycle_command(Device.DeviceCommandKind.SHUTDOWN))
    assert written[-1] == (Device.DeviceStatusKind.OFF, Device.DeviceReadinessKind.FAULTED)
    asyncio.run(app.control_step())
    assert app.readiness == Device.DeviceReadinessKind.FAULTED


def test_start_while_unhealthy_is_on_but_cannot_rearm():
    app = _make_app()
    app.status = Device.DeviceStatusKind.PAUSED
    app.arm_healthy = False

    asyncio.run(app.handle_lifecycle_command(Device.DeviceCommandKind.START))

    assert app.status == Device.DeviceStatusKind.ON
    assert app.readiness == Device.DeviceReadinessKind.NOT_READY
    assert app.request_motion_rearm({}) == {"armed": False}


def test_force_stop_attempts_stop_when_connected_unhealthy_without_active_flag():
    app = _make_app()
    app.arm_healthy = False
    app._twist_active = False

    asyncio.run(app._send_stop(force=True))

    assert app.driver.stops == 1
    assert app.driver.twists == [((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))]


def test_unhealthy_transition_attempts_stop_without_active_twist():
    app = _make_app()
    app.apply_health(motion.KortexHealth(0, 2, 0, 0, False, False))

    asyncio.run(app.control_step())
    asyncio.run(app.control_step())

    assert app.driver.stops == 1
    assert app.driver.twists == [((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))]


def test_fault_disarms_and_reports_fault_readiness():
    app = _make_app()
    app._twist_active = True
    app._arm_faulted = True
    app._publish_fault("Kinova reports ARMSTATE_IN_FAULT")

    asyncio.run(app.control_step())

    assert not app.motion_gate.armed
    assert app.status == Device.DeviceStatusKind.ERROR
    assert app.readiness == Device.DeviceReadinessKind.FAULTED
    assert app.driver.stops == 1
    assert app.driver.twists[-1] == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


@pytest.mark.parametrize(
    "command", [Device.DeviceCommandKind.START, Device.DeviceCommandKind.PAUSE]
)
def test_fault_remains_latched_on_lifecycle_commands(command):
    app = _make_app()
    app._publish_fault("Kinova fault")
    app.apply_health(motion.KortexHealth(7, 2, 0, 0, True, False))
    app.apply_command(command)

    assert app.status == Device.DeviceStatusKind.ERROR
    assert app.readiness == Device.DeviceReadinessKind.FAULTED
    assert not app.motion_gate.armed


def test_rpc_failure_reports_fault_attempts_zero_and_stops_ui():
    app = _make_app()
    app._twist_active = True
    calls = []
    readiness_writes = []
    messages = []
    app.ui.log = lambda message, level: messages.append((message, level))
    app.status_writer.write = lambda sample: readiness_writes.append(
        (sample.readiness.name, app.driver.stops, list(calls))
    )

    def record_stop(linear, angular):
        if any((*linear, *angular)):
            raise OSError("twist RPC failed")
        calls.append((tuple(linear), tuple(angular)))

    app.driver.send_twist = record_stop
    app._heartbeat_stop = asyncio.Event()
    app._workers = []
    stopped = []

    async def stop():
        stopped.append(True)

    asyncio.run(
        app._handle_failure(
            "Kinova control or observation failed: connection lost", SimpleNamespace(stop=stop)
        )
    )

    assert app.failed
    assert app.status == Device.DeviceStatusKind.ERROR
    assert app.readiness == Device.DeviceReadinessKind.FAULTED
    assert readiness_writes[-1] == (
        "FAULTED",
        1,
        [((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))],
    )
    assert app.driver.stops == 1
    assert calls[-1] == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    assert messages[-1] == ("Kinova control or observation failed: connection lost", "error")
    assert stopped


def test_startup_rpc_failure_preserves_fault_readiness_on_cleanup():
    app = _make_app()
    app.arm_connected = False
    app.participant = SimpleNamespace(
        enable=lambda: None,
        close=lambda: None,
        qos=SimpleNamespace(property=SimpleNamespace(exists=lambda _: False)),
    )
    app._rpc_executor = SimpleNamespace(shutdown=lambda **_: None)

    def fail_open():
        assert readiness_writes == ["NOT_READY"]
        assert app.status_sample.status == Device.DeviceStatusKind.ON
        assert not app.motion_gate.armed
        assert not app.arm_connected
        raise OSError("connection failed")

    app.driver.open = fail_open
    app.driver.close = lambda: None
    app.view = lambda: {}
    messages = []
    app.ui.log = lambda message, level: messages.append((message, level))
    readiness_writes = []
    app.status_writer.write = lambda sample: readiness_writes.append(sample.readiness.name)

    async def stop():
        pass

    asyncio.run(app.run(SimpleNamespace(stop=stop)))

    assert app.failed
    assert readiness_writes == ["NOT_READY", "FAULTED", "FAULTED"]
    assert messages[-1] == ("Kinova motion startup failed: connection failed", "error")


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("control", "Kinova control or observation failed: feedback unavailable"),
        ("lifecycle", "Kinova lifecycle command failed: command failed"),
    ],
)
def test_task_failure_reports_its_context_and_stops(monkeypatch, failure, expected):
    app = _make_app()
    app.arm_connected = False
    app.participant = SimpleNamespace(
        enable=lambda: None,
        close=lambda: None,
        qos=SimpleNamespace(property=SimpleNamespace(exists=lambda _: False)),
    )
    app._rpc_executor = SimpleNamespace(shutdown=lambda **_: None)
    app.heartbeat_writer = object()
    app.driver.open = lambda: None
    app.driver.close = lambda: None
    app.view = lambda: {}
    messages = []
    app.ui.log = lambda message, level: messages.append((message, level))

    async def commands():
        if failure == "lifecycle":
            yield SimpleNamespace(command=Device.DeviceCommandKind.START)
        await asyncio.Event().wait()

    async def handle_command(_command):
        raise OSError("command failed")

    async def rpc(function, *args):
        if function == app.driver.read_health:
            if failure == "control":
                raise OSError("feedback unavailable")
            await asyncio.Event().wait()
        return function(*args)

    async def idle(*_args):
        await asyncio.Event().wait()

    app.command_reader = SimpleNamespace(take_data_async=commands)
    app.handle_lifecycle_command = handle_command
    app._rpc = rpc
    app.monitor_control_health = idle
    monkeypatch.setattr(motion, "publish_heartbeats", idle)
    stopped = []

    async def stop():
        stopped.append(True)

    async def exercise():
        await asyncio.wait_for(app.run(SimpleNamespace(stop=stop)), 2)

    asyncio.run(exercise())

    assert app.failed
    assert (expected, "error") in messages
    assert app.status_sample.readiness == Device.DeviceReadinessKind.FAULTED
    assert stopped


def test_unacknowledged_motion_rpc_is_followed_by_zero_attempt():
    app = _make_app()
    app.request_motion_rearm({})
    app._test_state.update(linear=(0.01, 0.0, 0.0), neutral=False)
    app.driver.fail_nonzero_once = True
    app._heartbeat_stop = asyncio.Event()
    app._workers = []

    with pytest.raises(OSError, match="connection lost"):
        asyncio.run(app.control_step())
    assert app._twist_active

    async def stop():
        return None

    asyncio.run(
        app._handle_failure(
            "Kinova control or observation failed: connection lost", SimpleNamespace(stop=stop)
        )
    )

    assert app.driver.stops == 1
    assert app.driver.twists == [((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))]


def test_failed_base_stop_still_attempts_zero_and_reports_failure():
    app = _make_app()
    app._twist_active = True
    app.driver.fail_stop = True

    with pytest.raises(OSError, match="Base.Stop RPC failed"):
        asyncio.run(app._send_stop())

    assert app.driver.stops == 1
    assert app.driver.twists == [((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))]
    assert app._twist_active
