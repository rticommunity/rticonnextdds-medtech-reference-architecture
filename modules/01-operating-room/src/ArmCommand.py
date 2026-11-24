#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Shared arm command validation."""

import math


def clamp_vector(values: tuple[float, float, float], limit: float) -> tuple[float, float, float]:
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Non-finite arm velocity")
    if math.hypot(*values) <= limit:
        return values
    largest = max(abs(value) for value in values)
    normalized = (values[0] / largest, values[1] / largest, values[2] / largest)
    scale = limit / math.hypot(*normalized)
    return (normalized[0] * scale, normalized[1] * scale, normalized[2] * scale)
