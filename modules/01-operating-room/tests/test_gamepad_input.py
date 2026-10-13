#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

from __future__ import annotations

import os
import sys

import pytest
from module01_test_support import SRC_DIR

sys.path.insert(0, str(SRC_DIR))

pygame = pytest.importorskip("pygame")
from ArmControllerGamepad import initialize_gamepad_input, read_controller_state  # noqa: E402
from pygame._sdl2 import controller as pygame_controller  # noqa: E402


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


def test_gamepad_axes_use_pygame_controller_axis_constants():
    values = {
        pygame.CONTROLLER_AXIS_LEFTX: round(0.8 * 32767),
        pygame.CONTROLLER_AXIS_LEFTY: round(-0.6 * 32767),
        pygame.CONTROLLER_AXIS_RIGHTX: round(-0.9 * 32767),
        pygame.CONTROLLER_AXIS_TRIGGERLEFT: round(0.8 * 32767),
        pygame.CONTROLLER_AXIS_TRIGGERRIGHT: 0,
    }
    buttons = {
        pygame.CONTROLLER_BUTTON_DPAD_UP: False,
        pygame.CONTROLLER_BUTTON_DPAD_DOWN: False,
        pygame.CONTROLLER_BUTTON_DPAD_LEFT: False,
        pygame.CONTROLLER_BUTTON_DPAD_RIGHT: False,
        pygame.CONTROLLER_BUTTON_LEFTSHOULDER: False,
        pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: False,
        pygame.CONTROLLER_BUTTON_A: False,
        pygame.CONTROLLER_BUTTON_B: False,
    }

    class Controller:
        def __init__(self):
            self.read_axes = []
            self.read_buttons = []

        def get_axis(self, axis):
            self.read_axes.append(axis)
            return values[axis]

        def get_button(self, button):
            self.read_buttons.append(button)
            return buttons[button]

    gamepad = Controller()

    directions, active = read_controller_state(gamepad)
    assert directions == {
        "X": "POSITIVE",
        "Y": "POSITIVE",
        "ROLL": "POSITIVE",
        "GRIPPER": "POSITIVE",
    }
    assert active["LEFT STICK"]
    assert active["RIGHT STICK"]
    assert active["LEFT TRIGGER"]
    assert not active["RIGHT TRIGGER"]
    assert not active["D-PAD"]
    assert not active["BUMPERS"]
    assert not active["A / B"]
    assert gamepad.read_axes == [
        pygame.CONTROLLER_AXIS_LEFTX,
        pygame.CONTROLLER_AXIS_LEFTY,
        pygame.CONTROLLER_AXIS_RIGHTX,
        pygame.CONTROLLER_AXIS_TRIGGERLEFT,
        pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
    ]
    assert len(gamepad.read_buttons) == 8


def test_dpad_bumpers_and_face_buttons_publish_teleop_directions():
    axes = dict.fromkeys(
        (
            pygame.CONTROLLER_AXIS_LEFTX,
            pygame.CONTROLLER_AXIS_LEFTY,
            pygame.CONTROLLER_AXIS_RIGHTX,
            pygame.CONTROLLER_AXIS_TRIGGERLEFT,
            pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
        ),
        0,
    )
    buttons = {
        pygame.CONTROLLER_BUTTON_DPAD_UP: True,
        pygame.CONTROLLER_BUTTON_DPAD_DOWN: False,
        pygame.CONTROLLER_BUTTON_DPAD_LEFT: True,
        pygame.CONTROLLER_BUTTON_DPAD_RIGHT: False,
        pygame.CONTROLLER_BUTTON_LEFTSHOULDER: False,
        pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: True,
        pygame.CONTROLLER_BUTTON_A: True,
        pygame.CONTROLLER_BUTTON_B: False,
    }

    class Controller:
        def get_axis(self, axis):
            return axes[axis]

        def get_button(self, button):
            return buttons[button]

    directions, active = read_controller_state(Controller())

    assert directions == {
        "X": "NEGATIVE",
        "Y": "POSITIVE",
        "ROLL": "NEGATIVE",
        "GRIPPER": "POSITIVE",
    }
    assert active["D-PAD"]
    assert active["BUMPERS"]
    assert active["A / B"]


def test_left_and_right_bumpers_match_roll_left_and_right():
    axes = dict.fromkeys(
        (
            pygame.CONTROLLER_AXIS_LEFTX,
            pygame.CONTROLLER_AXIS_LEFTY,
            pygame.CONTROLLER_AXIS_RIGHTX,
            pygame.CONTROLLER_AXIS_TRIGGERLEFT,
            pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
        ),
        0,
    )
    buttons = {
        pygame.CONTROLLER_BUTTON_DPAD_UP: False,
        pygame.CONTROLLER_BUTTON_DPAD_DOWN: False,
        pygame.CONTROLLER_BUTTON_DPAD_LEFT: False,
        pygame.CONTROLLER_BUTTON_DPAD_RIGHT: False,
        pygame.CONTROLLER_BUTTON_LEFTSHOULDER: True,
        pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: False,
        pygame.CONTROLLER_BUTTON_A: False,
        pygame.CONTROLLER_BUTTON_B: False,
    }

    class Controller:
        def get_axis(self, axis):
            return axes[axis]

        def get_button(self, button):
            return buttons[button]

    gamepad = Controller()
    left_directions, _ = read_controller_state(gamepad)
    buttons[pygame.CONTROLLER_BUTTON_LEFTSHOULDER] = False
    buttons[pygame.CONTROLLER_BUTTON_RIGHTSHOULDER] = True
    right_directions, _ = read_controller_state(gamepad)

    assert left_directions["ROLL"] == "POSITIVE"
    assert right_directions["ROLL"] == "NEGATIVE"
