"""Browser commands preserve the threat demos' DDS interactions."""

import importlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules/04-security-threat/src"))
injector_module = importlib.import_module("ThreatInjector")
exfiltrator_module = importlib.import_module("ThreatExfiltrator")
common_module = importlib.import_module("threat_web")


class DDSError(Exception):
    pass


@pytest.fixture
def endpoints(monkeypatch):
    writer = Mock()
    writer.publication_matched_status.current_count = 1
    reader = Mock()
    reader.subscription_matched_status.current_count = 1
    reader.take_data.return_value = []
    participant = Mock()
    participant.find_datawriter.return_value = writer
    participant.find_datareader.return_value = reader
    provider = Mock()
    provider.create_participant_from_config.return_value = participant
    fake_dds = SimpleNamespace(
        QosProvider=SimpleNamespace(default=provider),
        Error=DDSError,
        DataWriter=lambda value: value,
        DataReader=lambda value: value,
    )
    for module in (injector_module, exfiltrator_module, common_module):
        monkeypatch.setattr(module, "dds", fake_dds)
    monkeypatch.setattr(injector_module.DdsUtils, "register_type", lambda _: None)
    return SimpleNamespace(
        writer=writer,
        reader=reader,
        participant=participant,
        provider=provider,
    )


def test_injector_modes_frequency_and_stop(endpoints):
    app = injector_module.ThreatInjectorApp()
    assert app.get_state()["status"] == "IDLE"
    app.command({"action": "mode", "mode": "UNSECURE"})
    endpoints.provider.create_participant_from_config.assert_called_once_with(
        injector_module.MODE_TO_DP_NAME["UNSECURE"]
    )
    app.command({"action": "frequency", "frequency": 20})
    app.command({"action": "launch"})
    app._poll()
    endpoints.writer.write.assert_called_once()
    assert app.get_state()["attacking"] is True
    assert app.get_state()["status"] == "ATTACKING"
    app.command({"action": "stop"})
    endpoints.participant.close.assert_called_once()
    assert app.get_state()["status"] == "IDLE"
    assert app.get_state()["attacking"] is False


@pytest.mark.parametrize("value", [0, 21, 1.5, True, "5"])
def test_invalid_frequency_does_not_change_state(endpoints, value):
    app = injector_module.ThreatInjectorApp()
    with pytest.raises(ValueError, match="1 to 20"):
        app.command({"action": "frequency", "frequency": value})
    assert app.get_state()["frequency"] == 5


def test_pause_command_is_one_shot(endpoints):
    app = injector_module.ThreatInjectorApp()
    app.command({"action": "mode", "mode": "UNSECURE"})
    app.command({"action": "attack", "attack": injector_module.ATTACK_CMD_PAUSE})
    app.command({"action": "launch"})
    endpoints.writer.write.assert_called_once()
    assert app.get_state()["attacking"] is False


def test_failed_participant_creation_is_visible(endpoints):
    app = injector_module.ThreatInjectorApp()
    endpoints.provider.create_participant_from_config.side_effect = DDSError("expired cert")
    with pytest.raises(RuntimeError, match="expired cert"):
        app.command({"action": "mode", "mode": "EXPIRED CERT"})
    assert app.get_state()["status"] == "ATTACK FAILED"
    assert app.get_state()["mode"] is None
    assert "expired cert" in app.get_state()["logs"][-1]["message"]


def test_mode_switch_closes_previous_participant(endpoints):
    app = exfiltrator_module.ThreatExfiltratorApp()
    app.command({"action": "mode", "mode": "UNSECURE"})
    app.command({"action": "mode", "mode": "ROGUE CA"})
    endpoints.participant.close.assert_called_once()
    assert app.get_state()["mode"] == "ROGUE CA"


def test_received_vitals_clear_after_timeout_and_stop(endpoints, monkeypatch):
    app = exfiltrator_module.ThreatExfiltratorApp()
    app.command({"action": "mode", "mode": "UNSECURE"})
    endpoints.reader.take_data.return_value = [
        SimpleNamespace(hr=75, spo2=98, etco2=38, nibp_s=120, nibp_d=80, patient_id=7),
    ]
    app._poll()
    assert app.get_state()["vitals"]["hr"] == 75
    assert app.get_state()["sample"] == 1
    snapshot = app.get_state()
    snapshot["vitals"]["hr"] = 0
    assert app.get_state()["vitals"]["hr"] == 75
    endpoints.reader.take_data.return_value = []
    monkeypatch.setattr(app, "_last_sample_time", time.monotonic() - 3)
    app._poll()
    assert app.get_state()["vitals"] is None
    app.command({"action": "stop"})
    assert app.get_state()["mode"] is None
    endpoints.participant.close.assert_called_once()
