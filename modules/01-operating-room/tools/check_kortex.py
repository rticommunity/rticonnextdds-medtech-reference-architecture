#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Check Kinova Kortex connectivity and reported state without DDS or motion commands."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from KortexDevice import KortexDevice  # noqa: E402


def check() -> int:
    device = KortexDevice()
    try:
        device.open()
        health = device.read_health()
        position, orientation = device.read_pose()
        print("Kinova connection: OK")
        print(f"Arm state: {health.arm_state}; servoing mode: {health.servoing_mode}")
        print(f"Fault banks: A=0x{health.fault_bank_a:08x}, B=0x{health.fault_bank_b:08x}")
        print(f"TCP position (m): {position}; orientation quaternion (x,y,z,w): {orientation}")
        print(f"Motion adapter health criteria: {'PASS' if health.ready else 'NOT READY'}")
        if not health.ready:
            print("Expected servoing-ready state, single-level servoing, and clear fault banks.")
        print("Watchdog, physical stop behavior and safety were not checked.")
        return 0 if health.ready else 1
    finally:
        device.close()


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        return check()
    except Exception as error:
        print(f"Kortex check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
