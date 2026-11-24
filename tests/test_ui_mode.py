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
import sys
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

import pytest
from aiohttp import ClientSession

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "resources" / "ui" / "web"
sys.path.insert(0, str(WEB_ROOT.parent / "support"))

from tools.medtech import launch  # noqa: E402


def _demo_ui_support():
    return importlib.import_module("DemoUiSupport")


@pytest.fixture
def launcher_environment(monkeypatch, tmp_path):
    from tools.medtech import module_runner

    monkeypatch.setattr(module_runner.platform_setup, "get_nddshome", lambda: tmp_path)
    monkeypatch.setattr(module_runner.platform_setup, "setup_library_env", lambda *_: None)
    monkeypatch.setattr(module_runner.platform_setup, "generated_system_path", lambda: tmp_path)


def test_launcher_defaults_to_browser_mode(launcher_environment):
    _, _, env = launch._resolve_module("04-security-threat", ["ThreatInjector"], False)
    assert env["RTI_DEMO_UI_MODE"] == "browser"


def test_launcher_propagates_native_mode(launcher_environment):
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

    assert launched["app"] is app
    assert callable(launched["async_main"])
    assert launched["icon"] == WEB_ROOT / "rti_logo.png"


def test_browser_server_failure_is_logged_in_server_task(capsys):
    class FailedServer:
        async def run(self):
            raise RuntimeError("server failed")

        async def wait_until_ready(self):
            await asyncio.Event().wait()

        async def stop(self):
            pass

    async def work(_app):
        pass

    assert not asyncio.run(
        asyncio.wait_for(_demo_ui_support()._run_browser(FailedServer(), work), 1)
    )
    assert "UI server failed: server failed" in capsys.readouterr().err


def test_browser_work_failure_is_logged_in_work_task(capsys):
    class Server:
        def __init__(self):
            self.stopped = asyncio.Event()

        async def run(self):
            await self.stopped.wait()

        async def wait_until_ready(self):
            pass

        async def stop(self):
            self.stopped.set()

    async def work(_app):
        raise RuntimeError("work failed")

    assert not asyncio.run(asyncio.wait_for(_demo_ui_support()._run_browser(Server(), work), 1))
    assert "Application task failed: work failed" in capsys.readouterr().err


def test_browser_work_cleanup_failure_is_not_reported_as_success(capsys):
    class Server:
        def __init__(self):
            self.stopped = asyncio.Event()

        async def run(self):
            await self.stopped.wait()

        async def wait_until_ready(self):
            pass

        async def stop(self):
            self.stopped.set()

    async def work(app):
        try:
            app.stopped.set()
            await asyncio.Event().wait()
        finally:
            raise RuntimeError("cleanup failed")

    assert not asyncio.run(asyncio.wait_for(_demo_ui_support()._run_browser(Server(), work), 1))
    assert "Application task failed: cleanup failed" in capsys.readouterr().err


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


