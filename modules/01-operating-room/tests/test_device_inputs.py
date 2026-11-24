#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

import importlib
import math
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from module01_test_support import MODULE_DIR

from tools.medtech import module_runner

sys.path.insert(0, str(module_runner.platform_setup.generated_system_path() / "python"))


def test_module_keeps_simulators_as_defaults():
    manifest = module_runner.read_manifest(MODULE_DIR)

    defaults = module_runner.select_apps(manifest, {}, None, MODULE_DIR.name)
    assert defaults["Arm"] == ["${PYTHON:Arm}"]
    assert defaults["ArmController"] == ["${CPP:ArmController}"]


class FalconBridge:
    def __init__(self):
        self.closed = False
        self.has_data = True
        self.homed = True
        self.firmware_ok = True
        self.homing_modes = []
        self.position = SimpleNamespace(x=0.01, y=0.02, z=0.03)

    def getCount(self):
        return 1

    def open(self, index):
        assert index == 0
        return True

    def loadFirmware(self):
        return self.firmware_ok

    def setHomingMode(self, enabled):
        self.homing_modes.append(enabled)

    def runIOLoop(self, flags):
        assert flags == 0x1 | 0x2 | 0x4
        return self.has_data

    def isHomed(self):
        return self.homed

    def getPosition(self):
        return self.position

    def getButtons(self):
        return 1

    def close(self):
        self.closed = True


def test_falcon_confirms_homing_reads_input_and_detects_timeout(monkeypatch):
    import FalconInput as falcon

    now = [10.0]
    monkeypatch.setattr(falcon.time, "monotonic", lambda: now[0])
    bridge = FalconBridge()
    device = falcon.FalconInput(bridge)
    device.open()
    assert bridge.homing_modes == [True]
    assert device.read() is None
    now[0] += falcon.HOMING_CONFIRM_SECONDS + 0.01
    assert device.read() == ((0.01, 0.02, 0.03), 1)
    assert device.homing_state == "READY"

    bridge.has_data = False
    now[0] += falcon.INPUT_TIMEOUT_SECONDS + 0.01
    with pytest.raises(TimeoutError, match="timed out"):
        device.read()
    device.close()
    assert bridge.closed
    assert bridge.homing_modes == [True, False]


def test_falcon_homing_requires_operator_action_and_stable_status(monkeypatch):
    import FalconInput as falcon

    now = [10.0]
    monkeypatch.setattr(falcon.time, "monotonic", lambda: now[0])
    bridge = FalconBridge()
    bridge.homed = False
    device = falcon.FalconInput(bridge)
    device.open()
    assert device.read() is None
    now[0] += falcon.HOMING_CHECK_SECONDS + 0.01
    assert device.read() is None
    assert device.homing_state == "WAITING"
    bridge.homed = True
    assert device.read() is None
    assert device.start_homing()
    assert not device.start_homing()
    assert device.read() is None
    bridge.homed = False
    now[0] += 0.02
    assert device.read() is None
    bridge.homed = True
    now[0] += 0.02
    assert device.read() is None
    now[0] += falcon.HOMING_CONFIRM_SECONDS + 0.01
    assert device.read() == ((0.01, 0.02, 0.03), 1)
    assert not device.start_homing()
    bridge.homed = False
    with pytest.raises(RuntimeError, match="homing status was lost"):
        device.read()
    device.close()


def test_falcon_homing_timeout_can_be_retried(monkeypatch):
    import FalconInput as falcon

    now = [10.0]
    monkeypatch.setattr(falcon.time, "monotonic", lambda: now[0])
    bridge = FalconBridge()
    bridge.homed = False
    device = falcon.FalconInput(bridge)
    device.open()
    now[0] += falcon.HOMING_CHECK_SECONDS + 0.01
    assert device.read() is None
    assert device.start_homing()
    now[0] += falcon.HOMING_TIMEOUT_SECONDS + 0.01
    assert device.read() is None
    assert device.homing_state == "TIMED OUT"
    assert device.start_homing()
    device.close()


def test_falcon_firmware_failure_closes_device():
    import FalconInput as falcon

    bridge = FalconBridge()
    bridge.firmware_ok = False
    device = falcon.FalconInput(bridge)
    with pytest.raises(RuntimeError, match="initialize Falcon firmware"):
        device.open()
    assert bridge.closed
    assert not device.opened


@pytest.mark.parametrize("failure", ["enumeration", "open"])
def test_falcon_device_errors_are_not_treated_as_absence(failure):
    import FalconInput as falcon

    bridge = FalconBridge()
    if failure == "enumeration":
        bridge.getCount = lambda: -1
        message = "enumerate"
    else:
        bridge.open = lambda _: False
        message = "open Falcon"
    device = falcon.FalconInput(bridge)
    with pytest.raises(RuntimeError, match=message):
        device.open()
    assert not device.opened


def test_falcon_incompatible_bridge_fails_without_a_device():
    import FalconInput as falcon

    device = falcon.FalconInput(SimpleNamespace(getCount=lambda: 0))
    with pytest.raises(RuntimeError, match="Incompatible pynifalcon bridge"):
        device.open()


