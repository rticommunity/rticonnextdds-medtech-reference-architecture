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
HOMING_CHECK_SECONDS = 1.0
HOMING_TIMEOUT_SECONDS = 30.0
HOMING_CONFIRM_SECONDS = 0.05
FALCON_IO_FLAGS = 0x1 | 0x2 | 0x4


class FalconInput:
    def __init__(self, bridge=None) -> None:
        self.bridge = bridge
        self.opened = False
        self.last_sample_at: float | None = None
        self.opened_at: float | None = None
        self.last_packet_at: float | None = None
        self.homing_state = "CLOSED"
        self.homing_started_at: float | None = None
        self.homed_since: float | None = None
        self.homing_enabled = False

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
        initialized = False
        try:
            if not self.bridge.loadFirmware():
                raise RuntimeError("Could not initialize Falcon firmware")
            self.bridge.setHomingMode(True)
            self.homing_enabled = True
            self.opened_at = time.monotonic()
            self.last_packet_at = None
            self.last_sample_at = None
            self.homing_started_at = None
            self.homed_since = None
            self.homing_state = "CHECKING"
            initialized = True
        finally:
            if not initialized:
                self.close()

    def start_homing(self) -> bool:
        if not self.opened or self.homing_state not in ("WAITING", "TIMED OUT"):
            return False
        self.homing_state = "HOMING"
        self.homing_started_at = time.monotonic()
        self.homed_since = None
        return True

    def read(self) -> tuple[tuple[float, float, float], int] | None:
        if not self.opened:
            raise RuntimeError("Falcon input device is not open")
        now = time.monotonic()
        assert self.opened_at is not None
        if self.homing_state == "CHECKING" and now - self.opened_at >= HOMING_CHECK_SECONDS:
            self.homing_state = "WAITING"
            self.homed_since = None
        elif self.homing_state == "HOMING":
            assert self.homing_started_at is not None
            if now - self.homing_started_at >= HOMING_TIMEOUT_SECONDS:
                self.homing_state = "TIMED OUT"
                self.homed_since = None
        if not self.bridge.runIOLoop(FALCON_IO_FLAGS):
            last = self.last_packet_at if self.last_packet_at is not None else self.opened_at
            timeout = (
                INPUT_TIMEOUT_SECONDS if self.last_packet_at is not None else HOMING_CHECK_SECONDS
            )
            if now - last >= timeout:
                raise TimeoutError("Falcon input timed out")
            return None
        self.last_packet_at = now
        homed = self.bridge.isHomed()
        if self.homing_state == "READY" and not homed:
            raise RuntimeError("Falcon homing status was lost")
        if self.homing_state in ("CHECKING", "HOMING"):
            if not homed:
                self.homed_since = None
            elif self.homed_since is None:
                self.homed_since = now
            elif now - self.homed_since >= HOMING_CONFIRM_SECONDS:
                self.homing_state = "READY"
        if self.homing_state != "READY":
            return None
        position = self.bridge.getPosition()
        values = (float(position.x), float(position.y), float(position.z))
        buttons = int(self.bridge.getButtons())
        if not all(math.isfinite(value) for value in values) or buttons < 0:
            raise ValueError("Falcon returned invalid input")
        self.last_sample_at = time.monotonic()
        return values, buttons

    def close(self) -> None:
        if self.opened:
            try:
                if self.homing_enabled:
                    self.bridge.setHomingMode(False)
            finally:
                try:
                    self.bridge.close()
                finally:
                    self.opened = False
                    self.homing_enabled = False
                    self.homing_state = "CLOSED"