@pytest.mark.browser
@pytest.mark.parametrize(
    ("module", "app"),
    (
        ("01-operating-room", "Arm"),
        ("01-operating-room", "ArmController"),
        ("01-operating-room", "Orchestrator"),
        ("01-operating-room", "PatientMonitor"),
        ("04-security-threat", "ThreatInjector"),
        ("04-security-threat", "ThreatExfiltrator"),
    ),
)
def test_gui_controls_remain_within_resized_windows(module, app):
    import playwright.sync_api as playwright

    with playwright.sync_playwright() as pw:
        bundled_chromium = Path(pw.chromium.executable_path)
    assert bundled_chromium.is_file(), (
        "Browser tests require Playwright Chromium. "
        "Run `python -m playwright install --with-deps chromium` after syncing "
        "the locked developer dependencies."
    )

    from test_utils import ProcessManager

    from tools.medtech.module_runner import MODULES_DIR, load_module_config

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
                executable_path=str(bundled_chromium),
                headless=True,
                args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
            )
            try:
                page = browser.new_page()
                page.goto(endpoint[0])
                page.wait_for_function("document.body.dataset.appKind")
                security = page.locator(".header-controls #header-security")
                expected_mode = "unknown" if module.startswith("04") else "disabled"
                page.wait_for_function(
                    "mode => document.querySelector('#header-security').dataset.mode === mode",
                    arg=expected_mode,
                )
                device = page.locator(".header-controls #header-device")
                if app in ("Arm", "ArmController", "PatientMonitor"):
                    assert device.inner_text().split() == ["Device", "ON"]
                else:
                    assert not device.is_visible()
                assert security.get_attribute("aria-label") == (
                    "DDS Security disabled"
                    if expected_mode == "disabled"
                    else "DDS security status unavailable"
                )
                if app in ("Orchestrator", "ThreatInjector", "ThreatExfiltrator"):
                    redundant_label_updates = page.evaluate("""async () => {
                        const toggle = document.querySelector('#activity-toggle');
                        let label = toggle.textContent;
                        let redundant = 0;
                        const observer = new MutationObserver(() => {
                            if (toggle.textContent === label) redundant++;
                            label = toggle.textContent;
                        });
                        observer.observe(toggle, {
                            childList: true, characterData: true, subtree: true,
                        });
                        await new Promise(resolve => setTimeout(resolve, 400));
                        observer.disconnect();
                        return redundant;
                    }""")
                    assert redundant_label_updates == 0, (
                        "Live updates must not replace the log toggle's unchanged text hit target"
                    )
                if app == "Orchestrator":
                    sensor_process = manager.start_app_ready("PatientSensor")
                    sensor = page.locator(".device-card").filter(has_text="PATIENT_SENSOR")
                    playwright.expect(sensor.locator(".device-status")).to_have_text("ON")
                    playwright.expect(sensor.locator(".device-status-label")).to_have_text(
                        "Lifecycle · last reported"
                    )
                    playwright.expect(sensor.locator(".device-presence")).to_have_text(
                        "Presence: PRESENT"
                    )
                    playwright.expect(sensor.locator(".device-readiness")).to_have_text(
                        "Readiness · last reported: READY"
                    )
                    sensor.click(delay=150)
                    playwright.expect(sensor).to_have_attribute("aria-pressed", "true")
                    playwright.expect(page.locator(".command-panel > p")).to_have_text(
                        "to PATIENT_SENSOR"
                    )
                    for command, status in (
                        ("pause", "PAUSED"),
                        ("start", "ON"),
                        ("shutdown", "OFF"),
                    ):
                        button = page.locator(f".{command}-command")
                        if command == "start":
                            button.focus()
                            page.keyboard.down("Space")
                            page.wait_for_timeout(150)
                            page.keyboard.up("Space")
                        else:
                            button.click(delay=150)
                        playwright.expect(sensor.locator(".device-status")).to_have_text(status)
                    assert (
                        "Writing SHUTDOWN to PATIENT_SENSOR"
                        in page.locator("#activity-panel").inner_text()
                    )
                    assert sensor_process.wait(timeout=5) == 0
                    playwright.expect(sensor.locator(".device-presence")).to_have_text(
                        "Presence: OFFLINE", timeout=5000
                    )
                    playwright.expect(sensor.locator(".device-status")).to_have_text("OFF")
                    playwright.expect(sensor.locator(".device-readiness")).to_have_text(
                        "Readiness · last reported: NOT_READY"
                    )
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

                    def scene_snapshot():
                        # WebGL can present a cleared frame while changing views.
                        deadline = time.monotonic() + 5
                        while time.monotonic() < deadline:
                            image = canvas.screenshot()
                            visible_pixels = page.evaluate(
                                """async (png) => {
                                    const image = new Image();
                                    image.src = `data:image/png;base64,${png}`;
                                    await image.decode();
                                    const buffer = document.createElement('canvas');
                                    buffer.width = image.width; buffer.height = image.height;
                                    const context = buffer.getContext('2d');
                                    context.drawImage(image, 0, 0);
                                    const pixels = context.getImageData(
                                        0, 0, buffer.width, buffer.height
                                    ).data;
                                    let visible = 0;
                                    for (let i = 0; i < pixels.length; i += 4) {
                                        if ([0, 1, 2].some(channel =>
                                            Math.abs(pixels[i + channel] - pixels[channel]) > 8
                                        )) visible++;
                                    }
                                    return visible;
                                }""",
                                base64.b64encode(image).decode(),
                            )
                            if visible_pixels > 50:
                                return image
                            page.wait_for_timeout(50)
                        pytest.fail("Arm canvas did not present visible geometry within 5 seconds")

                    page.wait_for_timeout(300)
                    home = scene_snapshot()
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
                    assert scene_snapshot() != home
                    page.get_by_role("button", name="Reset camera", exact=True).click()
                    page.wait_for_timeout(300)
                    assert scene_snapshot() == home
                    for view in ("Side view", "Top view"):
                        page.get_by_role("button", name=view, exact=True).click()
                        page.wait_for_timeout(300)
                        preset = scene_snapshot()
                        assert preset != home
                        page.wait_for_timeout(600)
                        assert scene_snapshot() == preset
                        page.get_by_role("button", name="Reset camera", exact=True).click()
                        page.wait_for_timeout(300)
                        assert scene_snapshot() == home
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
                        panned = scene_snapshot()
                        assert panned != home
                        if pan_view is None:
                            pan_view = panned
                        else:
                            assert panned == pan_view
                        assert panel.locator(".feedback-value").all_inner_texts() == telemetry
                        page.get_by_role("button", name="Reset camera", exact=True).click()
                        page.wait_for_timeout(300)
                        assert scene_snapshot() == home
                    for delta in (-200, 200):
                        page.mouse.move(x, y)
                        page.mouse.down()
                        page.mouse.move(x + 80, y + 40, steps=8)
                        page.mouse.up()
                        page.mouse.wheel(0, delta)
                        page.wait_for_timeout(200)
                        adjusted = scene_snapshot()
                        page.get_by_role("button", name="Fit arm", exact=True).click()
                        page.wait_for_timeout(300)
                        assert scene_snapshot() != adjusted
                        page.get_by_role("button", name="Reset camera", exact=True).click()
                        page.wait_for_timeout(300)
                        assert scene_snapshot() == home
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
                    if app in ("Orchestrator", "ThreatInjector", "ThreatExfiltrator"):
                        toggle = page.locator("#activity-toggle")
                        bounds = toggle.bounding_box()
                        assert bounds
                        for x, y in (
                            (4, bounds["height"] / 2),
                            (bounds["width"] / 2, bounds["height"] / 2),
                            (bounds["width"] - 4, bounds["height"] / 2),
                        ):
                            was_visible = page.locator("#activity-panel").is_visible()
                            toggle.click(position={"x": x, "y": y}, delay=150)
                            playwright.expect(page.locator("#activity-panel")).to_be_visible(
                                visible=not was_visible
                            )
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
                    option = fallback.locator(".sdk-scene3d-list [role=option]").first
                    point = option.evaluate("""node => {
                        window.sceneOptionText = node.firstChild;
                        const range = document.createRange();
                        range.selectNodeContents(node);
                        const text = range.getBoundingClientRect();
                        const box = node.getBoundingClientRect();
                        return {x: text.x + text.width / 2 - box.x, y: box.height / 2};
                    }""")
                    option.click(position=point, delay=350)
                    assert fallback.evaluate("sceneOptionText.isConnected")
                    assert option.get_attribute("aria-selected") == "true"
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


