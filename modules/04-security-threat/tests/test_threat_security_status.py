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
"""Module 04 security artifact status checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = MODULE_DIR.parent.parent
SCRIPT = MODULE_DIR / "security" / "setup_threat_security.py"


def test_threat_security_status_runs_clean() -> None:
    """Status report should run and not report expired threat artifacts."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--status", "-v"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    output = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, f"setup_threat_security --status failed:\n{output}"
    assert "EXPIRED" not in output, f"Expired threat security artifacts detected:\n{output}"
