#
# (c) 2025-2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

import socket

import stun


def main():
    print("Querying third-party STUN servers; this may take a minute...")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2)
            sock.bind(("0.0.0.0", 0))
            nat_type, _ = stun.get_nat_type(sock, "0.0.0.0", sock.getsockname()[1])
    except (OSError, TypeError, KeyError, ValueError) as exc:
        print(f"STUN probe failed: {exc}")
        print("Result: inconclusive. Consider Scenario 3 and test end-to-end.")
        return 1

    advice = {
        stun.FullCone: (
            "Scenario 2 may work with a compatible peer, including a peer behind another NAT type."
        ),
        stun.RestricNAT: ("Scenario 2 may work if the other peer is also behind a cone NAT."),
        stun.RestricPortNAT: ("Scenario 2 may work if the other peer is also behind a cone NAT."),
        stun.SymmetricNAT: (
            "Scenario 2 may work with a full-cone peer; otherwise consider Scenario 3."
        ),
    }
    if nat_type not in advice:
        print(f"STUN probe result: {nat_type}")
        print("Result: inconclusive. Consider Scenario 3 and test end-to-end.")
        return 1

    print(f"STUN library reported: {nat_type}")
    print("This is an advisory result, not proof of NAT type or reachability.")
    print(advice[nat_type])
    print("Scenario 1 is an option if a peer is publicly reachable on its configured UDP port.")
    print("Verify the chosen scenario with both endpoints and their actual network policies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
