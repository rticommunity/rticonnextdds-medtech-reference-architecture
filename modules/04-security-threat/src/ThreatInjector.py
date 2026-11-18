#
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software. RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

from __future__ import annotations

import sys
import time
from pathlib import Path

import rti.connextdds as dds

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "01-operating-room" / "src"))
import DdsUtils
from threat_web import ThreatWebApp
from ThreatTypes import ThreatEntities
from Types import Common, DdsEntities, Orchestrator, SurgicalRobot

entities = DdsEntities.Constants
threat_entities = ThreatEntities.Constants
MODE_TO_DP_NAME = {
    "UNSECURE": threat_entities.INJECTOR_UNSECURE_DP,
    "ROGUE CA": threat_entities.INJECTOR_ROGUE_CA_DP,
    "FORGED PERMS": threat_entities.INJECTOR_FORGED_PERMS_DP,
    "EXPIRED CERT": threat_entities.INJECTOR_EXPIRED_CERT_DP,
}
ATTACK_MOTOR_INJECT = "MOTOR INJECT"
ATTACK_CMD_PAUSE = "CMD INJECT (PAUSE)"
ATTACK_CMD_SHUTDOWN = "CMD INJECT (SHUTDOWN)"
ATTACKS = (ATTACK_MOTOR_INJECT, ATTACK_CMD_PAUSE, ATTACK_CMD_SHUTDOWN)
MOTORS = [
    SurgicalRobot.Motors.BASE,
    SurgicalRobot.Motors.SHOULDER,
    SurgicalRobot.Motors.ELBOW,
    SurgicalRobot.Motors.WRIST,
    SurgicalRobot.Motors.HAND,
]
JOINT_NAMES = ("BASE", "SHOULDER", "ELBOW", "WRIST", "HAND")


class ThreatInjectorApp(ThreatWebApp):
    def __init__(self):
        super().__init__("Threat Injector", MODE_TO_DP_NAME, 8094)
        self._motor_writer = None
        self._cmd_writer = None
        self._tick = 0
        self._next_inject = 0.0
        self.state.update(
            attack=ATTACK_MOTOR_INJECT,
            attacks=list(ATTACKS),
            attacking=False,
            frequency=5,
            angles=dict(zip(JOINT_NAMES, (204, 176, 156, 165, 151))),
        )
        DdsUtils.register_type(SurgicalRobot.MotorControl)
        DdsUtils.register_type(Orchestrator.DeviceCommand)

    def _reset(self):
        super()._reset()
        self._motor_writer = None
        self._cmd_writer = None
        self.state["attacking"] = False

    def _setup_entities(self):
        self._motor_writer = dds.DataWriter(
            self._participant.find_datawriter(entities.MOTOR_CONTROL_DW)
        )
        self._cmd_writer = dds.DataWriter(
            self._participant.find_datawriter(entities.DEVICE_COMMAND_DW)
        )

    def _command(self, command: dict):
        action = command.get("action")
        if action == "attack":
            attack = command.get("attack")
            if attack not in ATTACKS:
                raise ValueError("Unknown attack type")
            if self.state["attacking"]:
                raise RuntimeError("Stop injection before changing attack type")
            self.state["attack"] = attack
        elif action == "frequency":
            frequency = command.get("frequency")
            if type(frequency) is not int or not 1 <= frequency <= 20:
                raise ValueError("frequency must be an integer from 1 to 20 Hz")
            if self.state["attacking"]:
                raise RuntimeError("Stop injection before changing frequency")
            self.state["frequency"] = frequency
        elif action == "launch":
            if self._participant is None:
                raise RuntimeError("Select an available mode first")
            if self.state["attack"] != ATTACK_MOTOR_INJECT:
                self._do_inject()
            else:
                self.state["attacking"] = not self.state["attacking"]
                self._next_inject = time.monotonic()
                if not self.state["attacking"]:
                    self.state["status"] = "ACCESS GRANTED" if self._prev_matched else "NO ACCESS"
                self.log(
                    "INFO", "Injection started" if self.state["attacking"] else "Injection stopped"
                )
        else:
            super()._command(command)

    def _do_inject(self):
        attack = self.state["attack"]
        if attack == ATTACK_MOTOR_INJECT:
            index = self._tick % len(MOTORS)
            self._tick += 1
            increment = (self._tick // 10) % 2 == 0
            direction = (
                SurgicalRobot.MotorDirections.INCREMENT
                if increment
                else SurgicalRobot.MotorDirections.DECREMENT
            )
            sample = SurgicalRobot.MotorControl(id=MOTORS[index], direction=direction)
            writer = self._motor_writer
            joint = JOINT_NAMES[index]
            self.state["angles"][joint] = (
                self.state["angles"][joint] + (0.3 if increment else -0.3)
            ) % 360
            message = f"Writing MotorControl: {joint}, {direction}"
        else:
            cmd = (
                Orchestrator.DeviceCommands.PAUSE
                if attack == ATTACK_CMD_PAUSE
                else Orchestrator.DeviceCommands.SHUTDOWN
            )
            sample = Orchestrator.DeviceCommand(device=Common.DeviceType.ARM, command=cmd)
            writer = self._cmd_writer
            message = f"Writing DeviceCommand: {cmd} to ARM"
        try:
            writer.write(sample)
        except dds.Error as error:
            self.state.update(status="NO ACCESS", attacking=False)
            self.log("BLOCKED", f"Write rejected: {error}")
        else:
            self.state["status"] = "ATTACKING" if self._prev_matched else "NO ACCESS"
            self.log("OK" if self._prev_matched else "WARN", message)

    def _poll(self):
        if self._participant is None:
            return
        writer = (
            self._motor_writer if self.state["attack"] == ATTACK_MOTOR_INJECT else self._cmd_writer
        )
        matched = writer.publication_matched_status.current_count > 0
        if matched != self._prev_matched:
            self._prev_matched = matched
            self.state["status"] = "ACCESS GRANTED" if matched else "NO ACCESS"
            self.log(
                "OK" if matched else "BLOCKED",
                "Publication matched" if matched else "No publication match",
            )
        if self.state["attacking"] and time.monotonic() >= self._next_inject:
            self._do_inject()
            self._next_inject = time.monotonic() + 1 / self.state["frequency"]


if __name__ == "__main__":
    ThreatInjectorApp().run()
