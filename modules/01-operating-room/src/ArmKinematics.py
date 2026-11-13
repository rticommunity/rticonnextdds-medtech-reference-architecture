#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""MuJoCo/Mink simulated arm driven by fixed-base Cartesian velocity.

The original MJCF model defines the geometry, joints, actuators, and rate limits.
The base is right-handed with +Z up; tool +Z points toward its working end.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

import mink
import mujoco
import numpy as np
import numpy.typing as npt

Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]
JointVector = tuple[float, float, float, float, float, float]
Array = npt.NDArray[np.float64]

MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "arm.xml"
_DESCRIPTION = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
_ARM_JOINT_NAMES = ("base_yaw", "shoulder", "elbow", "wrist_x", "wrist_y", "wrist_z")
_TOOL_COLLISION_GEOMS = (
    "shaft",
    "palm",
    "left_finger_body",
    "left_finger_pad",
    "right_finger_body",
    "right_finger_pad",
)

BASE_HEIGHT_M = float(_DESCRIPTION.body("base_yaw").pos[2])
UPPER_ARM_M = float(_DESCRIPTION.body("elbow").pos[0])
FOREARM_M = float(_DESCRIPTION.body("wrist_x").pos[0])
TCP_OFFSET_M = float(_DESCRIPTION.body("tool").pos[2])
JOINT_LIMITS = tuple(
    (float(_DESCRIPTION.joint(name).range[0]), float(_DESCRIPTION.joint(name).range[1]))
    for name in _ARM_JOINT_NAMES
)
INITIAL_JOINTS: JointVector = (
    float(_DESCRIPTION.key("home").qpos[0]),
    float(_DESCRIPTION.key("home").qpos[1]),
    float(_DESCRIPTION.key("home").qpos[2]),
    float(_DESCRIPTION.key("home").qpos[3]),
    float(_DESCRIPTION.key("home").qpos[4]),
    float(_DESCRIPTION.key("home").qpos[5]),
)
MIN_JAW_GAP_M = float(_DESCRIPTION.tendon_range[_DESCRIPTION.tendon("jaw_gap").id, 0])
MAX_JAW_GAP_M = float(_DESCRIPTION.tendon_range[_DESCRIPTION.tendon("jaw_gap").id, 1])
INITIAL_JAW_GAP_M = float(np.sum(_DESCRIPTION.key("home").qpos[6:]))
MAX_LINEAR_SPEED = float(_DESCRIPTION.numeric("max_linear_speed").data[0])
MAX_ANGULAR_SPEED = float(_DESCRIPTION.numeric("max_angular_speed").data[0])
MAX_OPENING_RATE = float(_DESCRIPTION.numeric("max_opening_rate").data[0])
MAX_JOINT_SPEED_RAD_S = float(_DESCRIPTION.numeric("max_joint_speed").data[0])
MAX_LINEAR_SPEED_M_S = MAX_LINEAR_SPEED
MAX_ANGULAR_SPEED_RAD_S = MAX_ANGULAR_SPEED
MAX_JAW_RATE_M_S = MAX_OPENING_RATE
MAX_STEP_DT_S = 0.10
_PHYSICS_DT_S = float(_DESCRIPTION.opt.timestep)

SCENE_NODE_PATHS = {
    "base_yaw": "Arm/BaseYaw",
    "shoulder": "Arm/BaseYaw/Shoulder",
    "elbow": "Arm/BaseYaw/Shoulder/Elbow",
    "wrist": "Arm/BaseYaw/Shoulder/Elbow/Wrist",
    "tool": "Arm/BaseYaw/Shoulder/Elbow/Wrist/Tool",
    "left_finger": "Arm/BaseYaw/Shoulder/Elbow/Wrist/Tool/LeftFinger",
    "right_finger": "Arm/BaseYaw/Shoulder/Elbow/Wrist/Tool/RightFinger",
}
_SCENE_BODIES = {
    "base_yaw": ("base_yaw", "world"),
    "shoulder": ("shoulder", "base_yaw"),
    "elbow": ("elbow", "shoulder"),
    "wrist": ("wrist_z", "elbow"),
    "tool": ("tool", "wrist_z"),
    "left_finger": ("left_finger", "tool"),
    "right_finger": ("right_finger", "tool"),
}


