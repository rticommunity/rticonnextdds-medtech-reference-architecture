# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
# Licensed under the terms in LICENSE.

"""Resolve already provisioned EPS artifacts without contacting Cloud."""

import os
import re
from pathlib import Path

PREPARATION = (
    "Maintainer: configure the Full Security domain and participant templates using docs/EPS.md.",
    "Edge: run `rticloud login`, then from dedicated agent storage run "
    "`rticloud edge-sync agent --service <service-id> --domain-tpl-id <domain-template-id> "
    "--participant-tpl-id PatientSensor --deployment-name <name> "
    "--connext-dir <absolute-artifact-root>`.",
    "For additional roles, use `rticloud edge-sync agent enroll "
    "--service <service-id> --domain-tpl-id <domain-template-id> "
    "--participant-tpl-id <role> --deployment-name <name> "
    "--connext-dir <absolute-artifact-root>` from the same directory.",
    "Set MEDTECH_EPS_ARTIFACTS_DIR, MEDTECH_EPS_DEPLOYMENT_NAME and "
    "MEDTECH_EPS_DOMAIN_TAG for LAN and MEDTECH_EPS_WAN_DOMAIN_TAG for WAN.",
)

# Each launch role can own multiple participants; CDS uses only the WAN PSK.
LAN_ROLES = {
    "Arm": ("Arm",),
    "ArmController": ("ArmController",),
    "Orchestrator": ("Orchestrator", "SecureLogReader"),
    "PatientSensor": ("PatientSensor",),
    "PatientMonitor": ("PatientMonitor",),
    "RecordingService": ("RecordingService",),
    "ReplayService": ("ReplayService",),
    "RsActive": ("RsActiveLan",),
    "RsPassive": ("RsPassiveLan",),
}
WAN_ROLES = {
    "RsActive": "RsActiveWan",
    "RsPassive": "RsPassiveWan",
    "RsCloud": "RsCloudWan",
}
MODULE_ROLES = {
    "01-operating-room": (
        "Arm",
        "ArmController",
        "Orchestrator",
        "PatientSensor",
        "PatientMonitor",
    ),
    "02-record-playback": ("RecordingService", "ReplayService"),
    "03-remote-teleoperation": ("CdsCloud", "RsActive", "RsCloud", "RsPassive"),
}


def _component(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) or value.endswith("."):
        raise ValueError(f"{label} must be a single safe directory name.")
    return value


def launch_environment(selection: list[tuple[str, list[str] | None]]) -> dict[str, str]:
    if any(module not in MODULE_ROLES for module, _ in selection):
        raise ValueError("EPS supports Modules 01–03 only. Use local for Module 04.")
    roles = {role for module, apps in selection for role in (apps or MODULE_ROLES[module])}
    lan_roles = {role for app in roles for role in LAN_ROLES.get(app, ())}
    wan_roles = {WAN_ROLES[app] for app in roles if app in WAN_ROLES}
    root_setting = os.environ.get("MEDTECH_EPS_ARTIFACTS_DIR")
    deployment = os.environ.get("MEDTECH_EPS_DEPLOYMENT_NAME")
    if not root_setting or not deployment:
        raise ValueError("Set MEDTECH_EPS_ARTIFACTS_DIR and MEDTECH_EPS_DEPLOYMENT_NAME.")
    deployment = _component(deployment, "MEDTECH_EPS_DEPLOYMENT_NAME")
    root = Path(root_setting).expanduser().resolve()
    env = {
        "RTI_SECURITY_ARTIFACTS_DIR": str(root),
        "RTI_SECURITY_DEPLOYMENT_NAME": deployment,
        "RTI_SECURITY_LAN_BASE": "CommonSecurityConfig",
        "RTI_SECURITY_LAN_DOMAIN_DIR": "0",
        "RTI_SECURITY_WAN_BASE": "CommonSecurityConfig",
        "RTI_SECURITY_WAN_DOMAIN_DIR": "1",
    }
    required = set()
    for scope, domain_id, tag_setting, participants in (
        ("LAN", 0, "MEDTECH_EPS_DOMAIN_TAG", lan_roles),
        ("WAN", 1, "MEDTECH_EPS_WAN_DOMAIN_TAG", wan_roles),
    ):
        if not participants and not (scope == "WAN" and "CdsCloud" in roles):
            continue
        tag = _component(os.environ.get(tag_setting, ""), tag_setting)
        domain = f"{domain_id}.{tag}"
        env[f"RTI_SECURITY_{scope}_DOMAIN_DIR"] = domain
        env[f"RTI_SECURITY_{scope}_DOMAIN_TAG"] = tag
        env[f"RTI_SECURITY_{scope}_BASE"] = f"Managed{scope.title()}SecurityConfig"
        required.update(Path(domain, name) for name in ("psk_secret.key", "psk_secret_extra.key"))
        if not participants:
            continue
        required.update(
            Path(domain, name)
            for name in (
                "identity_ca.crt",
                "permissions_ca.crt",
                "governance.p7s",
                "crl.pem",
            )
        )
        required.update(
            Path(domain, deployment, role, name)
            for role in participants
            for name in ("identity.crt", "identity.key", "permissions.p7s")
        )
    missing = []
    for path in sorted(required):
        candidate = root / path
        if not candidate.is_file():
            missing.append(path)
            continue
        try:
            with candidate.open("rb") as stream:
                if not stream.read(1):
                    missing.append(path)
        except OSError:
            missing.append(path)
    if missing:
        raise ValueError(
            f"Incomplete EPS bundle at {root}: " + ", ".join(path.as_posix() for path in missing)
        )
    return env
