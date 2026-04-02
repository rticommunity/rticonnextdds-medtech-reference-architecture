"""XML / QoS environment setup for Module 03 — Remote Teleoperation."""

import os
import sys
from pathlib import Path

# Add system_arch/scripts/ to the import path for platform_setup
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR / ".." / ".." / ".." / "system_arch" / "scripts"))
import platform_setup

_SYSTEM_ARCH = Path("../../system_arch")


def setup_env(security: bool = False) -> dict:
    """Return an environment dict with ``NDDS_QOS_PROFILES`` set."""
    platform_setup.check_nddshome()

    qos_file = _SYSTEM_ARCH / "qos/Qos.xml"

    if security:
        print("Launching applications with Security...")
        apps_qos = _SYSTEM_ARCH / "qos/SecureAppsQos.xml"
    else:
        print("Launching applications without Security...")
        apps_qos = _SYSTEM_ARCH / "qos/NonSecureAppsQos.xml"

    env = os.environ.copy()
    env["NDDS_QOS_PROFILES"] = ";".join(str(p) for p in [qos_file, apps_qos])
    return env
