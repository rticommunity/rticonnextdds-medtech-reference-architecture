#!/usr/bin/env python3
#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software solely in combination with RTI Connext DDS. The Software
# is provided "as is", with no warranty of any type.

"""Licensed runtime smoke for the PyPI Connext Python API."""

import rti.connextdds as dds


def main() -> None:
    try:
        with dds.DomainParticipant(domain_id=0) as participant:
            print(f"Created and closed a licensed participant in domain {participant.domain_id}.")
    except Exception as exc:
        raise RuntimeError(
            "The licensed Connext runtime smoke failed while creating a participant. "
            "Provide a valid RTI license using RTI_LICENSE_FILE or another supported "
            "RTI license-file location."
        ) from exc


if __name__ == "__main__":
    main()
