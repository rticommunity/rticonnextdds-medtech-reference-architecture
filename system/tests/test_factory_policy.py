"""Verify application and service processes use their intended factory policy."""

import subprocess
import sys
from pathlib import Path

import pytest
from scripts import module_runner

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("module", "flags", "autoenable"),
    [
        ("01-operating-room", {"security": False}, False),
        ("01-operating-room", {"security": True}, False),
        ("02-record-playback", {"security": False}, True),
        ("02-record-playback", {"security": True}, True),
        ("04-security-threat", {}, False),
    ],
)
def test_factory_policy_is_process_specific(module, flags, autoenable):
    env, _ = module_runner.load_module_config(ROOT / "modules" / module, flags=flags)
    code = (
        "import rti.connextdds as dds; "
        "provider = dds.QosProvider.default; "
        "print(dds.DomainParticipant.participant_factory_qos.entity_factory"
        ".autoenable_created_entities)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == str(autoenable), result.stderr
