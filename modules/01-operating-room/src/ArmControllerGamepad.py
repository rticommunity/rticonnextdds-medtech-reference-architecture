#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Pygame gamepad adapter with an asyncio-owned RTI Demo UI presentation."""

from __future__ import annotations

import asyncio
import math
import os
import time
from typing import TYPE_CHECKING, Any

import pygame
from DemoUiSupport import DemoUiState, create_demo_ui, log_failure, run_app_task, run_demo_ui
from pygame._sdl2 import controller

if TYPE_CHECKING:
    from MedTech import Device

CONTROL_PERIOD_SECONDS = 0.02
FEEDBACK_STALE_SECONDS = 0.5
AXIS_DEAD_ZONE = 0.35
MAX_LINEAR_SPEED = 0.05
MAX_ANGULAR_SPEED = 0.5
MAX_OPENING_RATE = 0.02
ARM_ID = "arm-1"


def _bounded_input(value: float, lower: float, upper: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        return 0.0
    return max(lower, min(upper, value))


def _dead_zone(value: float) -> float:
    value = _bounded_input(value, -1.0, 1.0)
    magnitude = abs(value)
    if magnitude <= AXIS_DEAD_ZONE:
        return 0.0
    scaled = (magnitude - AXIS_DEAD_ZONE) / (1.0 - AXIS_DEAD_ZONE)
    return math.copysign(min(scaled, 1.0), value)


def _unit_vector(values: tuple[float, float, float]) -> tuple[float, float, float]:
    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude <= 1.0:
        return values
    return tuple(value / magnitude for value in values)


def teleop_rates_from_controls(
    left_x: float,
    left_y: float,
    right_x: float,
    right_y: float,
    left_trigger: float,
    right_trigger: float,
    dpad: dict[str, bool],
    bumpers: dict[str, bool],
    jaw_buttons: dict[str, bool],
    z_translation_enabled: bool = True,
) -> dict[str, dict[str, float] | float]:
    stick_x = _dead_zone(left_x)
    stick_y = _dead_zone(-left_y)
    dpad_x = float(dpad["right"]) - float(dpad["left"])
    dpad_y = float(dpad["up"]) - float(dpad["down"])
    if stick_x == 0.0:
        stick_x = dpad_x
    if stick_y == 0.0:
        stick_y = dpad_y

    rotating = bumpers["left"]
    linear = _unit_vector(
        (stick_x, stick_y, -_dead_zone(right_y) if not rotating and z_translation_enabled else 0.0)
    )
    angular = (0.0, 0.0, 0.0)
    if rotating:
        angular = _unit_vector(
            (
                _dead_zone(right_y),
                _dead_zone(right_x),
                _dead_zone(_bounded_input(right_trigger, 0.0, 1.0))
                - _dead_zone(_bounded_input(left_trigger, 0.0, 1.0)),
            )
        )
    jaw_direction = float(jaw_buttons["open"]) - float(jaw_buttons["close"])
    return {
        "linear_velocity": {
            "x": linear[0] * MAX_LINEAR_SPEED,
            "y": linear[1] * MAX_LINEAR_SPEED,
            "z": linear[2] * MAX_LINEAR_SPEED,
        },
        "angular_velocity": {
            "x": angular[0] * MAX_ANGULAR_SPEED,
            "y": angular[1] * MAX_ANGULAR_SPEED,
            "z": angular[2] * MAX_ANGULAR_SPEED,
        },
        "opening_rate": jaw_direction * MAX_OPENING_RATE,
    }


def bounded_teleop_rates(rates: dict) -> dict:
    def bounded_vector(vector: dict[str, float], limit: float) -> dict[str, float]:
        values = {
            axis: _bounded_input(vector.get(axis, 0.0), -limit, limit) for axis in ("x", "y", "z")
        }
        magnitude = math.sqrt(sum(value * value for value in values.values()))
        if magnitude > limit:
            scale = limit / magnitude
            values = {axis: value * scale for axis, value in values.items()}
        return values

    return {
        "linear_velocity": bounded_vector(rates.get("linear_velocity", {}), MAX_LINEAR_SPEED),
        "angular_velocity": bounded_vector(rates.get("angular_velocity", {}), MAX_ANGULAR_SPEED),
        "opening_rate": _bounded_input(
            rates.get("opening_rate", 0.0), -MAX_OPENING_RATE, MAX_OPENING_RATE
        ),
    }


def active_controls_from_rates(
    rates: dict[str, dict[str, float] | float],
    dpad: dict[str, bool],
    bumpers: dict[str, bool],
    jaw_buttons: dict[str, bool],
) -> dict[str, bool]:
    linear = rates["linear_velocity"]
    angular = rates["angular_velocity"]
    assert isinstance(linear, dict) and isinstance(angular, dict)
    return {
        "LEFT STICK": linear["x"] != 0.0 or linear["y"] != 0.0,
        "RIGHT STICK": linear["z"] != 0.0 or angular["x"] != 0.0 or angular["y"] != 0.0,
        "LT / RT": angular["z"] != 0.0,
        "D-PAD": any(dpad.values()),
        "LB": bumpers["left"],
        "A / B": any(jaw_buttons.values()),
    }


class GamepadControlState:
    def __init__(self) -> None:
        self.awaiting_right_stick_neutral = False

    def update(self, rotating: bool, right_x: float, right_y: float) -> None:
        if rotating:
            self.awaiting_right_stick_neutral = True
        elif _dead_zone(right_x) == 0.0 and _dead_zone(right_y) == 0.0:
            self.awaiting_right_stick_neutral = False


def read_controller_state(
    gamepad, control_state: GamepadControlState
) -> tuple[dict, dict[str, bool]]:
    axis = ArmControllerGamepadApp.normalize_axis
    trigger = ArmControllerGamepadApp.normalize_trigger
    dpad = {
        "up": bool(gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_UP)),
        "down": bool(gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_DOWN)),
        "left": bool(gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_LEFT)),
        "right": bool(gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_RIGHT)),
    }
    bumpers = {
        "left": bool(gamepad.get_button(pygame.CONTROLLER_BUTTON_LEFTSHOULDER)),
    }
    jaw_buttons = {
        "open": bool(gamepad.get_button(pygame.CONTROLLER_BUTTON_A)),
        "close": bool(gamepad.get_button(pygame.CONTROLLER_BUTTON_B)),
    }
    right_x = axis(gamepad.get_axis(pygame.CONTROLLER_AXIS_RIGHTX))
    right_y = axis(gamepad.get_axis(pygame.CONTROLLER_AXIS_RIGHTY))
    control_state.update(bumpers["left"], right_x, right_y)
    rates = teleop_rates_from_controls(
        axis(gamepad.get_axis(pygame.CONTROLLER_AXIS_LEFTX)),
        axis(gamepad.get_axis(pygame.CONTROLLER_AXIS_LEFTY)),
        right_x,
        right_y,
        trigger(gamepad.get_axis(pygame.CONTROLLER_AXIS_TRIGGERLEFT)),
        trigger(gamepad.get_axis(pygame.CONTROLLER_AXIS_TRIGGERRIGHT)),
        dpad,
        bumpers,
        jaw_buttons,
        z_translation_enabled=not control_state.awaiting_right_stick_neutral,
    )
    return rates, active_controls_from_rates(rates, dpad, bumpers, jaw_buttons)


