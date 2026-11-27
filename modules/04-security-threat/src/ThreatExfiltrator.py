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
from Types import DdsEntities, PatientMonitor

entities = DdsEntities.Constants
threat_entities = ThreatEntities.Constants
MODE_TO_DP_NAME = {
    "UNSECURE": threat_entities.EXFILTRATOR_UNSECURE_DP,
    "ROGUE CA": threat_entities.EXFILTRATOR_ROGUE_CA_DP,
    "FORGED PERMS": threat_entities.EXFILTRATOR_FORGED_PERMS_DP,
    "EXPIRED CERT": threat_entities.EXFILTRATOR_EXPIRED_CERT_DP,
}
DATA_TIMEOUT_S = 2.0


class ThreatExfiltratorApp(ThreatWebApp):
    def __init__(self):
        super().__init__("Threat Exfiltrator", MODE_TO_DP_NAME, 8095)
        self._vitals_reader = None
        self._last_sample_time = None
        self.state.update(vitals=None, sample=0)
        DdsUtils.register_type(PatientMonitor.Vitals)

    def _reset(self):
        super()._reset()
        self._vitals_reader = None
        self._last_sample_time = None
        self.state["vitals"] = None

    def _setup_entities(self):
        self._vitals_reader = dds.DataReader(self._participant.find_datareader(entities.VITALS_DR))

    def _poll(self):
        if self._vitals_reader is None:
            return
        matched = self._vitals_reader.subscription_matched_status.current_count > 0
        if matched != self._prev_matched:
            self._prev_matched = matched
            self.state["status"] = "ACCESS GRANTED" if matched else "NO ACCESS"
            self.log(
                "OK" if matched else "BLOCKED",
                "Subscription matched" if matched else "No subscription match",
            )
            if not matched:
                self.state["vitals"] = None
        for sample in self._vitals_reader.take_data():
            self.state["vitals"] = {
                name: float(getattr(sample, name))
                for name in ("hr", "spo2", "etco2", "nibp_s", "nibp_d")
            }
            self.state["vitals"]["patient_id"] = str(sample.patient_id)
            self.state["sample"] += 1
            self._last_sample_time = time.monotonic()
            self.state["status"] = "ACCESS GRANTED"
            self.log("OK", f"Received Vitals: {self.state['vitals']}")
        if (
            self._last_sample_time is not None
            and time.monotonic() - self._last_sample_time > DATA_TIMEOUT_S
        ):
            self.state["vitals"] = None
            self._last_sample_time = None
            self.log("WARN", "No fresh vitals; cleared stale data")


if __name__ == "__main__":
    ThreatExfiltratorApp().run()
