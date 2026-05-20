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
"""Module 02 path constants.

Bootstraps ``resource/python/`` onto sys.path so that every test file
in this directory can ``from scripts.test_utils import …`` directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Reuse centralized scripts package for platform detection and module config
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent.parent / "resource" / "python")
)


# ---------------------------------------------------------------------------
# Path bootstrapping
# ---------------------------------------------------------------------------
MODULE_DIR = Path(__file__).resolve().parent.parent  # modules/02-record-playback
REPO_ROOT = MODULE_DIR.parent.parent  # repo root
MODULE_01_DIR = MODULE_DIR.parent / "01-operating-room"
SYSTEM_ARCH_DIR = REPO_ROOT / "system_arch"

RECORDING_DIR = MODULE_DIR / "or_recording"
