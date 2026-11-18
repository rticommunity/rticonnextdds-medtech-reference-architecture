#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.
"""Shared heartbeat publication for DDS presence assertions."""

import asyncio

import rti.connextdds as dds


def heartbeat_period_from_deadline(writer):
    """Return one third of a writer's finite, positive offered deadline."""
    deadline = writer.qos.deadline.period
    if deadline == dds.Duration.infinite or deadline <= dds.Duration.zero:
        raise ValueError("Heartbeat writer deadline must be finite and positive")

    period = deadline / 3
    if period <= dds.Duration.zero:
        raise ValueError("Heartbeat period derived from deadline must be positive")
    return period


async def publish_heartbeats(writer, heartbeat, stop: asyncio.Event) -> None:
    """Publish a keyed heartbeat until stopped or cancelled."""
    period = heartbeat_period_from_deadline(writer).to_seconds()
    loop = asyncio.get_running_loop()
    next_write = loop.time()
    while not stop.is_set():
        writer.write(heartbeat)
        next_write += period
        now = loop.time()
        if next_write <= now:
            next_write = now + period
        await asyncio.sleep(next_write - now)
