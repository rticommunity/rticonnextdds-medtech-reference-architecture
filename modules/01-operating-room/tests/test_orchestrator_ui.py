#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""The browser Orchestrator controls must issue DDS device commands."""

from __future__ import annotations

import json
import time
from urllib.request import urlopen

import pytest
from module01_test_support import invoke as _invoke
from module01_test_support import local_ui_url as _local_ui_url
from test_utils import wait_for_device_status, wait_for_writer_match


def test_orchestrator_selected_device_receives_browser_command(
    proc_manager,
    nonsecure_utility_app,
):
    from MedTech import Device

    proc_manager.start_app_ready("PatientSensor")
    orchestrator = proc_manager.start_app_ready("Orchestrator")
    ui_url = _local_ui_url(
        orchestrator,
        "System Orchestrator listening on",
    )

    deadline = time.monotonic() + 5
    sensor_status = None
    while time.monotonic() < deadline:
        with urlopen(f"{ui_url}/api/state", timeout=2) as response:
            state = json.load(response).get("data", {})
        sensor = next(
            (device for device in state.get("devices", []) if device["name"] == "PATIENT_SENSOR"),
            None,
        )
        sensor_status = sensor["status"] if sensor else None
        if sensor_status == "ON":
            break
        time.sleep(0.05)
    assert sensor_status == "ON", "Patient Sensor was not observed as online"

    assert _invoke(ui_url, "select-device", {"device": "PATIENT_SENSOR"})["ok"]
    assert _invoke(ui_url, "send-device-command", {"command": "PAUSE"})["ok"]

    seen = wait_for_device_status(
        nonsecure_utility_app.device_status.reader,
        expected_devices={Device.DeviceType.PATIENT_SENSOR},
        device_statuses=[Device.DeviceStatusKind.PAUSED],
        timeout_sec=5,
    )
    assert Device.DeviceType.PATIENT_SENSOR in seen

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with urlopen(f"{ui_url}/api/state", timeout=2) as response:
            state = json.load(response)
        if any(
            entry["message"] == "Writing PAUSE to PATIENT_SENSOR"
            for entry in state["data"].get("logs", [])
        ):
            return
        time.sleep(0.05)
    raise AssertionError("Orchestrator did not record the command sent from its UI")


@pytest.mark.parametrize("staggered_loss", [True, False], ids=["staggered", "simultaneous"])
def test_orchestrator_tracks_keyed_heartbeat_loss_and_recovery(
    proc_manager, nonsecure_utility_app, staggered_loss
):
    from MedTech import Device

    process = proc_manager.start_app_ready("Orchestrator")
    url = _local_ui_url(process, "System Orchestrator listening on")
    status = nonsecure_utility_app.device_status.writer
    heartbeat = nonsecure_utility_app.device_heartbeat.writer
    assert wait_for_writer_match(status)
    assert wait_for_writer_match(heartbeat)
    devices = (Device.DeviceType.ARM, Device.DeviceType.ARM_CONTROLLER)
    for device in devices:
        status.write(
            Device.Status(
                device=device,
                status=Device.DeviceStatusKind.ERROR,
                readiness=Device.DeviceReadinessKind.FAULTED,
            )
        )

    def device_row(device):
        with urlopen(f"{url}/api/state", timeout=2) as response:
            return next(
                row for row in json.load(response)["data"]["devices"] if row["name"] == device.name
            )

    assert all(device_row(device)["presence"] == "UNKNOWN" for device in devices)

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        for device in devices:
            heartbeat.write(Device.Heartbeat(device=device))
        if all(
            device_row(device)["status"] == "ERROR" and device_row(device)["presence"] == "PRESENT"
            for device in devices
        ):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("Live device ERROR statuses were not preserved")

    if staggered_loss:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            heartbeat.write(Device.Heartbeat(device=Device.DeviceType.ARM_CONTROLLER))
            if (
                device_row(Device.DeviceType.ARM)["presence"] == "OFFLINE"
                and device_row(Device.DeviceType.ARM_CONTROLLER)["presence"] == "PRESENT"
            ):
                break
            time.sleep(0.05)
        else:
            raise AssertionError(
                "A silent key did not become offline while the other stayed present"
            )

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if all(
            device_row(device)["presence"] == "OFFLINE"
            and device_row(device)["status"] == "ERROR"
            and device_row(device)["readiness"] == "FAULTED"
            for device in devices
        ):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("Heartbeat loss did not preserve the last reported lifecycle")

    heartbeat.write(Device.Heartbeat(device=Device.DeviceType.ARM))

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if (
            device_row(Device.DeviceType.ARM)["presence"] == "PRESENT"
            and device_row(Device.DeviceType.ARM)["status"] == "ERROR"
            and device_row(Device.DeviceType.ARM)["readiness"] == "FAULTED"
            and device_row(Device.DeviceType.ARM_CONTROLLER)["presence"] == "OFFLINE"
            and device_row(Device.DeviceType.ARM_CONTROLLER)["status"] == "ERROR"
            and device_row(Device.DeviceType.ARM_CONTROLLER)["readiness"] == "FAULTED"
        ):
            return
        time.sleep(0.05)
    raise AssertionError("Presence recovery was not isolated to the reasserting key")
