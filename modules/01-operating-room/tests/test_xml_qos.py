#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.
"""Runtime smoke test for the named DDS participants configured in XML."""

import json
import sys
import time
from urllib.request import urlopen

import pytest
from module01_test_support import REPO_ROOT, SRC_DIR
from test_orchestrator_ui import _local_ui_url
from test_utils import make_isolated_qos_provider, register_type

from tools.medtech.platform_setup import generated_system_path


def test_operational_participants_load_from_qos_profiles():
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    from MedTech import DdsEntities, Device, Patient, Robot

    for type_class in (
        Device.Status,
        Device.Heartbeat,
        Device.Command,
        Patient.Vitals,
        Robot.Arm.TeleopControl,
        Robot.Tool.ParallelJawControl,
        Robot.Arm.Telemetry,
    ):
        register_type(type_class)

    system = REPO_ROOT / "system"
    provider = make_isolated_qos_provider(
        str(generated_system_path() / "xml" / "MedTech.xml"),
        str(system / "qos" / "Qos.xml"),
        str(system / "qos" / "NonSecureAppsQos.xml"),
        str(system / "model" / "DomainLibrary.xml"),
        str(system / "model" / "ParticipantLibrary.xml"),
    )
    participants = []
    try:
        for config_name in (
            DdsEntities.Constants.ARM_DP,
            DdsEntities.Constants.ARM_CONTROLLER_DP,
            DdsEntities.Constants.ORCHESTRATOR_DP,
            DdsEntities.Constants.PATIENT_SENSOR_DP,
            DdsEntities.Constants.PATIENT_MONITOR_DP,
        ):
            participants.append(provider.create_participant_from_config(config_name))
    finally:
        for participant in reversed(participants):
            participant.close()


@pytest.mark.secure
def test_secure_log_reader_loads_from_named_participant_config(proc_manager_secure):
    proc = proc_manager_secure.start_app_ready("Orchestrator")
    url = _local_ui_url(proc, "System Orchestrator listening on")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with urlopen(f"{url}/api/state", timeout=2) as response:
            status = json.load(response).get("data", {}).get("status")
        if status in {"SECURITY: OK", "SECURITY EVENT"}:
            assert proc.poll() is None
            return
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    pytest.fail("Orchestrator did not initialize its secure DDS reader")
