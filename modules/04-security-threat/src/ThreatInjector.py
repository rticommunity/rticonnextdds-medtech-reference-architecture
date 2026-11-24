#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Threat-injection use cases, Connext adapter, and web presentation state."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import rti.connextdds as dds

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[3] / "modules" / "01-operating-room" / "src"),
)
from DemoUiSupport import DemoUiState, create_demo_ui, participant_security_enabled, run_demo_ui
from MedTech import DdsEntities, Device, Geometry, Robot
from MedTechTypes import register_type
from ThreatTypes import ThreatEntities

if TYPE_CHECKING:
    from ArmKinematics import ArmModel

_MODES = ("UNSECURE", "ROGUE CA", "FORGED PERMS", "EXPIRED CERT")
_ATTACKS = ("TELEOP INJECT", "CMD INJECT (PAUSE)", "CMD INJECT (SHUTDOWN)")
_MODE_TO_PARTICIPANT = {
    "UNSECURE": ThreatEntities.Constants.INJECTOR_UNSECURE_DP,
    "ROGUE CA": ThreatEntities.Constants.INJECTOR_ROGUE_CA_DP,
    "FORGED PERMS": ThreatEntities.Constants.INJECTOR_FORGED_PERMS_DP,
    "EXPIRED CERT": ThreatEntities.Constants.INJECTOR_EXPIRED_CERT_DP,
}
_AXES = ("X", "Y", "ANGULAR_Z")
_PREVIEW_ERRORS = (ImportError, OSError, ArithmeticError, ValueError, RuntimeError)


def _rates(axis: str, direction: str):
    sign = 1.0 if direction == "POSITIVE" else -1.0
    linear = [0.0, 0.0, 0.0]
    angular = [0.0, 0.0, 0.0]
    if axis == "ANGULAR_Z":
        angular[2] = sign * 0.25
    else:
        linear[_AXES.index(axis)] = sign * 0.02
    return tuple(linear), tuple(angular)


