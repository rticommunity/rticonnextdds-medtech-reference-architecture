"""This script checks whether the security plugins can be loaded
in the current environment.

It attempts to create a secure DomainParticipant and uses a log
handler to determine if the failure is due to missing security
plugins or some other issue.

The script returns 0 if secure participant creation is possible
(i.e., security plugins can be loaded) and 1 otherwise.
"""

from __future__ import annotations

import sys

import rti.connextdds as dds


def _check_security() -> bool:
    """Try to create a secure participant using the provided environment.

    Returns True if secure participant creation succeeds, False otherwise.
    """

    can_load_security = True

    def log_handler(msg):
        nonlocal can_load_security
        if (
            can_load_security
            and "DDS_DomainParticipantTrustPlugins_initialize:FAILED TO LOAD" in msg
        ):
            can_load_security = False

    dds.DomainParticipant.participant_factory_qos <<= dds.EntityFactory.manually_enable
    dds.Logger.instance.verbosity = dds.Verbosity(dds.Verbosity.SILENT)
    dds.Logger.instance.verbosity_by_category(
        category=dds.LogCategory(dds.LogCategory.security),
        verbosity=dds.Verbosity(dds.Verbosity.EXCEPTION),
    )
    dds.Logger.instance.output_handler(log_handler)

    params = dds.QosProviderParams()
    params.ignore_user_profile = True
    params.ignore_environment_profile = True
    params.ignore_resource_profile = False
    provider = dds.QosProvider(params)
    qos = provider.participant_qos_from_profile(
        profile_name="BuiltinQosSnippetLib::Feature.Security.Enable"
    )

    try:
        participant = dds.DomainParticipant(domain_id=0, qos=qos)
        participant.close()
    except dds.Error:
        # A failure is expected in both scenarios, the log handler will
        # determine the ability to load the security plugins
        pass

    dds.Logger.instance.reset_output_handler()
    return can_load_security


if __name__ == "__main__":
    sys.exit(0 if _check_security() else 1)
