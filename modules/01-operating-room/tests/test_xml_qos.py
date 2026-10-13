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

import sys

import pytest
from module01_test_support import REPO_ROOT, SRC_DIR
from scripts.test_utils import make_isolated_qos_provider, register_type


def test_operational_participants_load_from_qos_profiles():
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    from Types import Common, DdsEntities, Orchestrator, PatientMonitor, SurgicalRobot

    for type_class in (
        Common.DeviceStatus,
        Common.DeviceHeartbeat,
        Orchestrator.DeviceCommand,
        PatientMonitor.Vitals,
        SurgicalRobot.TeleopControl,
    ):
        register_type(type_class)

    system_arch = REPO_ROOT / "system_arch"
    provider = make_isolated_qos_provider(
        str(system_arch / "Types.xml"),
        str(system_arch / "qos" / "Qos.xml"),
        str(system_arch / "qos" / "NonSecureAppsQos.xml"),
        str(system_arch / "xml_app_creation" / "DomainLibrary.xml"),
        str(system_arch / "xml_app_creation" / "ParticipantLibrary.xml"),
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
    assert proc.poll() is None
