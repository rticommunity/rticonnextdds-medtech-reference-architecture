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

import json
import math
import random
import struct
import sys

import mink
import mujoco
import numpy as np
import pytest
from module01_test_support import REPO_ROOT, SRC_DIR

sys.path.insert(0, str(SRC_DIR))

from ArmKinematics import (  # noqa: E402
    BASE_HEIGHT_M,
    FOREARM_M,
    JOINT_LIMITS,
    MAX_JAW_GAP_M,
    MAX_STEP_DT_S,
    MIN_JAW_GAP_M,
    TCP_OFFSET_M,
    UPPER_ARM_M,
    ArmModel,
    ArmSimulationError,
    forward_kinematics,
)


def _rotate(quaternion, vector):
    x, y, z, w = quaternion
    vx, vy, vz = vector
    tx = 2 * (y * vz - z * vy)
    ty = 2 * (z * vx - x * vz)
    tz = 2 * (x * vy - y * vx)
    return (
        vx + w * tx + y * tz - z * ty,
        vy + w * ty + z * tx - x * tz,
        vz + w * tz + x * ty - y * tx,
    )


def _distance(a, b):
    return math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def test_startup_tool_points_forward_and_down_and_remains_stationary_when_idle():
    model = ArmModel()
    before = model.pose
    assert _rotate(before["orientation"], (0, 0, 1)) == pytest.approx(
        (math.cos(0.35), 0, -math.sin(0.35)), abs=1e-9
    )
    assert before["position"][2] > BASE_HEIGHT_M
    state = model.step((0, 0, 0), (0, 0, 0), 0.0, 0.02)
    assert state["reachable"]
    assert state["pose"]["position"] == pytest.approx(before["position"], abs=1e-9)
    assert state["pose"]["orientation"] == pytest.approx(before["orientation"], abs=1e-9)


def test_startup_allows_one_second_of_motion_in_each_base_axis_direction():
    for axis in range(3):
        for direction in (-1, 1):
            for rotating in (False, True):
                model = ArmModel()
                rate = tuple(
                    direction * (0.5 if rotating else 0.05) if i == axis else 0.0 for i in range(3)
                )
                for _ in range(50):
                    state = model.step(
                        (0, 0, 0) if rotating else rate,
                        rate if rotating else (0, 0, 0),
                        0.0,
                        0.02,
                    )
                    assert state["reachable"], (axis, direction, rotating, state["error"])
                    assert state["error"] is None, (axis, direction, rotating, state["error"])


@pytest.mark.parametrize(
    "joints",
    [
        (0.0, 0.35, -0.75, 0.0, 0.2, 0.0),
        (0.7, 0.5, -1.2, 0.3, -0.4, 0.8),
        (-1.0, 0.8, 1.1, -0.5, 0.6, -0.7),
        (0.0, 1.3, 2.3, 0.0, 0.0, 0.0),
    ],
)
def test_engine_fk_preserves_original_fixed_links_and_tcp_offset(joints):
    pose = forward_kinematics(joints)
    model = ArmModel(joints=joints)
    assert model.pose["position"] == pytest.approx(pose.position, abs=1e-8)
    assert model.pose["orientation"] == pytest.approx(pose.orientation, abs=1e-8)
    shoulder = (0.0, 0.0, BASE_HEIGHT_M)
    elbow = (
        UPPER_ARM_M * math.cos(joints[0]) * math.cos(joints[1]),
        UPPER_ARM_M * math.sin(joints[0]) * math.cos(joints[1]),
        BASE_HEIGHT_M + UPPER_ARM_M * math.sin(joints[1]),
    )
    wrist_center = (
        (UPPER_ARM_M * math.cos(joints[1]) + FOREARM_M * math.cos(joints[1] + joints[2]))
        * math.cos(joints[0]),
        (UPPER_ARM_M * math.cos(joints[1]) + FOREARM_M * math.cos(joints[1] + joints[2]))
        * math.sin(joints[0]),
        BASE_HEIGHT_M
        + UPPER_ARM_M * math.sin(joints[1])
        + FOREARM_M * math.sin(joints[1] + joints[2]),
    )
    assert _distance(shoulder, elbow) == pytest.approx(UPPER_ARM_M)
    assert _distance(elbow, wrist_center) == pytest.approx(FOREARM_M)
    assert _distance(wrist_center, pose.position) == pytest.approx(TCP_OFFSET_M)
    state = model.step((0, 0, 0), (0, 0, 0), 0.0, 0.1)
    assert state["reachable"]
    assert state["joints"] == pytest.approx(joints, abs=1e-8)


