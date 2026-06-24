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

    # Generate QoS XML files with fully resolved absolute paths
    python3 setup_security.py --generate-resolved-qos

Prerequisite: ``NDDSHOME`` must be set to the Connext installation path.
"""

import argparse
import logging
import re
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
        name="OperationalDomain",
        issuer=TRUSTED_PERMISSIONS_CA,
        # Explicitly NONE: the reference architecture does not protect
        # discovery or liveliness metadata (RTPS payload is encrypted).
        discovery_protection_kind="NONE",
        liveliness_protection_kind="NONE",
    ),
    permissions=[
        Permissions(
            name="Arm",
            issuer=TRUSTED_PERMISSIONS_CA,
            publish_topics=[
                "t/DeviceStatus",
                "t/DeviceHeartbeat",
                "DDS:Security:LogTopicV2",
            ],
            subscribe_topics=["t/MotorControl", "t/DeviceCommand"],
        ),
        Permissions(
            name="ArmController",
            issuer=TRUSTED_PERMISSIONS_CA,
            publish_topics=[
                "t/MotorControl",
                "t/DeviceStatus",
                "t/DeviceHeartbeat",
                "DDS:Security:LogTopicV2",
            ],
            subscribe_topics=["t/DeviceCommand"],
        ),
        Permissions(
            name="Orchestrator",
            issuer=TRUSTED_PERMISSIONS_CA,
            publish_topics=["t/DeviceCommand", "DDS:Security:LogTopicV2"],
            subscribe_topics=["t/DeviceStatus", "t/DeviceHeartbeat"],
        ),
        Permissions(
            name="PatientMonitor",
            issuer=TRUSTED_PERMISSIONS_CA,
            publish_topics=[
                "t/DeviceStatus",
                "t/DeviceHeartbeat",
                "DDS:Security:LogTopicV2",
            ],
            subscribe_topics=["t/DeviceCommand", "t/Vitals"],
        ),
        Permissions(
            name="PatientSensor",
            issuer=TRUSTED_PERMISSIONS_CA,
            publish_topics=[
                "t/Vitals",
                "t/DeviceStatus",
                "t/DeviceHeartbeat",
                "DDS:Security:LogTopicV2",
            ],
            subscribe_topics=["t/DeviceCommand"],
        ),
        Permissions(
            name="SecureLogReader",
            issuer=TRUSTED_PERMISSIONS_CA,
            publish_topics=[],
            subscribe_topics=["DDS:Security:LogTopicV2"],
        ),
        # Read-only system observer: may subscribe to any topic, may publish
        # to none. The committed SystemObserver.xml is hand-edited to grant
        # subscribe on all topics/partitions (<topic>*</topic>), mirroring the
        # SecureLogReader pattern; publish is intentionally empty.
        Permissions(
            name="SystemObserver",
            issuer=TRUSTED_PERMISSIONS_CA,
            publish_topics=[],
            subscribe_topics=["*"],
        ),
        Permissions(
            name="Test",
            issuer=TRUSTED_PERMISSIONS_CA,
            publish_topics=[],
            subscribe_topics=["t/Vitals", "t/DeviceStatus"],
        ),
        Permissions(name="RecordingService", issuer=TRUSTED_PERMISSIONS_CA),
        Permissions(name="ReplayService", issuer=TRUSTED_PERMISSIONS_CA),
        Permissions(name="RsActiveLan", issuer=TRUSTED_PERMISSIONS_CA),
        Permissions(name="RsPassiveLan", issuer=TRUSTED_PERMISSIONS_CA),
    ],
)

TELEOP_WAN_DOMAIN = DomainScope(
    name="TeleopWanDomain",
    governance=Governance(
        name="TeleopWanDomain",
        issuer=TRUSTED_PERMISSIONS_CA,
        discovery_protection_kind="NONE",
        liveliness_protection_kind="NONE",
    ),
    permissions=[
        Permissions(name="RsActiveWan", issuer=TRUSTED_PERMISSIONS_CA),
        Permissions(name="RsPassiveWan", issuer=TRUSTED_PERMISSIONS_CA),
        Permissions(name="RsCloudWan", issuer=TRUSTED_PERMISSIONS_CA),
    ],
    psk_seeds=[
        # PSK seed for the WAN (TeleopWanDomain) domain.
        # Loaded by CDS and all WAN RS participants via
        # dds.sec.crypto.rtps_psk_secret_passphrase = file:<scope>/TeleopWanDomain.psk
        # Increment 'id' on every rotation (never reuse).
        # Valid range: 0-4294967295 for 7.7.x (0-254 for 7.3.x).
        PskSeed(filename="TeleopWanDomain.psk"),
    ],
)

# ---------------------------------------------------------------------------
# Modules (applications + participant identities)
# ---------------------------------------------------------------------------

OPERATING_ROOM = Module(
    name="operating-room",
    apps=[
        App(name="Arm", identities=[Identity(name="Arm", issuer=TRUSTED_IDENTITY_CA)]),
        App(
            name="ArmController",
            identities=[Identity(name="ArmController", issuer=TRUSTED_IDENTITY_CA)],
        ),
        App(
            name="Orchestrator",
            identities=[
                Identity(name="Orchestrator", issuer=TRUSTED_IDENTITY_CA),
                Identity(name="SecureLogReader", issuer=TRUSTED_IDENTITY_CA),
            ],
        ),
        App(
            name="PatientMonitor",
            identities=[Identity(name="PatientMonitor", issuer=TRUSTED_IDENTITY_CA)],
        ),
        App(
            name="PatientSensor",
            identities=[Identity(name="PatientSensor", issuer=TRUSTED_IDENTITY_CA)],
        ),
        App(
            name="SystemObserver",
            identities=[Identity(name="SystemObserver", issuer=TRUSTED_IDENTITY_CA)],
        ),
        App(name="Test", identities=[Identity(name="Test", issuer=TRUSTED_IDENTITY_CA)]),
    ],
)

RECORD_PLAYBACK = Module(
    name="record-playback",
    apps=[
        App(
            name="RecordingService",
            identities=[Identity(name="RecordingService", issuer=TRUSTED_IDENTITY_CA)],
        ),
        App(
            name="ReplayService",
            identities=[Identity(name="ReplayService", issuer=TRUSTED_IDENTITY_CA)],
        ),
    ],
)

REMOTE_TELEOP = Module(
    name="remote-teleop",
    apps=[
        App(
            name="RsActiveLan",
            identities=[Identity(name="RsActiveLan", issuer=TRUSTED_IDENTITY_CA)],
        ),
        App(
            name="RsActiveWan",
            identities=[Identity(name="RsActiveWan", issuer=TRUSTED_IDENTITY_CA)],
        ),
        App(
            name="RsPassiveLan",
            identities=[Identity(name="RsPassiveLan", issuer=TRUSTED_IDENTITY_CA)],
        ),
        App(
            name="RsPassiveWan",
            identities=[Identity(name="RsPassiveWan", issuer=TRUSTED_IDENTITY_CA)],
        ),
        App(
            name="RsCloudWan",
            identities=[Identity(name="RsCloudWan", issuer=TRUSTED_IDENTITY_CA)],
        ),
    ],
)

# ---------------------------------------------------------------------------
# Security tree
# ---------------------------------------------------------------------------

SECURITY_TREE = SecurityTree(
    certificate_authorities=[
        TRUSTED_ROOT_CA,
        TRUSTED_PERMISSIONS_CA,
        TRUSTED_IDENTITY_CA,
    ],
    domain_scopes=[OPERATIONAL_DOMAIN, TELEOP_WAN_DOMAIN],
    modules=[OPERATING_ROOM, RECORD_PLAYBACK, REMOTE_TELEOP],
    org_name="Company Name",
    country="US",
    state="CA",
    email_domain="company_name.com",
)


QOS_DIR = SECURITY_DIR.parent / "qos"

# QoS XML files to process when --generate-resolved-qos is used
_QOS_FILES_TO_RESOLVE = [
    "SecureAppsQos.xml",
    "SecureExternalAppsQos.xml",
]

# Regex matching the <configuration_variables> block that defines
# RTI_SECURITY_ARTIFACTS_DIR (including surrounding whitespace).
_CONFIG_VARS_RE = re.compile(
    r"\n\s*<configuration_variables>.*?</configuration_variables>\n",
    re.DOTALL,
)


def generate_resolved_qos(security_dir: Path, force: bool = False) -> None:
    """Generate QoS XML files with $(RTI_SECURITY_ARTIFACTS_DIR) resolved to absolute paths.

    Reads each source file from the qos/ directory, replaces the variable
    reference with the absolute security directory path, removes the
    <configuration_variables> block (no longer needed), and writes the
    result to <security_dir>/resolved_qos/.

    Existing files are skipped unless ``force`` is True.
    """
    log = logging.getLogger(__name__)
    out_dir = security_dir / "resolved_qos"
    out_dir.mkdir(parents=True, exist_ok=True)

    abs_security_path = str(security_dir)
    written_count = 0
    skipped_count = 0

    for filename in _QOS_FILES_TO_RESOLVE:
        src = QOS_DIR / filename
        if not src.is_file():
            log.warning("QoS source file not found, skipping: %s", src)
            continue

        content = src.read_text()

        # Replace the variable reference with the absolute path
        content = content.replace("$(RTI_SECURITY_ARTIFACTS_DIR)", abs_security_path)

        # Remove the <configuration_variables> block since paths are now absolute
        content = _CONFIG_VARS_RE.sub("\n", content)

        dest = out_dir / filename
        if dest.exists() and not force:
            log.warning(
                "Resolved QoS file already exists, skipping: %s - remove the file or use --force to regenerate",
                dest,
            )
            skipped_count += 1
            continue

        dest.write_text(content)
        log.info("Resolved QoS file written: %s", dest)
        written_count += 1

    print(
        f"Resolved QoS generation complete: {written_count} written, {skipped_count} skipped; output directory: {out_dir}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate DDS Security artifacts for the reference architecture."
    )
    parser.add_argument(
        "--scaffold",
        action="store_true",
        help="(Maintainer-only) Scaffold the directory tree from templates.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-generate artifacts even if they already exist.",
    )
    parser.add_argument("--strict", action="store_true", help="Promote warnings to fatal errors.")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report certificate expiry status and exit.",
    )
    parser.add_argument(
        "--warn-days",
        type=int,
        default=30,
        help="Days-to-expiry warning threshold for --status (default: 30).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase logging verbosity (-v=INFO, -vv=DEBUG).",
    )
    parser.add_argument(
        "--connext-version",
        help="Override Connext version (e.g. '7.5.0'). "
        "Auto-detected from rti.connextdds if not set.",
    )
    parser.add_argument(
        "--generate-resolved-qos",
        action="store_true",
        help="Generate QoS XML files (SecureAppsQos.xml, SecureExternalAppsQos.xml) "
        "with $(RTI_SECURITY_ARTIFACTS_DIR) resolved to absolute paths. "
        "Output is written to a 'resolved_qos' subfolder under the security directory. "
        "Existing files are skipped unless --force is set.",
    )
    args = parser.parse_args()

    level = (logging.WARNING, logging.INFO, logging.DEBUG)[min(args.verbose, 2)]
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    if args.connext_version:
        SECURITY_TREE.connext_version = tuple(int(x) for x in args.connext_version.split("."))
    else:
        detected = detect_connext_version()
        if detected:
            SECURITY_TREE.connext_version = detected
            logging.getLogger(__name__).info(
                "Detected Connext version: %s", ".".join(str(x) for x in detected)
            )

    if args.status:
        SECURITY_TREE.check_status(root=SECURITY_DIR, warn_days=args.warn_days)
    elif args.scaffold:
        scaffold_tree(SECURITY_TREE, root=SECURITY_DIR, strict=args.strict)
        print(f"Security directory tree scaffolded under {SECURITY_DIR}")
    elif args.generate_resolved_qos:
        generate_resolved_qos(SECURITY_DIR, force=args.force)
    else:
        summary = SECURITY_TREE.generate_artifacts(
            root=SECURITY_DIR, force=args.force, strict=args.strict
        )
        print(
            "Security artifact generation complete: "
            f"{summary['total_generated']} generated, "
            f"{summary['total_skipped']} skipped, "
            f"{summary['warnings']} validation warning(s)."
        )
        print(
            "Breakdown: "
            f"CA certs {summary['ca_certs_generated']} generated/{summary['ca_certs_skipped']} skipped; "
            f"signed governance {summary['signed_governance_generated']}/{summary['signed_governance_skipped']}; "
            f"signed permissions {summary['signed_permissions_generated']}/{summary['signed_permissions_skipped']}; "
            f"identity certs {summary['identity_certs_generated']}/{summary['identity_certs_skipped']}; "
            f"PSK seeds {summary['psk_seeds_generated']}/{summary['psk_seeds_skipped']}."
        )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        raise
