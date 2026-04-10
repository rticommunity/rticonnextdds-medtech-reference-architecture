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
participant in a subprocess and checks the publication_matched_status to
determine whether data can flow.
"""

import json
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


def _run_injector_probe(
    env: dict,
    dp_name: str,
    timeout_sec: float = 12.0,
) -> dict:
    """Launch a threat injector probe in a subprocess.

    Creates a DomainParticipant from the XML config, writes a few motor
    control samples, and returns a dict with:
      - "created": bool — whether the participant was created successfully
      - "matched": bool — whether publication_matched_status.current_count > 0
    """
    script = f"""\
import sys, time, json
sys.path.insert(0, "{OR_SRC_DIR}")
sys.path.insert(0, "{THREAT_SRC_DIR}")
import rti.connextdds as dds
from Types import DdsEntities

result = {{"created": False, "matched": False}}
try:
    provider = dds.QosProvider.default
    participant = provider.create_participant_from_config("{dp_name}")
    result["created"] = True

    # Use DynamicData writer since create_participant_from_config creates
    # untyped entities.
    cmd_dw = dds.DynamicData.DataWriter(
        participant.find_datawriter(DdsEntities.Constants.DEVICE_COMMAND_DW)
    )

    # Create a DynamicData sample from the provider's type definition
    cmd_type = provider.type("Orchestrator::DeviceCommand")
    sample = dds.DynamicData(cmd_type)
    sample["device"] = 5  # PATIENT_SENSOR enum value
    sample["command"] = 2  # PAUSE enum value

    deadline = time.monotonic() + {timeout_sec}
    while time.monotonic() < deadline:
        try:
            cmd_dw.write(sample)
        except Exception:
            pass
        if cmd_dw.publication_matched_status.current_count > 0:
            result["matched"] = True
            break
        time.sleep(0.5)

    participant.close()
except dds.Error as exc:
    result["error"] = str(exc)
except Exception as exc:
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
        return {"created": False, "matched": False, "error": proc.stderr}
    # Parse only the last line — DDS may print log messages to stdout
    lines = [line for line in proc.stdout.strip().splitlines() if line.startswith("{")]
    if not lines:
        return {"created": False, "matched": False, "error": "No JSON output"}
    return json.loads(lines[-1])


# ---------------------------------------------------------------------------
# Tests against unsecured OR apps
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestInjectorUnsecure:
    """Injector should match unsecured OR apps (no DDS Security)."""

    def test_unsecure_injection_succeeds(self, or_pm_nonsecure, or_env_nonsecure, threat_env):
        """Unsecured injector should match unsecured OR apps."""
        sensor = or_pm_nonsecure.start_module01_cpp("PatientSensor")
        time.sleep(5)
        assert sensor.poll() is None, f"PatientSensor exited early with code {sensor.returncode}"

        result = _run_injector_probe(
            threat_env,
            dp_name="ThreatParticipantLibrary::dp/ThreatInjector/Unsecure",
        )
        assert result["created"], f"Participant creation failed: {result.get('error')}"
        assert result["matched"], "Unsecured injector did not match unsecured OR apps"


# ---------------------------------------------------------------------------
# Tests against secured OR apps
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestInjectorSecure:
    """Security should block threat injector participants from matching secured OR apps."""

    def test_rogue_ca_injection_blocked(self, or_pm_secure, or_env_secure, threat_env):
        """Injector with rogue CA identity should not match secured OR apps."""
        or_pm_secure.start_module01_cpp("PatientSensor")
        time.sleep(3)

        result = _run_injector_probe(
            threat_env,
            dp_name="ThreatParticipantLibrary::dp/ThreatInjector/RogueCA",
            timeout_sec=10,
        )
        # The participant may be created but should NOT match
        assert not result["matched"], "Rogue CA injector should NOT match secured OR apps"

    def test_forged_perms_injection_blocked(self, or_pm_secure, or_env_secure, threat_env):
        """Injector with forged permissions should not match secured OR apps."""
        or_pm_secure.start_module01_cpp("PatientSensor")
        time.sleep(3)

        result = _run_injector_probe(
            threat_env,
            dp_name="ThreatParticipantLibrary::dp/ThreatInjector/ForgedPerms",
            timeout_sec=10,
        )
        assert not result["matched"], "Forged permissions injector should NOT match secured OR apps"

    def test_expired_cert_injection_fails(self, or_pm_secure, or_env_secure, threat_env):
        """Injector with expired certificate should fail to create participant or match."""
        or_pm_secure.start_module01_cpp("PatientSensor")
        time.sleep(3)

        result = _run_injector_probe(
            threat_env,
            dp_name="ThreatParticipantLibrary::dp/ThreatInjector/ExpiredCert",
            timeout_sec=10,
        )
        # Expired cert typically causes participant creation failure
        if result["created"]:
            assert not result["matched"], "Expired cert injector should NOT match secured OR apps"
        # If not created, that's also a valid block
