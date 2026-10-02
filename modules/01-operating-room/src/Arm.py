#
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

import signal
import sys
import threading
import time
from pathlib import Path

import rti.connextdds as dds
from DdsUtils import register_type
from web_server_utils import start_web_server
from Types import Common, DdsEntities, Orchestrator, SurgicalRobot

JOINT_NAMES = {
    SurgicalRobot.Motors.BASE: "BASE",
    SurgicalRobot.Motors.SHOULDER: "SHOULDER",
    SurgicalRobot.Motors.ELBOW: "ELBOW",
    SurgicalRobot.Motors.WRIST: "WRIST",
    SurgicalRobot.Motors.HAND: "HAND",
}

UPDATE_MS = 100  # refresh rate ms (~10 fps)

_MOTORS_ORDERED = [
    SurgicalRobot.Motors.BASE,
    SurgicalRobot.Motors.SHOULDER,
    SurgicalRobot.Motors.ELBOW,
    SurgicalRobot.Motors.WRIST,
    SurgicalRobot.Motors.HAND,
]

class ArmApp:
    def __init__(self):
        self.angles = {
            SurgicalRobot.Motors.BASE: 204.0,
            SurgicalRobot.Motors.SHOULDER: 176.0,
            SurgicalRobot.Motors.ELBOW: 156.0,
            SurgicalRobot.Motors.WRIST: 165.0,
            SurgicalRobot.Motors.HAND: 151.0,
        }
        self.directions = {
            SurgicalRobot.Motors.BASE: "STATIONARY",
            SurgicalRobot.Motors.SHOULDER: "STATIONARY",
            SurgicalRobot.Motors.ELBOW: "STATIONARY",
            SurgicalRobot.Motors.WRIST: "STATIONARY",
            SurgicalRobot.Motors.HAND: "STATIONARY",
        }

        self.arm_status = None
        self.status_writer = None
        self.hb_writer = None
        self.motor_control_reader = None
        self.cmd_reader = None
        self.cmd_waitset = None

    # ── DDS heartbeat thread ─────────────────────────────────────────
    def write_hb(self, hb_writer):
        while self.arm_status.status != Common.DeviceStatuses.OFF:
            hb = Common.DeviceHeartbeat()
            hb.device = Common.DeviceType.ARM
            hb_writer.write(hb)
            time.sleep(0.05)

    # ── DDS poll timer callback (Qt main thread, or headless loop) ────
    def _poll_dds(self):
        # Motor control samples
        samples = self.motor_control_reader.take_data()
        for sample in samples:
            if self.arm_status.status == Common.DeviceStatuses.ON:
                if sample.direction == SurgicalRobot.MotorDirections.INCREMENT:
                    self.angles[sample.id] = (self.angles[sample.id] + 0.3) % 360.0
                    self.directions[sample.id] = "INCREMENT"
                elif sample.direction == SurgicalRobot.MotorDirections.DECREMENT:
                    self.angles[sample.id] = (self.angles[sample.id] - 0.3) % 360.0
                    self.directions[sample.id] = "DECREMENT"
                else:
                    self.directions[sample.id] = "STATIONARY"

        # Command samples
        cmd_samples = self.cmd_reader.take_data()
        for sample in cmd_samples:
            if sample.command == Orchestrator.DeviceCommands.START:
                print("Arm received Start Command")
                self.arm_status.status = Common.DeviceStatuses.ON
                self._log_alert_web("Received START Command from Orchestrator")
            elif sample.command == Orchestrator.DeviceCommands.PAUSE:
                print("Arm received Pause Command")
                self.arm_status.status = Common.DeviceStatuses.PAUSED
                self._log_alert_web("Received PAUSE Command from Orchestrator")
            else:
                print("Arm received Shutdown Command")
                self.arm_status.status = Common.DeviceStatuses.OFF
                self._log_alert_web("Received SHUTDOWN Command from Orchestrator")
            self.status_writer.write(self.arm_status)

    # ── Connext setup ─────────────────────────────────────────────────
    def connext_setup(self):
        entities = DdsEntities.Constants
        register_type(Common.DeviceStatus)
        register_type(Common.DeviceHeartbeat)
        register_type(Orchestrator.DeviceCommand)
        register_type(SurgicalRobot.MotorControl)

        qos_provider = dds.QosProvider.default
        participant = qos_provider.create_participant_from_config(entities.ARM_DP)

        self.status_writer = dds.DataWriter(participant.find_datawriter(entities.STATUS_DW))
        self.hb_writer = dds.DataWriter(participant.find_datawriter(entities.HB_DW))
        self.arm_status = Common.DeviceStatus(
            device=Common.DeviceType.ARM, status=Common.DeviceStatuses.ON
        )
        self.status_writer.write(self.arm_status)

        self.motor_control_reader = dds.DataReader(
            participant.find_datareader(entities.MOTOR_CONTROL_DR)
        )
        self.cmd_reader = dds.DataReader(participant.find_datareader(entities.DEVICE_COMMAND_DR))

    # ── Entry point ───────────────────────────────────────────────────
    def run_web(self, port: int):
        self.connext_setup()
        self._state_lock = threading.Lock()
        self._alerts = []

        hb_thread = threading.Thread(target=self.write_hb, args=[self.hb_writer], daemon=True)
        hb_thread.start()

        self._running = True
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "_running", False))

        web_dir = Path(__file__).resolve().parent.parent / "web-arm"
        httpd = start_web_server(web_dir, self._get_state_web, port)
        print(f"Arm web UI listening on http://localhost:{port}/")
        print("Started Arm")

        try:
            while self._running and self.arm_status.status != Common.DeviceStatuses.OFF:
                self._poll_dds()
                time.sleep(UPDATE_MS / 1000.0)
        finally:
            httpd.shutdown()
            self.arm_status.status = Common.DeviceStatuses.OFF

    def _get_state_web(self) -> dict:
        status_names = {
            Common.DeviceStatuses.ON: "ON",
            Common.DeviceStatuses.PAUSED: "PAUSED",
            Common.DeviceStatuses.OFF: "OFF",
        }
        with self._state_lock:
            return {
                "status": status_names.get(self.arm_status.status, "OFF"),
                "angles": {JOINT_NAMES[m]: self.angles[m] for m in _MOTORS_ORDERED},
                "directions": {JOINT_NAMES[m]: self.directions[m] for m in _MOTORS_ORDERED},
                "alerts": list(self._alerts),
            }

    def _log_alert_web(self, msg: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._state_lock:
            self._alerts.append(f"{ts} - {msg}")
            del self._alerts[:-200]


if __name__ == "__main__":
    web_port = 8092
    if "--port" in sys.argv:
        web_port = int(sys.argv[sys.argv.index("--port") + 1])

    arm = ArmApp()
    arm.run_web(web_port)
