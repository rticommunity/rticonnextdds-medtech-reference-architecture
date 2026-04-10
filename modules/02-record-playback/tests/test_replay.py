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
"""Replay Service tests for Module 02.

Records data first, then launches Replay Service and verifies that a
DDS subscriber receives the replayed samples.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import (
    MODULE_01_DIR,
    MODULE_DIR,
    RECORDING_DIR,
    RECORDING_SERVICE,
    REPLAY_SERVICE,
)

SRC_DIR = MODULE_01_DIR / "src"


@pytest.mark.slow
class TestReplay:
    """RTI Replay Service should re-publish recorded data."""

    RECORDING_CONFIG = str(MODULE_DIR / "RecordingServiceConfiguration.xml")
    REPLAY_CONFIG = str(MODULE_DIR / "ReplayServiceConfiguration.xml")

    def test_replay_produces_vitals(self, proc_manager, dds_env, clean_recording_dir):
        """Replay Service should publish t/Vitals from a recording."""
        # ── Phase 1: Record some data ─────────────────────────────────
        proc_manager.start_module01_cpp("PatientSensor")
        time.sleep(2)

        rec_proc = proc_manager.start(
            [RECORDING_SERVICE, "-cfgFile", self.RECORDING_CONFIG, "-cfgName", "RecServCfg"],
            cwd=MODULE_DIR,
        )
        time.sleep(8)

        rec_proc.terminate()
        try:
            rec_proc.wait(timeout=10)
        except Exception:
            rec_proc.kill()
            rec_proc.wait(timeout=5)

        db_file = RECORDING_DIR / "or_recording_database.dat"
        assert db_file.is_file(), "Recording phase failed — no database"

        # Kill PatientSensor so the only source of data is the replay
        proc_manager.shutdown_all()
        time.sleep(1)

        # ── Phase 2: Replay and verify data arrives ───────────────────
        # Start Replay Service
        proc_manager.start(
            [REPLAY_SERVICE, "-cfgFile", self.REPLAY_CONFIG, "-cfgName", "RepServCfg"],
            cwd=MODULE_DIR,
        )
        time.sleep(2)

        # Run a short subscriber in a subprocess to capture replayed data
        subscriber_script = f"""\
import sys, time, json
sys.path.insert(0, "{SRC_DIR}")
import rti.connextdds as dds
from Types import PatientMonitor_Vitals, idl

provider = dds.QosProvider.default
participant_qos = provider.participant_qos_from_profile("DpQosLib::Test")
participant = dds.DomainParticipant(domain_id=0, qos=participant_qos)

ts = idl.get_type_support(PatientMonitor_Vitals)
dds.DomainParticipant.register_idl_type(PatientMonitor_Vitals, ts.type_name)
topic = dds.Topic(participant, "t/Vitals", PatientMonitor_Vitals)
dr_qos = provider.datareader_qos_from_profile("DataFlowLibrary::Streaming")
subscriber = dds.Subscriber(participant)
reader = dds.DataReader(subscriber, topic, dr_qos)

collected = []
deadline = time.monotonic() + 15
while time.monotonic() < deadline and len(collected) < 3:
    for s in reader.take():
        if s.info.valid:
            collected.append({{"hr": s.data.hr, "spo2": s.data.spo2}})
    if len(collected) < 3:
        time.sleep(0.1)

participant.close()
print(json.dumps(collected))
"""
        result = subprocess.run(
            [sys.executable, "-c", subscriber_script],
            env=dds_env,
            cwd=MODULE_01_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Replay subscriber failed (exit {result.returncode}):\n{result.stderr}"

        samples = json.loads(result.stdout.strip())
        assert len(samples) >= 1, "No vitals received from Replay Service"
