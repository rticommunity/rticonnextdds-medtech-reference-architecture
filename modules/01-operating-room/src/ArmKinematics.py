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

"""Deterministic six-axis spherical-wrist arm model for the operating-room demo.

Distances and linear rates use meters and meters per second. Angles and angular
rates use radians and radians per second. The arm base is right-handed with +Z
up; the tool's +Z axis points from the wrist toward the working end.
"""

from __future__ import annotations

import math
from typing import NamedTuple

Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]
JointVector = tuple[float, float, float, float, float, float]

BASE_HEIGHT_M = 0.14
UPPER_ARM_M = 0.24
FOREARM_M = 0.20
TCP_OFFSET_M = 0.105
MIN_JAW_GAP_M = 0.0
MAX_JAW_GAP_M = 0.060
INITIAL_JAW_GAP_M = 0.036

MAX_LINEAR_SPEED = 0.05
MAX_ANGULAR_SPEED = 0.5
MAX_OPENING_RATE = 0.02
MAX_JOINT_SPEED_RAD_S = 2.0
# Unit-qualified aliases keep the local demo values self-documenting.
MAX_LINEAR_SPEED_M_S = MAX_LINEAR_SPEED
MAX_ANGULAR_SPEED_RAD_S = MAX_ANGULAR_SPEED
MAX_JAW_RATE_M_S = MAX_OPENING_RATE
MAX_STEP_DT_S = 0.10

# These are limits for the hypothetical demo, not a physical robot.
JOINT_LIMITS: tuple[tuple[float, float], ...] = (
    (-math.pi, math.pi),
    (-2.35, 2.35),
    (-2.75, 2.75),
    (-math.pi, math.pi),
    (-2.15, 2.15),
    (-math.pi, math.pi),
)
INITIAL_JOINTS: JointVector = (0.0, 1.1, -1.6, 0.0, math.pi / 2.0 - 0.5, 0.0)

SCENE_NODE_PATHS = {
    "base_yaw": "Arm/BaseYaw",
    "shoulder": "Arm/BaseYaw/Shoulder",
    "elbow": "Arm/BaseYaw/Shoulder/Elbow",
    "wrist": "Arm/BaseYaw/Shoulder/Elbow/Wrist",
    "tool": "Arm/BaseYaw/Shoulder/Elbow/Wrist/Tool",
    "left_finger": "Arm/BaseYaw/Shoulder/Elbow/Wrist/Tool/LeftFinger",
    "right_finger": "Arm/BaseYaw/Shoulder/Elbow/Wrist/Tool/RightFinger",
}


class Pose(NamedTuple):
    position: Vector3
    orientation: Quaternion


def _finite_tuple(values, size: int, name: str) -> tuple[float, ...]:
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must contain {size} finite numbers") from exc
    if len(result) != size or not all(math.isfinite(value) for value in result):
        raise ValueError(f"{name} must contain {size} finite numbers")
    return result


def _q_normalize(q: Quaternion) -> Quaternion:
    norm = math.hypot(*q)
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError("orientation quaternion must have nonzero finite length")
    return tuple(value / norm for value in q)  # type: ignore[return-value]


def _q_multiply(a: Quaternion, b: Quaternion) -> Quaternion:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _q_conjugate(q: Quaternion) -> Quaternion:
    return (-q[0], -q[1], -q[2], q[3])


def _q_axis_angle(axis: Vector3, angle: float) -> Quaternion:
    half = angle * 0.5
    scale = math.sin(half)
    return _q_normalize((axis[0] * scale, axis[1] * scale, axis[2] * scale, math.cos(half)))


def _q_rotate(q: Quaternion, vector: Vector3) -> Vector3:
    x, y, z, w = q
    vx, vy, vz = vector
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + y * tz - z * ty,
        vy + w * ty + z * tx - x * tz,
        vz + w * tz + x * ty - y * tx,
    )


def _q_exp(rotation: Vector3) -> Quaternion:
    angle = math.sqrt(sum(value * value for value in rotation))
    if angle < 1e-12:
        return _q_normalize((rotation[0] * 0.5, rotation[1] * 0.5, rotation[2] * 0.5, 1.0))
    scale = math.sin(angle * 0.5) / angle
    return _q_normalize(
        (rotation[0] * scale, rotation[1] * scale, rotation[2] * scale, math.cos(angle * 0.5))
    )


def _q_rx(angle: float) -> Quaternion:
    return _q_axis_angle((1.0, 0.0, 0.0), angle)


