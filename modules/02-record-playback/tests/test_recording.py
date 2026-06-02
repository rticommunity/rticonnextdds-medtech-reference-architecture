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
"""Recording Service tests for Module 02.

Launches PatientSensor to produce data, then starts RTI Recording Service
and verifies that data is captured to a SQLite database.
"""

import time

import pytest
from module02_test_support import (
    RECORDING_DIR,
)


@pytest.mark.service
@pytest.mark.slow
class TestRecording:
    """RTI Recording Service should capture data from running applications."""

    def test_recording_creates_database(
        self, or_proc_manager, svc_proc_manager, clean_recording_dir
    ):
        """Recording Service should create or_recording_database.dat."""
        # Start PatientSensor to produce t/Vitals data
        or_proc_manager.start_app_ready("PatientSensor")

        # Start Recording Service
        rec_proc = svc_proc_manager.start_app_ready("RecordingService")
        # Record for ~3 seconds
        time.sleep(3)

        # Verify Recording Service is still alive
        assert rec_proc.poll() is None, (
            f"Recording Service exited early with code {rec_proc.returncode}"
        )

        # Kill PatientSensor and Recording Service to finalize the recording
        or_proc_manager.shutdown_all()
        svc_proc_manager.shutdown_all()

        # Verify the database file was created
        db_file = RECORDING_DIR / "or_recording_database.dat"
        assert db_file.is_file(), (
            f"Recording database not found at {db_file}. "
            f"Contents of {RECORDING_DIR}: "
            f"{list(RECORDING_DIR.iterdir()) if RECORDING_DIR.is_dir() else 'dir not found'}"
        )
        # Database should have non-trivial size (at least a few KB of data)
        assert db_file.stat().st_size > 1024, (
            f"Recording database too small: {db_file.stat().st_size} bytes"
        )
