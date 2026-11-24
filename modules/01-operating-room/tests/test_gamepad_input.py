#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

from __future__ import annotations

import asyncio
import importlib
import math
import os
import sys
from types import SimpleNamespace

import pytest
from module01_test_support import SRC_DIR

sys.path.insert(0, str(SRC_DIR))

pygame = pytest.importorskip("pygame")
import ArmControllerGamepad as gamepad_module  # noqa: E402
from ArmControllerGamepad import (  # noqa: E402
    MAX_ANGULAR_SPEED,
    MAX_LINEAR_SPEED,
    MAX_OPENING_RATE,
    GamepadControl,
    bounded_teleop_rates,
    initialize_gamepad_input,
)
from ArmKinematics import ArmModel, _q_rotate  # noqa: E402
from pygame._sdl2 import controller as pygame_controller  # noqa: E402


def _rates_from_controls(*args, **kwargs):
    rates, _ = GamepadControl().update(*args, **kwargs)
    return rates


def _read_controller_state(gamepad, control):
    app = gamepad_module.ArmControllerGamepadApp.__new__(gamepad_module.ArmControllerGamepadApp)
    app.gamepad = gamepad
    app.control = control
    return app.read_controls()


def _zero_controls():
    return (
        {
            pygame.CONTROLLER_AXIS_LEFTX: 0,
            pygame.CONTROLLER_AXIS_LEFTY: 0,
            pygame.CONTROLLER_AXIS_RIGHTX: 0,
            pygame.CONTROLLER_AXIS_RIGHTY: 0,
            pygame.CONTROLLER_AXIS_TRIGGERLEFT: 0,
            pygame.CONTROLLER_AXIS_TRIGGERRIGHT: 0,
        },
        {
            pygame.CONTROLLER_BUTTON_DPAD_UP: False,
            pygame.CONTROLLER_BUTTON_DPAD_DOWN: False,
            pygame.CONTROLLER_BUTTON_DPAD_LEFT: False,
            pygame.CONTROLLER_BUTTON_DPAD_RIGHT: False,
            pygame.CONTROLLER_BUTTON_LEFTSHOULDER: False,
            pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: False,
            pygame.CONTROLLER_BUTTON_A: False,
            pygame.CONTROLLER_BUTTON_B: False,
        },
    )


def test_gamepad_readiness_tracks_input_and_lifecycle(monkeypatch):
    from MedTech import Device

    app = gamepad_module.ArmControllerGamepadApp.__new__(gamepad_module.ArmControllerGamepadApp)
    app.status_sample = Device.Status(device=Device.DeviceType.ARM_CONTROLLER)
    app.status = Device.DeviceStatusKind.ON
    app.failed = False
    app.gamepad = None
    app.active_inputs = {}
    app.ui = SimpleNamespace(log=lambda *args: None, update=lambda **kwargs: None)
    app.view = lambda: {}
    app.stop_motion = lambda: None
    written = []
    app.status_writer = SimpleNamespace(
        write=lambda sample: written.append((sample.status, sample.readiness))
    )
    joystick = SimpleNamespace(get_instance_id=lambda: 1, get_name=lambda: "test")
    gamepad = SimpleNamespace(as_joystick=lambda: joystick, quit=lambda: None)
    monkeypatch.setattr(pygame_controller, "is_controller", lambda _: True)
    monkeypatch.setattr(pygame_controller, "Controller", lambda _: gamepad)

    app.write_status(app.status)
    app.connect_controller(0)
    app.set_status(Device.DeviceStatusKind.PAUSED)
    app.set_status(Device.DeviceStatusKind.ON)
    app.disconnect_controller()
    assert written == [
        (Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.NOT_READY),
        (Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.READY),
        (Device.DeviceStatusKind.PAUSED, Device.DeviceReadinessKind.NOT_READY),
        (Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.READY),
        (Device.DeviceStatusKind.ON, Device.DeviceReadinessKind.NOT_READY),
    ]