def _q_ry(angle: float) -> Quaternion:
    return _q_axis_angle((0.0, 1.0, 0.0), angle)


def _q_rz(angle: float) -> Quaternion:
    return _q_axis_angle((0.0, 0.0, 1.0), angle)


def _q_wrist(joints: JointVector) -> Quaternion:
    return _q_normalize(
        _q_multiply(_q_multiply(_q_rx(joints[3]), _q_ry(joints[4])), _q_rz(joints[5]))
    )


def _matrix_from_q(q: Quaternion) -> tuple[tuple[float, float, float], ...]:
    x, y, z, w = q
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def _xyz_euler_solutions(
    q: Quaternion, near: JointVector
) -> tuple[tuple[float, float, float], ...]:
    matrix = _matrix_from_q(q)
    sin_y = max(-1.0, min(1.0, matrix[0][2]))
    y = math.asin(sin_y)
    cos_y = math.cos(y)
    if abs(cos_y) < 1e-8:
        x = near[3]
        if sin_y > 0.0:
            x_plus_z = math.atan2(matrix[1][0], matrix[1][1])
            z = x_plus_z - x
        else:
            z_minus_x = math.atan2(matrix[1][0], matrix[1][1])
            z = z_minus_x + x
        return ((x, y, z),)
    x = math.atan2(-matrix[1][2], matrix[2][2])
    z = math.atan2(-matrix[0][1], matrix[0][0])
    return ((x, y, z), (x + math.pi, math.pi - y, z + math.pi))


def _nearest_limited(value: float, near: float, limits: tuple[float, float]) -> float | None:
    low, high = limits
    candidates = (value + 2.0 * math.pi * offset for offset in range(-2, 3))
    valid = [candidate for candidate in candidates if low - 1e-9 <= candidate <= high + 1e-9]
    return min(valid, key=lambda candidate: abs(candidate - near)) if valid else None


def forward_kinematics(joints) -> Pose:
    """Return the TCP pose for six joint angles in radians."""
    q = _finite_tuple(joints, 6, "joints")
    base, shoulder, elbow, wrist_x, wrist_y, wrist_z = q
    radial = UPPER_ARM_M * math.cos(shoulder) + FOREARM_M * math.cos(shoulder + elbow)
    height = (
        BASE_HEIGHT_M + UPPER_ARM_M * math.sin(shoulder) + FOREARM_M * math.sin(shoulder + elbow)
    )
    wrist_center = (radial * math.cos(base), radial * math.sin(base), height)
    wrist_joints: JointVector = tuple(q)  # type: ignore[assignment]
    orientation = _q_normalize(
        _q_multiply(
            _q_multiply(_q_rz(base), _q_ry(-(shoulder + elbow))),
            _q_wrist(wrist_joints),
        )
    )
    offset = _q_rotate(orientation, (0.0, 0.0, TCP_OFFSET_M))
    position = tuple(wrist_center[i] + offset[i] for i in range(3))
    return Pose(position, orientation)  # type: ignore[arg-type]