@pytest.mark.parametrize(
    "joints",
    ((0.8, 0.4, -0.9, 0.0, 0.3, 0.0), (-0.5, 0.6, -1.1, 0.2, -0.4, 0.3)),
)
def test_base_frame_translation_is_independent_of_tool_orientation(joints):
    model = ArmModel(joints=joints)
    before = model.pose
    linear = (0.04, -0.02, 0.01)
    expected_delta = tuple(value * 0.1 for value in linear)

    state = model.step(linear, (0.0, 0.0, 0.0), 0.0, 0.1)

    assert state["reachable"] is True
    assert state["pose"]["position"] == pytest.approx(
        tuple(before["position"][i] + expected_delta[i] for i in range(3)),
        abs=2e-4,
    )
    assert state["pose"]["orientation"] == pytest.approx(before["orientation"], abs=1e-3)


@pytest.mark.parametrize("axis", range(3))
def test_rotation_uses_base_axes_through_tcp_without_translating_it(axis):
    model = ArmModel(joints=(0.8, 0.4, -0.9, 0.2, 0.3, 0.1))
    before = model.pose
    angular = tuple(0.4 if i == axis else 0.0 for i in range(3))

    state = model.step((0.0, 0.0, 0.0), angular, 0.0, 0.1)

    orientation = state["pose"]["orientation"]
    assert state["reachable"]
    assert state["pose"]["position"] == pytest.approx(before["position"], abs=2e-4)
    assert orientation != pytest.approx(before["orientation"])
    assert math.sqrt(sum(value * value for value in orientation)) == pytest.approx(1.0)
    delta = tuple(math.sin(0.02) if i == axis else 0.0 for i in range(3)) + (math.cos(0.02),)
    for basis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        expected = _rotate(delta, _rotate(before["orientation"], basis))
        assert _rotate(orientation, basis) == pytest.approx(expected, abs=3e-3)


def test_combined_base_twist_reaches_nearby_continuous_joint_configuration():
    model = ArmModel()
    previous = model.joints

    state = model.step((0.02, 0.01, -0.01), (0.1, 0.15, -0.1), 0.0, 0.08)

    assert state["reachable"] is True
    assert all(low <= angle <= high for angle, (low, high) in zip(state["joints"], JOINT_LIMITS))
    assert max(abs(state["joints"][i] - previous[i]) for i in range(6)) < 0.1


@pytest.mark.parametrize(
    ("joints", "angular"),
    [
        (
            (0.3145374212, 1.2025086684, -1.6786208898, 1.0176732369, -0.2334806362, -3.1347202970),
            (0.0, 0.5, 0.0),
        ),
        (
            (0.4678116062, 0.7916797301, -1.6680195066, 1.7093020993, -1.2601357087, 3.1359350441),
            (0.0, -0.5, 0.0),
        ),
    ],
)
def test_joint_branch_jump_is_prevented_and_reversing_recovers(joints, angular):
    model = ArmModel(joints=joints)
    before = model.pose
    before_gap = model.jaw_gap

    state = model.step((0, 0, 0), angular, 0.02, 0.02)

    assert state["error"] == "Motion limit: reducing motion"
    assert max(abs(a - b) for a, b in zip(model.joints, joints)) <= 2.0 * 0.02 + 1e-4
    assert model.pose["position"] == pytest.approx(before["position"], abs=2e-4)
    assert model.jaw_gap == pytest.approx(before_gap + 0.0004, abs=3e-5)

    previous = model.joints
    recovered = model.step((0, 0, 0), tuple(-value for value in angular), 0.0, 0.02)
    assert recovered["reachable"]
    assert recovered["error"] is None
    assert model.pose != before
    assert max(abs(a - b) for a, b in zip(model.joints, previous)) <= 2.0 * 0.02 + 1e-4


