"""Threat Exfiltrator tests for Module 04.

Verifies that DDS Security correctly blocks (or allows) threat exfiltrator
participants from reading patient vitals.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import (
    MODULE_01_DIR,
    MODULE_DIR,
    OR_SRC_DIR,
    THREAT_SRC_DIR,
)


def _run_exfiltrator_probe(
    env: dict,
    dp_name: str,
    timeout_sec: float = 12.0,
) -> dict:
    """Launch a threat exfiltrator probe in a subprocess.

    Creates a DomainParticipant from the XML config, subscribes to t/Vitals,
    and returns a dict with:
      - "created": bool — whether the participant was created successfully
      - "matched": bool — whether subscription_matched_status.current_count > 0
      - "received": int — number of vitals samples received
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
    count = 0
    while time.monotonic() < deadline:
        if vitals_dr.subscription_matched_status.current_count > 0:
            result["matched"] = True
        for s in vitals_dr.take():
            if s.info.valid:
                count += 1
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
        return {"created": False, "matched": False, "received": 0, "error": proc.stderr}
    # Parse only the last line — DDS may print log messages to stdout
    lines = [line for line in proc.stdout.strip().splitlines() if line.startswith("{")]
    if not lines:
        return {"created": False, "matched": False, "received": 0, "error": "No JSON output"}
    return json.loads(lines[-1])


# ---------------------------------------------------------------------------
# Tests against unsecured OR apps
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestExfiltratorUnsecure:
    """Exfiltrator should read vitals from unsecured OR apps."""

    def test_unsecure_exfiltration_succeeds(self, or_pm_nonsecure, or_env_nonsecure, threat_env):
        """Unsecured exfiltrator should receive vitals from unsecured OR apps."""
        or_pm_nonsecure.start_module01_cpp("PatientSensor")
        time.sleep(3)

        result = _run_exfiltrator_probe(
            threat_env,
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/Unsecure",
        )
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        assert result["matched"], "Unsecured exfiltrator did not match unsecured OR apps"
        assert result["received"] >= 1, "Exfiltrator received no vitals"


# ---------------------------------------------------------------------------
# Tests against secured OR apps
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestExfiltratorSecure:
    """Security should block threat exfiltrator from reading vitals."""

    @pytest.mark.xfail(
        bool(os.environ.get("CI")),
        reason="Transport-dependent: unsecured discovery of secured participant may not work on CI",
    )
    def test_unsecure_exfiltrator_vs_secure_or(self, or_pm_secure, or_env_secure, threat_env):
        """Unsecured exfiltrator against secured OR apps.

        Note: The governance uses data_protection_kind=NONE (only
        rtps_protection_kind=ENCRYPT).  On the loopback/shared-memory
        transports an unauthenticated participant that never initiates the
        security handshake can still discover and read plaintext data
        samples.  This test therefore asserts the *observed* behaviour:
        the unsecured exfiltrator successfully reads vitals.

        To fully block unauthenticated readers, set
        data_protection_kind=ENCRYPT in the governance.
        """
        or_pm_secure.start_module01_cpp("PatientSensor")
        time.sleep(5)

        result = _run_exfiltrator_probe(
            threat_env,
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/Unsecure",
            timeout_sec=15,
        )
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        # On loopback, unsecured exfiltrator can still read because
        # data_protection_kind is NONE — only RTPS-level encryption is enabled.
        assert result["matched"], (
            "Unsecured exfiltrator should match secured OR on loopback (data_protection_kind=NONE in governance)"
        )

    def test_rogue_ca_exfiltrator_blocked(self, or_pm_secure, or_env_secure, threat_env):
        """Rogue CA exfiltrator should NOT receive vitals from secured OR apps."""
        or_pm_secure.start_module01_cpp("PatientSensor")
        time.sleep(3)

        result = _run_exfiltrator_probe(
            threat_env,
            dp_name="ThreatParticipantLibrary::dp/ThreatExfiltrator/RogueCA",
            timeout_sec=10,
        )
        assert result["received"] == 0, "Rogue CA exfiltrator should NOT receive vitals from secured OR"