class Pose(NamedTuple):
    position: Vector3
    orientation: Quaternion


class ArmSimulationError(RuntimeError):
    """A backend failure that must stop the application's simulation."""


def _finite_tuple(values: Iterable[float], size: int, name: str) -> tuple[float, ...]:
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must contain {size} finite numbers") from exc
    if len(result) != size or not all(math.isfinite(value) for value in result):
        raise ValueError(f"{name} must contain {size} finite numbers")
    return result


def _vector(values: Array) -> Vector3:
    return float(values[0]), float(values[1]), float(values[2])


def _quaternion(wxyz: Array) -> Quaternion:
    return float(wxyz[1]), float(wxyz[2]), float(wxyz[3]), float(wxyz[0])


def _q_rotate(quaternion: Quaternion, vector: Vector3) -> Vector3:
    x, y, z, w = quaternion
    rotated = np.empty(3)
    mujoco.mju_rotVecQuat(rotated, np.asarray(vector), np.array([w, x, y, z]))
    return _vector(rotated)


def _tcp_pose(model: mujoco.MjModel, data: mujoco.MjData) -> Pose:
    site = model.site("tcp").id
    rotation = np.empty(4)
    mujoco.mju_mat2Quat(rotation, data.site_xmat[site])
    return Pose(_vector(data.site_xpos[site]), _quaternion(rotation))


def forward_kinematics(joints: Iterable[float]) -> Pose:
    """Return the engine-derived TCP pose for six joint angles."""
    data = mujoco.MjData(_DESCRIPTION)
    data.qpos[:] = _DESCRIPTION.key("home").qpos
    data.qpos[:6] = _finite_tuple(joints, 6, "joints")
    mujoco.mj_forward(_DESCRIPTION, data)
    return _tcp_pose(_DESCRIPTION, data)


class _BaseVelocityTask(mink.Task):
    def __init__(self, nv: int) -> None:
        super().__init__(cost=np.ones(6))
        self.scale = np.array([1 / MAX_LINEAR_SPEED] * 3 + [1 / MAX_ANGULAR_SPEED] * 3)
        self.rate = np.zeros(6)
        self.unit = np.zeros(6)
        self.basis = np.zeros((5, 6))
        self.jacobian = np.zeros((6, nv))
        self.dt = _PHYSICS_DT_S

    def set_rate(self, linear: tuple[float, ...], angular: tuple[float, ...]) -> None:
        self.rate = np.array((*linear, *angular)) * self.scale
        self.unit = self.rate / np.linalg.norm(self.rate)
        # These five equality rows prohibit movement perpendicular to the twist.
        self.basis = np.linalg.svd(self.unit.reshape(1, 6), full_matrices=True)[2][1:]

    def update(self, configuration: mink.Configuration, dt: float) -> None:
        local = configuration.get_frame_jacobian("tcp", "site")
        rotation = configuration.get_transform_frame_to_world("tcp", "site").rotation().as_matrix()
        self.jacobian = self.scale[:, None] * np.vstack(
            (rotation @ local[:3], rotation @ local[3:])
        )
        self.dt = dt

    def compute_error(self, configuration: mink.Configuration) -> Array:
        return -self.rate * self.dt

    def compute_jacobian(self, configuration: mink.Configuration) -> Array:
        return self.jacobian


class _MotionDirection(mink.Task):
    def __init__(self, task: _BaseVelocityTask) -> None:
        super().__init__(cost=np.ones(5))
        self.task = task

    def compute_error(self, configuration: mink.Configuration) -> Array:
        return np.zeros(5)

    def compute_jacobian(self, configuration: mink.Configuration) -> Array:
        return self.task.basis @ self.task.jacobian


