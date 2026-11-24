#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""DDS and application state for the simulated surgical arm."""

from __future__ import annotations

import asyncio
import math

import rti.asyncio  # noqa: F401 - installs Connext's asyncio integration
import rti.connextdds as dds
from ArmCommand import clamp_vector
from ArmKinematics import (
    MAX_ANGULAR_SPEED,
    MAX_LINEAR_SPEED,
    MAX_OPENING_RATE,
    ArmModel,
    ArmSimulationError,
)
from DemoUiSupport import (
    DemoUiState,
    create_demo_ui,
    log_failure,
    participant_security_enabled,
    run_app_task,
    run_demo_ui,
)
from HeartbeatPresence import publish_heartbeats
from MedTech import DdsEntities, Device, Geometry, Robot
from MedTechTypes import device_status_after_command, register_type
from PhysicalMotionGate import MotionConditions, PhysicalMotionGate
from rti_demo_ui import CommandConfirmation

TITLE = "Surgical Arm Monitor"
BACKEND_LABEL = None
ARM_ID = "arm-1"
CONTROL_PERIOD = 0.02
TELEMETRY_PERIOD = 0.05
_ZERO = (0.0, 0.0, 0.0)
ARM_SCENE_MODEL_URL = "/models/articulated-arm.glb"
ARM_SCENE_CAMERA = {
    "mode": "orbit",
    "position": [0.72, 0.62, 0.82],
    "target": [0.0, 0.25, 0.0],
    "min_distance": 0.25,
    "max_distance": 4.0,
}


def add_arm_scene(app, model):
    scene = app.add_card("Articulated surgical arm").add_scene_3d(
        ARM_SCENE_MODEL_URL, camera=ARM_SCENE_CAMERA, background="#0a0e17", grid=False
    )
    for node_id, transform in model.node_transforms.items():
        scene.add_node(
            node_id,
            transform["path"],
            position=transform["position"],
            rotation=transform["rotation"],
            status="success" if model.reachable else "warning",
        )
    return scene


def update_arm_scene(scene, model) -> None:
    status = "success" if model.reachable else "warning"
    scene.apply_node_batch(
        [
            {
                "op": "update",
                "id": node_id,
                "position": transform["position"],
                "rotation": transform["rotation"],
                "status": status,
            }
            for node_id, transform in model.node_transforms.items()
        ]
    )


