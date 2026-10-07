import sys
import xml.etree.ElementTree as ET

import pytest
from module01_test_support import SRC_DIR

sys.path.insert(0, str(SRC_DIR))

from ArmKinematics import (  # noqa: E402
    GRIPPER_MAX_DEG,
    GRIPPER_MIN_DEG,
    GRIPPER_STEP_DEG,
    JOG_STEP_MM,
    ROTATION_STEP_DEG,
    apply_teleop_jog,
    planar_tool_position,
)
from Types import SurgicalRobot  # noqa: E402


@pytest.fixture
def initial_angles():
    return {
        SurgicalRobot.Motors.BASE: 204.0,
        SurgicalRobot.Motors.SHOULDER: 220.0,
        SurgicalRobot.Motors.ELBOW: 120.0,
        SurgicalRobot.Motors.WRIST: 220.0,
        SurgicalRobot.Motors.HAND: 45.0,
    }


def test_cartesian_jog_moves_tool_in_requested_direction(initial_angles):
    before_x, before_y = planar_tool_position(initial_angles)

    moved_x = apply_teleop_jog(
        initial_angles,
        SurgicalRobot.TeleopAxes.X,
        SurgicalRobot.TeleopDirections.POSITIVE,
    )
    moved_y = apply_teleop_jog(
        initial_angles,
        SurgicalRobot.TeleopAxes.Y,
        SurgicalRobot.TeleopDirections.POSITIVE,
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
            SurgicalRobot.Motors.SHOULDER,
            SurgicalRobot.Motors.ELBOW,
            SurgicalRobot.Motors.WRIST,
        )
    )

    moved = apply_teleop_jog(
        initial_angles,
        SurgicalRobot.TeleopAxes.X,
        SurgicalRobot.TeleopDirections.POSITIVE,
    )
    moved_orientation = sum(
        moved[motor] - 180.0
        for motor in (
            SurgicalRobot.Motors.SHOULDER,
            SurgicalRobot.Motors.ELBOW,
            SurgicalRobot.Motors.WRIST,
        )
    )
    assert moved_orientation == pytest.approx(orientation)


def test_gripper_is_limited_to_its_simulated_travel(initial_angles):
    opened = dict(initial_angles)
    opened[SurgicalRobot.Motors.HAND] = GRIPPER_MAX_DEG
    opened = apply_teleop_jog(
        opened,
        SurgicalRobot.TeleopAxes.GRIPPER,
        SurgicalRobot.TeleopDirections.POSITIVE,
    )

    closed = dict(initial_angles)
    closed[SurgicalRobot.Motors.HAND] = GRIPPER_MIN_DEG
    closed = apply_teleop_jog(
        closed,
        SurgicalRobot.TeleopAxes.GRIPPER,
        SurgicalRobot.TeleopDirections.NEGATIVE,
    )

    assert opened[SurgicalRobot.Motors.HAND] == GRIPPER_MAX_DEG
    assert closed[SurgicalRobot.Motors.HAND] == GRIPPER_MIN_DEG


def test_positive_roll_increases_visual_wrist_angle(initial_angles):
    rotated = apply_teleop_jog(
        initial_angles,
        SurgicalRobot.TeleopAxes.ROLL,
        SurgicalRobot.TeleopDirections.POSITIVE,
    )
    assert (
        rotated[SurgicalRobot.Motors.WRIST] - initial_angles[SurgicalRobot.Motors.WRIST]
        == ROTATION_STEP_DEG
    )


def test_gripper_motion_uses_small_incremental_steps(initial_angles):
    moved = apply_teleop_jog(
        initial_angles,
        SurgicalRobot.TeleopAxes.GRIPPER,
        SurgicalRobot.TeleopDirections.NEGATIVE,
    )
    assert (
        initial_angles[SurgicalRobot.Motors.HAND] - moved[SurgicalRobot.Motors.HAND]
        == GRIPPER_STEP_DEG
    )


def test_arm_controller_has_no_per_joint_angle_controls():
    ui_path = SRC_DIR.parent / "ui" / "armcontroller.glade"
    root = ET.parse(ui_path).getroot()
    ids = {node.get("id") for node in root.iter() if node.get("id")}
    labels = {node.text or "" for node in root.iter("property") if node.get("name") == "label"}

    assert not any(
        f"{joint}_{action}" in ids
        for joint in ("base", "shoulder", "elbow", "wrist", "hand")
        for action in ("inc", "dec", "play")
    )
    assert "joint_service_expander" not in ids
    assert "TOOL TIP" not in labels
    assert {"roll_left", "roll_right", "run_demo", "stop_motion"} <= ids