def inverse_kinematics(
    pose, near=None, *, max_joint_delta: float | None = None
) -> JointVector | None:
    """Solve a reachable TCP pose near ``near`` while respecting demo limits.

    If given, ``max_joint_delta`` bounds each joint's change from the seed.
    Returns ``None`` if no solution meets the limits. Invalid inputs raise
    ``ValueError``.
    """
    try:
        if isinstance(pose, dict):
            position_value = pose["position"]
            orientation_value = pose["orientation"]
        else:
            position_value = pose.position
            orientation_value = pose.orientation
    except (AttributeError, KeyError, TypeError) as exc:
        raise ValueError("pose must contain position and orientation") from exc
    position = _finite_tuple(position_value, 3, "pose position")
    orientation = _q_normalize(_finite_tuple(orientation_value, 4, "pose orientation"))
    seed = _finite_tuple(
        INITIAL_JOINTS if near is None else near,
        6,
        "near joints",
    )
    if max_joint_delta is not None:
        max_joint_delta = _finite_tuple((max_joint_delta,), 1, "max joint delta")[0]
        if max_joint_delta < 0.0:
            raise ValueError("max joint delta must be non-negative")

    tool_offset = _q_rotate(orientation, (0.0, 0.0, TCP_OFFSET_M))
    wrist = tuple(position[i] - tool_offset[i] for i in range(3))
    radial = math.hypot(wrist[0], wrist[1])
    height = wrist[2] - BASE_HEIGHT_M
    radius_squared = radial * radial + height * height
    cosine_elbow = (radius_squared - UPPER_ARM_M * UPPER_ARM_M - FOREARM_M * FOREARM_M) / (
        2.0 * UPPER_ARM_M * FOREARM_M
    )
    if cosine_elbow < -1.0 - 1e-9 or cosine_elbow > 1.0 + 1e-9:
        return None
    cosine_elbow = max(-1.0, min(1.0, cosine_elbow))
    yaw = math.atan2(wrist[1], wrist[0]) if radial > 1e-10 else seed[0]
    candidates: list[tuple[float, JointVector]] = []
    for branch_yaw, signed_radial in ((yaw, radial), (yaw + math.pi, -radial)):
        for elbow in (math.acos(cosine_elbow), -math.acos(cosine_elbow)):
            shoulder = math.atan2(height, signed_radial) - math.atan2(
                FOREARM_M * math.sin(elbow),
                UPPER_ARM_M + FOREARM_M * math.cos(elbow),
            )
            q03 = _q_normalize(_q_multiply(_q_rz(branch_yaw), _q_ry(-(shoulder + elbow))))
            relative_wrist = _q_normalize(_q_multiply(_q_conjugate(q03), orientation))
            for wrist_angles in _xyz_euler_solutions(relative_wrist, seed):
                raw = (branch_yaw, shoulder, elbow, *wrist_angles)
                limited = tuple(
                    _nearest_limited(value, seed[index], JOINT_LIMITS[index])
                    for index, value in enumerate(raw)
                )
                if any(value is None for value in limited):
                    continue
                config: JointVector = tuple(limited)  # type: ignore[assignment]
                if max_joint_delta is not None and any(
                    abs(config[i] - seed[i]) > max_joint_delta + 1e-9 for i in range(6)
                ):
                    continue
                score = sum((config[i] - seed[i]) ** 2 for i in range(6))
                candidates.append((score, config))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


