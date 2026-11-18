"""Tests for the shared generated-type helpers."""

from types import SimpleNamespace

import MedTechTypes
import pytest
from MedTech import Device


def test_registration_is_idempotent_only_for_the_same_type(monkeypatch):
    calls = []

    def register(data_type, name):
        calls.append((data_type, name))
        if name == "failure":
            raise RuntimeError("registration failed")

    monkeypatch.setattr(MedTechTypes, "_registered_types", {})
    monkeypatch.setattr(
        MedTechTypes,
        "dds",
        SimpleNamespace(DomainParticipant=SimpleNamespace(register_idl_type=register)),
    )
    MedTechTypes.register_type(Device.Status, "status")
    MedTechTypes.register_type(Device.Status, "status")
    assert calls == [(Device.Status, "status")]
    with pytest.raises(ValueError, match="already registered"):
        MedTechTypes.register_type(Device.Command, "status")
    with pytest.raises(RuntimeError, match="registration failed"):
        MedTechTypes.register_type(Device.Status, "failure")
    assert "failure" not in MedTechTypes._registered_types


def test_device_command_transitions_use_generated_enums():
    transition = MedTechTypes.device_status_after_command
    assert transition(Device.DeviceCommands.START) == Device.DeviceStatuses.ON
    assert transition(Device.DeviceCommands.PAUSE) == Device.DeviceStatuses.PAUSED
    assert transition(Device.DeviceCommands.SHUTDOWN) == Device.DeviceStatuses.OFF
    with pytest.raises(ValueError, match="Unsupported device command"):
        transition("REBOOT")
    with pytest.raises(ValueError, match="Unsupported device command"):
        transition(Device.DeviceStatuses.ON)