def test_falcon_closes_even_if_disabling_homing_fails():
    import FalconInput as falcon

    class Bridge(FalconBridge):
        def setHomingMode(self, enabled):
            if not enabled:
                raise RuntimeError("homing disable failed")
            super().setHomingMode(enabled)

    bridge = Bridge()
    device = falcon.FalconInput(bridge)
    device.open()
    with pytest.raises(RuntimeError, match="homing disable failed"):
        device.close()
    assert bridge.closed
    assert not device.opened


def test_falcon_rejects_invalid_input(monkeypatch):
    import FalconInput as falcon

    now = [10.0]
    monkeypatch.setattr(falcon.time, "monotonic", lambda: now[0])
    bridge = FalconBridge()
    device = falcon.FalconInput(bridge)
    device.open()
    assert device.read() is None
    now[0] += falcon.HOMING_CONFIRM_SECONDS + 0.01
    bridge.position = SimpleNamespace(x=float("nan"), y=0.0, z=0.0)
    with pytest.raises(ValueError, match="invalid input"):
        device.read()
    device.close()


def test_kinova_feedback_converts_xyz_extrinsic_degrees_and_rejects_nonfinite():
    from KortexDevice import pose_from_feedback

    feedback = SimpleNamespace(
        tool_pose_x=0.1,
        tool_pose_y=0.2,
        tool_pose_z=0.3,
        tool_pose_theta_x=90.0,
        tool_pose_theta_y=90.0,
        tool_pose_theta_z=0.0,
    )
    position, quaternion = pose_from_feedback(feedback)
    assert position == (0.1, 0.2, 0.3)
    assert quaternion == pytest.approx((0.5, 0.5, -0.5, 0.5))
    feedback.tool_pose_y = math.nan
    with pytest.raises(ValueError, match="non-finite"):
        pose_from_feedback(feedback)


@pytest.mark.parametrize(
    "module_name, class_name", [("Arm", "ArmApp"), ("ArmKortex", "ArmKortexApp")]
)
@pytest.mark.parametrize("stream", ["linear", "angular"])
@pytest.mark.parametrize("magnitude", [1.0, 1.7e308])
def test_arm_command_clamps_finite_vectors(module_name, class_name, stream, magnitude):
    import ArmKinematics as kinematics
    from MedTech import Device
    from PhysicalMotionGate import MotionConditions, PhysicalMotionGate

    cls = getattr(importlib.import_module(module_name), class_name)
    app = cls.__new__(cls)
    app.teleop_reader = object()
    app.tool_reader = object()
    arm = SimpleNamespace(
        linear_velocity=SimpleNamespace(x=0.0, y=0.0, z=0.0),
        angular_velocity=SimpleNamespace(x=0.0, y=0.0, z=0.0),
    )
    app._command = lambda reader: (
        arm if reader is app.teleop_reader else SimpleNamespace(opening_rate=0.0)
    )
    diagnostics = []
    app._diagnostic = diagnostics.append
    app.status = Device.DeviceStatusKind.ON
    app._health_observed_at = time.monotonic()
    app._motion_cancelled = threading.Event()
    app.motion_gate = PhysicalMotionGate()
    app.motion_gate.update(MotionConditions(True, True, True, True))
    assert app.motion_gate.rearm()

    if stream == "linear":
        target, limit = arm.linear_velocity, kinematics.MAX_LINEAR_SPEED
    else:
        target, limit = arm.angular_velocity, kinematics.MAX_ANGULAR_SPEED

    target.x = limit / 2
    linear, angular, _, valid = app.rates()
    assert valid
    assert (linear if stream == "linear" else angular) == (limit / 2, 0.0, 0.0)
    assert not diagnostics

    target.x, target.y = magnitude, -magnitude
    linear, angular, _, valid = app.rates()
    result = linear if stream == "linear" else angular
    assert valid
    assert app.commands_fresh
    assert not app.command_rates_neutral
    assert result == pytest.approx((limit / math.sqrt(2), -limit / math.sqrt(2), 0.0))
    assert diagnostics
    app.update_motion_gate(connected=True, healthy=True)
    assert app.motion_gate.armed


@pytest.mark.parametrize(
    "module_name, class_name", [("Arm", "ArmApp"), ("ArmKortex", "ArmKortexApp")]
)
@pytest.mark.parametrize("invalid_rate", [float("nan"), float("inf")])
def test_arm_command_rejects_nonfinite_vectors(module_name, class_name, invalid_rate):
    cls = getattr(importlib.import_module(module_name), class_name)
    app = cls.__new__(cls)
    app.teleop_reader = object()
    app.tool_reader = object()
    arm = SimpleNamespace(
        linear_velocity=SimpleNamespace(x=invalid_rate, y=0.0, z=0.0),
        angular_velocity=SimpleNamespace(x=0.0, y=0.0, z=0.0),
    )
    app._command = lambda reader: (
        arm if reader is app.teleop_reader else SimpleNamespace(opening_rate=0.0)
    )
    diagnostics = []
    app._diagnostic = diagnostics.append

    assert app.rates() == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0, False)
    assert not app.commands_fresh
    assert diagnostics


