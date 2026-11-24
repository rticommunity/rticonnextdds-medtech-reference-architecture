#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

from dataclasses import replace

import pytest
from PhysicalMotionGate import MotionConditions, PhysicalMotionGate


@pytest.fixture
def ready():
    return MotionConditions(
        arm_connected=True,
        arm_healthy=True,
        command_fresh=True,
        controls_neutral=True,
    )


def test_requires_explicit_rearm_with_neutral_controls(ready):
    gate = PhysicalMotionGate()
    gate.update(replace(ready, controls_neutral=False))
    assert not gate.can_rearm
    assert not gate.rearm()
    assert not gate.armed

    gate.update(ready)
    assert not gate.armed
    assert gate.can_rearm
    assert gate.rearm()
    assert not gate.can_rearm
    gate.update(replace(ready, controls_neutral=False))
    assert gate.armed


@pytest.mark.parametrize(
    "lost_condition",
    ("arm_connected", "arm_healthy", "command_fresh"),
)
def test_loss_disarms_and_recovery_does_not_rearm(ready, lost_condition):
    gate = PhysicalMotionGate()
    gate.update(ready)
    assert gate.rearm()

    gate.update(replace(ready, **{lost_condition: False}))
    assert not gate.armed
    assert not gate.rearm()

    gate.update(ready)
    assert not gate.armed
    assert gate.rearm()


def test_explicit_disarm_needs_new_rearm(ready):
    gate = PhysicalMotionGate()
    gate.update(ready)
    assert gate.rearm()
    gate.disarm()
    assert not gate.rearm()
    gate.update(ready)
    assert not gate.armed
    assert gate.rearm()