@contextmanager
def _snapshot_page(browser_name="chromium"):
    """Exercise frontend reconciliation independently of DDS and SDK transport timing."""
    import playwright.sync_api as playwright

    with playwright.sync_playwright() as pw:
        browser_type = getattr(pw, browser_name)
        executable = Path(browser_type.executable_path)
        assert executable.is_file(), (
            f"Run `python -m playwright install --with-deps {browser_name}`"
        )
        browser = browser_type.launch(executable_path=str(executable), headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 950})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def serve(route):
            path = route.request.url.removeprefix("http://frontend.test/")
            if path == "sdk/client.js":
                route.fulfill(
                    content_type="text/javascript",
                    body="""export function createClient() {
                        window.commands = [];
                        return {
                            subscribe(render) {
                                window.updateUi = data => {
                                    window.uiData = data;
                                    render({data});
                                };
                            },
                            start() {},
                            async invokeCommand(command, payload) {
                                window.commands.push({command, payload});
                            },
                        };
                    }""",
                )
            elif path in ("", "app.js", "app.css"):
                route.fulfill(path=WEB_ROOT / (path or "index.html"))
            else:
                route.fulfill(status=404, body="")

        page.route("http://frontend.test/**", serve)
        try:
            page.goto("http://frontend.test/")
            page.wait_for_function("typeof window.updateUi === 'function'")
            yield page
            assert not errors
        finally:
            browser.close()


