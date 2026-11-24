#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Software re-arm policy for a physical arm; not a physical safety system."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MotionConditions:
    arm_connected: bool
    arm_healthy: bool
    command_fresh: bool
    controls_neutral: bool

    @property
    def available(self) -> bool:
        return self.arm_connected and self.arm_healthy and self.command_fresh


class PhysicalMotionGate:
    def __init__(self) -> None:
        self._conditions = MotionConditions(False, False, False, False)
        self._armed = False

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def can_rearm(self) -> bool:
        return not self._armed and self._conditions.available and self._conditions.controls_neutral

    def update(self, conditions: MotionConditions) -> None:
        self._conditions = conditions
        if not conditions.available:
            self._armed = False

    def disarm(self) -> None:
        self._armed = False
        self._conditions = MotionConditions(False, False, False, False)

    def rearm(self) -> bool:
        """Process one explicit operator re-arm event, without queuing it."""
        if self.can_rearm:
            self._armed = True
            return True
        return False
