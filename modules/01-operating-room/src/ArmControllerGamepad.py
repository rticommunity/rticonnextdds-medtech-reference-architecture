#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Pygame gamepad adapter with an asyncio-owned RTI Demo UI presentation."""

from __future__ import annotations

import asyncio
import os
import time

import pygame
import rti.asyncio  # noqa: F401 - installs Connext's asyncio integration
import rti.connextdds as dds
from DdsUtils import register_type
from DemoUiSupport import DemoUiState, create_demo_ui, run_demo_ui
from pygame._sdl2 import controller
from Types import Common, DdsEntities, Orchestrator, SurgicalRobot

CONTROL_PERIOD_SECONDS = 0.02
HEARTBEAT_PERIOD_SECONDS = 0.05
AXIS_DEAD_ZONE = 0.35
TELEOP_AXES = ("X", "Y", "ROLL", "GRIPPER")


def teleop_directions_from_controls(
    left_x: float,
    left_y: float,
    roll: float,
    gripper_open: bool,
    gripper_close: bool,
) -> dict[str, str]:
    def direction(value: float, *, invert: bool = False) -> str:
        if invert:
            value = -value
        if abs(value) < AXIS_DEAD_ZONE:
            return "STOPPED"
        return "POSITIVE" if value > 0 else "NEGATIVE"

    gripper_direction = "STOPPED"
    if gripper_open != gripper_close:
        gripper_direction = "POSITIVE" if gripper_open else "NEGATIVE"
    return {
        "X": direction(left_x),
        "Y": direction(left_y, invert=True),
        "ROLL": direction(roll, invert=True),
        "GRIPPER": gripper_direction,
    }


def active_controls_from_directions(directions: dict[str, str]) -> dict[str, bool]:
    return {
        "LEFT STICK": any(directions[axis] != "STOPPED" for axis in ("X", "Y")),
        "RIGHT STICK": directions["ROLL"] != "STOPPED",
        "LEFT TRIGGER": directions["GRIPPER"] == "POSITIVE",
        "RIGHT TRIGGER": directions["GRIPPER"] == "NEGATIVE",
        "D-PAD": False,
        "BUMPERS": False,
        "A / B": False,
    }


def _merge_digital_direction(
    analog_direction: str,
    positive_pressed: bool,
    negative_pressed: bool,
) -> str:
    if analog_direction != "STOPPED":
        return analog_direction
    if positive_pressed != negative_pressed:
        return "POSITIVE" if positive_pressed else "NEGATIVE"
    return "STOPPED"


def read_controller_state(gamepad) -> tuple[dict[str, str], dict[str, bool]]:
    axis = GamepadApplication.normalize_axis
    trigger = GamepadApplication.normalize_trigger
    analog = teleop_directions_from_controls(
        axis(gamepad.get_axis(pygame.CONTROLLER_AXIS_LEFTX)),
        axis(gamepad.get_axis(pygame.CONTROLLER_AXIS_LEFTY)),
        axis(gamepad.get_axis(pygame.CONTROLLER_AXIS_RIGHTX)),
        trigger(gamepad.get_axis(pygame.CONTROLLER_AXIS_TRIGGERLEFT)) > AXIS_DEAD_ZONE,
        trigger(gamepad.get_axis(pygame.CONTROLLER_AXIS_TRIGGERRIGHT)) > AXIS_DEAD_ZONE,
    )
    dpad = {
        "up": gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_UP),
        "down": gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_DOWN),
        "left": gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_LEFT),
        "right": gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_RIGHT),
    }
    bumpers = {
        "left": gamepad.get_button(pygame.CONTROLLER_BUTTON_LEFTSHOULDER),
        "right": gamepad.get_button(pygame.CONTROLLER_BUTTON_RIGHTSHOULDER),
    }
    face = {
        "open": gamepad.get_button(pygame.CONTROLLER_BUTTON_A),
        "close": gamepad.get_button(pygame.CONTROLLER_BUTTON_B),
    }
    directions = {
        "X": _merge_digital_direction(analog["X"], dpad["right"], dpad["left"]),
        "Y": _merge_digital_direction(analog["Y"], dpad["up"], dpad["down"]),
        "ROLL": _merge_digital_direction(analog["ROLL"], bumpers["left"], bumpers["right"]),
        "GRIPPER": _merge_digital_direction(analog["GRIPPER"], face["open"], face["close"]),
    }
    active = active_controls_from_directions(analog)
    active["D-PAD"] = any(dpad.values())
    active["BUMPERS"] = any(bumpers.values())
    active["A / B"] = any(face.values())
    return directions, active


