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
"""Runtime smoke test for Module 04 threat participant XML configuration."""

import sys

from module04_test_support import OR_SRC_DIR, THREAT_SRC_DIR
from scripts.test_utils import make_isolated_qos_provider, register_type


def test_unsecure_threat_participants_load_from_qos_profiles(threat_env):
    for source_dir in (OR_SRC_DIR, THREAT_SRC_DIR):
        if str(source_dir) not in sys.path:
            sys.path.insert(0, str(source_dir))

    from Types import Orchestrator, PatientMonitor, SurgicalRobot

    for type_class in (
        Orchestrator.DeviceCommand,
        PatientMonitor.Vitals,
        SurgicalRobot.TeleopControl,
    ):
        register_type(type_class)

    env, _apps = threat_env
    provider = make_isolated_qos_provider(*env["NDDS_QOS_PROFILES"].split(";"))
    participants = []
    try:
        participants.append(
            provider.create_participant_from_config(
                "ThreatParticipantLibrary::dp/ThreatInjector/Unsecure"
            )
        )
        participants.append(
            provider.create_participant_from_config(
                "ThreatParticipantLibrary::dp/ThreatExfiltrator/Unsecure"
            )
        )
    finally:
        for participant in reversed(participants):
            participant.close()
