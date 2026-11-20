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
    def __init__(self, ui, scene, model) -> None:
        entities = DdsEntities.Constants
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
        self.arm_status_writer = dds.DataWriter(
            self.participant.find_datawriter(entities.ARM_STATUS_DW)
        )
        self.telemetry_writer = dds.DataWriter(
            self.participant.find_datawriter(entities.ARM_TELEMETRY_DW)
        )
        self.command_reader = dds.DataReader(
            self.participant.find_datareader(entities.DEVICE_COMMAND_DR)
        )
        self.status_sample = Device.Status(
            device=Device.DeviceType.ARM,
            status=Device.DeviceStatuses.ON,
        )
        self._last_published_readiness = None
        self._last_diagnostic_at = {}
        self.failed = False
        self.ui = ui
        self.status = Device.DeviceStatuses.ON
        self.model = model
        self.readiness = "NOT_READY"
        self.controller_connected = False
        self.telemetry_sequence = 0
        self.scene = scene

    def apply_command(self, command: Device.DeviceCommands) -> None:
        self.status = device_status_after_command(command)
        self.readiness = "NOT_READY"

    def view(self) -> dict:
        controller_status = "CONTROLLER CONNECTED" if self.controller_connected else "NO CONTROLLER"
        actual = self.model.view()
        return {
            "kind": "arm",
            "device_status": self.status.name,
            "title": "Surgical Arm Monitor",
            "status": self.status.name,
            "header_badges": [
                {
                    "label": "Controller",
                    "value": controller_status,
                    "tone": "good" if self.controller_connected else "muted",
                },
                {"label": "Arm readiness", "value": self.readiness},
            ],
            "footer": True,
            "arm": actual,
            "feedback": {
                "source": "reported",
                "publication_sequence": self.telemetry_sequence,
                "readiness": self.readiness,
                "status_known": True,
                "position": actual["position"],
                "orientation": actual["orientation"],
                "opening_width": actual["opening_width"],
            },
        }

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

        async def simulate() -> None:
            loop = asyncio.get_running_loop()
            previous = loop.time()
            next_telemetry = previous
            last_condition = None
            while self.status != Device.DeviceStatuses.OFF:
                now = loop.time()
                dt = min(now - previous, CONTROL_PERIOD * 2)
                previous = now
                linear, angular, opening_rate, valid = self.rates()
                if self.status != Device.DeviceStatuses.ON:
                    linear, angular, opening_rate, valid = _ZERO, _ZERO, 0.0, False
                self.readiness = (
                    "FAULT"
                    if self.status == Device.DeviceStatuses.ERROR
                    else "READY"
                    if valid
                    else "NOT_READY"
                )
                if self.status == Device.DeviceStatuses.ON:
                    try:
                        self.model.step(linear, angular, opening_rate, dt)
                    except (ArithmeticError, ValueError, ArmSimulationError) as exc:
                        self.status = Device.DeviceStatuses.ERROR
                        self.readiness = "FAULT"
                        self.write_status(self.status)
                        self.ui.log(f"Arm model fault; motion stopped: {exc}", "error")
                condition = self.model.last_error
                if condition and condition != last_condition:
                    self.ui.log(condition, "warn")
                last_condition = condition
                self.write_readiness(self.readiness)
                if now >= next_telemetry:
                    self.write_telemetry()
                    self.telemetry_sequence += 1
                    update_arm_scene(self.scene, self.model)
                    self.controller_connected = (
                        self.teleop_reader.subscription_matched_status.current_count > 0
                    )
                    self.ui.update(**self.view())
                    next_telemetry = now + TELEMETRY_PERIOD
                await asyncio.sleep(max(0.0, CONTROL_PERIOD - (loop.time() - now)))

        async def receive_commands() -> None:
            async for sample in self.command_reader.take_data_async():
                command = sample.command
                self.apply_command(command)
                self.clear_commands()
                self.write_status(self.status)
                self.write_readiness(self.readiness)
                self.ui.log(f"Received {command.name} command from Orchestrator")
                self.ui.update(**self.view())
                if self.status == Device.DeviceStatuses.OFF:
                    heartbeat_stop.set()
                    await app.stop()
                    for task in workers:
                        if task is not asyncio.current_task():
                            task.cancel()
                    return

        async def monitor_control_health() -> None:
            while self.status != Device.DeviceStatuses.OFF:
                for name, reader in (
                    ("Arm", self.teleop_reader),
                    ("Jaw", self.tool_reader),
                ):
                    if reader.requested_deadline_missed_status.total_count_change:
                        self._diagnostic(f"{name} command deadline missed (diagnostic only)")
                    if reader.liveliness_changed_status.not_alive_count_change > 0:
                        self._diagnostic(f"{name} command writer lost liveliness")
                await asyncio.sleep(0.1)

        try:
            self.participant.enable()
            self.ui.update(dds_security=participant_security_enabled(self.participant))
            self.status_writer.write(self.status_sample)
            enabled = True
            self.ui.update(**self.view())
            self.write_readiness(self.readiness)
            self.ui.log("Arm is online")
            async with asyncio.TaskGroup() as tasks:
                workers.append(
                    tasks.create_task(run_app_task(simulate, "Arm simulation", task_failed))
                )
                workers.append(
                    tasks.create_task(run_app_task(receive_commands, "Arm commands", task_failed))
                )
                workers.append(
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
                    )
                )
                workers.append(
                    tasks.create_task(
                        run_app_task(monitor_control_health, "Arm health", task_failed)
                    )
                )
        except Exception as error:
            self.failed = True
            log_failure("Arm", error)
        finally:
            heartbeat_stop.set()
            try:
                if enabled:
                    if self.status != Device.DeviceStatuses.OFF:
                        self.write_status(Device.DeviceStatuses.OFF)
                    self.write_readiness("NOT_READY")
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

    def clear_commands(self) -> None:
        self.teleop_reader.take()
        self.tool_reader.take()

    def _command(self, reader):
        state = dds.DataState(dds.InstanceState.ALIVE)
        for sample in reader.select().state(state).read():
            if sample.info.valid and sample.data.arm_id == ARM_ID:
                return sample.data
        return None

    @staticmethod
    def _vector(value, limit: float) -> tuple[float, float, float]:
        result = (value.x, value.y, value.z)
        if not all(math.isfinite(component) for component in result):
            raise ValueError("Non-finite arm velocity")
        if math.hypot(*result) > limit + 1e-12:
            raise ValueError(f"Arm velocity exceeds demo limit {limit}")
        return result

    def rates(self):
        arm = self._command(self.teleop_reader)
        tool = self._command(self.tool_reader)
        if arm is None:
            return _ZERO, _ZERO, 0.0, False
        try:
            linear = self._vector(arm.linear_velocity, MAX_LINEAR_SPEED)
            angular = self._vector(arm.angular_velocity, MAX_ANGULAR_SPEED)
        except ValueError as exc:
            self._diagnostic(str(exc))
            return _ZERO, _ZERO, 0.0, False
        opening_rate = 0.0
        if tool is not None:
            if not math.isfinite(tool.opening_rate) or abs(tool.opening_rate) > MAX_OPENING_RATE:
                self._diagnostic("Invalid jaw opening rate")
            else:
                opening_rate = tool.opening_rate
        return linear, angular, opening_rate, True

    def _diagnostic(self, message: str) -> None:
        now = asyncio.get_running_loop().time()
        if now - self._last_diagnostic_at.get(message, -math.inf) >= 1.0:
            self.ui.log(message, "warn")
            self._last_diagnostic_at[message] = now

    def write_readiness(self, readiness: str) -> None:
        if readiness != self._last_published_readiness:
            self.arm_status_writer.write(
                Robot.Arm.Status(
                    arm_id=ARM_ID,
                    readiness=getattr(Robot.Arm.Readiness, readiness),
                )
            )
            self._last_published_readiness = readiness

    def write_telemetry(self) -> None:
        pose = self.model.pose
        self.telemetry_writer.write(
            Robot.Arm.Telemetry(
                arm_id=ARM_ID,
                tcp_pose=Geometry.Pose(
                    position=Geometry.Vector3(*pose["position"]),
                    orientation=Geometry.Quaternion(*pose["orientation"]),
                ),
                parallel_jaw=Robot.Tool.ParallelJawState(opening_width=self.model.opening_width),
            )
        )

    def write_status(self, status: Device.DeviceStatuses) -> None:
        self.status_sample.status = status
        self.status_writer.write(self.status_sample)


def configure_ui(app, model):
    ui = DemoUiState(
        app,
        kind="arm",
        title="Surgical Arm Monitor",
        description="DDS-driven simulated surgical manipulator and teleoperation status.",
    )
    return ui, add_arm_scene(app, model)


def main() -> int:
    application = None
    result = 1
    try:
        app = create_demo_ui("Surgical Arm Monitor")
        model = ArmModel()
        ui, scene = configure_ui(app, model)
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
