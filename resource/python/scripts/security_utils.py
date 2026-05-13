"""Functional DDS Security runtime helper utilities.

These utilities verify security availability by attempting secure participant
creation with runtime configuration, rather than checking for file presence.
"""

from __future__ import annotations

import os

import rti.connextdds as dds

from scripts import platform_setup


def check_security(
    env: dict[str, str],
) -> bool:
    """Try to create a secure participant using the provided environment.

    Returns True if secure participant creation succeeds, False otherwise.
    """
    os.environ.update(env or {})
    try:
        provider = dds.QosProvider(
            str(
                platform_setup.get_nddshome()
                / "resource"
                / "xml"
                / "RTI_SHAPES_DEMO_QOS_PROFILES.xml"
            )
        )
    except dds.Error as exc:
        raise RuntimeError(f"Failed to load QoS profiles for security probe: {exc}") from exc

    try:
        participant = dds.DomainParticipant(
            domain_id=0, qos=provider.participant_qos_from_profile("Security::SecureAllowAll")
        )
        participant.enable()
        participant.close()
    except dds.Error:
        return False

    return True if participant else False
