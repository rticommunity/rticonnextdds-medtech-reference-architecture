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
"""Project-level prepared-build output tests.

Validates that the explicit CMake build stage prepared generated types and
application executables before pytest runs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.medtech import platform_setup

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _build_dir() -> Path:
    arch = os.environ.get("CONNEXTDDS_ARCH")
    assert arch, "CONNEXTDDS_ARCH must be set after sourcing the Connext environment"
    return PROJECT_ROOT / "build" / arch


def test_configure_and_codegen_outputs_are_prepared():
    """The explicit build stage must prepare CMake and generated type outputs."""
    build_dir = _build_dir()
    generated_dir = build_dir / "system" / "generated"
    expected_outputs = (
        build_dir / "CMakeCache.txt",
        generated_dir / "python" / "MedTech.py",
        generated_dir / "xml" / "MedTech.xml",
    )
    missing = [path for path in expected_outputs if not path.is_file()]
    assert not missing, f"Build outputs are missing; run `python medtech.py build` first: {missing}"


def test_module_01_executables_are_prepared():
    """The configured application binaries must be available to test fixtures."""
    executables = {
        name: Path(platform_setup.find_executable(name))
        for name in ("PatientSensor", "ArmController", "Orchestrator")
    }
    missing = [path for path in executables.values() if not path.is_file()]
    assert not missing, f"Built application executables are missing: {missing}"
