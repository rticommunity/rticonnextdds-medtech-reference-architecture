"""Shared environment setup for Module 04 — Security Threat.

Import and call ``setup_env()`` from launcher scripts.
"""

import os
import sys
from pathlib import Path

# Paths are relative to modules/04-security-threat/ working directory.
_QOS_FILE = Path("../../system_arch/qos/Qos.xml")
_DOMAIN_LIBRARY_FILE = Path("../../system_arch/xml_app_creation/DomainLibrary.xml")
_THREAT_QOS_FILE = Path("./xml_config/ThreatQos.xml")
_THREAT_PARTICIPANT_LIBRARY_FILE = Path("./xml_config/ThreatParticipants.xml")


def setup_env() -> dict:
    """Return an environment dict with QoS profiles and security artifact paths."""
    # ThreatQos.xml must come before ThreatParticipants.xml so that the
    # DpQosLib profiles are defined before the participant library references them.
    profiles = ";".join(
        str(p)
        for p in [
            _QOS_FILE,
            _DOMAIN_LIBRARY_FILE,
            _THREAT_QOS_FILE,
            _THREAT_PARTICIPANT_LIBRARY_FILE,
        ]
    )

    env = os.environ.copy()
    env["NDDS_QOS_PROFILES"] = profiles

    # Default security artifact directories (can be overridden by environment)
    env.setdefault("THREAT_SECURITY_ARTIFACTS_DIR", "./security")
    env.setdefault("RTI_SECURITY_ARTIFACTS_DIR", "../../system_arch/security")

    return env
