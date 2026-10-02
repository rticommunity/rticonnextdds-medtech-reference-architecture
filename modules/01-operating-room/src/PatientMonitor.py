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
from Types import Common, DdsEntities, Orchestrator, PatientMonitor

class PatientMonitorApp:
    def __init__(self):
        self.pm_status = None
        self.status_writer = None
        self.hb_writer = None
        self.vitals_reader = None
        self.cmd_reader = None
        self._vitals = (60.0, 98.0, 38.0, 120.0, 80.0)
        self._last_vitals_time = time.monotonic()
        # If no fresh vitals sample has arrived in this long, treat the feed
        # as stale (e.g. the Patient Sensor was paused independently) and
        # freeze the waveform instead of animating on stale data. Set well
        # above the sensor's ~50 ms publish period to tolerate normal jitter.
        self.DATA_STALE_S = 1.5

    # ── DDS heartbeat thread ─────────────────────────────────────────
    def write_hb(self):
        while self.pm_status.status != Common.DeviceStatuses.OFF:
            hb = Common.DeviceHeartbeat()
            hb.device = Common.DeviceType.PATIENT_MONITOR
            self.hb_writer.write(hb)
            time.sleep(0.05)

    # ── DDS polling (called by Qt timer every 150 ms, or headless loop) ──
    def _poll_dds(self):
        # Vitals
        if self.pm_status.status == Common.DeviceStatuses.ON:
            samples = self.vitals_reader.take_data()
            for sample in samples:
                self._vitals = (
                    float(sample.hr),
                    float(sample.spo2),
                    float(sample.etco2),
                    float(sample.nibp_s),
                    float(sample.nibp_d),
                )
                self._last_vitals_time = time.monotonic()


        # Commands
        cmd_samples = self.cmd_reader.take_data()
        for sample in cmd_samples:
            if sample.command == Orchestrator.DeviceCommands.START:
                print("Patient Monitor received Start command")
                self.pm_status.status = Common.DeviceStatuses.ON
                self._log_alert_web("Received START Command from Orchestrator")
            elif sample.command == Orchestrator.DeviceCommands.PAUSE:
                print("Patient Monitor received Pause command")
                self.pm_status.status = Common.DeviceStatuses.PAUSED
                self._log_alert_web("Received PAUSE Command from Orchestrator")
            else:
                print("Patient Monitor received Shutdown command")
                self.pm_status.status = Common.DeviceStatuses.OFF
                self._log_alert_web("Received SHUTDOWN Command from Orchestrator")
            self.status_writer.write(self.pm_status)

    # ── Connext setup ────────────────────────────────────────────────
    def connext_setup(self):
        entities = DdsEntities.Constants
        register_type(Common.DeviceStatus)
        register_type(Common.DeviceHeartbeat)
        register_type(Orchestrator.DeviceCommand)
        register_type(PatientMonitor.Vitals)

        qos_provider = dds.QosProvider.default
        participant = qos_provider.create_participant_from_config(entities.PATIENT_MONITOR_DP)

        self.status_writer = dds.DataWriter(participant.find_datawriter(entities.STATUS_DW))
        self.hb_writer = dds.DataWriter(participant.find_datawriter(entities.HB_DW))
        self.vitals_reader = dds.DataReader(participant.find_datareader(entities.VITALS_DR))
        self.cmd_reader = dds.DataReader(participant.find_datareader(entities.DEVICE_COMMAND_DR))
        self.pm_status = Common.DeviceStatus(
            device=Common.DeviceType.PATIENT_MONITOR,
            status=Common.DeviceStatuses.ON,
        )
        self.status_writer.write(self.pm_status)

    # ── Entry point ──────────────────────────────────────────────────
    def run_web(self, port: int):
        self.connext_setup()
        self._state_lock = threading.Lock()
        self._alerts = []

        hb_thread = threading.Thread(target=self.write_hb, daemon=True)
        hb_thread.start()

        self._running = True
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "_running", False))

        web_dir = Path(__file__).resolve().parent.parent / "web-patientmonitor"
        httpd = start_web_server(web_dir, self._get_state_web, port)
        print(f"Patient Monitor web UI listening on http://localhost:{port}/")
        print("Started Patient Monitor")

        try:
            while self._running and self.pm_status.status != Common.DeviceStatuses.OFF:
                self._poll_dds()
                time.sleep(0.15)
        finally:
            httpd.shutdown()
            self.pm_status.status = Common.DeviceStatuses.OFF

    def _get_state_web(self) -> dict:
        status_names = {
            Common.DeviceStatuses.ON: "ON",
            Common.DeviceStatuses.PAUSED: "PAUSED",
            Common.DeviceStatuses.OFF: "OFF",
        }
        hr, spo2, etco2, nibp_s, nibp_d = self._vitals
        data_stale = (time.monotonic() - self._last_vitals_time) > self.DATA_STALE_S
        with self._state_lock:
            return {
                "status": status_names.get(self.pm_status.status, "OFF"),
                "hr": hr,
                "spo2": spo2,
                "etco2": etco2,
                "nibp_s": nibp_s,
                "nibp_d": nibp_d,
                "data_stale": data_stale,
                "alerts": list(self._alerts),
            }

    def _log_alert_web(self, msg: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._state_lock:
            self._alerts.append(f"{ts} - {msg}")
            del self._alerts[:-200]


if __name__ == "__main__":
    web_port = 8093
    if "--port" in sys.argv:
        web_port = int(sys.argv[sys.argv.index("--port") + 1])

    pm = PatientMonitorApp()
    pm.run_web(web_port)