class ArmModel:
    """Six-axis arm and parallel-jaw state advanced by base-frame TCP velocity."""

    def __init__(self, joints: JointVector = INITIAL_JOINTS):
        self._joints = _finite_tuple(joints, 6, "joints")
        if any(
            value < limits[0] or value > limits[1]
            for value, limits in zip(self._joints, JOINT_LIMITS)
        ):
            raise ValueError("initial joint configuration exceeds demo limits")
        self._jaw_gap = INITIAL_JAW_GAP_M
        self.reachable = True
        self.last_error: str | None = None

    @property
    def joints(self) -> JointVector:
        return self._joints

    @property
    def pose(self) -> dict[str, tuple[float, ...]]:
        actual = forward_kinematics(self._joints)
        return {
            "position": actual.position,
            "orientation": actual.orientation,
        }

    @property
    def jaw_gap(self) -> float:
        return self._jaw_gap

    @property
    def opening_width(self) -> float:
        """Observed total jaw gap in meters."""
        return self._jaw_gap

    @property
    def node_transforms(self) -> dict[str, dict[str, object]]:
        base, shoulder, elbow, q4, q5, q6 = self._joints
        q_wrist = _q_wrist(self._joints)
        half_gap = self._jaw_gap * 0.5
        local = {
            "base_yaw": ((0.0, 0.0, BASE_HEIGHT_M), _q_rz(base)),
            "shoulder": ((0.0, 0.0, 0.0), _q_ry(-shoulder)),
            "elbow": ((UPPER_ARM_M, 0.0, 0.0), _q_ry(-elbow)),
            "wrist": ((FOREARM_M, 0.0, 0.0), q_wrist),
            "tool": ((0.0, 0.0, TCP_OFFSET_M), (0.0, 0.0, 0.0, 1.0)),
            "left_finger": ((half_gap, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)),
            "right_finger": ((-half_gap, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)),
        }
        return {
            node_id: {
                "path": SCENE_NODE_PATHS[node_id],
                "position": position,
                "rotation": _q_normalize(rotation),
            }
            for node_id, (position, rotation) in local.items()
        }

    def step(
        self,
        linear_velocity: Vector3,
        angular_velocity: Vector3,
        opening_rate: float,
        dt: float,
    ) -> dict[str, object]:
        """Integrate one elapsed interval and return the resulting actual state.

        Linear and angular velocities use the fixed, right-handed base frame.
        Angular velocity rotates about base-oriented axes through the TCP.
        A positive opening rate increases the total jaw gap; both fingers move
        equally and oppositely. Motion is reduced when needed to respect joint
        speed/workspace limits, or held if no smaller continuous step is found.
        The jaw continues to respect its own travel independently.
        """
        linear = _finite_tuple(linear_velocity, 3, "linear velocity")
        angular = _finite_tuple(angular_velocity, 3, "angular velocity")
        opening_rate_value = _finite_tuple((opening_rate,), 1, "opening rate")[0]
        dt_value = _finite_tuple((dt,), 1, "dt")[0]
        if dt_value < 0.0:
            raise ValueError("dt must be non-negative")
        linear_speed = math.sqrt(sum(value * value for value in linear))
        angular_speed = math.sqrt(sum(value * value for value in angular))
        if linear_speed > MAX_LINEAR_SPEED_M_S + 1e-9:
            raise ValueError(f"linear speed exceeds {MAX_LINEAR_SPEED_M_S} m/s demo limit")
        if angular_speed > MAX_ANGULAR_SPEED_RAD_S + 1e-9:
            raise ValueError(f"angular speed exceeds {MAX_ANGULAR_SPEED_RAD_S} rad/s demo limit")
        if abs(opening_rate_value) > MAX_JAW_RATE_M_S + 1e-9:
            raise ValueError(f"jaw rate exceeds {MAX_JAW_RATE_M_S} m/s demo limit")

        elapsed = min(dt_value, MAX_STEP_DT_S)
        current = forward_kinematics(self._joints)
        solution = None
        limiting_condition = None
        # Backtrack the whole twist, not individual joints, to preserve its path.
        for reduction in range(9):
            motion_dt = elapsed * 0.5**reduction
            target_position = tuple(current.position[i] + linear[i] * motion_dt for i in range(3))
            delta_rotation = _q_exp(tuple(value * motion_dt for value in angular))
            target_orientation = _q_normalize(_q_multiply(delta_rotation, current.orientation))
            target = Pose(target_position, target_orientation)  # type: ignore[arg-type]
            solution = inverse_kinematics(
                target, self._joints, max_joint_delta=MAX_JOINT_SPEED_RAD_S * elapsed
            )
            if solution is not None:
                break
            if reduction == 0:
                limiting_condition = (
                    "Joint speed limit"
                    if inverse_kinematics(target, self._joints) is not None
                    else "Workspace or joint limit"
                )
        if solution is None:
            self.reachable = False
            self.last_error = f"{limiting_condition}: holding position"
        else:
            self._joints = solution
            self.reachable = True
            self.last_error = (
                f"{limiting_condition}: reducing motion" if limiting_condition else None
            )

        self._jaw_gap = min(
            MAX_JAW_GAP_M,
            max(MIN_JAW_GAP_M, self._jaw_gap + opening_rate_value * elapsed),
        )
        return {
            "reachable": self.reachable,
            "error": self.last_error,
            "pose": self.pose,
            "joints": self._joints,
            "jaw_gap": self._jaw_gap,
            "opening_width": self._jaw_gap,
        }

    def view(self) -> dict[str, object]:
        """Return the model's actual pose, jaw state, and IK outcome."""
        actual = self.pose
        return {
            "pose": actual,
            "position": actual["position"],
            "orientation": actual["orientation"],
            "joints": self._joints,
            "opening_width": self._jaw_gap,
            "reachable": self.reachable,
            "error": self.last_error,
        }


__all__ = [
    "ArmModel",
    "BASE_HEIGHT_M",
    "FOREARM_M",
    "INITIAL_JAW_GAP_M",
    "INITIAL_JOINTS",
    "JOINT_LIMITS",
    "MAX_ANGULAR_SPEED_RAD_S",
    "MAX_ANGULAR_SPEED",
    "MAX_JAW_GAP_M",
    "MAX_JAW_RATE_M_S",
    "MAX_JOINT_SPEED_RAD_S",
    "MAX_OPENING_RATE",
    "MAX_LINEAR_SPEED_M_S",
    "MAX_LINEAR_SPEED",
    "MAX_STEP_DT_S",
    "MIN_JAW_GAP_M",
    "Pose",
    "SCENE_NODE_PATHS",
    "TCP_OFFSET_M",
    "UPPER_ARM_M",
    "forward_kinematics",
    "inverse_kinematics",
]
