#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""RTI Demo UI runtime mode and custom frontend smoke tests."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import ModuleType

from aiohttp import ClientSession
from rti_demo_ui import DemoUiApp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "resource" / "ui_web"
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "01-operating-room" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "resource" / "python"))

import DemoUiSupport  # noqa: E402

import launch  # noqa: E402


def test_launcher_defaults_to_browser_mode():
    _, _, env = launch._resolve_module("04-security-threat", ["ThreatInjector"], False)
    assert env["RTI_DEMO_UI_MODE"] == "browser"


def test_launcher_propagates_native_mode():
    _, _, env = launch._resolve_module(
        "04-security-threat",
        ["ThreatInjector"],
        False,
        ui_mode="native",
    )
    assert env["RTI_DEMO_UI_MODE"] == "native"


def test_native_mode_delegates_to_sdk_runner(monkeypatch):
    monkeypatch.setenv("RTI_DEMO_UI_MODE", "native")
    launched = {}

    def run_native(app, *, async_main):
        launched["app"] = app
        launched["async_main"] = async_main

    native_module = ModuleType("rti_demo_ui_native")
    native_module.run_native = run_native
    monkeypatch.setitem(sys.modules, "rti_demo_ui_native", native_module)

    async def no_work(_app):
        pass

    app = DemoUiApp("Native UI preflight", host="127.0.0.1", static_root=WEB_ROOT)
    DemoUiSupport.run_demo_ui(app, no_work)

    assert launched == {"app": app, "async_main": no_work}


def test_sdk_serves_the_custom_medtech_frontend_and_app_state(capsys):
    async def check_server():
        app = DemoUiSupport.create_demo_ui("RTI MedTech UI smoke test")
        app.set_data({"kind": "test", "status": "ON"})
        server_task = asyncio.create_task(app.run())
        try:
            ready = await app.wait_until_ready()
            announcement = capsys.readouterr().out
            assert "RTI MedTech UI smoke test listening on" in announcement
            assert ready.url in announcement
            async with ClientSession() as session:
                async with session.get(ready.url) as response:
                    assert response.status == 200
                    page = await response.text()
                    assert "<title>RTI Connext</title>" in page
                    assert 'id="app-main"' in page
                    assert "Application metrics" not in page
                async with session.get(f"{ready.url}/app.js") as response:
                    assert response.status == 200
                    assert "createClient" in await response.text()
                async with session.get(f"{ready.url}/api/state") as response:
                    assert response.status == 200
                    state = await response.json()
                    assert state["title"] == "RTI MedTech UI smoke test"
                    assert state["data"] == {"kind": "test", "status": "ON"}
                    json.dumps(state)
        finally:
            await app.stop()
            await server_task

    asyncio.run(check_server())
