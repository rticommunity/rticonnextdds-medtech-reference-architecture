"""Validate threat commands and report participant-creation failures."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules/04-security-threat/src"))
injector_module = importlib.import_module("ThreatInjector")
common_module = importlib.import_module("threat_web")


class DDSError(Exception):
    pass


@pytest.fixture
def injector_app(monkeypatch):
    monkeypatch.setattr(injector_module.DdsUtils, "register_type", lambda _: None)
    return injector_module.ThreatInjectorApp()


@pytest.mark.parametrize("value", [0, 21, 1.5, True, "5"])
def test_invalid_frequency_does_not_change_state(injector_app, value):
    with pytest.raises(ValueError, match="1 to 20"):
        injector_app.command({"action": "frequency", "frequency": value})
    assert injector_app.get_state()["frequency"] == 5


def test_failed_participant_creation_is_visible(injector_app, monkeypatch):
    provider = Mock()
    provider.create_participant_from_config.side_effect = DDSError("expired cert")
    monkeypatch.setattr(
        common_module,
        "dds",
        SimpleNamespace(QosProvider=SimpleNamespace(default=provider), Error=DDSError),
    )
    with pytest.raises(RuntimeError, match="expired cert"):
        injector_app.command({"action": "mode", "mode": "EXPIRED CERT"})
    assert injector_app.get_state()["status"] == "ATTACK FAILED"
    assert injector_app.get_state()["mode"] is None
    assert "expired cert" in injector_app.get_state()["logs"][-1]["message"]
