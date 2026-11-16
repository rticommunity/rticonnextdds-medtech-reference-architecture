#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""RTI Demo UI runtime mode and custom frontend smoke tests."""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import re
import select
import shutil
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest
from aiohttp import ClientSession

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "resource" / "ui_web"
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "01-operating-room" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "resource" / "python"))

import launch  # noqa: E402


def _demo_ui_support():
    return importlib.import_module("DemoUiSupport")


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


def test_native_icon_uses_a_platform_supported_format(monkeypatch):
    demo_ui_support = _demo_ui_support()
    monkeypatch.setattr(demo_ui_support.sys, "platform", "linux")
    assert demo_ui_support.native_icon_path() == WEB_ROOT / "rti_logo.png"
    monkeypatch.setattr(demo_ui_support.sys, "platform", "win32")
    assert demo_ui_support.native_icon_path() == WEB_ROOT / "rti_logo.ico"


def test_native_mode_delegates_to_sdk_runner(monkeypatch):
    demo_ui_support = _demo_ui_support()
    demo_ui_app = importlib.import_module("rti_demo_ui").DemoUiApp
    monkeypatch.setenv("RTI_DEMO_UI_MODE", "native")
    launched = {}

    def run_native(app, *, async_main, icon):
        launched["app"] = app
        launched["async_main"] = async_main
        launched["icon"] = icon

    native_module = ModuleType("rti_demo_ui_native")
    native_module.run_native = run_native
    monkeypatch.setitem(sys.modules, "rti_demo_ui_native", native_module)

    async def no_work(_app):
        pass

    app = demo_ui_app("Native UI preflight", host="127.0.0.1", static_root=WEB_ROOT)
    demo_ui_support.run_demo_ui(app, no_work)

    assert launched == {
        "app": app,
        "async_main": no_work,
        "icon": WEB_ROOT / "rti_logo.png",
    }


def test_sdk_serves_the_custom_medtech_frontend_and_app_state(capsys):
    demo_ui_support = _demo_ui_support()

    async def check_server():
        app = demo_ui_support.create_demo_ui("RTI MedTech UI smoke test")
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
                async with session.get(f"{ready.url}/rti_logo.png") as response:
                    assert response.status == 200
                    assert response.content_type == "image/png"
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


