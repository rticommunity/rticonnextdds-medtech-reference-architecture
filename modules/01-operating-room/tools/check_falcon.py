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


def check(*, home: bool = False) -> int:
    device = FalconInput()
    try:
        device.open()
        homing_requested = False
        sample = device.read()
        while sample is None:
            if device.homing_state in ("WAITING", "TIMED OUT"):
                if not home or homing_requested:
                    raise RuntimeError(
                        "Falcon homing was not confirmed; run with --home to home the device"
                    )
                if not device.start_homing():
                    raise RuntimeError("Could not start Falcon homing")
                homing_requested = True
                print("Move the Falcon handle fully out, then straight fully in.", flush=True)
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", action="store_true", help="Allow manual Falcon homing")
    args = parser.parse_args()
    try:
        return check(home=args.home)
    except Exception as error:
        print(f"Falcon check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
