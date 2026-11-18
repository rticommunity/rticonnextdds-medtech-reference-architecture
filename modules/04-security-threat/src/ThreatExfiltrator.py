#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Threat-exfiltration use cases, Connext adapter, and web presentation state."""

from __future__ import annotations

import asyncio
import time

import rti.asyncio  # noqa: F401 - installs Connext's asyncio integration
import rti.connextdds as dds
from DemoUiSupport import DemoUiState, create_demo_ui, run_demo_ui
from MedTech import DdsEntities, Patient
from MedTechTypes import register_type
from ThreatTypes import ThreatEntities

_MODES = ("UNSECURE", "ROGUE CA", "FORGED PERMS", "EXPIRED CERT")
_MODE_TO_PARTICIPANT = {
    "UNSECURE": ThreatEntities.Constants.EXFILTRATOR_UNSECURE_DP,
    "ROGUE CA": ThreatEntities.Constants.EXFILTRATOR_ROGUE_CA_DP,
    "FORGED PERMS": ThreatEntities.Constants.EXFILTRATOR_FORGED_PERMS_DP,
    "EXPIRED CERT": ThreatEntities.Constants.EXFILTRATOR_EXPIRED_CERT_DP,
}
DATA_TIMEOUT_SECONDS = 2.0


class ThreatExfiltrationLogic:
    def __init__(self) -> None:
        self.mode: str | None = None
        self.vitals: dict[str, float] | None = None
        self.last_sample_at: float | None = None
        self.access = "IDLE"
        self.failure_state: str | None = None

    def receive(self, vitals: dict[str, float]) -> dict[str, float]:
        self.vitals = vitals
        self.last_sample_at = time.monotonic()
        self.access = "ACCESS GRANTED"
        return self.vitals

    def stale(self) -> bool:
        return self.last_sample_at is None or (
            time.monotonic() - self.last_sample_at > DATA_TIMEOUT_SECONDS
        )


class ThreatExfiltratorDdsAdapter:
    def __init__(self) -> None:
        self.participant = None
        self.reader = None

    def open(self, mode: str) -> None:
        register_type(Patient.Vitals)
        self.participant = dds.QosProvider.default.create_participant_from_config(
            _MODE_TO_PARTICIPANT[mode]
        )
        self.reader = dds.DataReader(
            self.participant.find_datareader(DdsEntities.Constants.VITALS_DR)
        )
        self.participant.enable()

    def close(self) -> None:
        if self.participant is not None:
            self.participant.close()
        self.participant = self.reader = None


