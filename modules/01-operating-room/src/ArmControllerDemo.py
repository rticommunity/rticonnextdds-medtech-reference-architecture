#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Feedback-anchored showcase shared by the hardware controllers."""

import math


class ArmControllerDemo:
    WAYPOINTS = (
        (-0.012, 0.010, 0.008, 1.0),
        (-0.012, -0.010, 0.008, 0.0),
        (0.0, -0.010, 0.0, 1.0),
        (0.0, 0.0, 0.0, 0.0),
    )

    def __init__(self) -> None:
        self.running = False
        self.cycles = 0
        self.phase = 0
        self.phase_started = 0.0
        self.return_hold_until = 0.0
        self.origin = (0.0, 0.0, 0.0)
        self.jaw_origin = 0.0
        self.jaw_excursion = 0.0
        self.manual_blocked = False

    @staticmethod
    def ready(position, jaw, received_at, readiness, now) -> bool:
        return (
            position is not None
            and jaw is not None
            and received_at is not None
            and 0 <= now - received_at <= 0.5
            and readiness != "FAULTED"
            and all(math.isfinite(value) for value in (*position, jaw))
            and 0 <= jaw <= 0.06
        )

    def start(self, position, jaw, now) -> None:
        self.running = True
        self.manual_blocked = False
        self.cycles = 0
        self.phase = 0
        self.phase_started = self.return_hold_until = now
        self.origin = position
        self.jaw_origin = jaw
        self.jaw_excursion = 0.008 if jaw <= 0.03 else -0.008

    def stop(self) -> None:
        self.running = False

    def inhibit(self) -> None:
        self.stop()
        self.manual_blocked = True

    def select(self, manual_rates, manual_active, connected, ready, position, jaw, now):
        if self.manual_blocked:
            if manual_active:
                return None, None
            self.manual_blocked = False
        if not self.running:
            return manual_rates, None
        if not connected or not ready:
            self.inhibit()
            return None, "Demo input or feedback unavailable; stopped motion"
        if manual_active:
            self.stop()
            return manual_rates, "Manual input took over from demo"
        if now - self.phase_started > 4.0:
            self.inhibit()
            return None, "Demo waypoint timed out; stopped motion"
        return self.rates(position, jaw, now), None

    def rates(self, position, jaw, now) -> dict:
        linear = (0.0, 0.0, 0.0)
        opening = 0.0
        if now >= self.return_hold_until:
            waypoint = self.WAYPOINTS[self.phase]
            error = tuple(self.origin[i] + waypoint[i] - position[i] for i in range(3))
            jaw_error = self.jaw_origin + waypoint[3] * self.jaw_excursion - jaw
            distance = math.hypot(*error)
            if distance <= 0.0007 and abs(jaw_error) <= 0.0004:
                self.phase += 1
                if self.phase == len(self.WAYPOINTS):
                    self.phase = 0
                    self.cycles += 1
                    self.return_hold_until = now + 0.4
                self.phase_started = now
            else:
                linear = tuple(value * 4.0 for value in error)
                magnitude = math.hypot(*linear)
                if magnitude > 0.018:
                    linear = tuple(value * 0.018 / magnitude for value in linear)
                opening = max(-0.01, min(0.01, jaw_error * 4.0))
        return {
            "linear_velocity": dict(zip(("x", "y", "z"), linear)),
            "angular_velocity": dict.fromkeys(("x", "y", "z"), 0.0),
            "opening_rate": opening,
        }

    def controls(self, enabled: bool) -> dict:
        return {
            "title": "DEMO MOTION",
            "layout": "demo-controls",
            "controls": [
                {
                    "type": "button",
                    "label": "RUN DEMO",
                    "command": "start-demo",
                    "payload": {},
                    "style": "primary",
                    "disabled": not enabled or self.running,
                },
                {
                    "type": "button",
                    "label": "STOP MOTION",
                    "command": "stop-demo",
                    "payload": {},
                    "style": "danger",
                },
            ],
        }
