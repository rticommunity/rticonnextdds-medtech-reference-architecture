#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""DDS adapter and application state for the simulated surgical arm."""

from __future__ import annotations

import asyncio

import rti.asyncio  # noqa: F401 - installs Connext's asyncio integration
import rti.connextdds as dds
from ApplicationLogic import device_status_after_command
from ArmKinematics import ArmJoint, apply_teleop_jog
from DdsUtils import register_type
from DemoUiSupport import (
    DemoUiState,
    arm_angles_for_view,
    create_demo_ui,
    run_demo_ui,
)
from Types import Common, DdsEntities, Orchestrator, SurgicalRobot

_JOINT_NAMES = {
    ArmJoint.BASE: "base",
    ArmJoint.SHOULDER: "shoulder",
    ArmJoint.ELBOW: "elbow",
    ArmJoint.WRIST: "wrist",
    ArmJoint.HAND: "hand",
}
_INITIAL_ANGLES = {
    ArmJoint.BASE: 204.0,
    ArmJoint.SHOULDER: 220.0,
    ArmJoint.ELBOW: 120.0,
    ArmJoint.WRIST: 220.0,
    ArmJoint.HAND: 45.0,
}


class ArmApplication:
    def __init__(self) -> None:
        self.status = "ON"
        self.angles = dict(_INITIAL_ANGLES)
        self.controller_connected = False

    def apply_teleop(self, axis: str, direction: str) -> None:
        if self.status == "ON" and direction != "STOPPED":
            self.angles = apply_teleop_jog(self.angles, axis, direction)

    def apply_command(self, command: str) -> None:
        self.status = device_status_after_command(command)

    def view(self) -> dict:
        controller_status = "CONTROLLER CONNECTED" if self.controller_connected else "NO CONTROLLER"
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
                {"label": "Command QoS", "value": "ACTIVE"},
            ],
            "footer": True,
            "arm": {
                "active": True,
                "angles": arm_angles_for_view(self.angles, _JOINT_NAMES),
            },
        }


class ArmDdsAdapter:
    def __init__(self) -> None:
        entities = DdsEntities.Constants
        for data_type in (
            Common.DeviceStatus,
            Common.DeviceHeartbeat,
            Orchestrator.DeviceCommand,
            SurgicalRobot.TeleopControl,
        ):
            register_type(data_type)
        provider = dds.QosProvider.default
        self.participant = provider.create_participant_from_config(entities.ARM_DP)
        self.status_writer = dds.DataWriter(self.participant.find_datawriter(entities.STATUS_DW))
        self.heartbeat_writer = dds.DataWriter(self.participant.find_datawriter(entities.HB_DW))
        self.teleop_reader = dds.DataReader(
            self.participant.find_datareader(entities.TELEOP_CONTROL_DR)
        )
        self.command_reader = dds.DataReader(
            self.participant.find_datareader(entities.DEVICE_COMMAND_DR)
        )
        self.status = Common.DeviceStatus(
            device=Common.DeviceType.ARM,
            status=Common.DeviceStatuses.ON,
        )
        self.status_writer.write(self.status)

    def write_status(self, status: str) -> None:
        self.status.status = getattr(Common.DeviceStatuses, status)
        self.status_writer.write(self.status)

    def write_heartbeat(self) -> None:
        self.heartbeat_writer.write(Common.DeviceHeartbeat(device=Common.DeviceType.ARM))

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
    ui.update(**application.view())
    ui.log("Arm is online")

    async def receive_teleop() -> None:
        async for sample in adapter.teleop_reader.take_data_async():
            application.apply_teleop(sample.axis.name, sample.direction.name)
            ui.update(**application.view())

    async def receive_commands() -> None:
        async for sample in adapter.command_reader.take_data_async():
            command = sample.command.name
            application.apply_command(command)
            adapter.write_status(application.status)
            ui.log(f"Received {command} command from Orchestrator")
            ui.update(**application.view())
            if application.status == "OFF":
                await app.stop()
                return

    async def publish_heartbeat() -> None:
        while application.status != "OFF":
            adapter.write_heartbeat()
            await asyncio.sleep(0.05)

    async def monitor_match() -> None:
        while application.status != "OFF":
            application.controller_connected = (
                adapter.teleop_reader.subscription_matched_status.current_count > 0
            )
            ui.update(**application.view())
            await asyncio.sleep(0.5)

    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(receive_teleop())
            tasks.create_task(receive_commands())
            tasks.create_task(publish_heartbeat())
            tasks.create_task(monitor_match())
    finally:
        if application.status != "OFF":
            adapter.write_status("OFF")
        adapter.close()
        print("Shutting down Arm", flush=True)


def main() -> None:
    run_demo_ui(create_demo_ui("Surgical Arm Monitor"), run_application)


if __name__ == "__main__":
    main()