class ThreatExfiltratorApplication:
    def __init__(self, ui: DemoUiState) -> None:
        self.ui = ui
        self.logic = ThreatExfiltrationLogic()
        self.dds = ThreatExfiltratorDdsAdapter()
        self.reader_task: asyncio.Task | None = None
        self.matched: bool | None = None

    def view(self) -> dict:
        stale = self.logic.stale()
        vitals = dict(self.logic.vitals or {})
        vitals["fresh"] = not stale and self.matched is True
        if stale:
            vitals = {"fresh": False}
        controls = [
            {
                "title": "ATTACK MODE",
                "layout": "attack-modes",
                "controls": [
                    {
                        "type": "button",
                        "label": mode,
                        "command": "select-mode",
                        "payload": {"mode": mode},
                        "className": "mode-button selected"
                        if mode == self.logic.mode
                        else "mode-button",
                    }
                    for mode in _MODES
                ],
            },
            {
                "title": "",
                "layout": "attack-actions",
                "controls": [
                    {
                        "type": "button",
                        "label": "STOP ATTACK",
                        "command": "stop-attack",
                        "payload": {},
                        "className": "stop-button",
                        "disabled": self.dds.participant is None,
                    }
                ],
            },
        ]
        status = (
            self.logic.failure_state
            if self.logic.failure_state
            else "IDLE"
            if self.dds.participant is None
            else "ACCESS GRANTED"
            if self.matched is True and not stale
            else "WAITING FOR DATA"
            if self.matched is True
            else "NO ACCESS"
        )
        vitals_status = (
            "WAITING FOR VITALS"
            if self.dds.participant is None or not self.logic.vitals
            else "LIVE VITALS"
            if not stale and self.matched
            else "DATA QUIET"
            if stale and self.matched
            else "NO ACCESS"
        )
        return {
            "kind": "threat-exfiltrator",
            "title": "Threat Exfiltrator",
            "status": status,
            "vitals_status": vitals_status,
            "header_badges": [
                {"label": "Vitals", "value": vitals_status},
                {
                    "label": "Access",
                    "value": status,
                    "tone": (
                        "good"
                        if status == "ACCESS GRANTED"
                        else "danger"
                        if status == "ATTACK FAILED"
                        else "muted"
                        if status == "IDLE"
                        else "warn"
                    ),
                },
            ],
            "activity_title": "EXFILTRATION ACTIVITY",
            "show_activity_toggle": True,
            "vitals": vitals,
            "control_groups": controls,
            "footer": True,
        }

    async def select_mode(self, mode: str) -> dict:
        await self.stop_attack(log=False)
        self.logic.mode = mode
        self.logic.failure_state = None
        try:
            self.dds.open(mode)
        except dds.Error as exc:
            self.dds.close()
            self.logic.mode = None
            self.logic.access = "ATTACK FAILED"
            self.logic.failure_state = "ATTACK FAILED"
            self.ui.log(f"Participant creation blocked by security: {exc}", "blocked")
            self.ui.update(**self.view())
            return {"message": "Participant creation was denied by DDS Security"}
        self.matched = False
        self.reader_task = asyncio.create_task(self._receive_vitals(self.dds.reader))
        self.logic.vitals = None
        self.logic.last_sample_at = None
        self.logic.access = "WAITING FOR DATA"
        self.ui.log(f"Participant created — {mode}")
        self.ui.update(**self.view())
        return {"message": f"Selected {mode}; waiting for DDS data"}

    async def _receive_vitals(self, reader) -> None:
        async for sample in reader.take_data_async():
            vitals = self.logic.receive(
                {
                    "heart_rate": float(sample.hr),
                    "spo2": float(sample.spo2),
                    "etco2": float(sample.etco2),
                    "nibp_s": float(sample.nibp_s),
                    "nibp_d": float(sample.nibp_d),
                }
            )
            self.ui.log(
                "Received patient vitals — "
                f"HR {vitals['heart_rate']:.0f}, SpO₂ {vitals['spo2']:.1f}%, "
                f"EtCO₂ {vitals['etco2']:.0f} mmHg",
                "ok",
            )
            self.ui.update(**self.view())

    async def stop_attack(self, *, log: bool = True) -> dict:
        task = self.reader_task
        self.reader_task = None
        if task is not None and not task.done():
            task.cancel()
        try:
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            self.dds.close()
            self.logic.mode = None
            self.logic.vitals = None
            self.logic.last_sample_at = None
            self.logic.access = "IDLE"
            self.logic.failure_state = None
            self.matched = None
            if log:
                self.ui.log("Attack stopped — returned to idle")
            self.ui.update(**self.view())
        return {"message": "Attack stopped"}

    async def monitor_status(self) -> None:
        while True:
            if self.reader_task is not None and self.reader_task.done():
                task = self.reader_task
                self.reader_task = None
                task.result()
                raise RuntimeError("DDS patient-vitals reader stopped unexpectedly")
            if self.dds.reader is not None:
                matched = self.dds.reader.subscription_matched_status.current_count > 0
                if matched != self.matched:
                    self.matched = matched
                    self.logic.access = "ACCESS GRANTED" if matched else "NO ACCESS"
                    self.ui.log(
                        "Subscription matched — receiving data"
                        if matched
                        else "No subscription match — access denied by security",
                        "ok" if matched else "blocked",
                    )
                    self.ui.update(**self.view())
                if self.logic.last_sample_at and self.logic.stale():
                    self.logic.vitals = None
                    self.logic.last_sample_at = None
                    self.ui.log("Patient data is quiet")
                    self.ui.update(**self.view())
            await asyncio.sleep(0.25)


def configure_app(app):
    ui = DemoUiState(
        app,
        kind="threat-exfiltrator",
        title="Threat Exfiltrator",
        description="Security threat demonstration for RTI Connext DDS.",
    )
    application = ThreatExfiltratorApplication(ui)
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
        "stop-attack",
        {"type": "object", "properties": {}, "additionalProperties": False},
        application.stop_attack,
    )
    ui.update(**application.view())
    ui.log("Threat Exfiltrator is idle")

    async def run(_app) -> None:
        try:
            await application.monitor_status()
        finally:
            try:
                await application.stop_attack(log=False)
            finally:
                print("Shutting down Threat Exfiltrator", flush=True)

    return run


def main() -> None:
    app = create_demo_ui("Threat Exfiltrator")
    run_demo_ui(app, configure_app(app))


if __name__ == "__main__":
    main()
