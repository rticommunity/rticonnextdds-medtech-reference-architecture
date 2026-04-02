#!/usr/bin/env python3
"""Generate DDS Security artifacts for the reference architecture.

Run from the ``system_arch/security/`` directory::

    cd system_arch/security
    python3 setup_security.py

Prerequisite: ``NDDSHOME`` must be set to the Connext installation path.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Add system_arch/scripts/ to the import path for platform_setup
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR / ".." / "scripts"))
import platform_setup


def _run(cmd: "list[str]", env: dict) -> None:
    subprocess.run(cmd, env=env, check=True)


# ---------------------------------------------------------------------------
# Certificate generation helpers
# ---------------------------------------------------------------------------

def generate_identities(
    openssl: str,
    env: dict,
    identity_ext: str,
    module: str,
    participants: "list[str]",
) -> None:
    """Generate private keys and CA-signed identity certs for *participants*."""
    for participant in participants:
        base = f"identities/{module}/{participant}/{participant}"
        _run(
            [
                openssl, "req", "-nodes", "-new", "-newkey", "rsa:2048",
                "-config", f"{base}.cnf",
                "-keyout", f"{base}PrivateKey.pem",
                "-out", f"{base}.csr",
            ],
            env,
        )
        _run(
            [
                openssl, "x509", "-req", "-days", "730", "-text",
                "-CAcreateserial",
                "-extfile", identity_ext,
                "-CA", "ca/CaIdentity.pem",
                "-CAkey", "ca/private/CaPrivateKey.pem",
                "-in", f"{base}.csr",
                "-out", f"{base}Identity.pem",
            ],
            env,
        )


def sign_xmls(openssl: str, env: dict, xml_names: "list[str]") -> None:
    """Sign Governance and Permissions XMLs with S/MIME."""
    for xml in xml_names:
        basename = Path(xml).name
        _run(
            [
                openssl, "smime", "-sign",
                "-in", f"xml/{xml}.xml",
                "-text",
                "-out", f"xml/signed/Signed{basename}.p7s",
                "-signer", "ca/CaIdentity.pem",
                "-inkey", "ca/private/CaPrivateKey.pem",
            ],
            env,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    openssl, env = platform_setup.find_openssl()

    # Temporary extensions file for identity (end-entity) certificates.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".cnf", delete=False
    ) as ext_file:
        ext_file.write("keyUsage = critical, digitalSignature\n")
        identity_ext = ext_file.name

    try:
        # Self-signed CA
        _run(
            [
                openssl, "req", "-nodes", "-x509", "-days", "1825",
                "-text", "-sha256",
                "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
                "-keyout", "ca/private/CaPrivateKey.pem",
                "-out", "ca/CaIdentity.pem",
                "-config", "ca/Ca.cnf",
                "-extensions", "v3_ca",
            ],
            env,
        )

        # Generate identities per module
        generate_identities(
            openssl, env, identity_ext,
            "01-operating-room",
            ["Arm", "ArmController", "Orchestrator", "PatientMonitor",
             "PatientSensor", "SecureLogReader"],
        )
        generate_identities(
            openssl, env, identity_ext,
            "02-record-playback",
            ["RecordingService", "ReplayService"],
        )
        generate_identities(
            openssl, env, identity_ext,
            "03-remote-teleoperation",
            ["RsActive", "RsCloud", "RsPassive"],
        )

        # Sign Governance and Permissions files
        sign_xmls(openssl, env, [
            "GovernanceDomain0",
            "GovernanceDomain1",
            "01-operating-room/PermissionsArm",
            "01-operating-room/PermissionsArmController",
            "01-operating-room/PermissionsOrchestrator",
            "01-operating-room/PermissionsPatientMonitor",
            "01-operating-room/PermissionsPatientSensor",
            "01-operating-room/PermissionsSecureLogReader",
            "02-record-playback/PermissionsRecordingService",
            "02-record-playback/PermissionsReplayService",
            "03-remote-teleoperation/PermissionsRsActive",
            "03-remote-teleoperation/PermissionsRsCloud",
            "03-remote-teleoperation/PermissionsRsPassive",
        ])

        # Clean up CSR files
        for csr in Path("identities").rglob("*.csr"):
            csr.unlink()

    finally:
        os.unlink(identity_ext)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"OpenSSL command failed (exit code {exc.returncode})", file=sys.stderr)
        sys.exit(exc.returncode)
