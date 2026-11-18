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

import module02_test_support
import pytest
from module02_test_support import prepare_test_recording_workspace


def test_test_recording_workspace_preserves_existing_operator_recording(tmp_path, monkeypatch):
    """Test setup refuses the operator path and leaves its existing data unchanged."""
    operator_recording = tmp_path / "operator" / "or_recording"
    operator_recording.mkdir(parents=True)
    sentinel = operator_recording / "operator-recording.dat"
    sentinel.write_bytes(b"keep this operator recording")
    monkeypatch.setattr(module02_test_support, "OPERATOR_RECORDING_DIR", operator_recording)

    with pytest.raises(ValueError, match="operator recording directory"):
        prepare_test_recording_workspace(operator_recording.parent)

    workspace = prepare_test_recording_workspace(tmp_path / "test")

    assert workspace / "or_recording" != operator_recording
    assert sentinel.read_bytes() == b"keep this operator recording"
    assert (workspace / "RecordingServiceConfiguration.xml").is_file()
    assert (workspace / "ReplayServiceConfiguration.xml").is_file()


@pytest.mark.service
@pytest.mark.slow
class TestRecording:
    """RTI Recording Service should capture data from running applications."""

    def test_recording_creates_database(
        self, or_proc_manager, svc_proc_manager, clean_recording_dir
    ):
        """Recording Service should create or_recording_database.dat."""
        # Start PatientSensor to produce t/patient/vitals data
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
        db_file = clean_recording_dir / "or_recording_database.dat"
        contents = (
            list(clean_recording_dir.iterdir()) if clean_recording_dir.is_dir() else "dir not found"
        )
        assert db_file.is_file(), (
            f"Recording database not found at {db_file}. "
            f"Contents of {clean_recording_dir}: {contents}"
        )
        # Database should have non-trivial size (at least a few KB of data)
        assert db_file.stat().st_size > 1024, (
            f"Recording database too small: {db_file.stat().st_size} bytes"
        )