def test_gamepad_input_initializes_sdl_with_background_events_enabled(monkeypatch):
    calls = []
    monkeypatch.setenv("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "0")

    def record_initialization(name):
        def initialize():
            calls.append((name, os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"]))

        return initialize

    monkeypatch.setattr(pygame, "init", record_initialization("pygame"))
    monkeypatch.setattr(pygame.joystick, "init", record_initialization("joystick"))
    monkeypatch.setattr(pygame_controller, "init", record_initialization("controller"))

    initialize_gamepad_input()

    assert calls == [("pygame", "1"), ("joystick", "1"), ("controller", "1")]


def test_gamepad_write_status_publishes_selected_status():
    app = gamepad_module.ArmControllerGamepadApp.__new__(gamepad_module.ArmControllerGamepadApp)
    app.status_sample = SimpleNamespace(status=gamepad_module.Device.DeviceStatusKind.ON)
    app.failed = False
    app.gamepad = None
    written = []
    app.status_writer = SimpleNamespace(write=written.append)

    app.write_status(gamepad_module.Device.DeviceStatusKind.PAUSED)

    assert len(written) == 1
    assert written[0].status == gamepad_module.Device.DeviceStatusKind.PAUSED


@pytest.mark.parametrize(
    ("module_name", "class_name"),
    [
        ("ArmControllerGamepad", "ArmControllerGamepadApp"),
        ("ArmControllerFalcon", "ArmControllerFalconApp"),
    ],
)
@pytest.mark.parametrize("command", ["PAUSE", "SHUTDOWN"])
def test_controller_lifecycle_publishes_neutral_before_stopping(module_name, class_name, command):
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    app = cls.__new__(cls)
    app.demo = module.ArmControllerDemo()
    app.status = gamepad_module.Device.DeviceStatusKind.ON
    app.rates = app.zero_rates()
    app.rates["linear_velocity"]["x"] = 0.02
    app.rates["opening_rate"] = 0.01
    if module_name == "ArmControllerFalcon":
        app.control = module.FalconRelativeControl((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0))
    events = []
    app.teleop_writer = SimpleNamespace(
        write=lambda sample: events.append(("arm", sample, app.status))
    )
    app.tool_writer = SimpleNamespace(
        write=lambda sample: events.append(("jaw", sample.opening_rate, app.status))
    )
    app.write_status = lambda status: events.append(("status", status))
    app.ui = SimpleNamespace(update=lambda **_: None, log=lambda *_: None)
    app.view = lambda: {}
    app.running = True

    async def stop():
        pass

    async def commands():
        yield SimpleNamespace(command=getattr(gamepad_module.Device.DeviceCommandKind, command))

    app.app = SimpleNamespace(stop=stop)
    app.command_reader = SimpleNamespace(take_data_async=commands)
    asyncio.run(app.receive_commands())

    assert events[0][0] == "arm"
    assert events[0][2] == gamepad_module.Device.DeviceStatusKind.ON
    assert all(
        getattr(vector, axis) == 0.0
        for vector in (events[0][1].linear_velocity, events[0][1].angular_velocity)
        for axis in "xyz"
    )
    assert events[1] == ("jaw", 0.0, gamepad_module.Device.DeviceStatusKind.ON)
    assert events[2][0] == "status"


def test_controller_maps_proportional_stick_magnitudes():
    axes, buttons = _zero_controls()
    axes.update(
        {
            pygame.CONTROLLER_AXIS_LEFTX: round(0.675 * 32767),
            pygame.CONTROLLER_AXIS_LEFTY: round(-0.675 * 32767),
            pygame.CONTROLLER_AXIS_TRIGGERLEFT: 0,
        }
    )

    class Controller:
        def get_axis(self, axis):
            return axes[axis]

        def get_button(self, button):
            return buttons[button]

    rates, active = _read_controller_state(Controller(), GamepadControl())
    linear = rates["linear_velocity"]
    assert linear["x"] == pytest.approx(MAX_LINEAR_SPEED * 0.5, abs=1e-6)
    assert linear["y"] == pytest.approx(MAX_LINEAR_SPEED * 0.5, abs=1e-6)
    assert linear["z"] == pytest.approx(0.0)
    assert rates["angular_velocity"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert active["LEFT STICK"]
    assert not active["LT / RT"]


@pytest.mark.parametrize(
    ("axis", "input_value", "rotating", "velocity", "component", "direction", "active_input"),
    (
        (pygame.CONTROLLER_AXIS_LEFTX, 0.675, False, "linear_velocity", "x", 1, "LEFT STICK"),
        (pygame.CONTROLLER_AXIS_LEFTX, -0.675, False, "linear_velocity", "x", -1, "LEFT STICK"),
        (pygame.CONTROLLER_AXIS_LEFTY, -0.675, False, "linear_velocity", "y", 1, "LEFT STICK"),
        (pygame.CONTROLLER_AXIS_LEFTY, 0.675, False, "linear_velocity", "y", -1, "LEFT STICK"),
        (pygame.CONTROLLER_AXIS_RIGHTY, -0.675, False, "linear_velocity", "z", 1, "RIGHT STICK"),
        (pygame.CONTROLLER_AXIS_RIGHTY, 0.675, False, "linear_velocity", "z", -1, "RIGHT STICK"),
        (pygame.CONTROLLER_AXIS_TRIGGERLEFT, 0.675, True, "angular_velocity", "z", -1, "LT / RT"),
        (pygame.CONTROLLER_AXIS_TRIGGERRIGHT, 0.675, True, "angular_velocity", "z", 1, "LT / RT"),
        (pygame.CONTROLLER_AXIS_RIGHTX, 0.675, True, "angular_velocity", "y", 1, "RIGHT STICK"),
        (pygame.CONTROLLER_AXIS_RIGHTX, -0.675, True, "angular_velocity", "y", -1, "RIGHT STICK"),
        (pygame.CONTROLLER_AXIS_RIGHTY, -0.675, True, "angular_velocity", "x", -1, "RIGHT STICK"),
        (pygame.CONTROLLER_AXIS_RIGHTY, 0.675, True, "angular_velocity", "x", 1, "RIGHT STICK"),
    ),
)
def test_base_frame_axis_directions_and_active_input(
    axis, input_value, rotating, velocity, component, direction, active_input
):
    axes, buttons = _zero_controls()
    axes[axis] = round(input_value * 32767)
    buttons[pygame.CONTROLLER_BUTTON_LEFTSHOULDER] = rotating

    class Controller:
        def get_axis(self, axis):
            return axes[axis]

        def get_button(self, button):
            return buttons[button]

    rates, active = _read_controller_state(Controller(), GamepadControl())
    limit = MAX_LINEAR_SPEED if velocity == "linear_velocity" else MAX_ANGULAR_SPEED
    for vector in ("linear_velocity", "angular_velocity"):
        for name, value in rates[vector].items():
            expected = direction * limit * 0.5 if (vector, name) == (velocity, component) else 0.0
            assert value == pytest.approx(expected, abs=limit / 32767)
    expected_active = {active_input} | ({"LB"} if rotating else set())
    assert {label for label, enabled in active.items() if enabled} == expected_active


@pytest.mark.parametrize(
    ("right_x", "right_y"),
    ((1, 0), (-1, 0), (0, -1), (0, 1)),
)
def test_right_stick_rotates_about_fixed_base_axes_without_translating_tcp(right_x, right_y):
    rates = _rates_from_controls(
        0.0,
        0.0,
        right_x,
        right_y,
        0.0,
        0.0,
        {"up": False, "down": False, "left": False, "right": False},
        {"left": True, "right": False},
        {"open": False, "close": False},
    )
    model = ArmModel(joints=(0.8, 0.4, -0.9, 0.2, 0.3, 0.1))
    before = model.pose
    state = model.step(
        tuple(rates["linear_velocity"].values()),
        tuple(rates["angular_velocity"].values()),
        rates["opening_rate"],
        0.1,
    )
    assert state["reachable"]
    assert state["pose"]["position"] == pytest.approx(before["position"], abs=2e-4)
    forward_in_base = _q_rotate(state["pose"]["orientation"], (0, 0, 1))
    delta = (right_y * math.sin(0.025), right_x * math.sin(0.025), 0, math.cos(0.025))
    expected = _q_rotate(delta, _q_rotate(before["orientation"], (0, 0, 1)))
    assert forward_in_base == pytest.approx(expected, abs=3e-3)


@pytest.mark.parametrize(("left_trigger", "right_trigger", "direction"), ((1, 0, -1), (0, 1, 1)))
def test_gamepad_maps_combined_rotation_translation_and_jaw(left_trigger, right_trigger, direction):
    rates = _rates_from_controls(
        left_x=1.0,
        left_y=-1.0,
        right_x=1.0,
        right_y=-1.0,
        left_trigger=left_trigger,
        right_trigger=right_trigger,
        dpad={"up": False, "down": False, "left": False, "right": False},
        bumpers={"left": True, "right": False},
        jaw_buttons={"open": True, "close": False},
    )

    linear = rates["linear_velocity"]
    angular = rates["angular_velocity"]
    assert max(abs(value) for value in linear.values()) < MAX_LINEAR_SPEED
    assert sum(value * value for value in linear.values()) ** 0.5 == pytest.approx(MAX_LINEAR_SPEED)
    assert max(abs(value) for value in angular.values()) < MAX_ANGULAR_SPEED
    assert sum(value * value for value in angular.values()) ** 0.5 == pytest.approx(
        MAX_ANGULAR_SPEED
    )
    assert linear["x"] > 0 and linear["y"] > 0 and linear["z"] == 0
    assert angular["x"] < 0 and angular["y"] > 0 and angular["z"] * direction > 0
    assert rates["opening_rate"] == pytest.approx(MAX_OPENING_RATE)


def test_dead_zone_opposing_inputs_and_dpad_fallback_cancel_cleanly():
    rates = _rates_from_controls(
        left_x=0.2,
        left_y=-0.2,
        right_x=0.0,
        right_y=0.0,
        left_trigger=1.0,
        right_trigger=1.0,
        dpad={"up": True, "down": True, "left": True, "right": True},
        bumpers={"left": True, "right": True},
        jaw_buttons={"open": True, "close": True},
    )
    assert rates == {
        "linear_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        "angular_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        "opening_rate": 0.0,
    }

    fallback = _rates_from_controls(
        left_x=0.0,
        left_y=0.0,
        right_x=0.0,
        right_y=0.0,
        left_trigger=0.0,
        right_trigger=0.0,
        dpad={"up": True, "down": False, "left": True, "right": False},
        bumpers={"left": False, "right": False},
        jaw_buttons={"open": False, "close": False},
    )
    assert fallback["linear_velocity"]["x"] == pytest.approx(-MAX_LINEAR_SPEED / 2**0.5)
    assert fallback["linear_velocity"]["y"] == pytest.approx(MAX_LINEAR_SPEED / 2**0.5)


def test_face_buttons_open_close_and_release_to_zero():
    def rates(open_pressed, close_pressed):
        return _rates_from_controls(
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            {"up": False, "down": False, "left": False, "right": False},
            {"left": False, "right": False},
            {"open": open_pressed, "close": close_pressed},
        )

    assert rates(True, False)["opening_rate"] == pytest.approx(MAX_OPENING_RATE)
    assert rates(False, True)["opening_rate"] == pytest.approx(-MAX_OPENING_RATE)
    assert rates(True, True)["opening_rate"] == 0.0
    assert rates(False, False)["opening_rate"] == 0.0


def test_published_rates_are_finite_and_limited():
    bounded = bounded_teleop_rates(
        {
            "linear_velocity": {"x": float("nan"), "y": 2.0, "z": 2.0},
            "angular_velocity": {
                "x": float("inf"),
                "y": -2.0,
                "z": 2.0,
            },
            "opening_rate": -float("inf"),
        }
    )
    linear = bounded["linear_velocity"]
    angular = bounded["angular_velocity"]
    assert all(value == value for value in (*linear.values(), *angular.values()))
    assert sum(value * value for value in linear.values()) ** 0.5 == pytest.approx(MAX_LINEAR_SPEED)
    assert sum(value * value for value in angular.values()) ** 0.5 == pytest.approx(
        MAX_ANGULAR_SPEED
    )
    assert bounded["opening_rate"] == 0.0


def test_gamepad_reads_both_sticks_triggers_and_all_buttons():
    axes, buttons = _zero_controls()
    buttons[pygame.CONTROLLER_BUTTON_DPAD_UP] = True
    buttons[pygame.CONTROLLER_BUTTON_DPAD_LEFT] = True
    buttons[pygame.CONTROLLER_BUTTON_LEFTSHOULDER] = True
    buttons[pygame.CONTROLLER_BUTTON_A] = True

    class Controller:
        def __init__(self):
            self.read_axes = []
            self.read_buttons = []

        def get_axis(self, axis):
            self.read_axes.append(axis)
            return axes[axis]

        def get_button(self, button):
            self.read_buttons.append(button)
            return buttons[button]

    gamepad = Controller()
    rates, active = _read_controller_state(gamepad, GamepadControl())
    assert rates["linear_velocity"]["x"] < 0
    assert rates["linear_velocity"]["y"] > 0
    assert rates["angular_velocity"]["z"] == 0
    assert rates["opening_rate"] > 0
    assert active["D-PAD"] and active["LB"] and active["A / B"]
    assert gamepad.read_axes == [
        pygame.CONTROLLER_AXIS_RIGHTX,
        pygame.CONTROLLER_AXIS_RIGHTY,
        pygame.CONTROLLER_AXIS_LEFTX,
        pygame.CONTROLLER_AXIS_LEFTY,
        pygame.CONTROLLER_AXIS_TRIGGERLEFT,
        pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
    ]
    assert len(gamepad.read_buttons) == 7


def test_rotation_requires_modifier_and_right_horizontal_is_unused_in_translation():
    axes, buttons = _zero_controls()
    axes[pygame.CONTROLLER_AXIS_RIGHTX] = 32767
    axes[pygame.CONTROLLER_AXIS_TRIGGERRIGHT] = 32767

    class Controller:
        def get_axis(self, axis):
            return axes[axis]

        def get_button(self, button):
            return buttons[button]

    state = GamepadControl()
    rates, active = _read_controller_state(Controller(), state)
    assert rates["linear_velocity"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert rates["angular_velocity"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert not active["RIGHT STICK"] and not active["LT / RT"]
    buttons[pygame.CONTROLLER_BUTTON_LEFTSHOULDER] = True
    rates, active = _read_controller_state(Controller(), state)
    assert rates["angular_velocity"]["y"] > 0
    assert rates["angular_velocity"]["z"] > 0
    assert active["RIGHT STICK"] and active["LT / RT"] and active["LB"]


def test_gamepad_control_maps_inputs_and_retains_neutral_interlock():
    control = GamepadControl()
    dpad = dict.fromkeys(("up", "down", "left", "right"), False)
    bumpers = {"left": True}
    jaw_buttons = {"open": True, "close": False}

    def update(right_y):
        return control.update(0.0, 0.0, 0.0, right_y, 0.0, 0.0, dpad, bumpers, jaw_buttons)

    rates, active = update(-1.0)
    assert rates["angular_velocity"]["x"] == -MAX_ANGULAR_SPEED
    assert rates["opening_rate"] == MAX_OPENING_RATE
    assert active["RIGHT STICK"] and active["LB"] and active["A / B"]
    bumpers["left"] = False
    rates, active = update(-1.0)
    assert rates["linear_velocity"]["z"] == 0.0
    assert not active["RIGHT STICK"]
    update(0.0)
    rates, active = update(-1.0)
    assert rates["linear_velocity"]["z"] == MAX_LINEAR_SPEED
    assert active["RIGHT STICK"]


def test_z_translation_waits_for_both_right_stick_axes_to_return_to_dead_zone():
    axes, buttons = _zero_controls()

    class Controller:
        def get_axis(self, axis):
            return axes[axis]

        def get_button(self, button):
            return buttons[button]

    gamepad = Controller()
    state = GamepadControl()
    buttons[pygame.CONTROLLER_BUTTON_LEFTSHOULDER] = True
    axes[pygame.CONTROLLER_AXIS_RIGHTY] = -32767
    rates, _ = _read_controller_state(gamepad, state)
    assert rates["linear_velocity"]["z"] == 0
    assert rates["angular_velocity"]["x"] < 0

    buttons[pygame.CONTROLLER_BUTTON_LEFTSHOULDER] = False
    rates, _ = _read_controller_state(gamepad, state)
    assert rates["linear_velocity"]["z"] == 0
    assert rates["angular_velocity"]["x"] == 0
    axes[pygame.CONTROLLER_AXIS_RIGHTY] = 0
    axes[pygame.CONTROLLER_AXIS_RIGHTX] = 32767
    _read_controller_state(gamepad, state)
    assert state.awaiting_right_stick_neutral
    axes[pygame.CONTROLLER_AXIS_RIGHTX] = 0
    _read_controller_state(gamepad, state)
    assert not state.awaiting_right_stick_neutral
    axes[pygame.CONTROLLER_AXIS_RIGHTY] = -32767
    rates, _ = _read_controller_state(gamepad, state)
    assert rates["linear_velocity"]["z"] == pytest.approx(MAX_LINEAR_SPEED)


def test_gamepad_view_explains_controls_and_neutral_interlock():
    app = gamepad_module.ArmControllerGamepadApp.__new__(gamepad_module.ArmControllerGamepadApp)
    app.demo = gamepad_module.ArmControllerDemo()
    app.teleop_writer = SimpleNamespace(publication_matched_status=SimpleNamespace(current_count=0))
    app.tool_writer = SimpleNamespace(publication_matched_status=SimpleNamespace(current_count=0))
    app.feedback_view = lambda: {"feedback": {"readiness": "NOT_READY"}}
    app.has_arm_status = False
    app.status = SimpleNamespace(name="ON")
    app.gamepad = None
    app.input_name = "No gamepad"
    app.active_inputs = dict.fromkeys(
        ("LEFT STICK", "RIGHT STICK", "LT / RT", "D-PAD", "LB", "A / B"), False
    )
    app.control = GamepadControl()
    inputs = {item["label"]: item["description"] for item in app.view()["inputs"]}
    assert "Up / down: +Z / -Z" in inputs["RIGHT STICK"]
    assert "Hold to rotate" in inputs["LB"]
    assert "With LB" in inputs["LT / RT"]
    app.control.awaiting_right_stick_neutral = True
    inputs = {item["label"]: item["description"] for item in app.view()["inputs"]}
    assert "Return to neutral" in inputs["RIGHT STICK"]