@pytest.mark.parametrize(
    ("module", "app"),
    (
        ("01-operating-room", "Arm"),
        ("01-operating-room", "ArmController"),
        ("01-operating-room", "Orchestrator"),
        ("01-operating-room", "PatientMonitor"),
        ("04-security-threat", "ThreatExfiltrator"),
    ),
)
def test_gui_controls_remain_within_resized_windows(module, app):
    playwright = pytest.importorskip("playwright.sync_api")
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if chrome is None:
        pytest.skip("Responsive layout checks require Chrome or Chromium")

    from scripts.module_runner import MODULES_DIR, load_module_config
    from scripts.test_utils import ProcessManager

    directory = MODULES_DIR / module
    env, apps = load_module_config(directory, flags={"security": False})
    manager = ProcessManager(env, apps, cwd=directory)
    try:
        process = manager.start_app_ready(app)
        output = ""
        deadline = time.monotonic() + 5
        while not (endpoint := re.search(r"http://127\.0\.0\.1:\d+/", output)):
            remaining = deadline - time.monotonic()
            assert remaining > 0, f"{app} did not announce its URL: {output}"
            readable, _, _ = select.select([process.stdout], [], [], remaining)
            assert readable, f"{app} did not announce its URL: {output}"
            output += process.stdout.read1(4096).decode()

        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=chrome,
                headless=True,
                args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
            )
            try:
                page = browser.new_page()
                page.goto(endpoint[0])
                page.wait_for_function("document.body.dataset.appKind")
                if app == "Arm":
                    page.wait_for_function(
                        "document.querySelector('.arm-scene-status')?.textContent.includes('loaded')"
                    )
                    panel = page.locator(".actual-feedback")
                    assert panel.locator("h2").inner_text() == "REPORTED TELEMETRY"
                    assert "t/robot/arm/telemetry" not in panel.inner_text()
                    assert not panel.locator(".feedback-freshness").is_visible()
                    publication = panel.locator(".telemetry-publication")
                    assert publication.get_attribute("aria-label") == "Publishing telemetry"
                    page.emulate_media(reduced_motion="no-preference")
                    opacities = page.evaluate("""async () => {
                        const light = document.querySelector('.telemetry-publication');
                        const values = [];
                        for (let i = 0; i < 12; ++i) {
                            values.push(Number(getComputedStyle(light).opacity));
                            await new Promise(resolve => setTimeout(resolve, 80));
                        }
                        return values;
                    }""")
                    assert max(opacities) - min(opacities) > 0.5
                    assert "---" not in panel.locator(".feedback-value").all_inner_texts()
                    assert not page.locator(".sdk-scene3d-list").is_visible()
                    canvas = page.locator("#arm-scene-host canvas")
                    page.wait_for_timeout(300)
                    home = canvas.screenshot()
                    assert "pan" in page.locator(".arm-scene-status").inner_text()
                    label_mutations = page.evaluate("""async () => {
                        const buttons = [
                            ...document.querySelectorAll(
                                '[data-action="reset-camera"], [data-action="zoom-model"]'
                            )
                        ];
                        let mutations = 0;
                        const observer = new MutationObserver(records => {
                            mutations += records.length;
                        });
                        buttons.forEach(button => observer.observe(button, { childList: true }));
                        await new Promise(resolve => setTimeout(resolve, 600));
                        observer.disconnect();
                        return mutations;
                    }""")
                    assert label_mutations == 0, "Live updates must not replace button labels"
                    blue_pixels = page.evaluate(
                        """async (png) => {
                        const image = new Image();
                        image.src = `data:image/png;base64,${png}`;
                        await image.decode();
                        const buffer = document.createElement('canvas');
                        buffer.width = image.width; buffer.height = image.height;
                        const context = buffer.getContext('2d');
                        context.drawImage(image, 0, 0);
                        const pixels = context.getImageData(0, 0, buffer.width, buffer.height).data;
                        let blue = 0;
                        for (let i = 0; i < pixels.length; i += 4) {
                            if (pixels[i + 2] > 100 && pixels[i + 2] > pixels[i + 1] * 1.2
                                && pixels[i + 2] > pixels[i] * 1.5) blue++;
                        }
                        return blue;
                    }""",
                        base64.b64encode(home).decode(),
                    )
                    assert blue_pixels > 50, "Original blue arm accents must not be painted green"
                    page.get_by_role("button", name="Fit arm", exact=True).click()
                    page.wait_for_timeout(300)
                    assert canvas.screenshot() != home
                    page.get_by_role("button", name="Reset camera", exact=True).click()
                    page.wait_for_timeout(300)
                    assert canvas.screenshot() == home
                    for view in ("Side view", "Top view"):
                        page.get_by_role("button", name=view, exact=True).click()
                        page.wait_for_timeout(300)
                        preset = canvas.screenshot()
                        assert preset != home
                        page.wait_for_timeout(600)
                        assert canvas.screenshot() == preset
                        page.get_by_role("button", name="Reset camera", exact=True).click()
                        page.wait_for_timeout(300)
                        assert canvas.screenshot() == home
                    canvas_box = canvas.bounding_box()
                    assert canvas_box
                    x = canvas_box["x"] + canvas_box["width"] * 0.2
                    y = canvas_box["y"] + canvas_box["height"] * 0.2
                    telemetry = panel.locator(".feedback-value").all_inner_texts()
                    pan_view = None
                    for modifier in ("right", "shift"):
                        page.mouse.move(x, y)
                        if modifier == "shift":
                            page.keyboard.down("Shift")
                        page.mouse.down(button="right" if modifier == "right" else "left")
                        page.mouse.move(x + 80, y + 40, steps=8)
                        page.mouse.up(button="right" if modifier == "right" else "left")
                        if modifier == "shift":
                            page.keyboard.up("Shift")
                        page.wait_for_timeout(200)
                        panned = canvas.screenshot()
                        assert panned != home
                        if pan_view is None:
                            pan_view = panned
                        else:
                            assert panned == pan_view
                        assert panel.locator(".feedback-value").all_inner_texts() == telemetry
                        page.get_by_role("button", name="Reset camera", exact=True).click()
                        page.wait_for_timeout(300)
                        assert canvas.screenshot() == home
                    for delta in (-200, 200):
                        page.mouse.move(x, y)
                        page.mouse.down()
                        page.mouse.move(x + 80, y + 40, steps=8)
                        page.mouse.up()
                        page.mouse.wheel(0, delta)
                        page.wait_for_timeout(200)
                        adjusted = canvas.screenshot()
                        page.get_by_role("button", name="Fit arm", exact=True).click()
                        page.wait_for_timeout(300)
                        assert canvas.screenshot() != adjusted
                        page.get_by_role("button", name="Reset camera", exact=True).click()
                        page.wait_for_timeout(300)
                        assert canvas.screenshot() == home
                    assert page.locator(".camera-action-status").inner_text() == (
                        "Camera reset; arm position unchanged."
                    )
                    controller = manager.start_app_ready("ArmController")
                    page.wait_for_function(
                        "document.querySelector('.feedback-readiness')?.textContent"
                        " === 'Arm readiness: READY'"
                    )
                    controller_output = ""
                    deadline = time.monotonic() + 5
                    while not (
                        controller_endpoint := re.search(
                            r"http://127\.0\.0\.1:\d+/", controller_output
                        )
                    ):
                        remaining = deadline - time.monotonic()
                        assert remaining > 0, (
                            f"Controller did not announce URL: {controller_output}"
                        )
                        readable, _, _ = select.select([controller.stdout], [], [], remaining)
                        assert readable, f"Controller did not announce URL: {controller_output}"
                        controller_output += controller.stdout.read1(4096).decode()
                    controller_page = browser.new_page()
                    controller_page.goto(controller_endpoint[0])
                    positive_x = controller_page.get_by_role("button", name="X +", exact=True)
                    positive_x.wait_for()

                    def layout_bounds():
                        return page.evaluate("""() => {
                            const selectors = [
                                '.app-header', '.arm-scene-panel', '.actual-feedback',
                            ];
                            return selectors.map(selector => {
                                const r = document.querySelector(selector).getBoundingClientRect();
                                return [r.x, r.y, r.width, r.height];
                            });
                        }""")

                    baseline_bounds = layout_bounds()
                    positive_x.dispatch_event("keydown", {"key": " "})
                    warning = page.locator(".arm-motion-status")
                    warning.wait_for(timeout=5000)
                    assert "limit:" in warning.inner_text()
                    assert layout_bounds() == baseline_bounds
                    assert page.locator('.header-badge[data-label="motion"]').count() == 0
                    page.set_viewport_size({"width": 1050, "height": 740})
                    narrow_bounds = layout_bounds()
                    positive_x.dispatch_event("keyup", {"key": " "})
                    warning.wait_for(state="hidden", timeout=5000)
                    assert layout_bounds() == narrow_bounds
                    controller_page.close()
                    controller.terminate()
                    controller.wait(timeout=5)
                    page.wait_for_function(
                        "document.querySelector('.feedback-readiness')?.textContent"
                        " === 'Arm readiness: NOT_READY'"
                    )
                    assert not panel.locator(".feedback-freshness").is_visible()
                    assert publication.get_attribute("aria-label") == "Publishing telemetry"
                    assert "---" not in panel.locator(".feedback-value").all_inner_texts()
                for width, height in ((1600, 950), (800, 600), (640, 480), (390, 844), (320, 480)):
                    page.set_viewport_size({"width": width, "height": height})
                    overflow = page.evaluate("""() => {
                        const width = document.documentElement.clientWidth;
                        const panels = [...document.querySelectorAll('.vital-panel')]
                            .map(panel => panel.getBoundingClientRect());
                        return {
                            horizontal: document.documentElement.scrollWidth - width,
                            controls: [...document.querySelectorAll('button')]
                                .filter(button => {
                                    const r = button.getBoundingClientRect();
                                    return r.width && (r.left < -1 || r.right > width + 1);
                                }).map(button => button.textContent),
                            overlappingPanels: panels.some((a, i) => panels.slice(i + 1)
                                .some(b => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1
                                    && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1)),
                        };
                    }""")
                    assert overflow["horizontal"] <= 1, (app, width, overflow)
                    assert not overflow["controls"], (app, width, overflow)
                    assert not overflow["overlappingPanels"], (app, width, overflow)
                    if app == "Arm":
                        scene = page.locator(".arm-scene-panel").bounding_box()
                        telemetry = page.locator(".actual-feedback").bounding_box()
                        assert scene and telemetry
                        if width > 900:
                            assert telemetry["x"] >= scene["x"] + scene["width"]
                            assert abs(telemetry["y"] - scene["y"]) <= 1
                        else:
                            assert telemetry["y"] >= scene["y"] + scene["height"]
                if app == "Arm":
                    fallback = browser.new_page()
                    fallback.route("**/models/articulated-arm.glb", lambda route: route.abort())
                    fallback.goto(endpoint[0])
                    fallback.wait_for_function(
                        "document.querySelector('.arm-scene-status')?.textContent.includes('unavailable')"
                    )
                    assert fallback.locator(".sdk-scene3d-list").is_visible()
                    assert "REPORTED TELEMETRY" in fallback.locator(".actual-feedback").inner_text()
                    process.terminate()
                    process.wait(timeout=5)
                    page.wait_for_function(
                        "!document.querySelector('.telemetry-publication')"
                        "?.classList.contains('publishing')",
                        timeout=3000,
                    )
                    assert publication.get_attribute("aria-label") == (
                        "No recent telemetry publication"
                    )
            finally:
                browser.close()
    finally:
        manager.shutdown_all()
