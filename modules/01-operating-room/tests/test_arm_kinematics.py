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

import sys

import pytest
from module01_test_support import SRC_DIR

sys.path.insert(0, str(SRC_DIR))

from ArmKinematics import (  # noqa: E402
    GRIPPER_MAX_DEG,
    GRIPPER_MIN_DEG,
    GRIPPER_STEP_DEG,
    JOG_STEP_MM,
    ROTATION_STEP_DEG,
    ArmJoint,
    apply_teleop_jog,
    planar_tool_position,
)


@pytest.fixture
def initial_angles():
    return {
        ArmJoint.BASE: 204.0,
        ArmJoint.SHOULDER: 220.0,
        ArmJoint.ELBOW: 120.0,
        ArmJoint.WRIST: 220.0,
        ArmJoint.HAND: 45.0,
    }


def test_cartesian_jog_moves_tool_in_requested_direction(initial_angles):
    before_x, before_y = planar_tool_position(initial_angles)

    moved_x = apply_teleop_jog(
        initial_angles,
        "X",
        "POSITIVE",
    )
    moved_y = apply_teleop_jog(
        initial_angles,
        "Y",
        "POSITIVE",
    )

    after_x = planar_tool_position(moved_x)
    after_y = planar_tool_position(moved_y)
    assert after_x[0] > before_x
    assert after_y[1] > before_y
    assert after_x[0] - before_x == pytest.approx(JOG_STEP_MM)
    assert after_y[1] - before_y == pytest.approx(JOG_STEP_MM)


def test_cartesian_jog_preserves_tool_orientation(initial_angles):
    orientation = sum(
        initial_angles[motor] - 180.0
        for motor in (
            ArmJoint.SHOULDER,
            ArmJoint.ELBOW,
            ArmJoint.WRIST,
        )
    )

    moved = apply_teleop_jog(
        initial_angles,
        "X",
        "POSITIVE",
    )
    moved_orientation = sum(
        moved[motor] - 180.0
        for motor in (
            ArmJoint.SHOULDER,
            ArmJoint.ELBOW,
            ArmJoint.WRIST,
        )
    )
    assert moved_orientation == pytest.approx(orientation)


def test_gripper_is_limited_to_its_simulated_travel(initial_angles):
    opened = dict(initial_angles)
    opened[ArmJoint.HAND] = GRIPPER_MAX_DEG
    opened = apply_teleop_jog(
        opened,
        "GRIPPER",
        "POSITIVE",
    )

    closed = dict(initial_angles)
    closed[ArmJoint.HAND] = GRIPPER_MIN_DEG
    closed = apply_teleop_jog(
        closed,
        "GRIPPER",
        "NEGATIVE",
    )

    assert opened[ArmJoint.HAND] == GRIPPER_MAX_DEG
    assert closed[ArmJoint.HAND] == GRIPPER_MIN_DEG


def test_roll_left_increases_visual_wrist_angle(initial_angles):
    rolled_left = apply_teleop_jog(
        initial_angles,
        "ROLL",
        "POSITIVE",
    )
    assert rolled_left[ArmJoint.WRIST] - initial_angles[ArmJoint.WRIST] == ROTATION_STEP_DEG


def test_roll_right_decreases_visual_wrist_angle(initial_angles):
    rolled_right = apply_teleop_jog(
        initial_angles,
        "ROLL",
        "NEGATIVE",
    )
    assert rolled_right[ArmJoint.WRIST] - initial_angles[ArmJoint.WRIST] == -ROTATION_STEP_DEG


def test_gripper_motion_uses_small_incremental_steps(initial_angles):
    moved = apply_teleop_jog(
        initial_angles,
        "GRIPPER",
        "NEGATIVE",
    )
    assert initial_angles[ArmJoint.HAND] - moved[ArmJoint.HAND] == GRIPPER_STEP_DEG


def test_device_command_transitions_are_application_logic():
    from ApplicationLogic import device_status_after_command

    assert device_status_after_command("START") == "ON"
    assert device_status_after_command("PAUSE") == "PAUSED"
    assert device_status_after_command("SHUTDOWN") == "OFF"

    with pytest.raises(ValueError, match="Unsupported device command"):
        device_status_after_command("REBOOT")