@pytest.fixture
def snapshot_page():
    with _snapshot_page() as page:
        yield page


@pytest.mark.browser
def test_header_security_mode_is_separate_from_app_status(snapshot_page):
    page = snapshot_page
    page.evaluate("""() => window.updateUi({
        kind: 'threat-exfiltrator',
        dds_security: true,
        header_badges: [{label: 'Access', value: 'NO ACCESS'}],
    })""")
    security = page.locator(".header-controls #header-security")
    assert security.get_attribute("aria-label") == "DDS Security enabled"
    assert page.locator("#header-badges").inner_text() == "Access\nNO ACCESS"
    assert not page.locator("#header-device").is_visible()
    page.evaluate("() => window.updateUi({...window.uiData, dds_security: null})")
    assert security.get_attribute("aria-label") == "DDS security status unavailable"


@pytest.mark.browser
def test_dds_topics_follow_participant_xml_and_stay_open_across_snapshots(snapshot_page):
    page = snapshot_page
    participants = ET.parse(PROJECT_ROOT / "system/model/ParticipantLibrary.xml")
    security_demo = ET.parse(
        PROJECT_ROOT / "modules/04-security-threat/xml_config/ThreatParticipants.xml"
    )
    for kind, library, participant_name in (
        ("arm", participants, "Arm"),
        ("arm-controller", participants, "ArmController"),
        ("gamepad-controller", participants, "ArmController"),
        ("orchestrator", participants, "Orchestrator"),
        ("patient-monitor", participants, "PatientMonitor"),
        ("threat-injector", security_demo, "ThreatInjector/Unsecure"),
        ("threat-exfiltrator", security_demo, "ThreatExfiltrator/Unsecure"),
    ):
        participant = library.find(f".//domain_participant[@name='dp/{participant_name}']")
        assert participant is not None
        expected = {
            (f"{arrow} {entity.attrib['topic_ref']}", direction)
            for tag, arrow, direction in (
                ("data_writer", "↑", "Publish"),
                ("data_reader", "↓", "Subscribe"),
            )
            for entity in participant.findall(f".//{tag}")
        }
        page.evaluate("kind => window.updateUi({kind})", kind)
        pane = page.locator(".app-header #dds-topics")
        summary = pane.locator("summary")
        assert not pane.evaluate("el => el.open")
        summary.focus()
        summary.press("Enter")
        assert pane.evaluate("el => el.open")
        rows = pane.locator("li").evaluate_all(
            """rows => rows.map(row => [
                [...row.children].map(c => c.textContent).join(' '),
                row.firstElementChild.getAttribute('aria-label'),
            ])"""
        )
        assert sorted(map(tuple, rows)) == sorted(expected)
        assert not pane.locator("p").count()
        page.evaluate("() => window.updateUi({...window.uiData, title: 'Updated'})")
        assert pane.evaluate("el => el.open")
        assert summary.evaluate("el => el === document.activeElement")


