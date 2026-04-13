#!/usr/bin/env python3
"""Generate security artifacts for Module 04 — Security Threat.

Usage::

    # Generate all threat-module security artifacts
    python3 setup_threat_security.py

    # Re-generate even if artifacts already exist
    python3 setup_threat_security.py --force

    # (Maintainer-only) Scaffold directory tree from templates
    python3 setup_threat_security.py --scaffold

Prerequisite: ``system_arch/security/setup_security.py`` must have been run
first so that the trusted CA artifacts exist.
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).parent.parent.resolve()
PROJECT_ROOT = MODULE_DIR.parent.parent.resolve()
MAIN_SECURITY_DIR = PROJECT_ROOT / "system_arch" / "security"
MODULE_SECURITY_DIR = MODULE_DIR / "security"

# Add the main security dir to the import path
sys.path.insert(0, str(MAIN_SECURITY_DIR))

from security_tree import (
    CA,
    App,
    DomainScope,
    Governance,
    Identity,
    Module,
    Permissions,
    SecurityTree,
    TopicRule,
    scaffold_tree,
)
from dds_security import generate_expired_identity

# ---------------------------------------------------------------------------
# Certificate authorities
# ---------------------------------------------------------------------------

# Self-signed CA representing an untrusted adversary (local to this module)
ROGUE_CA = CA(name="RogueCa")

# Reference the main project's trusted CAs by absolute path so generate_artifacts
# finds their existing key/cert without re-generating them.
TRUSTED_ROOT_CA = CA(
    name="TrustedRootCa",
    path=MAIN_SECURITY_DIR / "ca" / "TrustedRootCa",
)
TRUSTED_PERMISSIONS_CA = CA(
    name="TrustedPermissionsCa",
    issuer=TRUSTED_ROOT_CA,
    path=MAIN_SECURITY_DIR / "ca" / "TrustedPermissionsCa",
)
TRUSTED_IDENTITY_CA = CA(
    name="TrustedIdentityCa",
    issuer=TRUSTED_ROOT_CA,
    path=MAIN_SECURITY_DIR / "ca" / "TrustedIdentityCa",
)

# ---------------------------------------------------------------------------
# Domain scopes
#
# The same ThreatDomain XML is signed by two CAs to enable the four threat
# demonstrations:
#   Threat 1 — Unauthorized subscriber  (TrustedIdentityCa identity  + TrustedPermissionsCa permissions)
#   Threat 2 — Unauthorized publisher   (TrustedIdentityCa identity  + TrustedPermissionsCa permissions)
#   Threat 3 — Tampered permissions     (TrustedIdentityCa identity  + RogueCa-signed permissions)
#   Threat 4 — Tampered governance      (TrustedIdentityCa identity  + RogueCa-signed governance)
# ---------------------------------------------------------------------------

# Governance overrides for the threat module: no LogTopicV2 rule (threat apps
# don't use the security log topic) and protection kinds set to NONE to match
# the project's previous configuration.
_THREAT_GOV_KWARGS = dict(
    name="ThreatDomain",
    discovery_protection_kind="NONE",
    liveliness_protection_kind="NONE",
    topic_rules=[TopicRule(topic_expression="*")],
)

THREAT_DOMAIN_TRUSTED = DomainScope(
    name="ThreatDomain",
    governance=Governance(issuer=TRUSTED_PERMISSIONS_CA, **_THREAT_GOV_KWARGS),
    permissions=[
        Permissions(
            name="ThreatInjector", issuer=TRUSTED_PERMISSIONS_CA,
            publish_topics=["t/MotorControl", "t/DeviceCommand"],
            subscribe_topics=["t/MotorControl", "t/DeviceCommand"],
        ),
        Permissions(
            name="ThreatExfiltrator", issuer=TRUSTED_PERMISSIONS_CA,
            publish_topics=[],
            subscribe_topics=["t/Vitals"],
        ),
    ],
)

THREAT_DOMAIN_ROGUE = DomainScope(
    name="ThreatDomain",
    governance=Governance(issuer=ROGUE_CA, **_THREAT_GOV_KWARGS),
    permissions=[
        Permissions(
            name="ThreatInjector", issuer=ROGUE_CA,
            publish_topics=["t/MotorControl", "t/DeviceCommand"],
            subscribe_topics=["t/MotorControl", "t/DeviceCommand"],
        ),
        Permissions(
            name="ThreatExfiltrator", issuer=ROGUE_CA,
            publish_topics=[],
            subscribe_topics=["t/Vitals"],
        ),
    ],
)

# ---------------------------------------------------------------------------
# Modules — each identity is signed by both CAs
# ---------------------------------------------------------------------------

SECURITY_THREAT = Module(
    name="security-threat",
    apps=[
        App(name="ThreatInjector", identities=[
            Identity(name="ThreatInjector", issuer=TRUSTED_IDENTITY_CA),
            Identity(name="ThreatInjector", issuer=ROGUE_CA),
        ]),
        App(name="ThreatExfiltrator", identities=[
            Identity(name="ThreatExfiltrator", issuer=TRUSTED_IDENTITY_CA),
            Identity(name="ThreatExfiltrator", issuer=ROGUE_CA),
        ]),
    ],
)

# ---------------------------------------------------------------------------
# Security tree
# ---------------------------------------------------------------------------

SECURITY_TREE = SecurityTree(
    # Only ROGUE_CA is generated here; trusted CAs are resolved via their path.
    certificate_authorities=[ROGUE_CA],
    domain_scopes=[THREAT_DOMAIN_TRUSTED, THREAT_DOMAIN_ROGUE],
    modules=[SECURITY_THREAT],
    org_name="Malicious Company Name",
    country="US",
    state="CA",
    email_domain="malicious_company_name.com",
)


def main():
    parser = argparse.ArgumentParser(
        description="Generate security artifacts for the security threat module.")
    parser.add_argument("--scaffold", action="store_true",
                        help="(Maintainer-only) Scaffold the directory tree from templates.")
    parser.add_argument("--force", action="store_true",
                        help="Re-generate artifacts even if they already exist.")
    parser.add_argument("--strict", action="store_true",
                        help="Promote warnings to fatal errors.")
    parser.add_argument("--status", action="store_true",
                        help="Report certificate expiry status and exit.")
    parser.add_argument("--warn-days", type=int, default=30,
                        help="Days-to-expiry warning threshold for --status (default: 30).")
    args = parser.parse_args()

    if args.status:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
        SECURITY_TREE.check_status(root=MODULE_SECURITY_DIR, warn_days=args.warn_days)
    elif args.scaffold:
        scaffold_tree(SECURITY_TREE, root=MODULE_SECURITY_DIR,
                      templates_dir=MAIN_SECURITY_DIR / "templates",
                      strict=args.strict)
    else:
        SECURITY_TREE.generate_artifacts(
            root=MODULE_SECURITY_DIR, force=args.force, strict=args.strict)

        # Generate expired identity certs for the ExpiredCert attack mode.
        # These are signed by the TrustedIdentityCa (so the CA chain is
        # valid) but have notAfter in the past, causing Connext to reject
        # them at participant creation time.
        for app_name in ("ThreatInjector", "ThreatExfiltrator"):
            id_dir = (MODULE_SECURITY_DIR / "identity" / "security-threat"
                      / app_name / app_name)
            expired_cert = (id_dir / "certs" / "TrustedIdentityCa"
                            / "expired" / f"{app_name}.crt")
            generate_expired_identity(
                key_path=id_dir / "private" / f"{app_name}.key",
                cnf=id_dir / f"{app_name}.cnf",
                out_cert=expired_cert,
                issuer_cnf=(MAIN_SECURITY_DIR / "ca" / "TrustedIdentityCa"
                            / "TrustedIdentityCa.cnf"),
                issuer_key=(MAIN_SECURITY_DIR / "ca" / "TrustedIdentityCa"
                            / "private" / "TrustedIdentityCa.key"),
                issuer_cert=(MAIN_SECURITY_DIR / "ca" / "TrustedIdentityCa"
                             / "certs" / "TrustedRootCa"
                             / "TrustedIdentityCa.crt"),
                issuer_cwd=MAIN_SECURITY_DIR / "ca" / "TrustedIdentityCa",
                force=args.force,
            )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        print("STDOUT:", e.stdout.decode() if e.stdout else "")
        print("STDERR:", e.stderr.decode() if e.stderr else "")
        raise