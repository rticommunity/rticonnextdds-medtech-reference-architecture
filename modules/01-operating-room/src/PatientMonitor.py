#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""DDS patient-vitals adapter and application state for the web monitor."""

from __future__ import annotations

import asyncio

import rti.asyncio  # noqa: F401 - installs Connext's asyncio integration
import rti.connextdds as dds
from ApplicationLogic import device_status_after_command
from DdsUtils import register_type, vitals_from_sample
from DemoUiSupport import DemoUiState, create_demo_ui, run_demo_ui
from MedTech import DdsEntities, Device
from MedTech import Patient as PatientTypes


class PatientMonitorApplication:
    def __init__(self) -> None:
        self.status = "ON"
        self.vitals: dict[str, float] | None = None
        self.last_sample_at: float | None = None

    def receive_vitals(self, vitals: dict[str, float]) -> dict[str, float]:
        self.vitals = vitals
        self.last_sample_at = asyncio.get_running_loop().time()
        return self.vitals

    def apply_command(self, command: str) -> None:
        self.status = device_status_after_command(command)

    def view(self, *, matched: bool = False) -> dict:
        fresh = self.last_sample_at is not None and (
            asyncio.get_running_loop().time() - self.last_sample_at <= 2.0
        )
        if self.status == "PAUSED":
            vitals_status = "STREAM PAUSED"
        elif self.status == "OFF":
            vitals_status = "MONITOR OFFLINE"
        elif self.last_sample_at is None or not matched:
            vitals_status = "WAITING FOR VITALS"
        elif not fresh:
            vitals_status = "DATA QUIET"
        else:
            vitals_status = "LIVE VITALS"
        vitals = dict(self.vitals or {})
        vitals["fresh"] = fresh
        return {
            "kind": "patient-monitor",
            "title": "Patient Monitor",
            "status": self.status,
            "vitals_status": vitals_status,
            "header_badges": [
                {"label": "Vitals", "value": vitals_status},
                {"label": "Device", "value": self.status},
            ],
            "footer": True,
            "vitals": vitals,
        }


class PatientMonitorDdsAdapter:
    def __init__(self) -> None:
        entities = DdsEntities.Constants
        for data_type in (
            Device.Status,
            Device.Heartbeat,
            Device.Command,
            PatientTypes.Vitals,
        ):
            register_type(data_type)
        provider = dds.QosProvider.default
        self.participant = provider.create_participant_from_config(entities.PATIENT_MONITOR_DP)
        self.status_writer = dds.DataWriter(self.participant.find_datawriter(entities.STATUS_DW))
        self.heartbeat_writer = dds.DataWriter(self.participant.find_datawriter(entities.HB_DW))
        self.vitals_reader = dds.DataReader(self.participant.find_datareader(entities.VITALS_DR))
        self.command_reader = dds.DataReader(
            self.participant.find_datareader(entities.DEVICE_COMMAND_DR)
        )
        self.status = Device.Status(
            device=Device.DeviceType.PATIENT_MONITOR,
            status=Device.DeviceStatuses.ON,
        )
        self.status_writer.write(self.status)

    def write_status(self, status: str) -> None:
        self.status.status = getattr(Device.DeviceStatuses, status)
        self.status_writer.write(self.status)

    def write_heartbeat(self) -> None:
        self.heartbeat_writer.write(Device.Heartbeat(device=Device.DeviceType.PATIENT_MONITOR))

    def close(self) -> None:
        self.participant.close()


async def run_application(app) -> None:
    application = PatientMonitorApplication()
    ui = DemoUiState(
        app,
        kind="patient-monitor",
        title="Patient Monitor",
        description="Live waveforms and vital signs received through RTI Connext DDS.",
    )
    adapter = PatientMonitorDdsAdapter()
    ui.update(**application.view())
    ui.log("Patient Monitor is online")

    async def receive_vitals() -> None:
        async for sample in adapter.vitals_reader.take_data_async():
            if application.status == "ON":
                application.receive_vitals(vitals_from_sample(sample))
                ui.update(**application.view(matched=True))

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

    async def refresh_state() -> None:
        while application.status != "OFF":
            matched = adapter.vitals_reader.subscription_matched_status.current_count > 0
            ui.update(**application.view(matched=matched))
            await asyncio.sleep(0.5)

    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(receive_vitals())
            tasks.create_task(receive_commands())
            tasks.create_task(publish_heartbeat())
            tasks.create_task(refresh_state())
    finally:
        if application.status != "OFF":
            adapter.write_status("OFF")
        adapter.close()
        print("Shutting down Patient Monitor", flush=True)


def main() -> None:
    run_demo_ui(create_demo_ui("Patient Monitor"), run_application)


if __name__ == "__main__":
    main()