@pytest.mark.browser
@pytest.mark.parametrize("width", (1280, 390))
@pytest.mark.parametrize(
    ("kind", "primary_selector"),
    (
        ("arm", ".arm-scene-panel"),
        ("patient-monitor", ".vitals-grid"),
        ("arm-controller", ".actual-feedback"),
        ("gamepad-controller", ".actual-feedback"),
        ("orchestrator", ".command-panel"),
    ),
)
def test_dds_topics_do_not_resize_primary_view(snapshot_page, kind, primary_selector, width):
    page = snapshot_page
    page.set_viewport_size({"width": width, "height": 900})
    page.evaluate("kind => window.updateUi({kind, arm_feedback: {}})", kind)
    pane = page.locator(".app-header #dds-topics")
    primary = page.locator(primary_selector)
    document_rect = """el => {
        const {x, y, width, height} = el.getBoundingClientRect();
        return [x + scrollX, y + scrollY, width, height];
    }"""
    before = primary.evaluate(document_rect)
    pane.locator("summary").click()
    assert pane.evaluate("el => el.open")
    assert primary.evaluate(document_rect) == before
    panel = pane.locator(".dds-topic-panel").bounding_box()
    assert panel and 0 <= panel["x"] < panel["x"] + panel["width"] <= width
    colors = pane.locator(".dds-topic-arrow").evaluate_all(
        "arrows => [...new Set(arrows.map(arrow => getComputedStyle(arrow).color))]"
    )
    assert len(colors) == 2


@pytest.mark.browser
@pytest.mark.parametrize("kind", ("threat-injector", "threat-exfiltrator"))
def test_threat_controls_keep_pointer_targets_and_current_commands(snapshot_page, kind):
    page = snapshot_page
    page.evaluate(
        """kind => updateUi({
            kind, control_groups: [{controls: [
                {type: 'button', label: 'UNSECURE', command: 'select-mode',
                 payload: {mode: 'UNSECURE'}, className: 'mode-button'},
                {type: 'button', label: 'STOP ATTACK', command: 'stop-attack', disabled: true},
            ]}],
        })""",
        kind,
    )
    button = page.get_by_role("button", name="UNSECURE", exact=True)
    button.focus()
    button.evaluate("(node) => { window.modeButton = node; window.modeText = node.firstChild; }")
    bounds = button.bounding_box()
    page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
    page.mouse.down()
    page.evaluate("""() => {
        const controls = uiData.control_groups[0].controls;
        controls[0].className = 'mode-button selected';
        controls[0].label = 'UNSECURE ACTIVE';
        controls[1].disabled = false;
        updateUi(uiData);
    }""")
    page.wait_for_timeout(150)
    page.mouse.up()
    assert page.evaluate("""() => modeButton.isConnected
        && document.activeElement === modeButton && modeButton.firstChild === modeText""")
    page.wait_for_function("commands.length === 1")
    assert page.locator(".mode-button.selected").count() == 1
    assert page.evaluate("commands[0]") == {
        "command": "select-mode",
        "payload": {"mode": "UNSECURE"},
    }
    page.evaluate("""() => {
        uiData.control_groups[0].controls[0].payload = {mode: 'SECURE'};
        updateUi(uiData);
    }""")
    page.get_by_role("button", name="UNSECURE ACTIVE", exact=True).press("Space")
    page.wait_for_function("commands.length === 2")
    assert page.evaluate("commands[1].payload") == {"mode": "SECURE"}


@pytest.mark.browser
@pytest.mark.parametrize("control_type", ("hold", "dpad"))
def test_jog_survives_unrelated_updates_but_stops_when_disabled(snapshot_page, control_type):
    page = snapshot_page
    page.evaluate(
        """type => updateUi({
            kind: 'arm-controller', control_groups: [
                {controls: [{type, command: 'jog', label: 'X+', axis: 'X',
                             direction: 'POSITIVE', disabled: false}]},
                {layout: 'demo-controls', controls: [
                    {type: 'button', label: 'RUN DEMO', command: 'run-demo', disabled: true},
                ]},
            ],
        })""",
        control_type,
    )
    jog = page.get_by_role("button", name=re.compile(r"X\+"))
    jog.focus()
    jog.evaluate("(node) => { window.jogButton = node; }")
    page.keyboard.down("Space")
    page.evaluate("""() => {
        uiData.control_groups[1].controls[0].disabled = false;
        updateUi(uiData);
    }""")
    page.wait_for_timeout(450)
    assert page.evaluate("jogButton.isConnected && document.activeElement === jogButton")
    commands = page.evaluate("commands")
    assert len(commands) >= 3
    assert all(command["payload"]["direction"] == "POSITIVE" for command in commands)
    page.evaluate("""() => {
        uiData.control_groups[0].controls[0].disabled = true;
        updateUi(uiData);
    }""")
    page.wait_for_function("commands.at(-1)?.payload.direction === 'STOPPED'")
    assert jog.is_disabled()
    stopped_count = page.evaluate("commands.length")
    page.wait_for_timeout(300)
    page.keyboard.up("Space")
    assert page.evaluate("commands.length") == stopped_count