class ArmApp:
    def __init__(
        self,
        ui,
        scene,
        model,
        *,
        motion_gate: PhysicalMotionGate | None = None,
    ) -> None:
        entities = DdsEntities.Constants
        for data_type in (
            Device.Status,
            Device.Heartbeat,
            Device.Command,
            Robot.Arm.TeleopControl,
            Robot.Tool.ParallelJawControl,
            Robot.Arm.Telemetry,
        ):
            register_type(data_type)
        provider = dds.QosProvider.default
        self.participant = provider.create_participant_from_config(entities.ARM_DP)
        self.status_writer = dds.DataWriter(self.participant.find_datawriter(entities.STATUS_DW))
        self.heartbeat_writer = dds.DataWriter(self.participant.find_datawriter(entities.HB_DW))
        self.teleop_reader = dds.DataReader(
            self.participant.find_datareader(entities.TELEOP_CONTROL_DR)
        )
        self.tool_reader = dds.DataReader(
            self.participant.find_datareader(entities.TOOL_CONTROL_DR)
        )
        self.telemetry_writer = dds.DataWriter(
            self.participant.find_datawriter(entities.ARM_TELEMETRY_DW)
        )
        self.command_reader = dds.DataReader(
            self.participant.find_datareader(entities.DEVICE_COMMAND_DR)
        )
        self.status_sample = Device.Status(
            device=Device.DeviceType.ARM,
            status=Device.DeviceStatusKind.ON,
        )
        self._last_published_readiness = None
        self._last_diagnostic_at = {}
        self.failed = False
        self.ui = ui
        self.title = TITLE
        self.backend_label = BACKEND_LABEL
        self.status = Device.DeviceStatusKind.ON
        self.motion_gate = motion_gate
        self.readiness = Device.DeviceReadinessKind.NOT_READY
        self.telemetry_sequence = 0
        self.commands_fresh = False
        self.command_rates_neutral = False
        self._control_wake = asyncio.Event()
        self.model = model
        self.scene = scene
        self.controller_connected = False
        if self.motion_gate is not None:
            self.ui.app.register_command(
                "rearm-motion",
                {"type": "object", "additionalProperties": False},
                self.request_motion_rearm,
                confirmation=CommandConfirmation(
                    title="Re-arm software motion gate?",
                    message=(
                        "This only changes the demo software gate; it does not establish "
                        "physical safety. Confirm the approved supervised procedure before "
                        "any physical motion."
                    ),
                ),
            )

    def apply_command(self, command: Device.DeviceCommandKind) -> None:
        self.status = device_status_after_command(command)
        self.readiness = Device.DeviceReadinessKind.NOT_READY
        if self.motion_gate is not None:
            self.motion_gate.disarm()
        if command in (Device.DeviceCommandKind.PAUSE, Device.DeviceCommandKind.SHUTDOWN):
            self.teleop_reader.take()
            self.tool_reader.take()

    def view(self) -> dict:
        controller_connected = self.controller_connected
        controller_status = "CONTROLLER CONNECTED" if controller_connected else "NO CONTROLLER"
        actual = self.model.view()
        header_badges = []
        if self.backend_label is not None:
            header_badges.append(
                {"label": "Arm backend", "value": self.backend_label, "tone": "muted"}
            )
        header_badges.extend(
            [
                {
                    "label": "Controller",
                    "value": controller_status,
                    "tone": "good" if controller_connected else "muted",
                },
                {
                    "label": "Arm readiness",
                    "value": self.readiness.name,
                    "tone": "good"
                    if self.readiness == Device.DeviceReadinessKind.READY
                    else "warn",
                },
            ]
        )
        control_groups = []
        if self.motion_gate is not None:
            gate_value = "ARMED" if self.motion_gate.armed else "DISARMED"
            header_badges.append(
                {
                    "label": "Software motion gate",
                    "value": gate_value,
                    "tone": "good" if self.motion_gate.armed else "warn",
                }
            )
            control_groups.append(
                {
                    "title": "MOTION PERMISSION",
                    "layout": "motion-gate",
                    "controls": [
                        {
                            "type": "button",
                            "label": "MOTION ARMED" if self.motion_gate.armed else "RE-ARM MOTION",
                            "command": "rearm-motion",
                            "payload": {},
                            "disabled": not self.motion_gate.can_rearm,
                            "className": "run-demo",
                        }
                    ],
                }
            )
        return {
            "kind": "arm",
            "device_status": self.status.name,
            "title": self.title,
            "backend_label": self.backend_label,
            "status": self.status.name,
            "header_badges": header_badges,
            "control_groups": control_groups,
            "footer": True,
            "arm": actual,
            "feedback": {
                "source": "reported",
                "publication_sequence": self.telemetry_sequence,
                "readiness": self.readiness.name,
                "status_known": True,
                "position": actual["position"],
                "orientation": actual["orientation"],
                "opening_width": actual["opening_width"],
            },
        }

    def request_motion_rearm(self, _payload: dict) -> dict[str, bool]:
        if self.motion_gate is None:
            return {"armed": False}
        self.rates()
        self.update_motion_gate(
            connected=getattr(self.model, "connected", True),
            healthy=getattr(self.model, "healthy", True),
        )
        armed = self.motion_gate.rearm()
        self.ui.log(
            "Software motion gate armed by operator"
            if armed
            else "Re-arm rejected; require a ready arm and fresh neutral commands",
            "ok" if armed else "warn",
        )
        self.ui.update(**self.view())
        return {"armed": armed}

    def update_motion_gate(self, *, connected: bool, healthy: bool) -> None:
        if self.motion_gate is None:
            return
        self.motion_gate.update(
            MotionConditions(
                arm_connected=connected,
                arm_healthy=healthy and self.status == Device.DeviceStatusKind.ON,
                command_fresh=self.commands_fresh,
                controls_neutral=self.command_rates_neutral,
            )
        )

    def _controller_writers_match(self) -> bool:
        arm_writers = self.teleop_reader.subscription_matched_status.current_count
        return arm_writers > 0

    def _control_deadline_missed(self, name, reader) -> None:
        if self.motion_gate is None:
            reader.take()
        else:
            self.motion_gate.disarm()
            self.teleop_reader.take()
            self.tool_reader.take()
        self.commands_fresh = False
        self.command_rates_neutral = False
        self._diagnostic(f"{name} command deadline missed; cached commands discarded")
        self._control_wake.set()

    async def monitor_control_health(self) -> None:
        waitset = dds.WaitSet()
        stop = dds.GuardCondition()
        waitset.attach_condition(stop)
        conditions = []
        for name, reader in (("Arm", self.teleop_reader), ("Jaw", self.tool_reader)):
            condition = dds.StatusCondition(reader)
            condition.enabled_statuses = dds.StatusMask.REQUESTED_DEADLINE_MISSED
            waitset.attach_condition(condition)
            conditions.append((condition, reader, name))
        try:
            while True:
                wait = asyncio.ensure_future(waitset.wait_async())
                try:
                    triggered = await asyncio.shield(wait)
                except asyncio.CancelledError:
                    stop.trigger_value = True
                    while not wait.done():
                        try:
                            await asyncio.shield(wait)
                        except asyncio.CancelledError:
                            continue
                    await wait
                    raise
                for condition, reader, name in conditions:
                    if (
                        condition in triggered
                        and reader.requested_deadline_missed_status.total_count_change
                    ):
                        self._control_deadline_missed(name, reader)
        finally:
            waitset.detach_all()

    async def run(self, app) -> None:
        heartbeat_stop = asyncio.Event()
        workers = []
        enabled = False

        async def task_failed() -> None:
            self.failed = True
            heartbeat_stop.set()
            for task in workers:
                if task is not asyncio.current_task():
                    task.cancel()
            await app.stop()

        async def control_and_observe() -> None:
            loop = asyncio.get_running_loop()
            now = loop.time()
            previous = now
            next_telemetry = now
            last_condition = None
            while self.status != Device.DeviceStatusKind.OFF:
                now = loop.time()
                dt = min(now - previous, CONTROL_PERIOD * 2)
                previous = now
                linear, angular, opening_rate, valid = self.rates()
                connected = getattr(self.model, "connected", True)
                healthy = getattr(self.model, "healthy", True)
                motion_permitted = True
                if self.motion_gate is not None:
                    self.update_motion_gate(connected=connected, healthy=healthy)
                    motion_permitted = self.motion_gate.armed
                if self.status != Device.DeviceStatusKind.ON or not connected or not healthy:
                    linear, angular, opening_rate, valid = _ZERO, _ZERO, 0.0, False
                if not motion_permitted:
                    linear, angular, opening_rate, valid = _ZERO, _ZERO, 0.0, False
                self.readiness = (
                    Device.DeviceReadinessKind.FAULTED
                    if self.status == Device.DeviceStatusKind.ERROR or not healthy
                    else Device.DeviceReadinessKind.READY
                    if valid and connected and motion_permitted
                    else Device.DeviceReadinessKind.NOT_READY
                )
                if (
                    self.status == Device.DeviceStatusKind.ON
                    and connected
                    and healthy
                    and motion_permitted
                ):
                    try:
                        self.model.step(linear, angular, opening_rate, dt)
                    except (ArithmeticError, ValueError, ArmSimulationError) as exc:
                        self.status = Device.DeviceStatusKind.ERROR
                        self.readiness = Device.DeviceReadinessKind.FAULTED
                        self.write_status(self.status)
                        self.ui.log(f"Arm model fault; motion stopped: {exc}", "error")
                condition = self.model.last_error
                if condition and condition != last_condition:
                    self.ui.log(condition, "warn")
                last_condition = condition
                self.write_readiness(self.readiness)
                if now >= next_telemetry:
                    if connected:
                        self.write_telemetry()
                        self.telemetry_sequence += 1
                        update_arm_scene(self.scene, self.model)
                    self.controller_connected = self._controller_writers_match()
                    self.ui.update(**self.view())
                    next_telemetry = now + TELEMETRY_PERIOD
                try:
                    await asyncio.wait_for(
                        self._control_wake.wait(),
                        timeout=max(0.0, CONTROL_PERIOD - (loop.time() - now)),
                    )
                except TimeoutError:
                    pass
                self._control_wake.clear()

        async def receive_commands() -> None:
            async for sample in self.command_reader.take_data_async():
                command = sample.command
                self.apply_command(command)
                self.write_status(self.status)
                self.write_readiness(self.readiness)
                self.ui.log(f"Received {command.name} command from Orchestrator")
                self.ui.update(**self.view())
                if self.status == Device.DeviceStatusKind.OFF:
                    heartbeat_stop.set()
                    await app.stop()
                    for task in workers:
                        if task is not asyncio.current_task():
                            task.cancel()
                    return

        try:
            self.participant.enable()
            enabled = True
            self.ui.update(dds_security=participant_security_enabled(self.participant))
            self.write_status(self.status)
            self.ui.update(**self.view())
            self.write_readiness(self.readiness)
            self.ui.log("Arm is online")
            async with asyncio.TaskGroup() as tasks:
                workers.extend(
                    [
                        tasks.create_task(
                            run_app_task(control_and_observe, "Arm simulation", task_failed)
                        ),
                        tasks.create_task(
                            run_app_task(receive_commands, "Arm commands", task_failed)
                        ),
                        tasks.create_task(
                            run_app_task(
                                lambda: publish_heartbeats(
                                    self.heartbeat_writer,
                                    Device.Heartbeat(device=Device.DeviceType.ARM),
                                    heartbeat_stop,
                                ),
                                "Arm heartbeat",
                                task_failed,
                            )
                        ),
                        tasks.create_task(
                            run_app_task(self.monitor_control_health, "Arm health", task_failed)
                        ),
                    ]
                )
        except Exception as error:
            self.failed = True
            log_failure("Arm", error)
        finally:
            heartbeat_stop.set()
            if getattr(self, "motion_gate", None) is not None:
                self.motion_gate.disarm()
            try:
                if enabled:
                    if self.status != Device.DeviceStatusKind.OFF:
                        self.write_status(Device.DeviceStatusKind.OFF)
                    if self.readiness != Device.DeviceReadinessKind.FAULTED:
                        self.write_readiness(Device.DeviceReadinessKind.NOT_READY)
            except Exception as error:
                self.failed = True
                log_failure("Arm final DDS write", error)
            finally:
                try:
                    self.participant.close()
                except Exception as error:
                    self.failed = True
                    log_failure("Arm participant close", error)
            if self.failed:
                try:
                    await app.stop()
                except Exception as error:
                    log_failure("Arm UI shutdown", error)
            print("Shutting down Arm", flush=True)

    def _command(self, reader):
        state = dds.DataState(dds.InstanceState.ALIVE)
        for sample in reader.select().state(state).read():
            if sample.info.valid and sample.data.arm_id == ARM_ID:
                return sample.data
        return None

    def _vector(self, value, limit: float) -> tuple[float, float, float]:
        result = (value.x, value.y, value.z)
        bounded = clamp_vector(result, limit)
        if bounded != result:
            self._diagnostic(f"Arm velocity clamped to demo limit {limit}")
        return bounded

    def rates(self):
        arm = self._command(self.teleop_reader)
        tool = self._command(self.tool_reader)
        self.commands_fresh = arm is not None and tool is not None
        self.command_rates_neutral = False
        if arm is None:
            return _ZERO, _ZERO, 0.0, False
        try:
            linear = self._vector(arm.linear_velocity, MAX_LINEAR_SPEED)
            angular = self._vector(arm.angular_velocity, MAX_ANGULAR_SPEED)
        except ValueError as exc:
            self.commands_fresh = False
            self._diagnostic(str(exc))
            return _ZERO, _ZERO, 0.0, False
        opening_rate = 0.0
        tool_valid = tool is not None
        if tool is not None:
            if not math.isfinite(tool.opening_rate) or abs(tool.opening_rate) > MAX_OPENING_RATE:
                self._diagnostic("Invalid jaw opening rate")
                tool_valid = False
            else:
                opening_rate = tool.opening_rate
        self.commands_fresh = self.commands_fresh and tool_valid
        self.command_rates_neutral = (
            self.commands_fresh
            and all(component == 0.0 for component in (*linear, *angular))
            and opening_rate == 0.0
        )
        return linear, angular, opening_rate, True

    def _diagnostic(self, message: str) -> None:
        now = asyncio.get_running_loop().time()
        if now - self._last_diagnostic_at.get(message, -math.inf) >= 1.0:
            self.ui.log(message, "warn")
            self._last_diagnostic_at[message] = now

    def write_readiness(self, readiness: Device.DeviceReadinessKind) -> None:
        if readiness != self._last_published_readiness:
            self.status_sample.readiness = readiness
            self.status_writer.write(self.status_sample)
            self._last_published_readiness = readiness

    def write_telemetry(self) -> None:
        pose = self.model.pose
        position, orientation = pose["position"], pose["orientation"]
        self.telemetry_writer.write(
            Robot.Arm.Telemetry(
                arm_id=ARM_ID,
                tcp_pose=Geometry.Pose(
                    position=Geometry.Vector3(*position),
                    orientation=Geometry.Quaternion(*orientation),
                ),
                parallel_jaw=Robot.Tool.ParallelJawState(opening_width=self.model.opening_width),
            )
        )

    def write_status(self, status: Device.DeviceStatusKind) -> None:
        self.status_sample.status = status
        self.status_sample.readiness = (
            Device.DeviceReadinessKind.NOT_READY
            if status == Device.DeviceStatusKind.OFF
            and self.readiness != Device.DeviceReadinessKind.FAULTED
            else self.readiness
        )
        self.status_writer.write(self.status_sample)
        self._last_published_readiness = self.status_sample.readiness


def configure_ui(app):
    return DemoUiState(
        app,
        kind="arm",
        title=TITLE,
        description="DDS-driven simulated surgical manipulator and teleoperation status.",
    )


def main() -> int:
    application = None
    result = 1
    try:
        app = create_demo_ui(TITLE)
        model = ArmModel()
        ui = configure_ui(app)
        scene = add_arm_scene(app, model)
        application = ArmApp(ui, scene, model)
        run_demo_ui(app, application.run)
        result = int(application.failed)
    except Exception as error:
        log_failure("Arm setup or UI", error)
    finally:
        if application is not None:
            try:
                if not application.participant.closed:
                    application.participant.close()
            except Exception as error:
                log_failure("Arm participant close", error)
                result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
