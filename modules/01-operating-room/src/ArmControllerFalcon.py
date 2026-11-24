#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Experimental deadman-held Falcon translation controller."""

from __future__ import annotations

import asyncio
import math
import os
import time
from typing import Any

import rti.asyncio  # noqa: F401 - installs Connext's asyncio integration
import rti.connextdds as dds
from ArmControllerDemo import ArmControllerDemo
from DemoUiSupport import (
    DemoUiState,
    create_demo_ui,
    log_failure,
    participant_security_enabled,
    run_app_task,
    run_demo_ui,
)
from FalconInput import INPUT_TIMEOUT_SECONDS, FalconInput
from HeartbeatPresence import publish_heartbeats
from MedTech import DdsEntities, Device, Geometry, Robot
from MedTechTypes import device_status_after_command, register_type

TITLE = "Novint Falcon Controller"
ARM_ID = "arm-1"
CONTROL_PERIOD_SECONDS = 0.02
INPUT_RETRY_SECONDS = 1.0
FEEDBACK_STALE_SECONDS = 0.5
MAX_LINEAR_SPEED = 0.05
MAX_ANGULAR_SPEED = 0.5
MAX_OPENING_RATE = 0.02
ZERO = (0.0, 0.0, 0.0)
DEADMAN = 0x01
MAX_SPEED = 0.01
MAX_ACCELERATION = 0.02
SMOOTHING = 0.35
CONTROL_GAP = 0.25


def workspace_bound(name: str, default: tuple[float, float, float]) -> tuple[float, ...]:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        result = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise ValueError(f"{name} must contain three comma-separated finite numbers") from exc
    if len(result) != 3 or not all(math.isfinite(part) for part in result):
        raise ValueError(f"{name} must contain three comma-separated finite numbers")
    return result


def limit_vector(values: tuple[float, ...], limit: float) -> tuple[float, ...]:
    magnitude = math.hypot(*values)
    if not math.isfinite(magnitude):
        raise ValueError("Falcon control produced a non-finite velocity")
    return values if magnitude <= limit else tuple(value * limit / magnitude for value in values)


