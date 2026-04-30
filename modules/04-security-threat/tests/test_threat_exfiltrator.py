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

import json
import subprocess
import sys
from pathlib import Path

import pytest
from module04_test_support import (
    MODULE_DIR,
    OR_SRC_DIR,
    THREAT_SRC_DIR,
    wait_for_process_ready,
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
    fail_fast_on_match_or_data: bool = False,
) -> dict:
    """Launch a threat exfiltrator probe in a subprocess.

    Creates a DomainParticipant from the XML config, subscribes to t/Vitals,
    and returns a dict with:
      - "created": bool — whether the participant was created successfully
      - "matched": bool — whether subscription_matched_status.current_count > 0
      - "received": int — number of vitals samples received

    If fail_fast_on_match_or_data is True, return as soon as any match or
    valid sample is observed. This is useful for negative/security tests where
    any observed data path should immediately fail.
    """
    script = f"""\
import sys, time, json
sys.path.insert(0, "{OR_SRC_DIR}")
sys.path.insert(0, "{THREAT_SRC_DIR}")
import rti.connextdds as dds
from Types import DdsEntities

result = {{"created": False, "matched": False, "received": 0}}
try:
    provider = dds.QosProvider.default
    participant = provider.create_participant_from_config("{dp_name}")
    result["created"] = True

    vitals_dr = dds.DynamicData.DataReader(
        participant.find_datareader("s/subscriber::dr/Vitals")
    )

    deadline = time.monotonic() + {timeout_sec}
    fail_fast = {str(fail_fast_on_match_or_data)}
    count = 0
    while time.monotonic() < deadline:
        if vitals_dr.subscription_matched_status.current_count > 0:
            result["matched"] = True
        for s in vitals_dr.take():
            if s.info.valid:
                count += 1
        if fail_fast and (result["matched"] or count > 0):
            break
        if count >= 3:
            break
        time.sleep(0.3)

    result["received"] = count
    participant.close()
except dds.Error as exc:
    result["error"] = str(exc)

print(json.dumps(result))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        cwd=MODULE_DIR,
        capture_output=True,
        text=True,
        timeout=int(timeout_sec) + 15,
    )
    if proc.returncode != 0:
        return {
            "created": False,
            "matched": False,
            "received": 0,
            "error": proc.stderr,
        }
    # Parse only the last line — DDS may print log messages to stdout
    lines = [line for line in proc.stdout.strip().splitlines() if line.startswith("{")]
    if not lines:
        return {
            "created": False,
            "matched": False,
            "received": 0,
            "error": "No JSON output",
        }
    return json.loads(lines[-1])


# ---------------------------------------------------------------------------
# Tests against unsecured OR apps
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestExfiltratorUnsecure:
    """Exfiltrator should read vitals from unsecured OR apps."""

    def test_unsecure_exfiltration_succeeds(
        self, or_pm_nonsecure, or_env_nonsecure, threat_env
    ):
        """Unsecured exfiltrator should receive vitals from unsecured OR apps."""
        _assert_unsecure_exfiltrator_probe_launch(threat_env)

        ps = or_pm_nonsecure.start_app("PatientSensor")
        wait_for_process_ready(ps, timeout_sec=10)
        assert ps.poll() is None, (
            f"PatientSensor exited early with code {ps.returncode}"
        )

        result = _run_exfiltrator_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/Unsecure",
        )
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        assert result["matched"], (
            "Unsecured exfiltrator did not match unsecured OR apps"
        )
        assert result["received"] >= 1, "Exfiltrator received no vitals"


# ---------------------------------------------------------------------------
# Tests against secured OR apps
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestExfiltratorSecure:
    """Security should block threat exfiltrator from reading vitals."""

    def test_unsecure_exfiltrator_vs_secure_or(
        self, or_pm_secure, or_env_secure, threat_env
    ):
        """Unsecured exfiltrator should not access secured OR vitals.

        A participant without DDS Security credentials must not establish
        the secure trust/access pipeline required to read secured data.
        """
        _assert_secure_or_launch(or_env_secure, or_pm_secure)
        _assert_unsecure_exfiltrator_probe_launch(threat_env)

        ps = or_pm_secure.start_app("PatientSensor")
        wait_for_process_ready(ps, timeout_sec=15)
        assert ps.poll() is None, (
            f"PatientSensor exited early with code {ps.returncode}"
        )

        result = _run_exfiltrator_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/Unsecure",
            timeout_sec=6,
            fail_fast_on_match_or_data=True,
        )
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        assert result["matched"] is False, (
            "Unsecured exfiltrator should NOT match secured OR apps"
        )
        assert result["received"] == 0, (
            "Unsecured exfiltrator should NOT receive vitals from secured OR"
        )

    def test_rogue_ca_exfiltrator_blocked(
        self, or_pm_secure, or_env_secure, threat_env
    ):
        """Rogue CA exfiltrator should NOT receive vitals from secured OR apps."""
        ps = or_pm_secure.start_app("PatientSensor")
        wait_for_process_ready(ps, timeout_sec=15)
        assert ps.poll() is None, (
            f"PatientSensor exited early with code {ps.returncode}"
        )

        result = _run_exfiltrator_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/RogueCA",
            timeout_sec=10,
        )
        assert result["received"] == 0, (
            "Rogue CA exfiltrator should NOT receive vitals from secured OR"
        )

    def test_forged_perms_exfiltrator_blocked(
        self, or_pm_secure, or_env_secure, threat_env
    ):
        """Forged permissions exfiltrator should NOT receive vitals from secured OR apps."""
        ps = or_pm_secure.start_app("PatientSensor")
        wait_for_process_ready(ps, timeout_sec=15)
        assert ps.poll() is None, (
            f"PatientSensor exited early with code {ps.returncode}"
        )

        result = _run_exfiltrator_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/ForgedPerms",
            timeout_sec=10,
        )
        assert result["received"] == 0, (
            "Forged permissions exfiltrator should NOT receive vitals from secured OR"
        )

    def test_expired_cert_exfiltrator_blocked(
        self, or_pm_secure, or_env_secure, threat_env
    ):
        """Expired certificate exfiltrator should fail to create participant or receive data."""
        ps = or_pm_secure.start_app("PatientSensor")
        wait_for_process_ready(ps, timeout_sec=15)
        assert ps.poll() is None, (
            f"PatientSensor exited early with code {ps.returncode}"
        )

        result = _run_exfiltrator_probe(
            threat_env[0],
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/ExpiredCert",
            timeout_sec=10,
        )
        # Expired cert typically causes participant creation failure
        if result["created"]:
            assert result["received"] == 0, (
                "Expired cert exfiltrator should NOT receive vitals from secured OR"
            )
        # If not created, that's also a valid block
