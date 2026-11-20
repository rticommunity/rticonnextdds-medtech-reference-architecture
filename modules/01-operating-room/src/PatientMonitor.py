#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""DDS and patient-vitals application state for the web monitor."""

from __future__ import annotations

import asyncio

import rti.asyncio  # noqa: F401 - installs Connext's asyncio integration
import rti.connextdds as dds
from DemoUiSupport import (
    DemoUiState,
    create_demo_ui,
    log_failure,
    participant_security_enabled,
    run_app_task,
    run_demo_ui,
)
from HeartbeatPresence import publish_heartbeats
from MedTech import DdsEntities, Device
from MedTech import Patient as PatientTypes
from MedTechTypes import device_status_after_command, register_type


class PatientMonitorApp:
    def __init__(self, ui) -> None:
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
        self.status_sample = Device.Status(
            device=Device.DeviceType.PATIENT_MONITOR,
            status=Device.DeviceStatuses.ON,
        )
        self.ui = ui
        self.failed = False
        self.status = Device.DeviceStatuses.ON
        self.vitals: dict[str, float] | None = None
        self.last_sample_at: float | None = None

    def receive_vitals(self, vitals: dict[str, float]) -> dict[str, float]:
        self.vitals = vitals
        self.last_sample_at = asyncio.get_running_loop().time()
        return self.vitals

    def apply_command(self, command: Device.DeviceCommands) -> None:
        self.status = device_status_after_command(command)

    def view(self, *, matched: bool = False) -> dict:
        fresh = self.last_sample_at is not None and (
            asyncio.get_running_loop().time() - self.last_sample_at <= 2.0
        )
        if self.status == Device.DeviceStatuses.PAUSED:
            vitals_status = "STREAM PAUSED"
        elif self.status == Device.DeviceStatuses.OFF:
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
            "device_status": self.status.name,
            "title": "Patient Monitor",
            "status": self.status.name,
            "vitals_status": vitals_status,
            "header_badges": [
                {"label": "Vitals", "value": vitals_status},
            ],
            "footer": True,
            "vitals": vitals,
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

        async def receive_vitals() -> None:
            async for sample in self.vitals_reader.take_data_async():
                if self.status == Device.DeviceStatuses.ON:
                    self.receive_vitals(
                        {
                            "heart_rate": float(sample.hr),
                            "spo2": float(sample.spo2),
                            "etco2": float(sample.etco2),
                            "nibp_s": float(sample.nibp_s),
                            "nibp_d": float(sample.nibp_d),
                        }
                    )
                    self.ui.update(**self.view(matched=True))

        async def receive_commands() -> None:
            async for sample in self.command_reader.take_data_async():
                command = sample.command
                self.apply_command(command)
                self.write_status(self.status)
                self.ui.log(f"Received {command.name} command from Orchestrator")
                self.ui.update(**self.view())
                if self.status == Device.DeviceStatuses.OFF:
                    heartbeat_stop.set()
                    await app.stop()
                    for task in workers:
                        if task is not asyncio.current_task():
                            task.cancel()
                    return

        async def refresh_state() -> None:
            while self.status != Device.DeviceStatuses.OFF:
                matched = self.vitals_reader.subscription_matched_status.current_count > 0
                self.ui.update(**self.view(matched=matched))
                await asyncio.sleep(0.5)

        try:
            self.participant.enable()
            self.ui.update(dds_security=participant_security_enabled(self.participant))
            self.status_writer.write(self.status_sample)
            enabled = True
            self.ui.update(**self.view())
            self.ui.log("Patient Monitor is online")
            async with asyncio.TaskGroup() as tasks:
                workers.append(
                    tasks.create_task(
                        run_app_task(receive_vitals, "Patient Monitor vitals", task_failed)
                    )
                )
                workers.append(
                    tasks.create_task(
                        run_app_task(receive_commands, "Patient Monitor commands", task_failed)
                    )
                )
                workers.append(
                    tasks.create_task(
                        run_app_task(
                            lambda: publish_heartbeats(
                                self.heartbeat_writer,
                                Device.Heartbeat(device=Device.DeviceType.PATIENT_MONITOR),
                                heartbeat_stop,
                            ),
                            "Patient Monitor heartbeat",
                            task_failed,
                        )
                    )
                )
                workers.append(
                    tasks.create_task(
                        run_app_task(refresh_state, "Patient Monitor UI", task_failed)
                    )
                )
        except Exception as error:
            self.failed = True
            log_failure("Patient Monitor", error)
        finally:
            heartbeat_stop.set()
            try:
                if enabled and self.status != Device.DeviceStatuses.OFF:
                    self.write_status(Device.DeviceStatuses.OFF)
            except Exception as error:
                self.failed = True
                log_failure("Patient Monitor final DDS write", error)
            finally:
                try:
                    self.participant.close()
                except Exception as error:
                    self.failed = True
                    log_failure("Patient Monitor participant close", error)
            if self.failed:
                try:
                    await app.stop()
                except Exception as error:
                    log_failure("Patient Monitor UI shutdown", error)
            print("Shutting down Patient Monitor", flush=True)

    def write_status(self, status: Device.DeviceStatuses) -> None:
        self.status_sample.status = status
        self.status_writer.write(self.status_sample)


def configure_ui(app):
    return DemoUiState(
        app,
        kind="patient-monitor",
        title="Patient Monitor",
        description="Live waveforms and vital signs received through RTI Connext DDS.",
    )


def main() -> int:
    application = None
    result = 1
    try:
        app = create_demo_ui("Patient Monitor")
        application = PatientMonitorApp(configure_ui(app))
        run_demo_ui(app, application.run)
        result = int(application.failed)
    except Exception as error:
        log_failure("Patient Monitor setup or UI", error)
    finally:
        if application is not None:
            try:
                if not application.participant.closed:
                    application.participant.close()
            except Exception as error:
                log_failure("Patient Monitor participant close", error)
                result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
