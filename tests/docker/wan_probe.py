#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software. RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

"""Publish and observe distinct heartbeats on one simulated LAN."""

import argparse
import sys
import time
from pathlib import Path

root = Path("/workspace")
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "tests/support"))

from test_utils import UtilityApp  # noqa: E402


def main():
    from MedTech import Device

    parser = argparse.ArgumentParser()
    parser.add_argument("side", choices=("a", "b"))
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()

    local, remote = (
        (Device.DeviceType.ARM, Device.DeviceType.PATIENT_SENSOR)
        if args.side == "a"
        else (Device.DeviceType.PATIENT_SENSOR, Device.DeviceType.ARM)
    )
    app = UtilityApp.make_non_secure()
    try:
        writer = app.device_heartbeat.writer
        reader = app.device_heartbeat.reader
        received = 0
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            writer.write(Device.Heartbeat(device=local))
            received += sum(sample.device == remote for sample in reader.take_data())
            time.sleep(0.2)
        print(f"side={args.side} remote_heartbeats={received}", flush=True)
    finally:
        app.close()


if __name__ == "__main__":
    main()
