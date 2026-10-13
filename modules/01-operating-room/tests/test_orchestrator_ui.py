#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""The browser Orchestrator controls must issue DDS device commands."""

from __future__ import annotations

import json
import re
import select
import time
from urllib.request import Request, urlopen

from scripts.test_utils import wait_for_device_status


def _local_ui_url(process, expected_prefix: str) -> str:
    assert process.stdout is not None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        readable, _, _ = select.select([process.stdout], [], [], 0.25)
        if not readable:
            continue
        line = process.stdout.readline().decode(errors="replace").strip()
        match = re.search(r"https?://127\.0\.0\.1:\d+", line)
        if match:
            assert line.startswith(expected_prefix), f"unexpected URL announcement: {line}"
            return match.group(0)
    raise AssertionError("Orchestrator did not print its local UI URL")


def _invoke(url: str, name: str, payload: dict) -> dict:
    with urlopen(f"{url}/api/command-capability", timeout=2) as response:
        capability = json.load(response)["capability"]
    request = Request(
        f"{url}/api/commands/{name}",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Origin": url,
            "X-RTI-Demo-Command-Capability": capability,
        },
        method="POST",
    )
    with urlopen(request, timeout=2) as response:
        return json.load(response)


def test_orchestrator_selected_device_receives_browser_command(
    proc_manager,
    nonsecure_utility_app,
):
    from Types import Common

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
        expected_devices={Common.DeviceType.PATIENT_SENSOR},
        device_statuses=[Common.DeviceStatuses.PAUSED],
        timeout_sec=5,
    )
    assert Common.DeviceType.PATIENT_SENSOR in seen

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
