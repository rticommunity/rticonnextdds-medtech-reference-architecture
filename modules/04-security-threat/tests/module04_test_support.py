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
"""Module 04 path constants and skip helpers."""

from __future__ import annotations

from pathlib import Path

# Add centralized scripts package to import path

# ---------------------------------------------------------------------------
# Path bootstrapping
# ---------------------------------------------------------------------------
MODULE_DIR = Path(__file__).resolve().parent.parent  # modules/04-security-threat
REPO_ROOT = MODULE_DIR.parent.parent
MODULE_01_DIR = MODULE_DIR.parent / "01-operating-room"
SYSTEM_DIR = REPO_ROOT / "system"
THREAT_SRC_DIR = MODULE_DIR / "src"
OR_SRC_DIR = MODULE_01_DIR / "src"