@pytest.mark.parametrize(
    ("joints", "speed"),
    [
        ((0.0, 0.1221944351, -0.2467257174, 0.0, 0.4754687177, 0.0), 0.05),
        (
            (2.9830066505, 0.6724478914, -0.2028537642, 2.9843311651, -0.7141922932, 2.9045811011),
            -0.05,
        ),
    ],
)
def test_reachable_straight_x_motion_slows_down_instead_of_freezing(joints, speed):
    model = ArmModel(joints=joints)
    before = model.pose
    previous = model.joints

    state = model.step((speed, 0, 0), (0, 0, 0), 0.0, 0.02)

    assert state["reachable"]
    assert state["error"] == "Motion limit: reducing motion"
    fraction = (model.pose["position"][0] - before["position"][0]) / (speed * 0.02)
    assert 0.0 < fraction < 1.0
    assert model.pose["position"][1:] == pytest.approx(before["position"][1:], abs=3e-4)
    assert model.pose["orientation"] == pytest.approx(before["orientation"], abs=1e-3)
    assert max(abs(a - b) for a, b in zip(model.joints, previous)) <= 2.0 * 0.02 + 1e-4
    model.step((0, 0, 0), (0, 0, 0), 0.0, 0.1)
    assert model.pose["position"][1:] == pytest.approx(before["position"][1:], abs=1e-5)


def test_joint_speed_limit_scales_with_elapsed_time():
    model = ArmModel(joints=(0.8, 0.4, -0.9, 0.2, 0.3, 0.1))
    for dt in (0.0, 0.001, 0.02, 0.1):
        previous = model.joints
        state = model.step((0.02, 0.01, -0.01), (0.1, 0.15, -0.1), 0.0, dt)
        assert state["reachable"]
        assert max(abs(a - b) for a, b in zip(model.joints, previous)) <= 2.0 * dt + 1e-4


def test_wrist_singularity_can_be_crossed_when_joint_motion_is_continuous():
    model = ArmModel(joints=(0.0, 0.35, -0.75, 0.0, 1.56, 0.0))
    before = model.joints

    state = model.step((0, 0, 0), (0, 0.5, 0), 0.0, 0.08)

    assert state["reachable"]
    assert before[4] < math.pi / 2 < model.joints[4]
    assert max(abs(a - b) for a, b in zip(model.joints, before)) <= 2.0 * 0.08