@pytest.mark.parametrize("invalid_rate", [float("nan"), float("inf")])
def test_invalid_arm_rate_disarms_motion_gate(invalid_rate):
    from Arm import ArmApp
    from MedTech import Device
    from PhysicalMotionGate import MotionConditions, PhysicalMotionGate

    app = ArmApp.__new__(ArmApp)
    app.teleop_reader = SimpleNamespace(
        subscription_matched_status=SimpleNamespace(current_count=1)
    )
    app.tool_reader = SimpleNamespace(subscription_matched_status=SimpleNamespace(current_count=1))
    arm = SimpleNamespace(
        linear_velocity=SimpleNamespace(x=invalid_rate, y=0.0, z=0.0),
        angular_velocity=SimpleNamespace(x=0.0, y=0.0, z=0.0),
    )
    tool = SimpleNamespace(opening_rate=0.0)
    app._command = lambda reader: arm if reader is app.teleop_reader else tool
    diagnostics = []
    app._diagnostic = diagnostics.append
    app.status = Device.DeviceStatusKind.ON
    app.motion_gate = PhysicalMotionGate()
    app.motion_gate.update(MotionConditions(True, True, True, True))
    assert app.motion_gate.rearm()

    assert app.rates() == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0, False)
    app.update_motion_gate(connected=True, healthy=True)
    assert not app.motion_gate.armed
    assert not app.motion_gate.can_rearm
    assert diagnostics

    arm.linear_velocity.x = 0.01
    app.rates()
    app.update_motion_gate(connected=True, healthy=True)
    assert not app.motion_gate.armed
    assert not app.motion_gate.can_rearm

    arm.linear_velocity.x = 0.0
    app.rates()
    app.update_motion_gate(connected=True, healthy=True)
    assert not app.motion_gate.armed
    assert app.motion_gate.can_rearm


@pytest.mark.parametrize("writer_count", [0, 2])
def test_simulated_motion_gate_does_not_depend_on_writer_count(writer_count):
    from Arm import ArmApp
    from MedTech import Device
    from PhysicalMotionGate import PhysicalMotionGate

    app = ArmApp.__new__(ArmApp)
    app.teleop_reader = SimpleNamespace(
        subscription_matched_status=SimpleNamespace(current_count=writer_count)
    )
    app.tool_reader = SimpleNamespace(
        subscription_matched_status=SimpleNamespace(current_count=writer_count)
    )
    app.status = Device.DeviceStatusKind.ON
    app.motion_gate = PhysicalMotionGate()
    app.commands_fresh = True
    app.command_rates_neutral = True
    app.update_motion_gate(connected=True, healthy=True)
    assert app.motion_gate.rearm()
    app.command_rates_neutral = False
    app.update_motion_gate(connected=True, healthy=True)
    assert app.motion_gate.armed


def test_pause_and_immediate_start_require_rearm():
    from Arm import ArmApp
    from MedTech import Device
    from PhysicalMotionGate import MotionConditions, PhysicalMotionGate

    app = ArmApp.__new__(ArmApp)
    app.teleop_reader = SimpleNamespace(take=lambda: None)
    app.tool_reader = SimpleNamespace(take=lambda: None)
    app.motion_gate = PhysicalMotionGate()
    app.motion_gate.update(MotionConditions(True, True, True, True))
    assert app.motion_gate.rearm()

    app.apply_command(Device.DeviceCommandKind.PAUSE)
    assert not app.motion_gate.armed
    app.apply_command(Device.DeviceCommandKind.START)
    assert not app.motion_gate.armed
    assert not app.motion_gate.can_rearm


@pytest.mark.parametrize(
    "module_name, class_name", [("Arm", "ArmApp"), ("ArmKortex", "ArmKortexApp")]
)
@pytest.mark.parametrize("command, expected_drains", [("START", 0), ("PAUSE", 2), ("SHUTDOWN", 2)])
def test_lifecycle_commands_drain_teleop_on_pause_and_shutdown(
    module_name, class_name, command, expected_drains
):
    import importlib

    from MedTech import Device
    from PhysicalMotionGate import PhysicalMotionGate

    cls = getattr(importlib.import_module(module_name), class_name)
    app = cls.__new__(cls)
    app._motion_cancelled = threading.Event()
    app.status = Device.DeviceStatusKind.ON
    app.readiness = Device.DeviceReadinessKind.NOT_READY
    app.motion_gate = PhysicalMotionGate()
    drained = []
    app.teleop_reader = SimpleNamespace(take=lambda: drained.append("arm"))
    app.tool_reader = SimpleNamespace(take=lambda: drained.append("tool"))

    app.apply_command(getattr(Device.DeviceCommandKind, command))

    expected = [] if not expected_drains else ["arm", "tool"] if module_name == "Arm" else ["arm"]
    assert drained == expected
