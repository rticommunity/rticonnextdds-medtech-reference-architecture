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
"""Threat Exfiltrator tests for Module 04.

Verifies that DDS Security correctly blocks (or allows) threat exfiltrator
participants from reading patient vitals.
"""

import sys
from pathlib import Path

import pytest
import rti.connextdds as dds
from scripts.test_utils import (
    make_isolated_qos_provider,
    register_type,
    wait_for_reader_match,
)


def _assert_secure_or_launch(or_env_secure, or_pm_secure) -> None:
    """Verify the secured Module 01 launch configuration used by this test."""
    env, apps = or_env_secure
    profiles = env["NDDS_QOS_PROFILES"]

    assert "SecureAppsQos.xml" in profiles, (
        "Secure OR fixture should resolve NDDS_QOS_PROFILES with SecureAppsQos.xml"
    )
    assert "NonSecureAppsQos.xml" not in profiles, (
        "Secure OR fixture should not use NonSecureAppsQos.xml"
    )
    assert "PatientSensor" in apps, "Secure OR fixture should define PatientSensor app"
    assert or_pm_secure.apps["PatientSensor"] == apps["PatientSensor"]

    patient_sensor_cmd = apps["PatientSensor"]
    assert len(patient_sensor_cmd) == 1, (
        f"PatientSensor should resolve to a single executable command, got: {patient_sensor_cmd}"
    )
    assert Path(patient_sensor_cmd[0]).name == "PatientSensor", (
        f"PatientSensor executable path not resolved as expected: {patient_sensor_cmd[0]}"
    )


def _assert_unsecure_exfiltrator_probe_launch(threat_env) -> None:
    """Verify the unsecured exfiltrator probe configuration used by this test."""
    env, apps = threat_env
    profiles = env["NDDS_QOS_PROFILES"]

    assert "ThreatQos.xml" in profiles, (
        "Threat fixture should include ThreatQos.xml in NDDS_QOS_PROFILES"
    )
    assert "ThreatParticipants.xml" in profiles, (
        "Threat fixture should include ThreatParticipants.xml in NDDS_QOS_PROFILES"
    )
    assert "SecureAppsQos.xml" not in profiles, (
        "Threat fixture should not directly inherit Module 01 secure app profiles"
    )
    assert apps["ThreatExfiltrator"][0] == sys.executable, (
        "ThreatExfiltrator app should launch with the current Python interpreter"
    )
    assert Path(apps["ThreatExfiltrator"][1]).name == "ThreatExfiltrator.py", (
        f"ThreatExfiltrator command not resolved as expected: {apps['ThreatExfiltrator']}"
    )


def _run_exfiltrator_probe(
    env: dict,
    dp_name: str,
    timeout_sec: float = 12.0,
) -> dict:
    """Test whether a threat exfiltrator can match secured OR apps.

    Creates a DomainParticipant from the XML config using an isolated
    QosProvider and checks subscription_matched_status via WaitSet.

    Returns a dict with:
      - "created": bool — whether the participant was created successfully
      - "matched": bool — whether subscription_matched_status.current_count > 0
    """
    from Types import PatientMonitor

    xml_files = env["NDDS_QOS_PROFILES"].split(";")
    provider = make_isolated_qos_provider(*xml_files)

    result = {"created": False, "matched": False}
    try:
        register_type(PatientMonitor.Vitals)
        participant = provider.create_participant_from_config(dp_name)
        if participant is not None:
            result["created"] = True

            reader = dds.DataReader(participant.find_datareader("s/subscriber::dr/Vitals"))
            result["matched"] = wait_for_reader_match(reader, timeout_sec=timeout_sec)
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
class TestExfiltratorUnsecure:
    """Exfiltrator should read vitals from unsecured OR apps."""

    def test_unsecure_exfiltration_succeeds(self, or_pm_nonsecure, or_env_nonsecure, threat_env):
        """Unsecured exfiltrator should receive vitals from unsecured OR apps."""
        _assert_unsecure_exfiltrator_probe_launch(threat_env)

        or_pm_nonsecure.start_app_ready("PatientSensor")

        result = _run_exfiltrator_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/Unsecure",
        )
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        assert result["matched"], "Unsecured exfiltrator did not match unsecured OR apps"


# ---------------------------------------------------------------------------
# Tests against secured OR apps
# ---------------------------------------------------------------------------


@pytest.mark.secure
@pytest.mark.slow
class TestExfiltratorSecure:
    """Security should block threat exfiltrator from reading vitals."""

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def _start_patient_sensor(cls, or_pm_secure_class):
        """Launch PatientSensor once for all tests in this class."""
        or_pm_secure_class.start_app_ready("PatientSensor")

    def test_unsecure_exfiltrator_vs_secure_or(self, or_pm_secure_class, or_env_secure, threat_env):
        """Unsecured exfiltrator should not access secured OR vitals.

        A participant without DDS Security credentials must not establish
        the secure trust/access pipeline required to read secured data.
        """
        _assert_secure_or_launch(or_env_secure, or_pm_secure_class)
        _assert_unsecure_exfiltrator_probe_launch(threat_env)

        result = _run_exfiltrator_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/Unsecure",
            timeout_sec=6,
        )
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        assert result["matched"] is False, "Unsecured exfiltrator should NOT match secured OR apps"

    def test_rogue_ca_exfiltrator_blocked(self, or_pm_secure_class, or_env_secure, threat_env):
        """Rogue CA exfiltrator should NOT receive vitals from secured OR apps."""
        result = _run_exfiltrator_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/RogueCA",
            timeout_sec=4,
        )
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        assert not result["matched"], "Rogue CA exfiltrator should NOT match secured OR apps"

    def test_forged_perms_exfiltrator_blocked(self, or_pm_secure_class, or_env_secure, threat_env):
        """Forged permissions exfiltrator should NOT receive vitals from secured OR apps."""
        result = _run_exfiltrator_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/ForgedPerms",
            timeout_sec=4,
        )
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        assert not result["matched"], (
            "Forged permissions exfiltrator should NOT match secured OR apps"
        )

    def test_expired_cert_exfiltrator_blocked(self, or_pm_secure_class, or_env_secure, threat_env):
        """Expired certificate exfiltrator should fail to create participant or match."""
        result = _run_exfiltrator_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/ExpiredCert",
            timeout_sec=4,
        )
        # Expired cert typically causes participant creation failure
        assert not result["created"], (
            f"Participant creation should have failed: {result.get('error')}"
        )
