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
"""Module 01 path constants and test helpers."""

from __future__ import annotations

import json
import re
import select
import time
from pathlib import Path
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Path bootstrapping — mirror what the launch scripts do
# ---------------------------------------------------------------------------
MODULE_DIR = Path(__file__).resolve().parent.parent  # modules/01-operating-room
REPO_ROOT = MODULE_DIR.parent.parent  # repo root
SRC_DIR = MODULE_DIR / "src"
SYSTEM_DIR = REPO_ROOT / "system"
SECURITY_DIR = SYSTEM_DIR / "security"


def local_ui_url(process, expected_prefix: str) -> str:
    assert process.stdout is not None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        readable, _, _ = select.select([process.stdout], [], [], 0.25)
        if not readable:
            continue
        line = process.stdout.readline().decode(errors="replace").strip()
        match = re.search(r"https?://127\.0\.0\.1:\d+", line)
        if match:
            assert line.startswith(expected_prefix), f"unexpected URL announcement: {line}"
            return match.group(0)
    raise AssertionError(f"{expected_prefix} did not print its local UI URL")


def invoke(url: str, name: str, payload: dict) -> dict:
    with urlopen(f"{url}/api/command-capability", timeout=2) as response:
        capability = json.load(response)["capability"]
    request = Request(
        f"{url}/api/commands/{name}",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Origin": url,
            "X-RTI-Demo-Command-Capability": capability,
        },
        method="POST",
    )
    with urlopen(request, timeout=2) as response:
        return json.load(response)


def ui_data(url: str) -> dict:
    with urlopen(f"{url}/api/state", timeout=2) as response:
        return json.load(response)["data"]


def wait_for_ui_data(url, predicate, timeout=5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = ui_data(url)
        if predicate(data):
            return data
        time.sleep(0.05)
    raise AssertionError(f"UI state did not satisfy condition: {data}")
