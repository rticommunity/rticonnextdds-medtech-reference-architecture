#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

"""This script checks whether the security plugins can be loaded
in the current environment.

It attempts to create a secure DomainParticipant without security artifacts
and checks the log for the explicit plugin-load failure diagnostic.

The script returns 0 if the plugin-load failure was not observed, 1 if it
was observed, and 2 for an unexpected probe error.
"""

from __future__ import annotations

import sys
import traceback


def _check_security() -> bool:
    """Return whether the explicit plugin-load failure diagnostic was absent."""
    import rti.connextdds as dds

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
    try:
        available = _check_security()
    except Exception:
        traceback.print_exc()
        sys.exit(2)
    if not available:
        print("Connext Security plugin failed to load.", file=sys.stderr)
    sys.exit(0 if available else 1)