def test_unreachable_step_retains_last_actual_pose_and_joint_state():
    model = ArmModel(joints=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    before_pose = model.pose
    before_joints = model.joints

    state = model.step((0.05, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0, 0.1)

    assert state["reachable"] is False
    assert state["error"]
    assert state["pose"]["position"] == pytest.approx(before_pose["position"], abs=1e-9)
    assert state["pose"]["orientation"] == pytest.approx(before_pose["orientation"], abs=1e-9)
    assert state["joints"] == pytest.approx(before_joints, abs=1e-9)


@pytest.mark.parametrize(
    ("joints", "message"),
    [
        ((), "joints"),
        ((math.nan, 0, 0, 0, 0, 0), "finite"),
        ((0, 2.4, 0, 0, 0, 0), "exceeds demo limits"),
    ],
)
def test_model_rejects_invalid_initial_joints(joints, message):
    with pytest.raises(ValueError, match=message):
        ArmModel(joints=joints)


def test_signed_jaw_rate_changes_total_gap_symmetrically_and_clamps():
    model = ArmModel()
    start = model.jaw_gap

    opened = model.step((0, 0, 0), (0, 0, 0), 0.02, 0.1)
    assert opened["jaw_gap"] == pytest.approx(start + 0.002, abs=3e-5)
    nodes = model.node_transforms
    assert nodes["left_finger"]["position"][0] == pytest.approx(opened["jaw_gap"] / 2, abs=2e-6)
    assert nodes["right_finger"]["position"][0] == pytest.approx(-opened["jaw_gap"] / 2, abs=2e-6)

    for _ in range(100):
        model.step((0, 0, 0), (0, 0, 0), 0.02, 0.1)
    assert model.jaw_gap == pytest.approx(MAX_JAW_GAP_M, abs=1e-7)
    for _ in range(100):
        model.step((0, 0, 0), (0, 0, 0), -0.02, 0.1)
    assert model.jaw_gap == pytest.approx(MIN_JAW_GAP_M, abs=1e-7)


def test_combined_motion_keeps_closed_jaws_coupled_without_false_limit_faults():
    rng = random.Random(712)
    model = ArmModel()
    reached_closed = False
    for tick in range(600):
        if tick % 30 == 0:
            linear = np.array([rng.uniform(-1, 1) for _ in range(3)])
            linear *= 0.05 / np.linalg.norm(linear)
            angular = np.array([rng.uniform(-1, 1) for _ in range(3)])
            angular *= 0.5 / np.linalg.norm(angular)
            rate = rng.choice((-0.02, 0, 0.02))
        model.step(tuple(linear), tuple(angular), rate, 0.02)
        assert MIN_JAW_GAP_M - 1e-6 <= model.opening_width <= MAX_JAW_GAP_M + 1e-6
        reached_closed |= model.opening_width < 1e-6
        nodes = model.node_transforms
        left = nodes["left_finger"]["position"][0]
        right = nodes["right_finger"]["position"][0]
        assert left - right == pytest.approx(model.opening_width, abs=1e-10)
        # The physical gear constraint permits small compliance under acceleration.
        assert abs(left + right) < 5e-4
    assert reached_closed


@pytest.mark.parametrize("opening_rate", (-0.02, 0.0, 0.02))
def test_rendered_jaws_remain_attached_and_match_observed_contact_gap(opening_rate):
    asset = (REPO_ROOT / "resources/ui/web/models/articulated-arm.glb").read_bytes()
    json_length = struct.unpack_from("<I", asset, 12)[0]
    document = json.loads(asset[20 : 20 + json_length])
    nodes = {node["name"]: node for node in document["nodes"]}
    model = ArmModel()
    for _ in range(40):
        model.step((0, 0, 0), (0, 0, 0), opening_rate, 0.1)

    def bounds(name, parent_position=(0, 0, 0)):
        node = nodes[name]
        primitive = document["meshes"][node["mesh"]]["primitives"][0]
        positions = document["accessors"][primitive["attributes"]["POSITION"]]
        offset = tuple(a + b for a, b in zip(node["translation"], parent_position))
        return tuple(
            tuple(value + shift for value, shift in zip(positions[limit], offset))
            for limit in ("min", "max")
        )

    palm_min, palm_max = bounds("GripperPalm")
    shaft_min, shaft_max = bounds("ToolShaft")
    pads = {}
    for side, node_id in (("Left", "left_finger"), ("Right", "right_finger")):
        position = model.node_transforms[node_id]["position"]
        finger_min, finger_max = bounds(f"{side}FingerBody", position)
        pads[side] = bounds(f"{side}FingerPad", position)
        assert all(
            min(finger_max[i], palm_max[i]) > max(finger_min[i], palm_min[i]) for i in range(3)
        ), "Finger must remain physically attached to the palm over its full travel"
        pad_min, pad_max = pads[side]
        assert all(
            min(finger_max[i], pad_max[i]) > max(finger_min[i], pad_min[i]) for i in range(3)
        ), "Contact pad must remain attached to its finger"
        assert (pad_min[2] + pad_max[2]) / 2 == pytest.approx(0.0)

    assert pads["Left"][0][0] - pads["Right"][1][0] == pytest.approx(model.opening_width)
    assert shaft_min[2] < palm_min[2] < shaft_max[2] < palm_max[2]
    assert shaft_max[2] < pads["Left"][0][2], "Shaft must not occupy the gripping space"


def test_elapsed_step_is_bounded_and_invalid_rates_are_rejected():
    model = ArmModel()
    initial = model.pose["position"]
    state = model.step((0.05, 0.0, 0.0), (0, 0, 0), 0.0, 2.0)
    expected = _rotate(model.pose["orientation"], (0.05 * MAX_STEP_DT_S, 0, 0))
    assert _distance(initial, state["pose"]["position"]) == pytest.approx(
        math.sqrt(sum(value * value for value in expected)), abs=2e-4
    )

    with pytest.raises(ValueError, match="linear speed"):
        model.step((0.3, 0, 0), (0, 0, 0), 0.0, 0.1)
    with pytest.raises(ValueError, match="angular speed"):
        model.step((0, 0, 0), (0.0, 0.51, 0.0), 0.0, 0.1)
    with pytest.raises(ValueError, match="jaw rate"):
        model.step((0, 0, 0), (0, 0, 0), 0.021, 0.1)
    with pytest.raises(ValueError, match="finite"):
        model.step((float("nan"), 0, 0), (0, 0, 0), 0.0, 0.1)
    with pytest.raises(ValueError, match="dt"):
        model.step((0, 0, 0), (0, 0, 0), 0.0, -0.1)


def test_workspace_limit_does_not_flip_elbow_or_block_return_to_previous_position():
    model = ArmModel()
    start = model.pose
    limited = False
    for direction in (1, -1):
        for _ in range(350):
            previous = model.joints
            state = model.step((direction * 0.05, 0, 0), (0, 0, 0), 0, 0.02)
            limited |= state["error"] is not None
            assert model.joints[2] < 0, "The elbow must not cross its extension singularity"
            assert max(abs(a - b) for a, b in zip(model.joints, previous)) <= 0.0405
            assert model.pose["position"][1:] == pytest.approx(start["position"][1:], abs=1e-3)
            assert all(
                lo - 1e-6 <= q <= hi + 1e-6 for q, (lo, hi) in zip(model.joints, JOINT_LIMITS)
            )
    assert limited
    assert state["error"] is None
    assert model.pose["position"][0] <= start["position"][0] + 0.003


@pytest.mark.parametrize(
    ("joints", "velocity", "pair"),
    [
        (
            (-0.9564, 1.5549, -2.5288, 0.9333, 2.0245, -1.1802),
            (-0.03792, 0.03258, 0),
            ("base", "palm"),
        ),
        (
            (1.6068424, 1.4425253, 2.2408657, 0.0514485, -1.8052425, -2.7561504),
            (-0.0000302, 0.0495897, -0.0063920),
            ("upper_arm", "right_finger_pad"),
        ),
    ],
)
def test_collision_approach_slows_before_contact_and_reverse_recovers(joints, velocity, pair):
    model = ArmModel(joints=joints)
    geom_a, geom_b = (model._model.geom(name).id for name in pair)
    points = np.zeros(6)
    limited = False
    for _ in range(200):
        state = model.step(velocity, (0, 0, 0), 0, 0.02)
        limited |= state["error"] is not None
        for first, second in model._limits[2].geom_id_pairs:
            clearance = mujoco.mj_geomDistance(
                model._model, model._data, first, second, 0.1, points
            )
            assert clearance > 0
    assert limited
    assert mujoco.mj_geomDistance(model._model, model._data, geom_a, geom_b, 0.1, points) < 0.025
    stopped = model.pose["position"]
    for _ in range(100):
        state = model.step(tuple(-value for value in velocity), (0, 0, 0), 0, 0.02)
    assert _distance(stopped, model.pose["position"]) > 0.02
    assert state["error"] is None


def test_arm_ik_cannot_solve_collisions_using_uncommanded_jaw_motion(monkeypatch):
    model = ArmModel(joints=(-0.9564, 1.5549, -2.5288, 0.9333, 2.0245, -1.1802))
    solve_ik = mink.solve_ik
    finger_velocities = []

    def record(*args, **kwargs):
        velocity = solve_ik(*args, **kwargs)
        finger_velocities.extend(velocity[6:])
        return velocity

    monkeypatch.setattr(mink, "solve_ik", record)
    for _ in range(100):
        model.step((-0.03792, 0.03258, 0), (0, 0, 0), 0, 0.02)
    assert max(abs(value) for value in finger_velocities) < 1e-8


def test_actuators_brake_on_release_without_chasing_a_previous_pose_target():
    model = ArmModel()
    for _ in range(50):
        model.step((0.05, 0, 0), (0, 0, 0), 0.02, 0.02)
    released_pose = model.pose
    released_gap = model.opening_width
    assert np.max(np.abs(model._data.qvel)) > 0
    for _ in range(25):
        state = model.step((0, 0, 0), (0, 0, 0), 0, 0.02)
    assert _distance(released_pose["position"], model.pose["position"]) < 3e-4
    assert abs(model.opening_width - released_gap) < 3e-5
    assert np.max(np.abs(model._data.qvel)) < 1e-8
    assert state["error"] is None
    held_pose = model.pose
    held_gap = model.opening_width
    model.step((0, 0, 0), (0, 0, 0), 0, 0.1)
    assert model.pose["position"] == pytest.approx(held_pose["position"], abs=1e-9)
    assert model.opening_width == pytest.approx(held_gap, abs=1e-9)


def test_numerical_backend_failure_is_not_reported_as_success(monkeypatch):
    def fail(*args, **kwargs):
        raise mink.NoSolutionFound("daqp")

    model = ArmModel()
    monkeypatch.setattr(mink, "solve_ik", fail)
    with pytest.raises(ArmSimulationError, match="daqp"):
        model.step((0.05, 0, 0), (0, 0, 0), 0, 0.02)
    assert not model.reachable
    assert model.last_error
    assert np.all(model._data.ctrl == 0)


@pytest.mark.parametrize("gap", (-0.002, 0.062))
def test_out_of_range_physical_jaw_gap_is_a_backend_fault(gap):
    model = ArmModel()
    model._data.qpos[6:] = gap / 2
    with pytest.raises(ArmSimulationError, match="mechanical range"):
        model.step((0, 0, 0), (0, 0, 0), 0, 0.002)
    assert not model.reachable
    assert np.all(model._data.ctrl == 0)
