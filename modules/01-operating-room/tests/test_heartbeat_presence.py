import asyncio
from types import SimpleNamespace

import pytest
import rti.connextdds as dds
from HeartbeatPresence import heartbeat_period_from_deadline, publish_heartbeats


def _writer_with_deadline(period):
    return SimpleNamespace(qos=SimpleNamespace(deadline=SimpleNamespace(period=period)))


def test_heartbeat_period_is_one_third_of_writer_deadline():
    period = heartbeat_period_from_deadline(
        _writer_with_deadline(dds.Duration.from_milliseconds(200))
    )

    assert period.to_seconds() == pytest.approx(200 / 3000)


@pytest.mark.parametrize("deadline", [dds.Duration.zero, dds.Duration.infinite])
def test_heartbeat_period_rejects_non_finite_or_non_positive_deadlines(deadline):
    with pytest.raises(ValueError, match="finite and positive"):
        heartbeat_period_from_deadline(_writer_with_deadline(deadline))


def test_publisher_repeats_same_key_at_deadline_derived_cadence_and_stops():
    async def run():
        stop = asyncio.Event()
        calls = []
        heartbeat = object()
        writer = _writer_with_deadline(dds.Duration.from_milliseconds(90))

        def write(sample):
            calls.append((asyncio.get_running_loop().time(), sample))
            if len(calls) == 3:
                stop.set()

        writer.write = write
        await asyncio.wait_for(publish_heartbeats(writer, heartbeat, stop), timeout=1)
        assert [sample for _, sample in calls] == [heartbeat] * 3
        assert calls[2][0] - calls[0][0] >= 0.05

    asyncio.run(run())


def test_publisher_propagates_write_failure():
    async def run():
        writer = _writer_with_deadline(dds.Duration.from_milliseconds(90))

        def write(_sample):
            raise RuntimeError("write failed")

        writer.write = write
        with pytest.raises(RuntimeError, match="write failed"):
            await publish_heartbeats(writer, object(), asyncio.Event())

    asyncio.run(run())
