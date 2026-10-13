#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

from __future__ import annotations


def device_status_after_command(command: str) -> str:
    transitions = {"START": "ON", "PAUSE": "PAUSED", "SHUTDOWN": "OFF"}
    try:
        return transitions[command]
    except KeyError as exc:
        raise ValueError(f"Unsupported device command: {command}") from exc
