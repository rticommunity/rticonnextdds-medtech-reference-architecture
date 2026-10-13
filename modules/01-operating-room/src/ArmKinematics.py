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

import math
from enum import IntEnum


class ArmJoint(IntEnum):
    """Internal simulator joints; these are not DDS control commands."""

    BASE = 0
    SHOULDER = 1
    ELBOW = 2
    WRIST = 3
    HAND = 4


LINK_1_MM = 160.0
LINK_2_MM = 120.0
JOG_STEP_MM = 2.0
ROTATION_STEP_DEG = 1.0
GRIPPER_STEP_DEG = 2.0
GRIPPER_MIN_DEG = 0.0
GRIPPER_MAX_DEG = 90.0
MIN_REACH_MM = abs(LINK_1_MM - LINK_2_MM) + 1.0
MAX_REACH_MM = LINK_1_MM + LINK_2_MM - 1.0


def _normalise_degrees(angle: float) -> float:
    return angle % 360.0


def planar_tool_position(angles: dict) -> tuple[float, float]:
    shoulder = math.radians(90.0 + angles[ArmJoint.SHOULDER] - 180.0)
    elbow = math.radians(angles[ArmJoint.ELBOW] - 180.0)
    return (
        LINK_1_MM * math.cos(shoulder) + LINK_2_MM * math.cos(shoulder + elbow),
        LINK_1_MM * math.sin(shoulder) + LINK_2_MM * math.sin(shoulder + elbow),
    )


def apply_teleop_jog(angles: dict, axis, direction) -> dict:
    updated = dict(angles)
    axis = getattr(axis, "name", axis)
    direction = getattr(direction, "name", direction)
    if direction == "STOPPED":
        return updated
    if direction not in {"POSITIVE", "NEGATIVE"}:
        raise ValueError(f"Unsupported teleoperation direction: {direction}")

    sign = 1.0 if direction == "POSITIVE" else -1.0

    if axis in {"X", "Y"}:
        x, y = planar_tool_position(updated)
        if axis == "X":
            x += sign * JOG_STEP_MM
        else:
            y += sign * JOG_STEP_MM

        radius = min(MAX_REACH_MM, max(MIN_REACH_MM, math.hypot(x, y)))
        scale = radius / max(math.hypot(x, y), 1e-9)
        x *= scale
        y *= scale

        current_elbow_delta = updated[ArmJoint.ELBOW] - 180.0
        elbow_sign = -1.0 if current_elbow_delta < 0.0 else 1.0
        cos_elbow = (radius * radius - LINK_1_MM * LINK_1_MM - LINK_2_MM * LINK_2_MM) / (
            2.0 * LINK_1_MM * LINK_2_MM
        )
        elbow = elbow_sign * math.acos(min(1.0, max(-1.0, cos_elbow)))
        shoulder = math.atan2(y, x) - math.atan2(
            LINK_2_MM * math.sin(elbow),
            LINK_1_MM + LINK_2_MM * math.cos(elbow),
        )

        old_tool_orientation = sum(
            updated[motor] - 180.0
            for motor in (
                ArmJoint.SHOULDER,
                ArmJoint.ELBOW,
                ArmJoint.WRIST,
            )
        )
        new_shoulder = _normalise_degrees(180.0 + math.degrees(shoulder - math.pi / 2.0))
        new_elbow = _normalise_degrees(180.0 + math.degrees(elbow))
        updated[ArmJoint.SHOULDER] = new_shoulder
        updated[ArmJoint.ELBOW] = new_elbow
        updated[ArmJoint.WRIST] = _normalise_degrees(
            180.0 + old_tool_orientation - (new_shoulder - 180.0) - (new_elbow - 180.0)
        )
    elif axis == "ROLL":
        motor = ArmJoint.WRIST
        updated[motor] = _normalise_degrees(updated[motor] + sign * ROTATION_STEP_DEG)
    elif axis == "GRIPPER":
        motor = ArmJoint.HAND
        updated[motor] = min(
            GRIPPER_MAX_DEG,
            max(GRIPPER_MIN_DEG, updated[motor] + sign * GRIPPER_STEP_DEG),
        )
    else:
        raise ValueError(f"Unsupported teleoperation axis: {axis}")

    return updated
