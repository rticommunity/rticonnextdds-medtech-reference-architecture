"""Tests for the system-wide effective dataflow QoS."""

from pathlib import Path

import pytest
import rti.connextdds as dds
from scripts.test_utils import make_isolated_qos_provider

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("profile", "deadline_ms", "lifespan_ms"),
    (("Control", 50, 250), ("Telemetry", 200, None), ("Heartbeat", 200, None)),
)
def test_dataflow_snippets_preserve_effective_qos(profile, deadline_ms, lifespan_ms):
    provider = make_isolated_qos_provider(str(ROOT / "system" / "qos" / "Qos.xml"))
    writer = provider.datawriter_qos_from_profile(f"DataFlowLibrary::{profile}")
    reader = provider.datareader_qos_from_profile(f"DataFlowLibrary::{profile}")

    for qos in (writer, reader):
        assert qos.deadline.period == dds.Duration.from_milliseconds(deadline_ms)
        assert qos.durability.kind == dds.DurabilityKind.VOLATILE
        assert qos.reliability.kind == dds.ReliabilityKind.BEST_EFFORT
        assert qos.history.kind == dds.HistoryKind.KEEP_LAST
        assert qos.history.depth == 1
    expected_lifespan = (
        dds.Duration.infinite
        if lifespan_ms is None
        else dds.Duration.from_milliseconds(lifespan_ms)
    )
    assert writer.lifespan.duration == expected_lifespan