def initialize_gamepad_input() -> None:
    # The browser is foreground while this app's SDL window is hidden.
    os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
    pygame.init()
    pygame.joystick.init()
    controller.init()


def _vector_view(vector) -> dict[str, float]:
    return {axis: round(float(getattr(vector, axis)), 4) for axis in ("x", "y", "z")}


class ArmControllerGamepadApp:
    def __init__(self, ui: DemoUiState) -> None:
        import rti.asyncio  # noqa: F401 - installs Connext's asyncio integration
        import rti.connextdds as dds
        from MedTech import DdsEntities, Device, Robot
        from MedTechTypes import register_type

        for data_type in (
            Device.Status,
            Device.Heartbeat,
            Device.Command,
            Robot.Arm.TeleopControl,
            Robot.Tool.ParallelJawControl,
            Robot.Arm.Status,
            Robot.Arm.Telemetry,
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
        self.tool_writer = dds.DataWriter(
            self.participant.find_datawriter(entities.TOOL_CONTROL_DW)
        )
        self.command_reader = dds.DataReader(
            self.participant.find_datareader(entities.DEVICE_COMMAND_DR)
        )
        self.arm_status_reader = dds.DataReader(
            self.participant.find_datareader(entities.ARM_STATUS_DR)
        )
        self.arm_telemetry_reader = dds.DataReader(
            self.participant.find_datareader(entities.ARM_TELEMETRY_DR)
        )
        self.status_sample = Device.Status(
            device=Device.DeviceType.ARM_CONTROLLER,
            status=Device.DeviceStatuses.ON,
        )
        self.failed = False
        self.ui = ui
        self.status = Device.DeviceStatuses.ON
        self.gamepad = None
        self.gamepad_instance_id = None
        self.gamepad_name = "No supported gamepad connected; waiting"
        self.control_state = GamepadControlState()
        self.rates = self.zero_rates()
        self.active_inputs: dict[str, bool] = dict.fromkeys(
            (
                "LEFT STICK",
                "RIGHT STICK",
                "LT / RT",
                "D-PAD",
                "LB",
                "A / B",
            ),
            False,
        )
        self.last_arm_readiness = "NOT_READY"
        self.has_arm_status = False
        self.last_telemetry: dict | None = None
        self.last_telemetry_time: float | None = None
        self.running = True

    @staticmethod
    def zero_rates() -> dict:
        return {
            "linear_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angular_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "opening_rate": 0.0,
        }

    def feedback_view(self) -> dict:
        now = time.monotonic()
        telemetry = self.last_telemetry or {}
        return {
            "feedback": {
                "readiness": self.last_arm_readiness,
                "status_known": self.has_arm_status,
                "position": None
                if telemetry.get("tcp_pose") is None
                else telemetry["tcp_pose"]["position"],
                "orientation": None
                if telemetry.get("tcp_pose") is None
                else telemetry["tcp_pose"]["orientation"],
                "opening_width": telemetry.get("jaw_opening_width"),
                "freshness": {
                    "telemetry": self.last_telemetry_time is not None
                    and now - self.last_telemetry_time <= FEEDBACK_STALE_SECONDS,
                },
            }
        }

    def view(self) -> dict:
        feedback = self.feedback_view()["feedback"]
        readiness_badge = (
            feedback["readiness"] + " · LAST KNOWN" if self.has_arm_status else "UNKNOWN"
        )
        return {
            "kind": "gamepad-controller",
            "title": "Xbox Arm Controller",
            "status": self.status.name,
            "header_badges": [
                {
                    "label": "Input",
                    "value": "CONNECTED" if self.gamepad is not None else "WAITING",
                    "tone": "good" if self.gamepad is not None else "warn",
                },
                {"label": "Device", "value": self.status.name},
                {"label": "Control frame", "value": "BASE (+Z UP)"},
                {
                    "label": "Arm",
                    "value": readiness_badge,
                    "tone": "good"
                    if feedback["readiness"] == "READY" and self.has_arm_status
                    else "warn",
                },
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
                    ("LEFT STICK", "Move across the workspace: base X / Y"),
                    (
                        "RIGHT STICK",
                        "Return to neutral to resume Z motion"
                        if self.control_state.awaiting_right_stick_neutral
                        and not self.active_inputs["LB"]
                        else "Up / down: +Z / -Z; with LB: right / left rotate +Y / -Y, "
                        "up / down rotate -X / +X",
                    ),
                    ("LB", "Hold to rotate; releases rotation and pauses Z until stick is neutral"),
                    ("LT / RT", "With LB: rotate base Z negative / positive"),
                    ("D-PAD", "Digital base X / Y motion fallback"),
                    ("A / B", "A opens / B closes the parallel jaws while held"),
                )
            ],
            "footer": True,
            "feedback": feedback,
        }

    def set_status(self, status: Device.DeviceStatuses) -> None:
        if self.status != status:
            self.status = status
            self.write_status(status)
        self.ui.update(**self.view())

    def publish_rates(self, rates: dict) -> None:
        from MedTech import Device, Geometry, Robot

        if self.status == Device.DeviceStatuses.ON:
            rates = bounded_teleop_rates(rates)
            linear = rates["linear_velocity"]
            angular = rates["angular_velocity"]
            self.teleop_writer.write(
                Robot.Arm.TeleopControl(
                    arm_id=ARM_ID,
                    linear_velocity=Geometry.Vector3(x=linear["x"], y=linear["y"], z=linear["z"]),
                    angular_velocity=Geometry.Vector3(
                        x=angular["x"], y=angular["y"], z=angular["z"]
                    ),
                )
            )
            self.tool_writer.write(
                Robot.Tool.ParallelJawControl(arm_id=ARM_ID, opening_rate=rates["opening_rate"])
            )

    def write_status(self, status: Device.DeviceStatuses) -> None:
        self.status_sample.status = status
        self.status_writer.write(self.status_sample)

    def stop_motion(self) -> None:
        from MedTech import Device

        self.rates = self.zero_rates()
        if self.status == Device.DeviceStatuses.ON:
            self.publish_rates(self.rates)

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
        self.stop_motion()
        self.active_inputs = dict.fromkeys(self.active_inputs, False)
        self.ui.log(self.gamepad_name, "warn")

    @staticmethod
    def normalize_axis(value: int) -> float:
        return max(-1.0, min(1.0, value / 32767.0))

    @staticmethod
    def normalize_trigger(value: int) -> float:
        return max(0.0, min(1.0, value / 32767.0))

    def read_controls(self) -> tuple[dict, dict[str, bool]]:
        if self.gamepad is None:
            rates = self.zero_rates()
            return rates, dict.fromkeys(self.active_inputs, False)
        return read_controller_state(self.gamepad, self.control_state)

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
        from MedTech import Device
        from MedTechTypes import device_status_after_command

        async for sample in self.command_reader.take_data_async():
            command = sample.command
            status = device_status_after_command(command)
            if command == Device.DeviceCommands.PAUSE:
                self.rates = self.zero_rates()
                self.set_status(status)
                self.ui.log("Arm Controller paused by Orchestrator", "warn")
            elif command == Device.DeviceCommands.START:
                self.set_status(status)
                self.ui.log("Arm Controller started by Orchestrator", "ok")
            else:
                self.rates = self.zero_rates()
                self.set_status(status)
                self.running = False
                await self.app.stop()
                return

    @staticmethod
    def _sample_data(sample: Any):
        return getattr(sample, "data", sample)

    async def receive_arm_status(self) -> None:
        async for sample in self.arm_status_reader.take_data_async():
            status = self._sample_data(sample)
            if getattr(status, "arm_id", None) != ARM_ID:
                continue
            self.last_arm_readiness = status.readiness.name
            self.has_arm_status = True
            self.ui.update(**self.view())

    async def receive_arm_telemetry(self) -> None:
        async for sample in self.arm_telemetry_reader.take_data_async():
            telemetry = self._sample_data(sample)
            if getattr(telemetry, "arm_id", None) != ARM_ID:
                continue
            pose = getattr(telemetry, "tcp_pose", None)
            jaw = getattr(telemetry, "parallel_jaw", None)
            self.last_telemetry = {
                "tcp_pose": None
                if pose is None
                else {
                    "position": _vector_view(pose.position),
                    "orientation": {
                        axis: round(float(getattr(pose.orientation, axis)), 5)
                        for axis in ("x", "y", "z", "w")
                    },
                },
                "jaw_opening_width": None if jaw is None else round(float(jaw.opening_width), 4),
            }
            self.last_telemetry_time = time.monotonic()
            self.ui.update(**self.view())

    async def run(self, app) -> None:
        from HeartbeatPresence import publish_heartbeats
        from MedTech import Device

        self.app = app
        heartbeat_stop = asyncio.Event()
        workers = []
        enabled = False

        async def task_failed() -> None:
            self.failed = True
            self.running = False
            heartbeat_stop.set()
            for task in workers:
                if task is not asyncio.current_task():
                    task.cancel()
            await app.stop()

        try:
            self.participant.enable()
            self.status_writer.write(self.status_sample)
            enabled = True
            initialize_gamepad_input()
            pygame.display.set_mode((1, 1), pygame.HIDDEN)
            for index in range(controller.get_count()):
                self.connect_controller(index)
            self.ui.update(**self.view())
            self.ui.log("Xbox Arm Controller is online")
            next_ui_refresh = 0.0
            async with asyncio.TaskGroup() as tasks:
                workers.extend(
                    [
                        tasks.create_task(
                            run_app_task(self.receive_commands, "Gamepad commands", task_failed)
                        ),
                        tasks.create_task(
                            run_app_task(self.receive_arm_status, "Gamepad arm status", task_failed)
                        ),
                        tasks.create_task(
                            run_app_task(
                                self.receive_arm_telemetry, "Gamepad telemetry", task_failed
                            )
                        ),
                        tasks.create_task(
                            run_app_task(
                                lambda: publish_heartbeats(
                                    self.heartbeat_writer,
                                    Device.Heartbeat(device=Device.DeviceType.ARM_CONTROLLER),
                                    heartbeat_stop,
                                ),
                                "Gamepad heartbeat",
                                task_failed,
                            ),
                        ),
                    ]
                )
                try:
                    while self.running:
                        now = time.monotonic()
                        self.process_events()
                        self.rates, self.active_inputs = self.read_controls()
                        if self.status == Device.DeviceStatuses.ON:
                            self.publish_rates(self.rates)
                        if now >= next_ui_refresh:
                            self.ui.update(**self.view())
                            next_ui_refresh = now + 0.2
                        await asyncio.sleep(CONTROL_PERIOD_SECONDS)
                except Exception as error:
                    self.failed = True
                    log_failure("Gamepad input", error)
                finally:
                    heartbeat_stop.set()
                    for task in workers:
                        task.cancel()
        except Exception as error:
            self.failed = True
            log_failure("Gamepad", error)
        finally:
            heartbeat_stop.set()
            try:
                if enabled:
                    self.stop_motion()
                    self.status = Device.DeviceStatuses.OFF
                    self.write_status(self.status)
            except Exception as error:
                self.failed = True
                log_failure("Gamepad final DDS write", error)
            finally:
                try:
                    if self.gamepad is not None:
                        self.gamepad.quit()
                except Exception as error:
                    self.failed = True
                    log_failure("Gamepad device close", error)
                finally:
                    try:
                        pygame.quit()
                    except Exception as error:
                        self.failed = True
                        log_failure("Gamepad SDL shutdown", error)
                    finally:
                        try:
                            self.participant.close()
                        except Exception as error:
                            self.failed = True
                            log_failure("Gamepad participant close", error)
            if self.failed:
                try:
                    await app.stop()
                except Exception as error:
                    log_failure("Gamepad UI shutdown", error)
            print("Xbox Arm Controller stopped", flush=True)


def configure_ui(app):
    return DemoUiState(
        app,
        kind="gamepad-controller",
        title="Xbox Arm Controller",
        description="Controller input is translated into RTI Connext DDS teleoperation.",
    )


def main() -> int:
    application = None
    result = 1
    try:
        app = create_demo_ui("Xbox Arm Controller")
        ui = configure_ui(app)
        application = ArmControllerGamepadApp(ui)
        run_demo_ui(app, application.run)
        result = int(application.failed)
    except Exception as error:
        log_failure("Gamepad setup or UI", error)
    finally:
        if application is not None:
            try:
                if not application.participant.closed:
                    application.participant.close()
            except Exception as error:
                log_failure("Gamepad participant close", error)
                result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
