#!/usr/bin/env python3
"""Generate security artifacts for Module 04 — Security Threat.

Must be run from the ``modules/04-security-threat/security/`` directory::

    cd modules/04-security-threat/security
    python3 setup_threat_security.py

Prerequisite: ``system_arch/security/setup_security.py`` must have been run
first so that the trusted CA artifacts exist.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TRUSTED_CA_DIR = SCRIPT_DIR / ".." / ".." / ".." / "system_arch" / "security"

# Add system_arch/scripts/ to the import path for platform_setup
sys.path.insert(0, str(SCRIPT_DIR / ".." / ".." / ".." / "system_arch" / "scripts"))
import platform_setup


def _run(cmd: "list[str]", env: dict) -> None:
    subprocess.run(cmd, env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    openssl, env = platform_setup.find_openssl()
    # Export TRUSTED_CA_DIR for expired/ca.cnf which uses relative paths
    env["TRUSTED_CA_DIR"] = str(TRUSTED_CA_DIR)

    # Verify trusted CA artifacts exist
    ca_cert = TRUSTED_CA_DIR / "ca" / "CaIdentity.pem"
    ca_key = TRUSTED_CA_DIR / "ca" / "private" / "CaPrivateKey.pem"
    if not ca_cert.is_file() or not ca_key.is_file():
        print(
            f"ERROR: Trusted CA artifacts not found at {TRUSTED_CA_DIR / 'ca'}/\n"
            "Please run system_arch/security/setup_security.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Temporary extensions file for identity certs
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".cnf", delete=False
    ) as ext_file:
        ext_file.write("keyUsage = critical, digitalSignature\n")
        identity_ext = ext_file.name

    try:
        print("=== Generating Module 04 Security Artifacts ===")

        # ─── 1. Rogue CA (self-signed) ────────────────────────────────
        print("--- Generating Rogue CA...")
        Path("rogue_ca/private").mkdir(parents=True, exist_ok=True)
        _run(
            [
                openssl, "ecparam", "-name", "prime256v1",
                "-genkey", "-noout",
                "-out", "rogue_ca/private/RogueCaPrivateKey.pem",
            ],
            env,
        )
        _run(
            [
                openssl, "req", "-new", "-x509", "-days", "1825",
                "-text", "-sha256",
                "-key", "rogue_ca/private/RogueCaPrivateKey.pem",
                "-out", "rogue_ca/RogueCaIdentity.pem",
                "-config", "rogue_ca/RogueCa.cnf",
            ],
            env,
        )

        # ─── 2. RogueCA identities (signed by rogue CA) ───────────────
        print("--- Generating Rogue CA identities...")
        for participant in ("ThreatInjector", "ThreatExfiltrator"):
            base = f"identities/{participant}/{participant}"
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
                    "-extfile", identity_ext,
                    "-CA", "rogue_ca/RogueCaIdentity.pem",
                    "-CAkey", "rogue_ca/private/RogueCaPrivateKey.pem",
                    "-CAcreateserial",
                    "-in", f"{base}.csr",
                    "-out", f"{base}Identity.pem",
                ],
                env,
            )
            Path(f"{base}.csr").unlink(missing_ok=True)

        # Sign rogue-org permissions with rogue CA
        _run(
            [
                openssl, "smime", "-sign",
                "-in", "xml/PermissionsRogueCAInjector.xml",
                "-text",
                "-out", "identities/ThreatInjector/SignedPermissionsRogueCAInjector.p7s",
                "-signer", "rogue_ca/RogueCaIdentity.pem",
                "-inkey", "rogue_ca/private/RogueCaPrivateKey.pem",
            ],
            env,
        )
        _run(
            [
                openssl, "smime", "-sign",
                "-in", "xml/PermissionsRogueCAExfiltrator.xml",
                "-text",
                "-out", "identities/ThreatExfiltrator/SignedPermissionsRogueCAExfiltrator.p7s",
                "-signer", "rogue_ca/RogueCaIdentity.pem",
                "-inkey", "rogue_ca/private/RogueCaPrivateKey.pem",
            ],
            env,
        )

        # Sign governance with rogue CA
        Path("xml/signed").mkdir(parents=True, exist_ok=True)
        _run(
            [
                openssl, "smime", "-sign",
                "-in", "xml/GovernanceDomain0.xml",
                "-text",
                "-out", "xml/signed/SignedGovernanceDomain0RogueCA.p7s",
                "-signer", "rogue_ca/RogueCaIdentity.pem",
                "-inkey", "rogue_ca/private/RogueCaPrivateKey.pem",
            ],
            env,
        )

        # ─── 3. ForgedPerms identities (signed by TRUSTED CA) ─────────
        print("--- Generating ForgedPerms identities (trusted CA signed)...")
        for participant in ("ThreatInjector", "ThreatExfiltrator"):
            base = f"forged_perms/{participant}/{participant}"
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
                    "-extfile", identity_ext,
                    "-CA", str(ca_cert),
                    "-CAkey", str(ca_key),
                    "-CAcreateserial",
                    "-in", f"{base}.csr",
                    "-out", f"{base}Identity.pem",
                ],
                env,
            )
            Path(f"{base}.csr").unlink(missing_ok=True)

        # Sign permissions with ROGUE CA (this is the "forged" part)
        for participant in ("ThreatInjector", "ThreatExfiltrator"):
            _run(
                [
                    openssl, "smime", "-sign",
                    "-in", f"xml/Permissions{participant}.xml",
                    "-text",
                    "-out", f"forged_perms/{participant}/SignedPermissions{participant}.p7s",
                    "-signer", "rogue_ca/RogueCaIdentity.pem",
                    "-inkey", "rogue_ca/private/RogueCaPrivateKey.pem",
                ],
                env,
            )

        # ─── 4. Expired cert identities ───────────────────────────────
        print("--- Generating Expired Certificate identities...")
        for f in ("expired/index.txt", "expired/index.txt.attr", "expired/serial"):
            Path(f).unlink(missing_ok=True)
        Path("expired/index.txt").touch()
        Path("expired/serial").write_text("1000\n")
        Path("expired/newcerts").mkdir(parents=True, exist_ok=True)

        for participant in ("ThreatInjector", "ThreatExfiltrator"):
            base = f"expired/{participant}/{participant}Expired"
            _run(
                [
                    openssl, "req", "-nodes", "-new", "-newkey", "rsa:2048",
                    "-config", f"{base}.cnf",
                    "-keyout", f"expired/{participant}/{participant}PrivateKey.pem",
                    "-out", f"{base}.csr",
                ],
                env,
            )
            _run(
                [
                    openssl, "ca", "-batch",
                    "-config", "expired/ca.cnf",
                    "-startdate", "20200101000000Z",
                    "-enddate", "20220101000000Z",
                    "-in", f"{base}.csr",
                    "-out", f"{base}Identity.pem",
                ],
                env,
            )
            Path(f"{base}.csr").unlink(missing_ok=True)

        # Sign permissions with trusted CA for ExpiredCert mode
        for participant in ("ThreatInjector", "ThreatExfiltrator"):
            _run(
                [
                    openssl, "smime", "-sign",
                    "-in", f"xml/Permissions{participant}.xml",
                    "-text",
                    "-out", f"expired/{participant}/SignedPermissions{participant}.p7s",
                    "-signer", str(ca_cert),
                    "-inkey", str(ca_key),
                ],
                env,
            )

        # Sign governance with trusted CA (for ForgedPerms and ExpiredCert modes)
        _run(
            [
                openssl, "smime", "-sign",
                "-in", "xml/GovernanceDomain0.xml",
                "-text",
                "-out", "xml/signed/SignedGovernanceDomain0.p7s",
                "-signer", str(ca_cert),
                "-inkey", str(ca_key),
            ],
            env,
        )

        print("=== Security artifact generation complete ===")
        print()
        print("Generated artifacts:")
        print("  rogue_ca/RogueCaIdentity.pem                          (self-signed rogue CA)")
        print("  identities/ThreatInjector/ThreatInjectorIdentity.pem  (rogue-CA-signed)")
        print("  identities/ThreatExfiltrator/ThreatExfiltratorIdentity.pem (rogue-CA-signed)")
        print("  forged_perms/ThreatInjector/ThreatInjectorIdentity.pem     (trusted-CA-signed)")
        print("  forged_perms/ThreatInjector/SignedPermissionsThreatInjector.p7s (rogue-CA-signed!)")
        print("  expired/ThreatInjector/ThreatInjectorExpiredIdentity.pem    (trusted-CA-signed, EXPIRED)")
        print("  xml/signed/SignedGovernanceDomain0.p7s                (trusted-CA-signed)")
        print("  xml/signed/SignedGovernanceDomain0RogueCA.p7s         (rogue-CA-signed)")

    finally:
        os.unlink(identity_ext)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"OpenSSL command failed (exit code {exc.returncode})", file=sys.stderr)
        sys.exit(exc.returncode)