class _CommandSpeed(mink.Limit):
    def __init__(self, task: _BaseVelocityTask) -> None:
        self.task = task

    def compute_qp_inequalities(
        self, configuration: mink.Configuration, dt: float
    ) -> mink.Constraint:
        row = self.task.unit @ self.task.jacobian
        # A solver may slow/hold the command, but must not reverse or amplify it.
        return mink.Constraint(
            np.vstack((row, -row)),
            np.array([np.linalg.norm(self.task.rate) * dt, 0.0]),
        )


class ArmModel:
    """MuJoCo state advanced by constrained IK and velocity-controlled actuators."""

    def __init__(self, joints: JointVector = INITIAL_JOINTS) -> None:
        initial = _finite_tuple(joints, 6, "joints")
        if any(value < low or value > high for value, (low, high) in zip(initial, JOINT_LIMITS)):
            raise ValueError("initial joint configuration exceeds demo limits")
        self._model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
        self._configuration = mink.Configuration(self._model)
        self._data = self._configuration.data
        mujoco.mj_resetDataKeyframe(self._model, self._data, self._model.key("home").id)
        self._data.qpos[:6] = initial
        mujoco.mj_forward(self._model, self._data)
        self._task = _BaseVelocityTask(self._model.nv)
        self._direction = _MotionDirection(self._task)
        self._fixed_tool_dofs = mink.DofFreezingTask(
            self._model,
            [
                int(self._model.jnt_dofadr[self._model.joint(name).id])
                for name in ("left_finger", "right_finger")
            ],
        )
        self._limits = [
            mink.ConfigurationLimit(self._model, gain=0.1),
            mink.VelocityLimit(
                self._model,
                {name: MAX_JOINT_SPEED_RAD_S for name in _ARM_JOINT_NAMES},
            ),
            mink.CollisionAvoidanceLimit(
                self._model,
                [
                    (("base",), ("forearm", "wrist_housing", *_TOOL_COLLISION_GEOMS)),
                    (("upper_arm",), _TOOL_COLLISION_GEOMS),
                ],
                gain=0.05,
                minimum_distance_from_collisions=0.015,
                collision_detection_distance=0.08,
            ),
            _CommandSpeed(self._task),
        ]
        self.reachable = True
        self.last_error: str | None = None

    @property
    def joints(self) -> JointVector:
        q = self._data.qpos
        return float(q[0]), float(q[1]), float(q[2]), float(q[3]), float(q[4]), float(q[5])

    @property
    def pose(self) -> dict[str, tuple[float, ...]]:
        actual = _tcp_pose(self._model, self._data)
        return {"position": actual.position, "orientation": actual.orientation}

    @property
    def jaw_gap(self) -> float:
        return float(np.sum(self._data.qpos[6:]))

    @property
    def opening_width(self) -> float:
        return self.jaw_gap

    @property
    def node_transforms(self) -> dict[str, dict[str, object]]:
        nodes = {}
        for node, (body_name, parent_name) in _SCENE_BODIES.items():
            body = self._model.body(body_name).id
            parent = self._model.body(parent_name).id
            parent_rotation = self._data.xmat[parent].reshape(3, 3)
            position = parent_rotation.T @ (self._data.xpos[body] - self._data.xpos[parent])
            inverse = np.empty(4)
            rotation = np.empty(4)
            mujoco.mju_negQuat(inverse, self._data.xquat[parent])
            mujoco.mju_mulQuat(rotation, inverse, self._data.xquat[body])
            nodes[node] = {
                "path": SCENE_NODE_PATHS[node],
                "position": _vector(position),
                "rotation": _quaternion(rotation),
            }
        return nodes

    def step(
        self,
        linear_velocity: Vector3,
        angular_velocity: Vector3,
        opening_rate: float,
        dt: float,
    ) -> dict[str, object]:
        """Advance actual state; zero commands brake without chasing old targets."""
        linear = _finite_tuple(linear_velocity, 3, "linear velocity")
        angular = _finite_tuple(angular_velocity, 3, "angular velocity")
        rate = _finite_tuple((opening_rate,), 1, "opening rate")[0]
        elapsed = _finite_tuple((dt,), 1, "dt")[0]
        if elapsed < 0:
            raise ValueError("dt must be non-negative")
        if math.hypot(*linear) > MAX_LINEAR_SPEED + 1e-9:
            raise ValueError(f"linear speed exceeds {MAX_LINEAR_SPEED} m/s demo limit")
        if math.hypot(*angular) > MAX_ANGULAR_SPEED + 1e-9:
            raise ValueError(f"angular speed exceeds {MAX_ANGULAR_SPEED} rad/s demo limit")
        if abs(rate) > MAX_OPENING_RATE + 1e-9:
            raise ValueError(f"jaw rate exceeds {MAX_OPENING_RATE} m/s demo limit")
        elapsed = min(elapsed, MAX_STEP_DT_S)
        active = math.hypot(*linear, *angular) > 0
        if active:
            self._task.set_rate(linear, angular)
        fraction = 1.0
        self.reachable = True
        self.last_error = None
        if elapsed == 0:
            return {**self.view(), "jaw_gap": self.jaw_gap}
        steps = max(1, math.ceil(elapsed / _PHYSICS_DT_S - 1e-9))
        substep = elapsed / steps
        self._model.opt.timestep = substep
        try:
            for _ in range(steps):
                self._configuration.update()
                self._data.ctrl[:6] = 0.0
                if active:
                    self._task.update(self._configuration, substep)
                    directions, singular_values, _ = np.linalg.svd(
                        self._task.jacobian, full_matrices=False
                    )
                    # Slow only commands that excite weak Cartesian directions,
                    # not every axis whenever the wrist approaches a singularity.
                    weakness = np.maximum(0.0, 1.0 - singular_values / 0.2)
                    excitation = directions.T @ self._task.unit
                    damping = 0.01 + float(np.sum((weakness * excitation) ** 2))
                    velocity = mink.solve_ik(
                        self._configuration,
                        [self._task],
                        substep,
                        "daqp",
                        limits=self._limits,
                        constraints=[self._direction, self._fixed_tool_dofs],
                        damping=damping,
                    )
                    self._data.ctrl[:6] = velocity[:6]
                    progress = self._task.unit @ self._task.jacobian @ velocity
                    fraction = min(fraction, float(progress / np.linalg.norm(self._task.rate)))
                self._data.ctrl[6] = np.clip(
                    rate,
                    0.1 * (MIN_JAW_GAP_M - self.opening_width) / substep,
                    0.1 * (MAX_JAW_GAP_M - self.opening_width) / substep,
                )
                mujoco.mj_step(self._model, self._data)
                if np.any(self._data.warning.number):
                    raise ArmSimulationError("MuJoCo reported a simulation warning")
                self._configuration.check_limits()
                if not MIN_JAW_GAP_M - 1e-6 <= self.opening_width <= MAX_JAW_GAP_M + 1e-6:
                    raise ArmSimulationError("Parallel-jaw gap exceeds its mechanical range")
            mujoco.mj_forward(self._model, self._data)
        except (
            mink.NoSolutionFound,
            mink.NotWithinConfigurationLimits,
            mujoco.FatalError,
            np.linalg.LinAlgError,
            ArmSimulationError,
        ) as exc:
            self._data.ctrl[:] = 0
            self.reachable = False
            self.last_error = f"MuJoCo/Mink simulation failed: {exc}"
            raise ArmSimulationError(self.last_error) from exc
        if active and fraction < 0.95:
            self.reachable = fraction > 1e-3
            action = "reducing motion" if self.reachable else "holding position"
            self.last_error = f"Motion limit: {action}"
        return {**self.view(), "jaw_gap": self.jaw_gap}

    def view(self) -> dict[str, object]:
        actual = self.pose
        return {
            "pose": actual,
            "position": actual["position"],
            "orientation": actual["orientation"],
            "joints": self.joints,
            "opening_width": self.opening_width,
            "reachable": self.reachable,
            "error": self.last_error,
        }