class ThreatInjectionLogic:
    def __init__(self) -> None:
        self.mode: str | None = None
        self.attack = _ATTACKS[0]
        self.attacking = False
        self.frequency_hz = 5
        self.tick = 0
        self.failure_state: str | None = None

    def next_teleop(self) -> tuple[str, str]:
        axis = _AXES[(self.tick // 10) % len(_AXES)]
        direction = "POSITIVE" if (self.tick // (10 * len(_AXES))) % 2 == 0 else "NEGATIVE"
        self.tick += 1
        return axis, direction

    def command_attack(self) -> str:
        return "PAUSE" if self.attack == _ATTACKS[1] else "SHUTDOWN"


class ThreatInjectorDdsAdapter:
    def __init__(self) -> None:
        self.participant = None
        self.dds_security: bool | None = None
        self.teleop_writer = None
        self.command_writer = None

    def open(self, mode: str) -> None:
        for data_type in (
            Device.Status,
            Device.Command,
            Robot.Arm.TeleopControl,
        ):
            register_type(data_type)
        provider = dds.QosProvider.default
        self.participant = provider.create_participant_from_config(_MODE_TO_PARTICIPANT[mode])
        entities = DdsEntities.Constants
        self.teleop_writer = dds.DataWriter(
            self.participant.find_datawriter(entities.TELEOP_CONTROL_DW)
        )
        self.command_writer = dds.DataWriter(
            self.participant.find_datawriter(entities.DEVICE_COMMAND_DW)
        )
        self.participant.enable()
        self.dds_security = participant_security_enabled(self.participant)

    def close(self) -> None:
        if self.participant is not None:
            self.participant.close()
        self.participant = self.teleop_writer = self.command_writer = None
        self.dds_security = None

    def write_teleop(self, axis: str, direction: str) -> None:
        linear, angular = _rates(axis, direction)
        sample = Robot.Arm.TeleopControl(
            arm_id="arm-1",
            linear_velocity=Geometry.Vector3(*linear),
            angular_velocity=Geometry.Vector3(*angular),
        )
        self.teleop_writer.write(sample)

    def write_device_command(self, command: str) -> None:
        self.command_writer.write(
            Device.Command(
                device=Device.DeviceType.ARM,
                command=getattr(Device.DeviceCommandKind, command),
            )
        )

    def publication_matched(self) -> bool:
        writers = (self.teleop_writer, self.command_writer)
        return all(writer is not None for writer in writers) and any(
            writer.publication_matched_status.current_count > 0
            for writer in writers
            if writer is not None
        )


class ThreatInjectorApplication:
    def __init__(self, app, ui: DemoUiState) -> None:
        self.app = app
        self.ui = ui
        self.logic = ThreatInjectionLogic()
        self.dds = ThreatInjectorDdsAdapter()
        self._attack_task: asyncio.Task | None = None
        self._matched: bool | None = None
        self._preview: ArmModel | None = None
        self._preview_error: str | None = None
        try:
            from ArmKinematics import ArmModel

            self._preview = ArmModel()
        except _PREVIEW_ERRORS as exc:
            self._disable_preview(exc)

    def _disable_preview(self, error: Exception) -> None:
        self._preview = None
        self._preview_error = str(error)
        self.ui.log(
            f"Command preview unavailable: {error}. DDS injection remains available", "warn"
        )

    def _preview_view(self) -> dict:
        if self._preview is not None:
            try:
                return {**self._preview.view(), "active": True, "preview": True}
            except _PREVIEW_ERRORS as exc:
                self._disable_preview(exc)
        return {"active": False, "preview": True, "error": self._preview_error}

    def view(self) -> dict:
        ready = self.dds.participant is not None
        teleop_attack = self.logic.attack == _ATTACKS[0]
        launch_label = "STOP INJECTION" if self.logic.attacking else "LAUNCH ATTACK"
        status = (
            self.logic.failure_state
            if self.logic.failure_state
            else "ATTACKING"
            if self.logic.attacking and self._matched
            else "NO ACCESS"
            if self.logic.attacking or (ready and not self._matched)
            else "ARMED"
            if ready
            else "IDLE"
        )
        mode_controls = [
            {
                "type": "button",
                "label": mode,
                "command": "select-mode",
                "payload": {"mode": mode},
                "className": "mode-button selected" if mode == self.logic.mode else "mode-button",
            }
            for mode in _MODES
        ]
        attack_controls = [
            {
                "type": "button",
                "label": attack,
                "command": "select-attack",
                "payload": {"attack": attack},
                "className": "attack-button selected"
                if attack == self.logic.attack
                else "attack-button",
                "disabled": not ready or self.logic.attacking,
            }
            for attack in _ATTACKS
        ]
        controls = [
            {
                "title": "ATTACK MODE",
                "layout": "attack-modes",
                "controls": mode_controls,
            },
            {
                "title": "ATTACK TYPE",
                "layout": "attack-types",
                "controls": attack_controls,
            },
            {
                "title": "INJECT FREQUENCY",
                "layout": "frequency-control",
                "controls": [
                    {
                        "type": "range",
                        "label": "Inject Frequency (Hz)",
                        "unit": " Hz",
                        "min": 1,
                        "max": 20,
                        "value": self.logic.frequency_hz,
                        "command": "set-frequency",
                        "parameter": "frequency_hz",
                        "disabled": not ready or not teleop_attack or self.logic.attacking,
                    }
                ],
            },
            {
                "title": "",
                "layout": "attack-actions",
                "controls": [
                    {
                        "type": "button",
                        "label": launch_label,
                        "command": "toggle-attack",
                        "payload": {},
                        "className": "launch-button",
                        "disabled": not ready,
                    },
                    {
                        "type": "button",
                        "label": "STOP ATTACK",
                        "command": "stop-attack",
                        "payload": {},
                        "className": "stop-button",
                        "disabled": not self.logic.attacking,
                    },
                ],
            },
        ]
        return {
            "kind": "threat-injector",
            "dds_security": self.dds.dds_security,
            "title": "Threat Injector",
            "status": status,
            "header_badges": [
                {
                    "label": "Attack",
                    "value": status,
                    "tone": (
                        "danger"
                        if status == "ATTACK FAILED"
                        else "good"
                        if status == "ATTACKING"
                        else "muted"
                        if status == "IDLE"
                        else "warn"
                    ),
                }
            ],
            "activity_title": "SECURITY ACTIVITY",
            "show_activity_toggle": True,
            "arm": self._preview_view(),
            "preview_label": "COMMAND PREVIEW - not observed arm feedback",
            "control_groups": controls,
            "footer": True,
        }

    async def select_mode(self, mode: str) -> dict:
        if self.logic.attacking:
            await self.stop_attack()
        self.dds.close()
        self.logic.mode = mode
        self.logic.failure_state = None
        try:
            self.dds.open(mode)
        except dds.Error as exc:
            self.logic.mode = None
            self.logic.failure_state = "ATTACK FAILED"
            self._matched = False
            self.dds.close()
            self.ui.update(**self.view())
            self.ui.log(f"Participant creation blocked by security: {exc}", "blocked")
            return {"message": "Participant creation was denied by DDS Security"}
        self._matched = False
        self.ui.log(f"Created participant for {mode}")
        self.ui.update(**self.view())
        return {"message": f"{mode} participant selected"}

    async def select_attack(self, attack: str) -> dict:
        if self.logic.attacking:
            await self.stop_attack()
        self.logic.attack = attack
        self.ui.update(**self.view())
        return {"message": f"Selected {attack}"}

    async def set_frequency(self, frequency_hz: int) -> dict:
        self.logic.frequency_hz = frequency_hz
        self.ui.update(**self.view())
        return {"message": f"Injection frequency set to {frequency_hz} Hz"}

    async def toggle_attack(self, _payload: dict) -> dict:
        if self.dds.participant is None:
            return {"message": "Select an attack mode first"}
        if self.logic.attack != _ATTACKS[0]:
            self._inject_once()
            return {"message": f"Sent one {self.logic.command_attack()} command"}
        if self.logic.attacking:
            await self.stop_attack()
            return {"message": "Injection stopped"}
        self.logic.attacking = True
        self._attack_task = asyncio.create_task(self._inject_repeatedly())
        self.ui.log(f"Attack launched — mode: {self.logic.mode}, type: {self.logic.attack}")
        self.ui.update(**self.view())
        return {"message": "Injection started"}

    async def stop_attack(self) -> dict:
        self.logic.attacking = False
        if self._attack_task is not None:
            task = self._attack_task
            self._attack_task = None
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._matched = None
        self.logic.failure_state = None
        self.ui.log("Injection stopped")
        self.ui.update(**self.view())
        return {"message": "Injection stopped"}

    def _inject_once(self) -> None:
        try:
            if self.logic.attack == _ATTACKS[0]:
                axis, direction = self.logic.next_teleop()
                self.dds.write_teleop(axis, direction)
                if self._preview is not None:
                    try:
                        linear, angular = _rates(axis, direction)
                        self._preview.step(linear, angular, 0.0, 0.02)
                    except _PREVIEW_ERRORS as exc:
                        self._disable_preview(exc)
                self.ui.log(
                    f"Writing TeleopControl — axis: {axis}, direction: {direction}",
                    "ok" if self._matched else "warn",
                )
            else:
                command = self.logic.command_attack()
                self.dds.write_device_command(command)
                self.ui.log(
                    f"Writing DeviceCommand — {command} to ARM",
                    "ok" if self._matched else "warn",
                )
        except dds.Error as exc:
            self.ui.log(f"DDS write rejected: {exc}", "blocked")
            self._matched = False
        self.ui.update(**self.view())

    async def _inject_repeatedly(self) -> None:
        while self.logic.attacking:
            self._inject_once()
            await asyncio.sleep(1 / self.logic.frequency_hz)

    async def monitor_matches(self) -> None:
        while True:
            matched = self.dds.publication_matched()
            if self._attack_task is not None and self._attack_task.done():
                task = self._attack_task
                self._attack_task = None
                task.result()
            if matched != self._matched:
                self._matched = matched
                self.ui.log(
                    "DDS writer matched to a reader"
                    if matched
                    else "No publication match — access may be denied",
                    "ok" if matched else "blocked",
                )
                self.ui.update(**self.view())
            await asyncio.sleep(0.5)


def configure_app(app):
    for data_type in (
        Device.Status,
        Device.Command,
        Robot.Arm.TeleopControl,
    ):
        register_type(data_type)
    ui = DemoUiState(
        app,
        kind="threat-injector",
        title="Threat Injector",
        description="Security threat demonstration for RTI Connext DDS.",
    )
    application = ThreatInjectorApplication(app, ui)
    app.register_command(
        "select-mode",
        {
            "type": "object",
            "properties": {"mode": {"type": "string", "enum": list(_MODES)}},
            "required": ["mode"],
            "additionalProperties": False,
        },
        lambda payload: application.select_mode(payload["mode"]),
    )
    app.register_command(
        "select-attack",
        {
            "type": "object",
            "properties": {"attack": {"type": "string", "enum": list(_ATTACKS)}},
            "required": ["attack"],
            "additionalProperties": False,
        },
        lambda payload: application.select_attack(payload["attack"]),
    )
    app.register_command(
        "set-frequency",
        {
            "type": "object",
            "properties": {"frequency_hz": {"type": "integer", "minimum": 1, "maximum": 20}},
            "required": ["frequency_hz"],
            "additionalProperties": False,
        },
        lambda payload: application.set_frequency(payload["frequency_hz"]),
    )
    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    app.register_command("toggle-attack", empty, application.toggle_attack)
    app.register_command("stop-attack", empty, application.stop_attack)
    ui.update(**application.view())
    ui.log("Threat Injector is idle")

    async def run(_app) -> None:
        try:
            await application.monitor_matches()
        finally:
            try:
                await application.stop_attack()
            finally:
                application.dds.close()

    return run


def main() -> None:
    app = create_demo_ui("Threat Injector")
    run_demo_ui(app, configure_app(app))


if __name__ == "__main__":
    main()
