"""XML / QoS environment setup for Module 01 — Digital Operating Room.

Call ``setup_env()`` to obtain an environment dict with
``NDDS_QOS_PROFILES`` and native library paths configured.
"""

import os
import sys
from pathlib import Path

# Add system_arch/scripts/ to the import path for platform_setup
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR / ".." / ".." / ".." / "system_arch" / "scripts"))
import platform_setup

# Paths are relative to modules/01-operating-room/ working directory.
_SYSTEM_ARCH = Path("../../system_arch")
_QOS_FILE = _SYSTEM_ARCH / "qos/Qos.xml"
_DOMAIN_LIBRARY_FILE = _SYSTEM_ARCH / "xml_app_creation/DomainLibrary.xml"
_PARTICIPANT_LIBRARY_FILE = _SYSTEM_ARCH / "xml_app_creation/ParticipantLibrary.xml"


def setup_env(security: bool = False) -> dict:
    """Build and return an environment dict for launching applications.

    * Checks that ``NDDSHOME`` is set.
    * Sets ``NDDS_QOS_PROFILES`` according to *security*.
    * Adds Connext and OpenSSL library directories to the platform's
      dynamic-library search path.
    """
    nddshome = platform_setup.check_nddshome()

    if security:
        print("Launching applications with Security...")
        apps_qos = _SYSTEM_ARCH / "qos/SecureAppsQos.xml"
    else:
        print("Launching applications without Security...")
        apps_qos = _SYSTEM_ARCH / "qos/NonSecureAppsQos.xml"

    profiles = ";".join(
        str(p)
        for p in [_QOS_FILE, apps_qos, _DOMAIN_LIBRARY_FILE, _PARTICIPANT_LIBRARY_FILE]
    )

    env = os.environ.copy()
    env["NDDS_QOS_PROFILES"] = profiles
    platform_setup.setup_library_env(env, nddshome)

    return env