@pytest.mark.browser
def test_arm_motion_gate_control_updates_in_place_and_invokes_command(snapshot_page):
    page = snapshot_page
    page.evaluate(
        """() => updateUi({
            kind: 'arm',
            backend_label: 'KINOVA · SUPERVISED MOTION',
            control_groups: [{title: 'MOTION PERMISSION', layout: 'motion-gate', controls: [
                {type: 'button', label: 'RE-ARM MOTION', command: 'rearm-motion',
                 payload: {}, disabled: true, className: 'run-demo'},
            ]}],
        })"""
    )
    button = page.get_by_role("button", name="RE-ARM MOTION", exact=True)
    assert button.is_disabled()
    page.evaluate("""() => {
        uiData.control_groups[0].controls[0].disabled = false;
        updateUi(uiData);
    }""")
    button.focus()
    button.evaluate("(node) => { window.motionGateButton = node; }")
    page.evaluate("""() => {
        uiData.control_groups[0].controls[0].label = 'RE-ARM AVAILABLE';
        updateUi(uiData);
    }""")
    assert page.evaluate(
        "motionGateButton.isConnected && document.activeElement === motionGateButton"
    )
    available_button = page.get_by_role("button", name="RE-ARM AVAILABLE", exact=True)
    assert not available_button.is_disabled()
    available_button.click()
    page.wait_for_function("commands.length === 1")
    assert page.evaluate("commands[0]") == {
        "command": "rearm-motion",
        "payload": {},
    }

    page.evaluate("""() => {
        uiData.control_groups[0].controls[0].disabled = true;
        uiData.control_groups[0].controls[0].label = 'MOTION ARMED';
        updateUi(uiData);
    }""")
    armed_button = page.get_by_role("button", name="MOTION ARMED", exact=True)
    assert armed_button.is_disabled()
    assert page.evaluate("motionGateButton.isConnected")


@pytest.mark.browser
def test_frequency_edit_survives_snapshots_and_publishes_operator_value(snapshot_page):
    page = snapshot_page
    page.evaluate("""() => updateUi({
        kind: 'threat-injector', control_groups: [{controls: [
            {type: 'range', label: 'Inject Frequency (Hz)', unit: ' Hz',
             min: 1, max: 20, value: 5, command: 'set-frequency', parameter: 'frequency_hz'},
        ]}],
    })""")
    slider = page.locator('input[type="range"]')
    slider.focus()
    slider.evaluate("(node) => { window.frequencyInput = node; }")
    slider.press("ArrowRight")
    page.evaluate("updateUi(uiData)")
    assert slider.input_value() == "6"
    assert page.evaluate("frequencyInput.isConnected && document.activeElement === frequencyInput")
    slider.press("ArrowRight")
    page.wait_for_function("commands.length === 2")
    assert page.evaluate("commands.at(-1)") == {
        "command": "set-frequency",
        "payload": {"frequency_hz": 7},
    }
    slider.blur()
    page.evaluate("""() => {
        uiData.control_groups[0].controls[0].value = 7;
        updateUi(uiData);
    }""")
    assert page.locator(".range-value").inner_text() == "7 Hz"
    bounds = slider.bounding_box()
    page.mouse.move(bounds["x"] + bounds["width"] / 3, bounds["y"] + bounds["height"] / 2)
    page.mouse.down()
    page.mouse.move(bounds["x"] + bounds["width"] * 0.8, bounds["y"] + bounds["height"] / 2)
    edited_value = slider.input_value()
    assert int(edited_value) > 7
    page.evaluate("updateUi(uiData)")
    assert slider.input_value() == edited_value
    page.mouse.up()
    page.wait_for_function(
        "value => commands.at(-1)?.payload.frequency_hz === value",
        arg=int(edited_value),
    )