def _bounded_input(value: float, lower: float, upper: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        return 0.0
    return max(lower, min(upper, value))


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


class FalconRelativeControl:
    def __init__(self, lower: tuple[float, ...], upper: tuple[float, ...]) -> None:
        if (
            len(lower) != 3
            or len(upper) != 3
            or not all(math.isfinite(value) for value in (*lower, *upper))
            or any(lo >= hi for lo, hi in zip(lower, upper))
        ):
            raise ValueError("Falcon workspace bounds must be finite and ordered")
        self.lower, self.upper = lower, upper
        self.reset()

    def reset(self, reason: str = "Release button 1 before engaging") -> None:
        self.require_release = True
        self.reference = None
        self.previous = None
        self.velocity = ZERO
        self.smoothed = ZERO
        self.reason = reason

    def update(
        self,
        position: tuple[float, ...],
        buttons: int,
        arm_position: tuple[float, ...] | None,
        ready: bool,
        now: float,
    ) -> tuple[float, ...]:
        if (
            not ready
            or arm_position is None
            or len(position) != 3
            or len(arm_position) != 3
            or not all(math.isfinite(value) for value in (*position, *arm_position, now))
            or buttons < 0
        ):
            self.reset("Waiting for fresh, ready arm feedback")
            return ZERO
        if self.previous is not None and not 0 < now - self.previous <= CONTROL_GAP:
            self.reset("Control loop interrupted; release button 1")
            return ZERO
        pressed = bool(buttons & DEADMAN)
        if self.require_release:
            if not pressed:
                self.require_release = False
                self.reason = "Hold button 1 to capture a reference"
            return ZERO
        if not pressed:
            self.reference = None
            self.previous = None
            self.velocity = self.smoothed = ZERO
            self.reason = "Hold button 1 to capture a reference"
            return ZERO
        if self.reference is None:
            if not all(
                lo <= value <= hi for value, lo, hi in zip(arm_position, self.lower, self.upper)
            ):
                self.reset("Arm position is outside the configured target workspace")
                return ZERO
            self.reference = (position, arm_position)
            self.previous = now
            self.reason = "Translation active"
            return ZERO
        assert self.previous is not None
        falcon_origin, arm_origin = self.reference
        target = tuple(
            min(hi, max(lo, origin + value - start))
            for value, start, origin, lo, hi in zip(
                position, falcon_origin, arm_origin, self.lower, self.upper
            )
        )
        desired = limit_vector(tuple(target[i] - arm_position[i] for i in range(3)), MAX_SPEED)
        self.smoothed = tuple(
            SMOOTHING * desired[i] + (1 - SMOOTHING) * self.smoothed[i] for i in range(3)
        )
        delta = limit_vector(
            tuple(self.smoothed[i] - self.velocity[i] for i in range(3)),
            MAX_ACCELERATION * (now - self.previous),
        )
        self.velocity = tuple(self.velocity[i] + delta[i] for i in range(3))
        self.previous = now
        return self.velocity


def _vector_view(vector) -> dict[str, float]:
    return {axis: round(float(getattr(vector, axis)), 4) for axis in ("x", "y", "z")}


class ArmControllerFalconApp:
    title = TITLE
    kind = "gamepad-controller"
    app_label = TITLE
    input_label = "Falcon"

    def __init__(self, ui: DemoUiState, device=None) -> None:
        self.control = FalconRelativeControl(
            workspace_bound("FALCON_WORKSPACE_MIN", (-0.25, -0.25, 0.10)),
            workspace_bound("FALCON_WORKSPACE_MAX", (0.25, 0.25, 0.60)),
        )
        for data_type in (
            Device.Status,
            Device.Heartbeat,
            Device.Command,
            Robot.Arm.TeleopControl,
            Robot.Tool.ParallelJawControl,
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
            self.participant.find_datareader(entities.STATUS_DR)
        )
        self.arm_telemetry_reader = dds.DataReader(
            self.participant.find_datareader(entities.ARM_TELEMETRY_DR)
        )
        self.status_sample = Device.Status(
            device=Device.DeviceType.ARM_CONTROLLER,
            status=Device.DeviceStatusKind.ON,
        )
        self.failed = False
        self.ui = ui
        self.status = Device.DeviceStatusKind.ON
        self.input_device = device or FalconInput()
        self.input_name = "Novint Falcon · TRANSLATION"
        self.rates = self.zero_rates()
        self.active_inputs: dict[str, bool] = {"POSITION": False, "BUTTONS": False}
        self.last_input: tuple[tuple[float, float, float], int] | None = None
        self.last_arm_readiness = "NOT_READY"
        self.has_arm_status = False
        self._arm_status_handle = None
        self._published_readiness = None
        self.last_telemetry: dict | None = None
        self.last_telemetry_time: float | None = None
        self.demo_position = None
        self.demo_jaw = None
        self.demo = ArmControllerDemo()
        self.running = True
        self.next_input_attempt_at = 0.0
        self.ui.app.register_command(
            "start-demo",
            {"type": "object", "additionalProperties": False},
            self.start_demo,
        )
        self.ui.app.register_command(
            "stop-demo",
            {"type": "object", "additionalProperties": False},
            self.stop_demo,
        )
        self.ui.app.register_command(
            "home-falcon",
            {"type": "object", "additionalProperties": False},
            self.request_homing,
        )

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
        input_status, input_tone = self.input_status()
        input_descriptions = self._input_descriptions()
        homing_state = self.input_device.homing_state
        homing_instructions = {
            "NO DEVICE": "Connect a Falcon; the controller will retry automatically.",
            "CHECKING": "Checking Falcon homing status.",
            "WAITING": "Select HOME FALCON before manually homing the device.",
            "HOMING": "Move the Falcon handle fully out, then straight fully in.",
            "TIMED OUT": "Falcon homing timed out; select HOME FALCON to retry.",
        }
        return {
            "kind": self.kind,
            "device_status": self.status.name,
            "title": self.title,
            "status": self.status.name,
            "header_badges": [
                {
                    "label": self.input_label,
                    "value": input_status,
                    "tone": input_tone,
                },
                {
                    "label": "Arm readiness",
                    "value": readiness_badge,
                    "tone": "good"
                    if feedback["readiness"] == "READY" and self.has_arm_status
                    else "warn",
                },
                {
                    "label": "Demo",
                    "value": f"RUNNING · {self.demo.cycles} LOOPS" if self.demo.running else "IDLE",
                },
                *[
                    {
                        "label": label,
                        "value": "MATCHED" if matched else "NO MATCH",
                        "tone": "good" if matched else "muted",
                    }
                    for label, matched in (
                        (
                            "Arm command subscribers",
                            self.teleop_writer.publication_matched_status.current_count > 0,
                        ),
                        (
                            "Jaw command subscribers",
                            self.tool_writer.publication_matched_status.current_count > 0,
                        ),
                    )
                ],
            ],
            "input_connected": self.input_connected(),
            "input_label": self.input_label,
            "input_name": self.input_name,
            "demo": {"running": self.demo.running, "cycles": self.demo.cycles},
            "input_connection_text": (
                f"Falcon · {input_status}" if not self.input_connected() else None
            ),
            "control_groups": [
                {
                    "title": "FALCON HOMING",
                    "controls": [
                        {
                            "type": "button",
                            "label": "HOME FALCON",
                            "command": "home-falcon",
                            "payload": {},
                            "disabled": self.status != Device.DeviceStatusKind.ON
                            or homing_state not in ("WAITING", "TIMED OUT"),
                            "className": "run-demo",
                        }
                    ],
                },
                self.demo.controls(
                    self.status == Device.DeviceStatusKind.ON
                    and self.input_connected()
                    and not any(self.active_inputs.values())
                    and self.demo_ready()
                ),
            ],
            "inputs": [
                {
                    "label": label,
                    "description": description,
                    "active": self.active_inputs[label],
                }
                for label, description in input_descriptions
            ],
            "footer": True,
            "feedback": feedback,
            "control_instruction": homing_instructions.get(
                homing_state, f"{self.control.reason}. Rotation and jaw are disabled."
            ),
        }

    def input_connected(self) -> bool:
        last_sample_at = self.input_device.last_sample_at
        return (
            self.input_device.opened
            and last_sample_at is not None
            and time.monotonic() - last_sample_at < INPUT_TIMEOUT_SECONDS
        )

    def input_status(self) -> tuple[str, str]:
        if self.input_connected():
            return "READY", "good"
        if self.input_device.homing_state == "TIMED OUT":
            return "ERROR · HOMING TIMEOUT", "danger"
        return {
            "NO DEVICE": "NO FALCON DETECTED",
            "CHECKING": "CHECKING",
            "WAITING": "WAITING FOR HOMING",
            "HOMING": "HOMING",
        }.get(self.input_device.homing_state, "WAITING"), "warn"

    def request_homing(self, _payload: dict) -> dict[str, bool]:
        started = self.status == Device.DeviceStatusKind.ON and self.input_device.start_homing()
        if started:
            self.stop_motion()
            self.control.reset("Homing Falcon")
        self.ui.log(
            "Falcon homing started; move the handle fully out, then straight fully in"
            if started
            else "Falcon homing request rejected",
            "warn",
        )
        self.ui.update(**self.view())
        return {"started": started}

    def _input_descriptions(self) -> tuple[tuple[str, str], ...]:
        if self.last_input is None:
            return (("POSITION", "Waiting for input"), ("BUTTONS", "Waiting for input"))
        position, buttons = self.last_input
        return (
            ("POSITION", f"X {position[0]:.4f}, Y {position[1]:.4f}, Z {position[2]:.4f} m"),
            ("BUTTONS", f"Bitfield: {buttons:#x} · button 1 is deadman"),
        )

    def set_status(self, status: Device.DeviceStatusKind) -> None:
        if self.status != status:
            self.stop_motion()
            self.control.reset()
            self.status = status
            self.write_status(status)
        self.ui.update(**self.view())

    def publish_rates(self, rates: dict) -> None:
        if self.status == Device.DeviceStatusKind.ON:
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

    def write_status(self, status: Device.DeviceStatusKind) -> None:
        self.status_sample.status = status
        self.status_sample.readiness = (
            Device.DeviceReadinessKind.FAULTED
            if self.failed
            else Device.DeviceReadinessKind.READY
            if status == Device.DeviceStatusKind.ON and self.input_connected()
            else Device.DeviceReadinessKind.NOT_READY
        )
        self.status_writer.write(self.status_sample)
        self._published_readiness = self.status_sample.readiness

    def stop_motion(self) -> None:
        self.demo.inhibit()
        self.rates = self.zero_rates()
        if self.status == Device.DeviceStatusKind.ON:
            self.publish_rates(self.rates)

    def demo_ready(self) -> bool:
        return self.demo.ready(
            self.demo_position,
            self.demo_jaw,
            self.last_telemetry_time,
            self.last_arm_readiness,
            time.monotonic(),
        )

    def start_demo(self, _payload: dict) -> dict[str, bool]:
        started = (
            self.status == Device.DeviceStatusKind.ON
            and self.input_connected()
            and not any(self.active_inputs.values())
            and not self.demo.running
            and self.demo_ready()
        )
        if started:
            self.demo.start(self.demo_position, self.demo_jaw, time.monotonic())
        self.ui.log(
            "Started feedback-anchored demo motion"
            if started
            else "Cannot start demo: require connected neutral input and fresh arm/jaw feedback",
            "ok" if started else "warn",
        )
        self.ui.update(**self.view())
        return {"started": started}

    def stop_demo(self, _payload: dict) -> dict[str, bool]:
        self.stop_motion()
        self.ui.log("Stopped all motion")
        self.ui.update(**self.view())
        return {"stopped": True}

    def demo_rates(self, manual_rates: dict, now: float) -> dict:
        rates, message = self.demo.select(
            manual_rates,
            any(self.active_inputs.values()),
            self.input_connected(),
            self.demo_ready(),
            self.demo_position,
            self.demo_jaw,
            now,
        )
        if message:
            self.ui.log(message, "warn" if rates is None else "info")
        return self.zero_rates() if rates is None else rates

    def read_controls(self) -> tuple[dict, dict[str, bool]]:
        sample = self.input_device.read()
        rates = self.zero_rates()
        if sample is None or self.status != Device.DeviceStatusKind.ON:
            self.control.reset("Waiting for Falcon input or controller START")
            return rates, dict.fromkeys(self.active_inputs, False)
        position, buttons = sample
        self.last_input = sample
        now = time.monotonic()
        telemetry = self.last_telemetry or {}
        pose = telemetry.get("tcp_pose")
        arm_position = None if pose is None else pose.get("position")
        arm_xyz = None if arm_position is None else tuple(arm_position[axis] for axis in "xyz")
        telemetry_matched = self.arm_telemetry_reader.subscription_matched_status.current_count == 1
        if not telemetry_matched:
            self.last_telemetry = None
            self.last_telemetry_time = None
        ready = (
            self.has_arm_status
            and self.last_arm_readiness == "READY"
            and telemetry_matched
            and self.last_telemetry_time is not None
            and 0 <= now - self.last_telemetry_time <= FEEDBACK_STALE_SECONDS
        )
        velocity = self.control.update(position, buttons, arm_xyz, ready, now)
        rates["linear_velocity"] = dict(zip("xyz", velocity))
        return rates, {"POSITION": any(velocity), "BUTTONS": bool(buttons & DEADMAN)}

    def initialize_input(self) -> None:
        if not self.input_device.open():
            self.ui.log("No Falcon detected; waiting for a device", "warn")
            self.next_input_attempt_at = time.monotonic() + INPUT_RETRY_SECONDS
        self.ui.log("Falcon translation: release then hold button 1; no jaw or rotation", "warn")
        self.ui.log(f"Falcon target workspace: {self.control.lower} to {self.control.upper}")

    def close_controller(self) -> None:
        self.input_device.close()

    async def receive_commands(self) -> None:
        async for sample in self.command_reader.take_data_async():
            command = sample.command
            status = device_status_after_command(command)
            if command == Device.DeviceCommandKind.PAUSE:
                self.rates = self.zero_rates()
                self.set_status(status)
                self.ui.log("Arm Controller paused by Orchestrator", "warn")
            elif command == Device.DeviceCommandKind.START:
                if self.status == Device.DeviceStatusKind.ON:
                    self.stop_motion()
                    self.control.reset()
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
        async for status, info in self.arm_status_reader.take_async():
            if info.valid:
                if status.device != Device.DeviceType.ARM:
                    continue
                self._arm_status_handle = info.instance_handle
                self.last_arm_readiness = status.readiness.name
                self.has_arm_status = info.state.instance_state == dds.InstanceState.ALIVE
            elif info.instance_handle != self._arm_status_handle:
                continue
            elif info.state.instance_state != dds.InstanceState.ALIVE:
                self.has_arm_status = False
            self.ui.update(**self.view())

    async def receive_arm_telemetry(self) -> None:
        async for sample in self.arm_telemetry_reader.take_data_async():
            telemetry = self._sample_data(sample)
            if getattr(telemetry, "arm_id", None) != ARM_ID:
                continue
            pose = getattr(telemetry, "tcp_pose", None)
            jaw = getattr(telemetry, "parallel_jaw", None)
            self.demo_position = (
                None
                if pose is None
                else tuple(float(getattr(pose.position, axis)) for axis in ("x", "y", "z"))
            )
            self.demo_jaw = None if jaw is None else float(jaw.opening_width)
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
            self.ui.update(dds_security=participant_security_enabled(self.participant))
            self.write_status(self.status)
            enabled = True
            self.initialize_input()
            self.ui.update(**self.view())
            self.ui.log(f"{self.app_label} is online")
            next_ui_refresh = 0.0
            async with asyncio.TaskGroup() as tasks:
                workers.extend(
                    [
                        tasks.create_task(
                            run_app_task(
                                self.receive_commands,
                                f"{self.app_label} commands",
                                task_failed,
                            )
                        ),
                        tasks.create_task(
                            run_app_task(
                                self.receive_arm_status,
                                f"{self.app_label} arm status",
                                task_failed,
                            )
                        ),
                        tasks.create_task(
                            run_app_task(
                                self.receive_arm_telemetry,
                                f"{self.app_label} telemetry",
                                task_failed,
                            )
                        ),
                        tasks.create_task(
                            run_app_task(
                                lambda: publish_heartbeats(
                                    self.heartbeat_writer,
                                    Device.Heartbeat(device=Device.DeviceType.ARM_CONTROLLER),
                                    heartbeat_stop,
                                ),
                                f"{self.app_label} heartbeat",
                                task_failed,
                            ),
                        ),
                    ]
                )
                try:
                    while self.running:
                        now = time.monotonic()
                        if not self.input_device.opened and now >= self.next_input_attempt_at:
                            self.next_input_attempt_at = now + INPUT_RETRY_SECONDS
                            if self.input_device.open():
                                self.ui.log("Falcon detected; checking homing status", "ok")
                        self.rates, self.active_inputs = self.read_controls()
                        self.rates = self.demo_rates(self.rates, now)
                        readiness = (
                            Device.DeviceReadinessKind.READY
                            if self.status == Device.DeviceStatusKind.ON and self.input_connected()
                            else Device.DeviceReadinessKind.NOT_READY
                        )
                        if readiness != self._published_readiness:
                            self.write_status(self.status)
                        if self.status == Device.DeviceStatusKind.ON:
                            self.publish_rates(self.rates)
                        if now >= next_ui_refresh:
                            self.ui.update(**self.view())
                            next_ui_refresh = now + 0.2
                        await asyncio.sleep(CONTROL_PERIOD_SECONDS)
                except Exception as error:
                    self.failed = True
                    log_failure(f"{self.app_label} input", error)
                finally:
                    heartbeat_stop.set()
                    for task in workers:
                        task.cancel()
        except Exception as error:
            self.failed = True
            log_failure(self.app_label, error)
        finally:
            heartbeat_stop.set()
            try:
                if enabled:
                    self.stop_motion()
                    self.status = Device.DeviceStatusKind.OFF
                    self.write_status(self.status)
            except Exception as error:
                self.failed = True
                log_failure(f"{self.app_label} final DDS write", error)
            finally:
                try:
                    self.close_controller()
                except Exception as error:
                    self.failed = True
                    log_failure(f"{self.app_label} device close", error)
                finally:
                    try:
                        self.participant.close()
                    except Exception as error:
                        self.failed = True
                        log_failure(f"{self.app_label} participant close", error)
            if self.failed:
                try:
                    await app.stop()
                except Exception as error:
                    log_failure(f"{self.app_label} UI shutdown", error)
            print(f"{self.app_label} stopped", flush=True)


def configure_ui(app):
    return DemoUiState(
        app,
        kind="gamepad-controller",
        title=TITLE,
        description="Experimental Falcon relative-translation control.",
    )


def main() -> int:
    application = None
    result = 1
    try:
        input_device = FalconInput()
        input_device.prepare()
        app = create_demo_ui(TITLE)
        ui = configure_ui(app)
        application = ArmControllerFalconApp(ui, device=input_device)
        run_demo_ui(app, application.run)
        result = int(application.failed)
    except Exception as error:
        log_failure("Falcon controller setup or UI", error)
    finally:
        if application is not None:
            try:
                if not application.participant.closed:
                    application.participant.close()
            except Exception as error:
                log_failure("Falcon controller participant close", error)
                result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
