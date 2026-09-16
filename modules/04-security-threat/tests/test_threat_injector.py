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
"""Threat Injector tests for Module 04.

Verifies that DDS Security correctly blocks (or allows) threat injector
participants depending on the attack mode and whether OR apps are secured.

Each test launches OR apps (secured or unsecured), then creates a threat
participant with an isolated QosProvider and checks the
publication_matched_status to determine whether data can flow.
"""

import pytest
import rti.connextdds as dds
from scripts.test_utils import (
    make_isolated_qos_provider,
    register_type,
    wait_for_writer_match,
)


def _run_injector_probe(
    env: dict,
    dp_name: str,
    timeout_sec: float = 12.0,
) -> dict:
    """Test whether a threat injector can match secured OR apps.

    Creates a DomainParticipant from the XML config using an isolated
    QosProvider and checks publication_matched_status via WaitSet.
    No data is written — only match detection.

    Returns a dict with:
      - "created": bool — whether the participant was created successfully
      - "matched": bool — whether publication_matched_status.current_count > 0
    """
    from Types import Orchestrator

    xml_files = env["NDDS_QOS_PROFILES"].split(";")
    provider = make_isolated_qos_provider(*xml_files)

    result = {"created": False, "matched": False}
    try:
        register_type(Orchestrator.DeviceCommand)
        participant = provider.create_participant_from_config(dp_name)
        if participant is not None:
            result["created"] = True

            writer = dds.DataWriter(participant.find_datawriter("p/publisher::dw/DeviceCommand"))
            result["matched"] = wait_for_writer_match(writer, timeout_sec=timeout_sec)
    except dds.Error as exc:
        result["error"] = str(exc)
    finally:
        if result["created"]:
            participant.close()

    return result


# ---------------------------------------------------------------------------
# Tests against unsecured OR apps
# ---------------------------------------------------------------------------


@pytest.mark.secure
@pytest.mark.slow
class TestInjectorUnsecure:
    """Injector should match unsecured OR apps (no DDS Security)."""

    def test_unsecure_injection_succeeds(self, or_pm_nonsecure, or_env_nonsecure, threat_env):
        """Unsecured injector should match unsecured OR apps."""
        or_pm_nonsecure.start_app_ready("PatientSensor")

        result = _run_injector_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatInjector/Unsecure",
        )
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        assert result["matched"], "Unsecured injector did not match unsecured OR apps"


# ---------------------------------------------------------------------------
# Tests against secured OR apps
# ---------------------------------------------------------------------------


@pytest.mark.secure
@pytest.mark.slow
class TestInjectorSecure:
    """Security should block threat injector participants from matching secured OR apps."""

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def _start_patient_sensor(cls, or_pm_secure_class):
        """Launch PatientSensor once for all tests in this class."""
        or_pm_secure_class.start_app_ready("PatientSensor")

    def test_rogue_ca_injection_blocked(self, or_pm_secure_class, or_env_secure, threat_env):
        """Injector with rogue CA identity should not match secured OR apps."""
        result = _run_injector_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatInjector/RogueCA",
            timeout_sec=4,
        )
        # The participant may be created but should NOT match
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        assert not result["matched"], "Rogue CA injector should NOT match secured OR apps"

    def test_forged_perms_injection_blocked(self, or_pm_secure_class, or_env_secure, threat_env):
        """Injector with forged permissions should not match secured OR apps."""
        result = _run_injector_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatInjector/ForgedPerms",
            timeout_sec=4,
        )
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        assert not result["matched"], "Forged permissions injector should NOT match secured OR apps"

    def test_expired_cert_injection_fails(self, or_pm_secure_class, or_env_secure, threat_env):
        """Injector with expired certificate should fail to create participant or match."""
        result = _run_injector_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatInjector/ExpiredCert",
            timeout_sec=4,
        )
        # Expired cert typically causes participant creation failure
        assert not result["created"], (
            f"Participant creation should have failed: {result.get('error')}"
        )
