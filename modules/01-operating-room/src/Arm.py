#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""DDS adapter and application state for the simulated surgical arm."""

from __future__ import annotations

import asyncio
import math

import rti.asyncio  # noqa: F401 - installs Connext's asyncio integration
import rti.connextdds as dds
from ApplicationLogic import device_status_after_command
from ArmKinematics import (
    MAX_ANGULAR_SPEED,
    MAX_LINEAR_SPEED,
    MAX_OPENING_RATE,
    ArmModel,
)
from DdsUtils import register_type
from DemoUiSupport import (
    DemoUiState,
    add_arm_scene,
    create_demo_ui,
    run_demo_ui,
    update_arm_scene,
)
from MedTech import DdsEntities, Device, Geometry, Robot

ARM_ID = "arm-1"
CONTROL_PERIOD = 0.02
TELEMETRY_PERIOD = 0.05
_ZERO = (0.0, 0.0, 0.0)


class ArmApplication:
    def __init__(self) -> None:
        self.status = "ON"
        self.model = ArmModel()
        self.readiness = "NOT_READY"
        self.controller_connected = False
        self.telemetry_sequence = 0

    def apply_command(self, command: str) -> None:
        self.status = device_status_after_command(command)
        self.readiness = "NOT_READY"

    def view(self) -> dict:
        controller_status = "CONTROLLER CONNECTED" if self.controller_connected else "NO CONTROLLER"
        actual = self.model.view()
        return {
            "kind": "arm",
            "title": "Surgical Arm Monitor",
            "status": self.status,
            "header_badges": [
                {
                    "label": "TeleopControl",
                    "value": controller_status,
                    "tone": "good" if self.controller_connected else "muted",
                },
                {"label": "Status", "value": self.status},
                {"label": "Control frame", "value": "BASE (+Z UP)"},
                {"label": "Arm", "value": self.readiness},
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


class ArmDdsAdapter:
    def __init__(self) -> None:
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
        self.status = Device.Status(
            device=Device.DeviceType.ARM,
            status=Device.DeviceStatuses.ON,
        )
        self.status_writer.write(self.status)
        self._readiness = None
        self._last_diagnostic = {}

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

    def rates(self, ui: DemoUiState):
        arm = self._command(self.teleop_reader)
        tool = self._command(self.tool_reader)
        if arm is None:
            return _ZERO, _ZERO, 0.0, False
        try:
            linear = self._vector(arm.linear_velocity, MAX_LINEAR_SPEED)
            angular = self._vector(arm.angular_velocity, MAX_ANGULAR_SPEED)
        except ValueError as exc:
            self._diagnostic(str(exc), ui)
            return _ZERO, _ZERO, 0.0, False
        opening_rate = 0.0
        if tool is not None:
            if not math.isfinite(tool.opening_rate) or abs(tool.opening_rate) > MAX_OPENING_RATE:
                self._diagnostic("Invalid jaw opening rate", ui)
            else:
                opening_rate = tool.opening_rate
        return linear, angular, opening_rate, True

    def _diagnostic(self, message: str, ui: DemoUiState) -> None:
        now = asyncio.get_running_loop().time()
        if now - self._last_diagnostic.get(message, -math.inf) >= 1.0:
            ui.log(message, "warn")
            self._last_diagnostic[message] = now

    def write_readiness(self, readiness: str) -> None:
        if readiness != self._readiness:
            self.arm_status_writer.write(
                Robot.Arm.Status(
                    arm_id=ARM_ID,
                    readiness=getattr(Robot.Arm.Readiness, readiness),
                )
            )
            self._readiness = readiness

    def write_telemetry(self, model: ArmModel) -> None:
        pose = model.pose
        self.telemetry_writer.write(
            Robot.Arm.Telemetry(
                arm_id=ARM_ID,
                tcp_pose=Geometry.Pose(
                    position=Geometry.Vector3(*pose["position"]),
                    orientation=Geometry.Quaternion(*pose["orientation"]),
                ),
                parallel_jaw=Robot.Tool.ParallelJawState(opening_width=model.opening_width),
            )
        )

    def write_status(self, status: str) -> None:
        self.status.status = getattr(Device.DeviceStatuses, status)
        self.status_writer.write(self.status)

    def write_heartbeat(self) -> None:
        self.heartbeat_writer.write(Device.Heartbeat(device=Device.DeviceType.ARM))

    def close(self) -> None:
        self.participant.close()


async def run_application(app) -> None:
    application = ArmApplication()
    ui = DemoUiState(
        app,
        kind="arm",
        title="Surgical Arm Monitor",
        description="DDS-driven simulated surgical manipulator and teleoperation status.",
    )
    adapter = ArmDdsAdapter()
    scene = add_arm_scene(app, application.model)
    ui.update(**application.view())
    adapter.write_readiness(application.readiness)
    ui.log("Arm is online")

    async def simulate() -> None:
        loop = asyncio.get_running_loop()
        previous = loop.time()
        next_telemetry = previous
        last_condition = None
        while application.status != "OFF":
            now = loop.time()
            dt = min(now - previous, CONTROL_PERIOD * 2)
            previous = now
            linear, angular, opening_rate, valid = adapter.rates(ui)
            if application.status != "ON":
                linear, angular, opening_rate, valid = _ZERO, _ZERO, 0.0, False
            application.readiness = (
                "FAULT" if application.status == "ERROR" else "READY" if valid else "NOT_READY"
            )
            if application.status == "ON":
                try:
                    application.model.step(linear, angular, opening_rate, dt)
                except (ArithmeticError, ValueError) as exc:
                    application.status = "ERROR"
                    application.readiness = "FAULT"
                    adapter.write_status("ERROR")
                    ui.log(f"Arm model fault; motion stopped: {exc}", "error")
            condition = application.model.last_error
            if condition and condition != last_condition:
                ui.log(condition, "warn")
            last_condition = condition
            adapter.write_readiness(application.readiness)
            if now >= next_telemetry:
                adapter.write_telemetry(application.model)
                application.telemetry_sequence += 1
                update_arm_scene(scene, application.model)
                application.controller_connected = (
                    adapter.teleop_reader.subscription_matched_status.current_count > 0
                )
                ui.update(**application.view())
                next_telemetry = now + TELEMETRY_PERIOD
            await asyncio.sleep(max(0.0, CONTROL_PERIOD - (loop.time() - now)))

    async def receive_commands() -> None:
        async for sample in adapter.command_reader.take_data_async():
            command = sample.command.name
            application.apply_command(command)
            adapter.clear_commands()
            adapter.write_status(application.status)
            adapter.write_readiness(application.readiness)
            ui.log(f"Received {command} command from Orchestrator")
            ui.update(**application.view())
            if application.status == "OFF":
                await app.stop()
                return

    async def publish_heartbeat() -> None:
        while application.status != "OFF":
            adapter.write_heartbeat()
            for name, reader in (
                ("Arm", adapter.teleop_reader),
                ("Jaw", adapter.tool_reader),
            ):
                if reader.requested_deadline_missed_status.total_count_change:
                    adapter._diagnostic(f"{name} command deadline missed (diagnostic only)", ui)
                if reader.liveliness_changed_status.not_alive_count_change > 0:
                    adapter._diagnostic(f"{name} command writer lost liveliness", ui)
            await asyncio.sleep(0.05)

    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(simulate())
            tasks.create_task(receive_commands())
            tasks.create_task(publish_heartbeat())
    finally:
        if application.status != "OFF":
            adapter.write_status("OFF")
        adapter.write_readiness("NOT_READY")
        adapter.close()
        print("Shutting down Arm", flush=True)


def main() -> None:
    run_demo_ui(create_demo_ui("Surgical Arm Monitor"), run_application)


if __name__ == "__main__":
    main()
