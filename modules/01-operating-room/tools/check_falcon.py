#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Check Novint Falcon connectivity and input without DDS or arm commands."""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from FalconInput import FalconInput  # noqa: E402


def check() -> int:
    device = FalconInput()
    try:
        device.open()
        sample = device.read()
        while sample is None:
            time.sleep(0.005)
            sample = device.read()
        position, buttons = sample
        print("Falcon connection and homing: OK")
        print(f"Position (m): {position}; button bitfield: 0x{buttons:x}")
        print("Mapping, force feedback and physical stop behavior were not checked.")
        return 0
    finally:
        device.close()


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        return check()
    except Exception as error:
        print(f"Falcon check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
