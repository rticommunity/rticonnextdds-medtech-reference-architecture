#!/usr/bin/env python3
"""Generate DDS Security artifacts for the reference architecture.

Usage::

    # Generate all security artifacts (keys, certs, signed XML)
    python3 setup_security.py

    # Re-generate even if artifacts already exist
    python3 setup_security.py --force

    # (Maintainer-only) Scaffold the directory tree from templates.
    # Run this once when adding new CAs, identities, or domain scopes,
    # then hand-edit the generated config/XML files as needed before
    # committing them to the repo.
    python3 setup_security.py --scaffold

Prerequisite: ``NDDSHOME`` must be set to the Connext installation path.
"""

import argparse
import logging
import subprocess
from pathlib import Path

from security_tree import (
    CA,
    App,
    DomainScope,
    Governance,
    Identity,
    Module,
    Permissions,
    PskSeed,
    SecurityTree,
    detect_connext_version,
    scaffold_tree,
)

SECURITY_DIR = Path(__file__).parent.resolve()

# ---------------------------------------------------------------------------
# Certificate authorities
# ---------------------------------------------------------------------------

TRUSTED_ROOT_CA = CA(name="TrustedRootCa")
TRUSTED_PERMISSIONS_CA = CA(name="TrustedPermissionsCa", issuer=TRUSTED_ROOT_CA)
TRUSTED_IDENTITY_CA = CA(name="TrustedIdentityCa", issuer=TRUSTED_ROOT_CA)

# ---------------------------------------------------------------------------
# Domain scopes (governance + permissions)
# ---------------------------------------------------------------------------

OPERATIONAL_DOMAIN = DomainScope(
    name="OperationalDomain",
    governance=Governance(
        name="OperationalDomain", issuer=TRUSTED_PERMISSIONS_CA,
        # Explicitly NONE: the reference architecture does not protect
        # discovery or liveliness metadata (RTPS payload is encrypted).
        discovery_protection_kind="NONE",
        liveliness_protection_kind="NONE",
    ),
    permissions=[
        Permissions(name="Arm", issuer=TRUSTED_PERMISSIONS_CA,
                    publish_topics=["t/DeviceStatus", "t/DeviceHeartbeat",
                                    "DDS:Security:LogTopicV2"],
                    subscribe_topics=["t/MotorControl", "t/DeviceCommand"]),
        Permissions(name="ArmController", issuer=TRUSTED_PERMISSIONS_CA,
                    publish_topics=["t/MotorControl", "t/DeviceStatus",
                                    "t/DeviceHeartbeat",
                                    "DDS:Security:LogTopicV2"],
                    subscribe_topics=["t/DeviceCommand"]),
        Permissions(name="Orchestrator", issuer=TRUSTED_PERMISSIONS_CA,
                    publish_topics=["t/DeviceCommand",
                                    "DDS:Security:LogTopicV2"],
                    subscribe_topics=["t/DeviceStatus", "t/DeviceHeartbeat"]),
        Permissions(name="PatientMonitor", issuer=TRUSTED_PERMISSIONS_CA,
                    publish_topics=["t/DeviceStatus", "t/DeviceHeartbeat",
                                    "DDS:Security:LogTopicV2"],
                    subscribe_topics=["t/DeviceCommand", "t/Vitals"]),
        Permissions(name="PatientSensor", issuer=TRUSTED_PERMISSIONS_CA,
                    publish_topics=["t/Vitals", "t/DeviceStatus",
                                    "t/DeviceHeartbeat",
                                    "DDS:Security:LogTopicV2"],
                    subscribe_topics=["t/DeviceCommand"]),
        Permissions(name="SecureLogReader", issuer=TRUSTED_PERMISSIONS_CA,
                    publish_topics=[],
                    subscribe_topics=["DDS:Security:LogTopicV2"]),
        Permissions(name="RecordingService", issuer=TRUSTED_PERMISSIONS_CA),
        Permissions(name="ReplayService", issuer=TRUSTED_PERMISSIONS_CA),
        Permissions(name="RsActiveLan", issuer=TRUSTED_PERMISSIONS_CA),
        Permissions(name="RsPassiveLan", issuer=TRUSTED_PERMISSIONS_CA),
    ],
)

