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

import time

import pytest
from module02_test_support import (
    RECORDING_DIR,
)
from scripts.test_utils import (
    UtilityApp,
    wait_for_reader_match,
    wait_for_samples,
)


@pytest.mark.service
@pytest.mark.slow
class TestReplay:
    """RTI Replay Service should re-publish recorded data."""

    def test_replay_produces_vitals(self, or_proc_manager, svc_proc_manager, clean_recording_dir):
        """Replay Service should publish t/Vitals from a recording."""
        # ── Phase 1: Record some data ─────────────────────────────────
        ps = or_proc_manager.start_app_ready("PatientSensor")

        rec_proc = svc_proc_manager.start_app_ready("RecordingService")
        time.sleep(3)

        # Kill PatientSensor and Recording Service to finalize the recording
        or_proc_manager.shutdown_all()
        svc_proc_manager.shutdown_all()

        assert rec_proc.poll() is not None, "Recording Service did not exit"
        assert ps.poll() is not None, "PatientSensor did not exit"

        db_file = RECORDING_DIR / "or_recording_database.dat"
        assert db_file.is_file(), "Recording phase failed — no database"

        # ── Phase 2: Replay and verify data arrives ───────────────────

        with UtilityApp.make_non_secure() as app:
            reader = app.vitals.reader

            # Start Replay Service
            svc_proc_manager.start_app_ready("ReplayService")

            assert wait_for_reader_match(reader, timeout_sec=1), (
                "Vitals reader never matched Replay Service"
            )
            samples = wait_for_samples(reader, n=1, timeout_sec=3)

            assert len(samples) >= 1, "No vitals received from Replay Service"
