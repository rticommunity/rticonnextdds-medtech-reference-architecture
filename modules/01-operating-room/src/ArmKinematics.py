import math

from Types import SurgicalRobot

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
    shoulder = math.radians(90.0 + angles[SurgicalRobot.Motors.SHOULDER] - 180.0)
    elbow = math.radians(angles[SurgicalRobot.Motors.ELBOW] - 180.0)
    return (
        LINK_1_MM * math.cos(shoulder) + LINK_2_MM * math.cos(shoulder + elbow),
        LINK_1_MM * math.sin(shoulder) + LINK_2_MM * math.sin(shoulder + elbow),
    )


def apply_teleop_jog(angles: dict, axis, direction) -> dict:
    updated = dict(angles)
    if direction == SurgicalRobot.TeleopDirections.STOPPED:
        return updated

    sign = 1.0 if direction == SurgicalRobot.TeleopDirections.POSITIVE else -1.0

    if axis in (SurgicalRobot.TeleopAxes.X, SurgicalRobot.TeleopAxes.Y):
        x, y = planar_tool_position(updated)
        if axis == SurgicalRobot.TeleopAxes.X:
            x += sign * JOG_STEP_MM
        else:
            y += sign * JOG_STEP_MM

        radius = min(MAX_REACH_MM, max(MIN_REACH_MM, math.hypot(x, y)))
        scale = radius / max(math.hypot(x, y), 1e-9)
        x *= scale
        y *= scale

        current_elbow_delta = updated[SurgicalRobot.Motors.ELBOW] - 180.0
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
                SurgicalRobot.Motors.SHOULDER,
                SurgicalRobot.Motors.ELBOW,
                SurgicalRobot.Motors.WRIST,
            )
        )
        new_shoulder = _normalise_degrees(180.0 + math.degrees(shoulder - math.pi / 2.0))
        new_elbow = _normalise_degrees(180.0 + math.degrees(elbow))
        updated[SurgicalRobot.Motors.SHOULDER] = new_shoulder
        updated[SurgicalRobot.Motors.ELBOW] = new_elbow
        updated[SurgicalRobot.Motors.WRIST] = _normalise_degrees(
            180.0 + old_tool_orientation - (new_shoulder - 180.0) - (new_elbow - 180.0)
        )
    elif axis == SurgicalRobot.TeleopAxes.ROLL:
        motor = SurgicalRobot.Motors.WRIST
        updated[motor] = _normalise_degrees(updated[motor] + sign * ROTATION_STEP_DEG)
    elif axis == SurgicalRobot.TeleopAxes.GRIPPER:
        motor = SurgicalRobot.Motors.HAND
        updated[motor] = min(
            GRIPPER_MAX_DEG,
            max(GRIPPER_MIN_DEG, updated[motor] + sign * GRIPPER_STEP_DEG),
        )

    return updated
