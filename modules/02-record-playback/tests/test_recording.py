"""Recording Service tests for Module 02.

Launches PatientSensor to produce data, then starts RTI Recording Service
and verifies that data is captured to a SQLite database.
"""

import time
from pathlib import Path

import pytest
from conftest import (
    MODULE_DIR,
    RECORDING_DIR,
    RECORDING_SERVICE,
)


@pytest.mark.slow
class TestRecording:
    """RTI Recording Service should capture data from running applications."""

    RECORDING_CONFIG = str(MODULE_DIR / "RecordingServiceConfiguration.xml")

    def test_recording_creates_database(self, proc_manager, clean_recording_dir):
        """Recording Service should create or_recording_database.dat."""
        # Start PatientSensor to produce t/Vitals data
        proc_manager.start_module01_cpp("PatientSensor")
        time.sleep(2)  # let sensor start publishing

        # Start Recording Service
        rec_proc = proc_manager.start(
            [RECORDING_SERVICE, "-cfgFile", self.RECORDING_CONFIG, "-cfgName", "RecServCfg"],
            cwd=MODULE_DIR,
        )
        # Record for ~8 seconds
        time.sleep(8)

        # Verify Recording Service is still alive
        assert rec_proc.poll() is None, f"Recording Service exited early with code {rec_proc.returncode}"

        # Stop recording service gracefully
        rec_proc.terminate()
        try:
            rec_proc.wait(timeout=10)
        except Exception:
            rec_proc.kill()
            rec_proc.wait(timeout=5)

        # Verify the database file was created
        db_file = RECORDING_DIR / "or_recording_database.dat"
        assert db_file.is_file(), (
            f"Recording database not found at {db_file}. "
            f"Contents of {RECORDING_DIR}: "
            f"{list(RECORDING_DIR.iterdir()) if RECORDING_DIR.is_dir() else 'dir not found'}"
        )
        # Database should have non-trivial size (at least a few KB of data)
        assert db_file.stat().st_size > 1024, f"Recording database too small: {db_file.stat().st_size} bytes"