TELEOP_WAN_DOMAIN = DomainScope(
    name="TeleopWanDomain",
    governance=Governance(
        name="TeleopWanDomain", issuer=TRUSTED_PERMISSIONS_CA,
        discovery_protection_kind="NONE",
        liveliness_protection_kind="NONE",
    ),
    permissions=[
        Permissions(name="RsActiveWan",  issuer=TRUSTED_PERMISSIONS_CA),
        Permissions(name="RsPassiveWan", issuer=TRUSTED_PERMISSIONS_CA),
        Permissions(name="RsCloudWan",   issuer=TRUSTED_PERMISSIONS_CA),
    ],
    psk_seeds=[
        # PSK seed for the WAN (TeleopWanDomain) domain.
        # Loaded by CDS and all WAN RS participants via
        # dds.sec.crypto.rtps_psk_secret_passphrase = file:<scope>/TeleopWanDomain.psk
        # Increment 'id' on every rotation (never reuse). Valid range: 0-254 for 7.3.x.
        PskSeed(filename="TeleopWanDomain.psk"),
    ],
)

# ---------------------------------------------------------------------------
# Modules (applications + participant identities)
# ---------------------------------------------------------------------------

OPERATING_ROOM = Module(
    name="operating-room",
    apps=[
        App(name="Arm",
            identities=[Identity(name="Arm",             issuer=TRUSTED_IDENTITY_CA)]),
        App(name="ArmController",
            identities=[Identity(name="ArmController",   issuer=TRUSTED_IDENTITY_CA)]),
        App(name="Orchestrator",
            identities=[Identity(name="Orchestrator",    issuer=TRUSTED_IDENTITY_CA),
                        Identity(name="SecureLogReader", issuer=TRUSTED_IDENTITY_CA)]),
        App(name="PatientMonitor",
            identities=[Identity(name="PatientMonitor",  issuer=TRUSTED_IDENTITY_CA)]),
        App(name="PatientSensor",
            identities=[Identity(name="PatientSensor",   issuer=TRUSTED_IDENTITY_CA)]),
    ],
)

RECORD_PLAYBACK = Module(
    name="record-playback",
    apps=[
        App(name="RecordingService",
            identities=[Identity(name="RecordingService", issuer=TRUSTED_IDENTITY_CA)]),
        App(name="ReplayService",
            identities=[Identity(name="ReplayService",    issuer=TRUSTED_IDENTITY_CA)]),
    ],
)

REMOTE_TELEOP = Module(
    name="remote-teleop",
    apps=[
        App(name="RsActiveLan",
            identities=[Identity(name="RsActiveLan",  issuer=TRUSTED_IDENTITY_CA)]),
        App(name="RsActiveWan",
            identities=[Identity(name="RsActiveWan",  issuer=TRUSTED_IDENTITY_CA)]),
        App(name="RsPassiveLan",
            identities=[Identity(name="RsPassiveLan", issuer=TRUSTED_IDENTITY_CA)]),
        App(name="RsPassiveWan",
            identities=[Identity(name="RsPassiveWan", issuer=TRUSTED_IDENTITY_CA)]),
        App(name="RsCloudWan",
            identities=[Identity(name="RsCloudWan",   issuer=TRUSTED_IDENTITY_CA)]),
    ],
)

# ---------------------------------------------------------------------------
# Security tree
# ---------------------------------------------------------------------------

SECURITY_TREE = SecurityTree(
    certificate_authorities=[TRUSTED_ROOT_CA, TRUSTED_PERMISSIONS_CA, TRUSTED_IDENTITY_CA],
    domain_scopes=[OPERATIONAL_DOMAIN, TELEOP_WAN_DOMAIN],
    modules=[OPERATING_ROOM, RECORD_PLAYBACK, REMOTE_TELEOP],
    org_name="Company Name",
    country="US",
    state="CA",
    email_domain="company_name.com",
)


def main():
    parser = argparse.ArgumentParser(
        description="Generate DDS Security artifacts for the reference architecture.")
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
    parser.add_argument("--connext-version",
                        help="Override Connext version (e.g. '7.5.0'). "
                             "Auto-detected from rti.connextdds if not set.")
    args = parser.parse_args()

    if args.connext_version:
        SECURITY_TREE.connext_version = tuple(
            int(x) for x in args.connext_version.split("."))
    else:
        detected = detect_connext_version()
        if detected:
            SECURITY_TREE.connext_version = detected
            logging.getLogger(__name__).info(
                "Detected Connext version: %s",
                ".".join(str(x) for x in detected))

    if args.status:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
        SECURITY_TREE.check_status(root=SECURITY_DIR, warn_days=args.warn_days)
    elif args.scaffold:
        scaffold_tree(SECURITY_TREE, root=SECURITY_DIR, strict=args.strict)
    else:
        SECURITY_TREE.generate_artifacts(
            root=SECURITY_DIR, force=args.force, strict=args.strict)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        raise
