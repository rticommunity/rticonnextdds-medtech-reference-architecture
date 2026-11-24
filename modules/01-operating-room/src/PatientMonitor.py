#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""DDS and patient-vitals application state for the web monitor."""

from __future__ import annotations

import asyncio
import os
from enum import Enum, auto

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

DEFAULT_PATIENT_ID = "ab1234"


class VitalsStatus(Enum):
    WAITING_FOR_VITALS = auto()
    LIVE_VITALS = auto()
    INVALID_VITALS = auto()
    DATA_QUIET = auto()
    STREAM_PAUSED = auto()
    MONITOR_OFFLINE = auto()


def patient_filter_parameter(patient_id: str) -> str:
    if (
        not patient_id
        or len(patient_id.encode("utf-8")) > 8
        or "\0" in patient_id
        or "'" in patient_id
    ):
        raise ValueError("MEDTECH_PATIENT_ID must be 1 to 8 UTF-8 bytes without NUL or apostrophes")
    return f"'{patient_id}'"


class PatientMonitorApp:
    def __init__(self, ui) -> None:
        patient_id = os.environ.get("MEDTECH_PATIENT_ID", DEFAULT_PATIENT_ID)
        filter_parameter = patient_filter_parameter(patient_id)
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
        dds.ContentFilteredTopic(self.vitals_reader.topic_description).filter_parameters = [
            filter_parameter
        ]
        self.command_reader = dds.DataReader(
            self.participant.find_datareader(entities.DEVICE_COMMAND_DR)
        )
        self.status_sample = Device.Status(
            device=Device.DeviceType.PATIENT_MONITOR,
            status=Device.DeviceStatusKind.ON,
        )
        self.ui = ui
        self.failed = False
        self.status = Device.DeviceStatusKind.ON
        self.vitals: dict[str, float] | None = None
        self.vitals_status = VitalsStatus.WAITING_FOR_VITALS

    def receive_vitals(self, vitals: dict[str, float]) -> dict[str, float]:
        self.vitals = vitals
        self.vitals_status = VitalsStatus.LIVE_VITALS
        return self.vitals

    def process_vitals_sample(self, sample: PatientTypes.Vitals, info: dds.SampleInfo) -> None:
        if not info.valid or self.status != Device.DeviceStatusKind.ON:
            return
        invalid_fields = []
        if sample.spo2 > 100:
            invalid_fields.append("SpO2")
        if sample.nibp_d > sample.nibp_s:
            invalid_fields.append("blood pressure")
        if invalid_fields:
            self.vitals = None
            self.vitals_status = VitalsStatus.INVALID_VITALS
            self.ui.log(f"Invalid vitals: {', '.join(invalid_fields)}", "warn")
        else:
            self.receive_vitals(
                {
                    "heart_rate": float(sample.hr),
                    "spo2": float(sample.spo2),
                    "etco2": float(sample.etco2),
                    "nibp_s": float(sample.nibp_s),
                    "nibp_d": float(sample.nibp_d),
                }
            )
        self.update_readiness()
        self.ui.update(**self.view())

    def apply_command(self, command: Device.DeviceCommandKind) -> None:
        status = device_status_after_command(command)
        if status == Device.DeviceStatusKind.ON:
            self.vitals_reader.take()
        self.status = status
        self.vitals = None
        self.vitals_status = VitalsStatus.WAITING_FOR_VITALS

    def vitals_are_fresh(self) -> bool:
        return self.vitals_status == VitalsStatus.LIVE_VITALS

    def mark_vitals_quiet(self) -> None:
        if (
            self.status == Device.DeviceStatusKind.ON
            and self.vitals_status != VitalsStatus.WAITING_FOR_VITALS
        ):
            self.vitals_status = VitalsStatus.DATA_QUIET
            self.update_readiness()
            self.ui.update(**self.view())

    async def receive_vitals_stream(self) -> None:
        data_condition = dds.ReadCondition(
            self.vitals_reader, dds.DataState(dds.SampleState.NOT_READ)
        )
        deadline_condition = dds.StatusCondition(self.vitals_reader)
        deadline_condition.enabled_statuses = dds.StatusMask.REQUESTED_DEADLINE_MISSED
        stop_condition = dds.GuardCondition()
        waitset = dds.WaitSet()
        waitset += data_condition
        waitset += deadline_condition
        waitset += stop_condition
        try:
            while True:
                pending_wait = asyncio.ensure_future(waitset.wait_async())
                try:
                    active_conditions = await asyncio.shield(pending_wait)
                except asyncio.CancelledError:
                    stop_condition.trigger_value = True
                    await pending_wait
                    raise
                if deadline_condition in active_conditions:
                    if self.vitals_reader.requested_deadline_missed_status.total_count_change:
                        self.mark_vitals_quiet()
                if data_condition in active_conditions:
                    for sample, info in (
                        self.vitals_reader.select().condition(data_condition).take()
                    ):
                        if info.valid:
                            self.process_vitals_sample(sample, info)
                        if info.state.instance_state != dds.InstanceState.ALIVE:
                            self.mark_vitals_quiet()
        finally:
            waitset.detach_all()
            data_condition.close()

    def view(self) -> dict:
        fresh = self.vitals_are_fresh()
        if self.status == Device.DeviceStatusKind.PAUSED:
            vitals_status = VitalsStatus.STREAM_PAUSED
        elif self.status == Device.DeviceStatusKind.OFF:
            vitals_status = VitalsStatus.MONITOR_OFFLINE
        else:
            vitals_status = self.vitals_status
        vitals_label = vitals_status.name.replace("_", " ")
        vitals = dict(self.vitals or {})
        vitals["fresh"] = fresh
        return {
            "kind": "patient-monitor",
            "device_status": self.status.name,
            "title": "Patient Monitor",
            "status": self.status.name,
            "vitals_status": vitals_label,
            "header_badges": [
                {"label": "Vitals", "value": vitals_label},
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

        async def receive_commands() -> None:
            async for sample in self.command_reader.take_data_async():
                command = sample.command
                self.apply_command(command)
                self.write_status(self.status)
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
            self.ui.update(dds_security=participant_security_enabled(self.participant))
            self.status_writer.write(self.status_sample)
            enabled = True
            self.ui.update(**self.view())
            self.ui.log("Patient Monitor is online")
            async with asyncio.TaskGroup() as tasks:
                workers.append(
                    tasks.create_task(
                        run_app_task(
                            self.receive_vitals_stream, "Patient Monitor vitals", task_failed
                        )
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
        except Exception as error:
            self.failed = True
            log_failure("Patient Monitor", error)
        finally:
            heartbeat_stop.set()
            try:
                if enabled and self.status != Device.DeviceStatusKind.OFF:
                    self.write_status(Device.DeviceStatusKind.OFF)
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

    def write_status(self, status: Device.DeviceStatusKind) -> None:
        self.status_sample.status = status
        self.status_sample.readiness = (
            Device.DeviceReadinessKind.FAULTED
            if self.failed
            else Device.DeviceReadinessKind.READY
            if status == Device.DeviceStatusKind.ON and self.vitals_are_fresh()
            else Device.DeviceReadinessKind.NOT_READY
        )
        self.status_writer.write(self.status_sample)

    def update_readiness(self) -> None:
        readiness = (
            Device.DeviceReadinessKind.READY
            if self.status == Device.DeviceStatusKind.ON and self.vitals_are_fresh()
            else Device.DeviceReadinessKind.NOT_READY
        )
        if self.status_sample.readiness != readiness:
            self.write_status(self.status)


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