@pytest.mark.browser
def test_activity_preserves_rows_and_reading_position_while_following_tail(snapshot_page):
    page = snapshot_page
    page.evaluate("""() => updateUi({
        kind: 'orchestrator', logs: Array.from({length: 120}, (_, i) => ({
            time: '12:00', level: 'info', message: `Event ${i}`,
        })),
    })""")
    page.wait_for_function("""() => {
        const log = document.querySelector('.activity-log');
        return log.scrollTop > 0;
    }""")
    page.evaluate("""() => {
        window.logBody = document.querySelector('.activity-log');
        window.keptRow = logBody.children[60];
        logBody.scrollTop = keptRow.offsetTop - logBody.firstElementChild.offsetTop;
        window.rowOffset = keptRow.getBoundingClientRect().top;
        updateUi(uiData);
    }""")
    assert page.evaluate("logBody.isConnected && keptRow.isConnected")
    page.evaluate("""() => {
        uiData.logs.push({time: '12:01', level: 'info', message: 'New event'});
        updateUi(uiData);
    }""")
    assert page.evaluate("keptRow.isConnected")
    assert abs(page.evaluate("keptRow.getBoundingClientRect().top - rowOffset")) <= 1
    page.evaluate("""() => {
        logBody.scrollTop = logBody.scrollHeight;
        uiData.logs.push({time: '12:02', level: 'info', message: 'Latest event'});
        updateUi(uiData);
    }""")
    assert page.evaluate("logBody.scrollHeight - logBody.scrollTop - logBody.clientHeight") <= 1
    assert page.locator(".activity-entry").count() == 120


@pytest.mark.browser
def test_physical_monitors_do_not_show_simulated_motion_or_scene(snapshot_page):
    page = snapshot_page
    page.evaluate("""() => updateUi({
        kind: 'arm', scene_available: false, device_status: 'ON',
        feedback: {source: 'reported', readiness: 'NOT_READY', status_known: true},
    })""")
    assert page.locator(".arm-scene-panel").count() == 0
    assert "NOT_READY" in page.locator(".actual-feedback").inner_text()
    assert page.locator("[data-feedback='position'] .feedback-value").inner_text() == "---"
    assert page.locator("[data-feedback='opening_width'] .feedback-value").inner_text() == "---"
    page.evaluate("""() => updateUi({
        kind: 'gamepad-controller', input_connected: false, input_label: 'Falcon',
        control_instruction: 'Observe-only input; no arm or jaw commands are published.',
        inputs: [],
    })""")
    assert page.locator(".gamepad-instruction").inner_text() == (
        "Observe-only input; no arm or jaw commands are published."
    )
    assert "FALCON" in page.locator(".gamepad-connection").inner_text()
    assert "GAMEPAD" not in page.locator(".gamepad-connection").inner_text()
    page.evaluate("""() => updateUi({
        kind: 'gamepad-controller', input_connected: false,
        control_instruction: 'Waiting for fresh, ready arm feedback.',
        inputs: [],
    })""")
    assert page.locator(".gamepad-instruction").inner_text() == (
        "Waiting for fresh, ready arm feedback."
    )


@pytest.mark.browser
def test_gamepad_feedback_survives_input_and_connection_updates(snapshot_page):
    page = snapshot_page
    page.evaluate("""() => updateUi({
        kind: 'gamepad-controller', input_connected: false,
        inputs: [{label: 'RIGHT STICK', description: 'Move Z', active: false}],
    })""")
    page.evaluate("""() => {
        window.feedback = document.querySelector('.actual-feedback');
        window.inputRow = document.querySelector('.gamepad-input-row');
        uiData.input_connected = true;
        uiData.input_name = 'Test gamepad';
        uiData.inputs[0].active = true;
        uiData.inputs[0].description = 'Return to neutral';
        updateUi(uiData);
    }""")
    assert page.evaluate("feedback.isConnected && inputRow.isConnected")
    assert "Test gamepad CONNECTED" in page.locator(".gamepad-connection").inner_text()
    assert page.locator(".gamepad-input-label.active").count() == 1
    assert page.locator(".gamepad-input-description").inner_text() == "Return to neutral"