def read_controller_directions(gamepad) -> dict[str, str]:
    return read_controller_state(gamepad)[0]


def initialize_gamepad_input() -> None:
    # The browser is foreground while this app's SDL window is hidden.
    os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
    pygame.init()
    pygame.joystick.init()
    controller.init()


class GamepadDdsAdapter:
    def __init__(self) -> None:
        for data_type in (
            Common.DeviceStatus,
            Common.DeviceHeartbeat,
            Orchestrator.DeviceCommand,
            SurgicalRobot.TeleopControl,
        ):
            register_type(data_type)
        entities = DdsEntities.Constants
        self.participant = dds.QosProvider.default.create_participant_from_config(
            entities.ARM_CONTROLLER_DP
        )
        self.status_writer = dds.DataWriter(self.participant.find_datawriter(entities.STATUS_DW))
        self.heartbeat_writer = dds.DataWriter(self.participant.find_datawriter(entities.HB_DW))
        self.teleop_writer = dds.DataWriter(
            self.participant.find_datawriter(entities.TELEOP_CONTROL_DW)
        )
        self.command_reader = dds.DataReader(
            self.participant.find_datareader(entities.DEVICE_COMMAND_DR)
        )
        self.status = Common.DeviceStatus(
            device=Common.DeviceType.ARM_CONTROLLER,
            status=Common.DeviceStatuses.ON,
        )
        self.status_writer.write(self.status)

    def set_status(self, status: str) -> None:
        self.status.status = getattr(Common.DeviceStatuses, status)
        self.status_writer.write(self.status)

    def publish_heartbeat(self) -> None:
        self.heartbeat_writer.write(Common.DeviceHeartbeat(device=Common.DeviceType.ARM_CONTROLLER))

    def publish_teleop(self, axis_name: str, direction_name: str) -> None:
        sample = SurgicalRobot.TeleopControl(
            axis=getattr(SurgicalRobot.TeleopAxes, axis_name),
            direction=getattr(SurgicalRobot.TeleopDirections, direction_name),
        )
        self.teleop_writer.write(sample)

    async def device_commands(self):
        async for sample in self.command_reader.take_data_async():
            yield sample.command.name

    def close(self) -> None:
        self.participant.close()


