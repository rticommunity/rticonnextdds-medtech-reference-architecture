#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Novint Falcon input connection and sample validation."""

import math
import time

INPUT_TIMEOUT_SECONDS = 0.1
FALCON_IO_FLAGS = 0x1 | 0x2 | 0x4


class FalconInput:
    def __init__(self, bridge=None) -> None:
        self.bridge = bridge
        self.opened = False
        self.last_sample_at: float | None = None
        self.opened_at: float | None = None

    def open(self) -> None:
        if self.bridge is None:
            try:
                from pynifalcon import FalconDeviceBridge
            except ImportError as exc:
                raise RuntimeError(
                    "Falcon requires the compatible pynifalcon bridge on PYTHONPATH"
                ) from exc
            self.bridge = FalconDeviceBridge()
        if not self.bridge.open(0):
            raise RuntimeError("Could not open Falcon input device")
        self.opened = True
        self.opened_at = time.monotonic()

    def read(self) -> tuple[tuple[float, float, float], int] | None:
        if not self.opened:
            raise RuntimeError("Falcon input device is not open")
        now = time.monotonic()
        if not self.bridge.runIOLoop(FALCON_IO_FLAGS):
            last = self.last_sample_at if self.last_sample_at is not None else self.opened_at
            if last is None or now - last >= INPUT_TIMEOUT_SECONDS:
                raise TimeoutError(
                    "Falcon input timed out; firmware must already be loaded and device homed"
                )
            return None
        if not self.bridge.isHomed():
            raise RuntimeError("Falcon is not homed")
        position = self.bridge.getPosition()
        values = (float(position.x), float(position.y), float(position.z))
        buttons = int(self.bridge.getButtons())
        if not all(math.isfinite(value) for value in values) or buttons < 0:
            raise ValueError("Falcon returned invalid input")
        self.last_sample_at = time.monotonic()
        return values, buttons

    def close(self) -> None:
        if self.opened:
            self.bridge.close()
            self.opened = False