class GamepadApplication:
    def __init__(self, ui: DemoUiState) -> None:
        self.dds = GamepadDdsAdapter()
        self.ui = ui
        self.status = "ON"
        self.gamepad = None
        self.gamepad_instance_id = None
        self.gamepad_name = "No supported gamepad connected; waiting"
        self.directions = dict.fromkeys(TELEOP_AXES, "STOPPED")
        self.active_inputs = active_controls_from_directions(self.directions)
        self.last_published = dict.fromkeys(TELEOP_AXES, "STOPPED")
        self.next_publish = dict.fromkeys(TELEOP_AXES, 0.0)
        self.next_heartbeat = 0.0
        self.running = True

    def view(self) -> dict:
        return {
            "kind": "gamepad-controller",
            "title": "Xbox Arm Controller",
            "status": self.status,
            "header_badges": [
                {
                    "label": "Input",
                    "value": "CONNECTED" if self.gamepad is not None else "WAITING",
                    "tone": "good" if self.gamepad is not None else "warn",
                },
                {"label": "Device", "value": self.status},
            ],
            "input_connected": self.gamepad is not None,
            "gamepad_name": self.gamepad_name,
            "inputs": [
                {
                    "label": label,
                    "description": description,
                    "active": self.active_inputs[label],
                }
                for label, description in (
                    ("LEFT STICK", "Jog end effector in planar X / Y"),
                    ("RIGHT STICK", "Rotate gripper wrist"),
                    ("LEFT TRIGGER", "Open gripper"),
                    ("RIGHT TRIGGER", "Close gripper"),
                    ("D-PAD", "Jog end effector in planar X / Y"),
                    ("BUMPERS", "Left / right bumpers roll left / right"),
                    ("A / B", "Open / close gripper"),
                )
            ],
            "footer": True,
        }

    def set_status(self, status) -> None:
        if self.status != status:
            self.status = status
            self.dds.set_status(status)
        self.ui.update(**self.view())

    def publish_direction(self, axis_name: str, direction_name: str) -> None:
        if self.status != "ON":
            return
        self.dds.publish_teleop(axis_name, direction_name)
        self.last_published[axis_name] = direction_name
        self.next_publish[axis_name] = time.monotonic() + CONTROL_PERIOD_SECONDS

    def stop_active_axes(self) -> None:
        for axis_name, direction in self.last_published.items():
            if direction != "STOPPED":
                self.publish_direction(axis_name, "STOPPED")
        self.directions = dict.fromkeys(TELEOP_AXES, "STOPPED")

    def connect_controller(self, device_index: int) -> None:
        if self.gamepad is not None or not controller.is_controller(device_index):
            return
        self.gamepad = controller.Controller(device_index)
        joystick = self.gamepad.as_joystick()
        self.gamepad_instance_id = joystick.get_instance_id()
        self.gamepad_name = joystick.get_name() or "Xbox-style controller"
        self.ui.log(f"Connected gamepad: {self.gamepad_name}", "ok")

    def disconnect_controller(self) -> None:
        if self.gamepad is not None:
            self.gamepad.quit()
        self.gamepad = None
        self.gamepad_instance_id = None
        self.gamepad_name = "No supported gamepad connected; waiting"
        self.stop_active_axes()
        self.active_inputs = active_controls_from_directions(self.directions)
        self.ui.log(self.gamepad_name, "warn")

    @staticmethod
    def normalize_axis(value: int) -> float:
        return max(-1.0, min(1.0, value / 32767.0))

    @staticmethod
    def normalize_trigger(value: int) -> float:
        return max(0.0, min(1.0, value / 32767.0))

    def read_controls(self) -> tuple[dict[str, str], dict[str, bool]]:
        if self.gamepad is None:
            directions = dict.fromkeys(TELEOP_AXES, "STOPPED")
            return directions, active_controls_from_directions(directions)
        return read_controller_state(self.gamepad)

    def process_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.CONTROLLERDEVICEADDED:
                self.connect_controller(event.device_index)
            elif (
                event.type == pygame.CONTROLLERDEVICEREMOVED
                and event.instance_id == self.gamepad_instance_id
            ):
                self.disconnect_controller()

    async def receive_commands(self) -> None:
        async for command in self.dds.device_commands():
            if command == "PAUSE":
                self.stop_active_axes()
                self.set_status("PAUSED")
                self.ui.log("Arm Controller paused by Orchestrator", "warn")
            elif command == "START":
                self.set_status("ON")
                self.ui.log("Arm Controller started by Orchestrator", "ok")
            else:
                self.stop_active_axes()
                self.set_status("OFF")
                self.running = False
                await self.app.stop()
                return

    async def run(self, app) -> None:
        self.app = app
        initialize_gamepad_input()
        pygame.display.set_mode((1, 1), pygame.HIDDEN)
        for index in range(controller.get_count()):
            self.connect_controller(index)
        self.ui.update(**self.view())
        self.ui.log("Xbox Arm Controller is online")
        next_ui_refresh = 0.0
        try:
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self.receive_commands())
                while self.running:
                    now = time.monotonic()
                    self.process_events()
                    self.directions, self.active_inputs = self.read_controls()
                    if self.status == "ON":
                        for axis_name, direction in self.directions.items():
                            if direction != self.last_published[axis_name] or (
                                direction != "STOPPED" and now >= self.next_publish[axis_name]
                            ):
                                self.publish_direction(axis_name, direction)
                    if now >= self.next_heartbeat:
                        self.dds.publish_heartbeat()
                        self.next_heartbeat = now + HEARTBEAT_PERIOD_SECONDS
                    if now >= next_ui_refresh:
                        self.ui.update(**self.view())
                        next_ui_refresh = now + 0.2
                    await asyncio.sleep(CONTROL_PERIOD_SECONDS)
        finally:
            self.stop_active_axes()
            self.status = "OFF"
            self.dds.set_status("OFF")
            if self.gamepad is not None:
                self.gamepad.quit()
            pygame.quit()
            self.dds.close()
            self.ui.log("Xbox Arm Controller stopped")


async def run_application(app) -> None:
    ui = DemoUiState(
        app,
        kind="gamepad-controller",
        title="Xbox Arm Controller",
        description="Controller input is translated into RTI Connext DDS teleoperation.",
    )
    application = GamepadApplication(ui)
    await application.run(app)


def main() -> None:
    run_demo_ui(create_demo_ui("Xbox Arm Controller"), run_application)


if __name__ == "__main__":
    main()
