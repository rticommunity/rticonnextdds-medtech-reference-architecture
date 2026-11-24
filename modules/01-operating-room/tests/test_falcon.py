#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

import asyncio
import json
import math
import os
import secrets
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
from module01_test_support import (
    MODULE_DIR,
    REPO_ROOT,
    invoke,
    local_ui_url,
    ui_data,
    wait_for_ui_data,
)

from tools.medtech import medtech_cli, module_runner

sys.path.insert(0, str(module_runner.platform_setup.generated_system_path() / "python"))

from ArmControllerFalcon import (  # noqa: E402
    MAX_ACCELERATION,
    MAX_SPEED,
    ZERO,
    ArmControllerFalconApp,
    FalconRelativeControl,
    workspace_bound,
)


def test_falcon_variant_is_explicitly_selected():
    manifest = module_runner.read_manifest(MODULE_DIR)
    selected = module_runner.select_apps(
        manifest, {"ArmController": "falcon"}, None, MODULE_DIR.name
    )
    assert selected["ArmController"] == ["${PYTHON:ArmControllerFalcon}"]
    assert medtech_cli.capabilities([selected["ArmController"]], "browser") == set()


def test_kortex_variant_is_explicitly_selected():
    manifest = module_runner.read_manifest(MODULE_DIR)
    selected = module_runner.select_apps(manifest, {"Arm": "kortex"}, None, MODULE_DIR.name)
    assert selected["Arm"] == ["${PYTHON:ArmKortex}"]
    assert medtech_cli.capabilities([selected["Arm"]], "browser") == {"arm"}


@pytest.mark.parametrize(
    ("module", "app", "forbidden"),
    [
        ("ArmKortex", "ArmKortexApp", ("Arm", "ArmKinematics", "mujoco", "mink")),
        ("ArmControllerFalcon", "ArmControllerFalconApp", ("ArmControllerGamepad", "pygame")),
    ],
)
def test_hardware_apps_import_without_simulated_app(module, app, forbidden):
    env, _ = module_runner.load_module_config(MODULE_DIR, flags={"security": False})
    env["PYTHONPATH"] = str(MODULE_DIR / "src") + os.pathsep + env["PYTHONPATH"]
    code = (
        "import importlib, sys; "
        f"module = importlib.import_module({module!r}); "
        f"assert getattr(module, {app!r}).__bases__ == (object,); "
        f"assert not set({forbidden!r}) & sys.modules.keys()"
    )
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_relative_control_requires_release_and_limits_speed_and_acceleration():
    control = FalconRelativeControl((-0.25, -0.25, 0.1), (0.25, 0.25, 0.6))
    arm = (0.0, 0.0, 0.3)
    assert control.update(ZERO, 1, arm, True, 1.0) == ZERO
    assert control.update(ZERO, 0, arm, True, 1.02) == ZERO
    assert control.update((0.01, 0.0, 0.0), 1, arm, True, 1.04) == ZERO
    velocity = control.update((0.03, 0.02, 0.0), 1, arm, True, 1.06)
    assert velocity[0] > 0 and velocity[1] > 0
    assert math.hypot(*velocity) <= MAX_ACCELERATION * 0.02 + 1e-12
    for i in range(1, 200):
        velocity = control.update((0.1, 0.1, 0.0), 1, arm, True, 1.06 + i * 0.02)
        assert math.hypot(*velocity) <= MAX_SPEED + 1e-12
    assert control.update((0.1, 0.1, 0.0), 0, arm, True, 5.1) == ZERO
    assert control.update((0.1, 0.1, 0.0), 1, arm, True, 5.12) == ZERO


@pytest.mark.parametrize("reason", ["feedback", "gap", "nonfinite", "outside"])
def test_inhibit_requires_release_before_recapturing_reference(reason):
    control = FalconRelativeControl((-0.25, -0.25, 0.1), (0.25, 0.25, 0.6))
    arm = (0.0, 0.0, 0.3)
    control.update(ZERO, 0, arm, True, 1.0)
    control.update(ZERO, 1, arm, True, 1.02)
    assert control.update((0.02, 0.0, 0.0), 1, arm, True, 1.04)[0] > 0
    if reason == "feedback":
        assert control.update(ZERO, 1, None, False, 1.06) == ZERO
    elif reason == "gap":
        assert control.update(ZERO, 1, arm, True, 2.0) == ZERO
    elif reason == "nonfinite":
        assert control.update((math.nan, 0.0, 0.0), 1, arm, True, 1.06) == ZERO
    else:
        control.reset()
        control.update(ZERO, 0, arm, True, 1.06)
        assert control.update(ZERO, 1, (0.3, 0.0, 0.3), True, 1.08) == ZERO
    assert control.update(ZERO, 1, arm, True, 2.02) == ZERO
    assert control.update(ZERO, 0, arm, True, 2.04) == ZERO
    assert control.update(ZERO, 1, arm, True, 2.06) == ZERO
    assert control.update((0.01, 0.0, 0.0), 1, arm, True, 2.08)[0] > 0


def test_workspace_configuration_rejects_bad_values(monkeypatch):
    monkeypatch.setenv("FALCON_WORKSPACE_MAX", "0.5, 0.25, 0.6")
    assert workspace_bound("FALCON_WORKSPACE_MAX", ZERO) == (0.5, 0.25, 0.6)
    monkeypatch.setenv("FALCON_WORKSPACE_MAX", "nan, 1, 2")
    with pytest.raises(ValueError, match="finite"):
        workspace_bound("FALCON_WORKSPACE_MAX", ZERO)
    with pytest.raises(ValueError, match="ordered"):
        FalconRelativeControl((0.0, 0.0, 0.0), (0.0, 1.0, 1.0))


def test_relative_control_moves_simulated_arm_with_appropriate_workspace():
    from ArmKinematics import ArmModel

    model = ArmModel()
    initial = model.pose["position"]
    control = FalconRelativeControl((-0.25, -0.25, 0.1), (0.5, 0.25, 0.6))
    control.update(ZERO, 0, initial, True, 1.0)
    control.update(ZERO, 1, initial, True, 1.02)
    for i in range(1, 151):
        velocity = control.update(
            (0.01, 0.0, 0.0), 1, model.pose["position"], True, 1.02 + i * 0.02
        )
        model.step(velocity, ZERO, 0.0, 0.02)
    assert model.pose["position"][0] > initial[0] + 0.004


def local_dds_env(tmp_path, variants):
    env, apps = module_runner.load_module_config(
        MODULE_DIR,
        flags={"security": False},
        variants=variants,
    )
    qos_path = REPO_ROOT / "system/qos/Qos.xml"
    domain_path = REPO_ROOT / "system/model/DomainLibrary.xml"
    qos = qos_path.read_text()
    original = "<transport_builtin>\n            <shmem>"
    assert original in qos
    qos = qos.replace(
        original, "<transport_builtin>\n            <mask>SHMEM</mask>\n            <shmem>", 1
    )
    domain = domain_path.read_text().replace(
        'domain_id="0"', f'domain_id="{60 + secrets.randbelow(120)}"'
    )
    local_qos, local_domain = tmp_path / "qos.xml", tmp_path / "domain.xml"
    local_qos.write_text(qos)
    local_domain.write_text(domain)
    env["NDDS_QOS_PROFILES"] = (
        env["NDDS_QOS_PROFILES"]
        .replace(str(qos_path), str(local_qos))
        .replace(str(domain_path), str(local_domain))
    )
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env["PYTHONPATH"]
    return env, apps


def local_dds_utility(tmp_path):
    import rti.connextdds as dds
    from test_utils import UtilityApp, make_isolated_qos_provider

    provider = make_isolated_qos_provider(
        str(module_runner.platform_setup.generated_system_path() / "xml" / "MedTech.xml"),
        str(tmp_path / "qos.xml"),
        str(REPO_ROOT / "system/qos/NonSecureAppsQos.xml"),
        str(tmp_path / "domain.xml"),
        str(REPO_ROOT / "system/model/ParticipantLibrary.xml"),
    )
    domain_id = int(
        (tmp_path / "domain.xml").read_text().split('domain_id="', 1)[1].split('"', 1)[0]
    )
    participant = dds.DomainParticipant(
        domain_id, provider.participant_qos_from_profile("DpQosLib::Test")
    )
    participant.enable()
    return UtilityApp(qos_provider=provider, participant=participant)


def fake_falcon(tmp_path):
    state = tmp_path / "input-state"

    def set_input(value):
        pending = tmp_path / "next-input-state"
        pending.write_text(value)
        pending.replace(state)

    set_input("released")
    (tmp_path / "pynifalcon.py").write_text(
        """
import os
from pathlib import Path
from types import SimpleNamespace

class FalconDeviceBridge:
    def getCount(self):
        return int(Path(os.environ["TEST_FALCON_STATE"]).read_text() != "absent")
    def open(self, index):
        return index == 0 and self.getCount() > 0
    def loadFirmware(self):
        return True
    def setHomingMode(self, enabled):
        pass
    def runIOLoop(self, flags):
        return True
    def isHomed(self):
        return Path(os.environ["TEST_FALCON_STATE"]).read_text() != "unhomed"
    def getPosition(self):
        moving = Path(os.environ["TEST_FALCON_STATE"]).read_text() == "move"
        return SimpleNamespace(x=0.02 if moving else 0.0, y=0.0, z=0.0)
    def getButtons(self):
        return int(Path(os.environ["TEST_FALCON_STATE"]).read_text() != "released")
    def close(self):
        pass
"""
    )
    return state, set_input


@pytest.mark.browser
def test_falcon_waits_for_device_and_connects_when_attached(tmp_path):
    import playwright.sync_api as playwright
    from MedTech import Device
    from test_utils import ProcessManager, wait_for_samples

    state, set_input = fake_falcon(tmp_path)
    set_input("absent")
    env, apps = local_dds_env(tmp_path, {"ArmController": "falcon"})
    env["TEST_FALCON_STATE"] = str(state)
    utility = local_dds_utility(tmp_path)
    manager = ProcessManager(env, apps, cwd=MODULE_DIR)
    try:
        controller = manager.start_app_ready("ArmController")
        url = local_ui_url(controller, "Novint Falcon Controller listening on")
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url)
                playwright.expect(page.locator(".gamepad-connection")).to_contain_text(
                    "NO FALCON DETECTED"
                )
                button = page.get_by_role("button", name="HOME FALCON")
                playwright.expect(button).to_be_disabled()
                statuses = wait_for_samples(
                    utility.device_status.reader,
                    filter_fn=lambda sample: sample.device == Device.DeviceType.ARM_CONTROLLER,
                )
                assert statuses[-1].readiness == Device.DeviceReadinessKind.NOT_READY
                commands = wait_for_samples(utility.teleop_control.reader)
                assert commands
                assert (
                    commands[-1].linear_velocity.x,
                    commands[-1].linear_velocity.y,
                    commands[-1].linear_velocity.z,
                ) == (0.0, 0.0, 0.0)
                assert (
                    commands[-1].angular_velocity.x,
                    commands[-1].angular_velocity.y,
                    commands[-1].angular_velocity.z,
                ) == (0.0, 0.0, 0.0)
                jaw_commands = wait_for_samples(utility.tool_control.reader)
                assert jaw_commands and jaw_commands[-1].opening_rate == 0.0
                set_input("unhomed")
                playwright.expect(button).to_be_enabled(timeout=10000)
                playwright.expect(page.locator(".gamepad-connection")).to_contain_text(
                    "WAITING FOR HOMING"
                )
                assert controller.poll() is None
            finally:
                browser.close()
    finally:
        manager.shutdown_all()
        utility.close()


def test_falcon_missing_bridge_is_a_startup_error(tmp_path):
    from test_utils import ProcessManager

    (tmp_path / "pynifalcon.py").write_text("raise ImportError('test missing dependency')\n")
    env, apps = local_dds_env(tmp_path, {"ArmController": "falcon"})
    manager = ProcessManager(env, apps, cwd=MODULE_DIR)
    try:
        controller = manager.start_app("ArmController")
        _, stderr = controller.communicate(timeout=10)
        assert controller.returncode != 0
        assert b"Falcon requires the compatible pynifalcon bridge" in stderr
        assert b"KeyError: 'master'" not in stderr
    finally:
        manager.shutdown_all()


@pytest.mark.browser
def test_falcon_ui_homes_explicitly_and_publishes_neutral(tmp_path):
    import playwright.sync_api as playwright
    from MedTech import Device
    from test_utils import ProcessManager, wait_for_samples

    state, set_input = fake_falcon(tmp_path)
    set_input("unhomed")
    env, apps = local_dds_env(tmp_path, {"ArmController": "falcon"})
    env["TEST_FALCON_STATE"] = str(state)
    utility = local_dds_utility(tmp_path)
    manager = ProcessManager(env, apps, cwd=MODULE_DIR)
    try:
        controller = manager.start_app_ready("ArmController")
        url = local_ui_url(controller, "Novint Falcon Controller listening on")
        with playwright.sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url)
                button = page.get_by_role("button", name="HOME FALCON")
                playwright.expect(button).to_be_enabled(timeout=10000)
                playwright.expect(page.locator(".gamepad-connection")).to_contain_text(
                    "WAITING FOR HOMING"
                )
                statuses = wait_for_samples(
                    utility.device_status.reader,
                    filter_fn=lambda sample: sample.device == Device.DeviceType.ARM_CONTROLLER,
                )
                assert statuses[-1].readiness == Device.DeviceReadinessKind.NOT_READY
                commands = wait_for_samples(utility.teleop_control.reader)
                assert commands
                assert commands[-1].linear_velocity.x == 0
                assert commands[-1].linear_velocity.y == 0
                assert commands[-1].linear_velocity.z == 0
                button.click()
                playwright.expect(page.locator(".gamepad-connection")).to_contain_text("HOMING")
                playwright.expect(button).to_be_disabled()
                assert not invoke(url, "home-falcon", {})["result"]["started"]
                playwright.expect(page.locator(".gamepad-instruction")).to_contain_text("fully out")
                commands = wait_for_samples(utility.teleop_control.reader)
                assert commands and commands[-1].linear_velocity.x == 0
                set_input("released")
                playwright.expect(page.locator(".gamepad-connection")).to_contain_text("CONNECTED")
                playwright.expect(button).to_be_disabled()
                statuses = wait_for_samples(
                    utility.device_status.reader,
                    filter_fn=lambda sample: (
                        sample.device == Device.DeviceType.ARM_CONTROLLER
                        and sample.readiness == Device.DeviceReadinessKind.READY
                    ),
                )
                assert statuses
            finally:
                browser.close()
    finally:
        manager.shutdown_all()
        utility.close()


@pytest.mark.parametrize("variant", ["simulated", "xbox", "falcon"])
def test_controller_reports_independent_command_subscriber_matches(tmp_path, variant):
    from test_utils import ProcessManager

    variants = {} if variant == "simulated" else {"ArmController": variant}
    env, apps = local_dds_env(tmp_path, variants)
    if variant == "falcon":
        state, _ = fake_falcon(tmp_path)
        env["TEST_FALCON_STATE"] = str(state)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    utility = local_dds_utility(tmp_path)
    manager = ProcessManager(env, apps, cwd=MODULE_DIR)
    try:
        controller = manager.start_app_ready("ArmController")
        title = {
            "simulated": "Arm Controller listening on",
            "xbox": "Xbox Arm Controller listening on",
            "falcon": "Novint Falcon Controller listening on",
        }[variant]
        url = local_ui_url(controller, title)

        def badges(arm, jaw):
            def matches(data):
                values = {badge["label"]: badge["value"] for badge in data["header_badges"]}
                return (
                    values.get("Arm command subscribers") == arm
                    and values.get("Jaw command subscribers") == jaw
                )

            return matches

        wait_for_ui_data(url, badges("NO MATCH", "NO MATCH"))
        arm_reader = utility.teleop_control.reader
        wait_for_ui_data(url, badges("MATCHED", "NO MATCH"))
        jaw_reader = utility.tool_control.reader
        wait_for_ui_data(url, badges("MATCHED", "MATCHED"))
        arm_reader.close()
        wait_for_ui_data(url, badges("NO MATCH", "MATCHED"))
        jaw_reader.close()
        wait_for_ui_data(url, badges("NO MATCH", "NO MATCH"))
    finally:
        manager.shutdown_all()
        utility.close()


def test_falcon_with_simulated_arm_over_local_only_dds(tmp_path):
    from test_utils import ProcessManager

    state, set_input = fake_falcon(tmp_path)
    env, apps = local_dds_env(tmp_path, {"ArmController": "falcon"})
    env["TEST_FALCON_STATE"] = str(state)
    env["FALCON_WORKSPACE_MAX"] = "0.5,0.25,0.6"
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    manager = ProcessManager(env, apps, cwd=MODULE_DIR)
    try:
        arm = manager.start_app_ready("Arm")
        arm_url = local_ui_url(arm, "Surgical Arm Monitor listening on")
        initial = wait_for_ui_data(
            arm_url, lambda data: data.get("feedback", {}).get("position") is not None
        )["feedback"]["position"][0]
        controller = manager.start_app_ready("ArmController")
        controller_url = local_ui_url(controller, "Novint Falcon Controller listening on")
        wait_for_ui_data(
            controller_url,
            lambda data: data.get("control_instruction", "").startswith("Hold button 1"),
            timeout=10,
        )
        set_input("held")
        wait_for_ui_data(
            controller_url,
            lambda data: data.get("control_instruction", "").startswith("Translation active"),
        )
        set_input("move")
        wait_for_ui_data(
            arm_url,
            lambda data: data["feedback"]["position"][0] > initial + 0.001,
            timeout=8,
        )
        set_input("released")
        wait_for_ui_data(
            controller_url,
            lambda data: data.get("control_instruction", "").startswith("Hold button 1"),
        )
        time.sleep(0.8)
        settled = ui_data(arm_url)["feedback"]["position"]
        time.sleep(0.3)
        held = ui_data(arm_url)["feedback"]["position"]
        assert math.dist(held, settled) < 0.0002
    finally:
        manager.shutdown_all()


def fake_kinova(tmp_path):
    stub = tmp_path / "run_fake_kinova.py"
    stub.write_text(
        """
import json
import os
import ArmKortex as motion

class Driver:
    def open(self):
        pass
    def read_health(self):
        return motion.KortexHealth(7, 2, 0, 0, True, False)
    def read_pose(self):
        return ((0.1, 0.0, 0.3), (0.0, 0.0, 0.0, 1.0))
    def send_twist(self, linear, angular):
        with open(os.environ["TEST_KINOVA_TWISTS"], "a") as output:
            output.write(json.dumps([linear, angular]) + "\\n")
    def stop(self):
        with open(os.environ["TEST_KINOVA_TWISTS"], "a") as output:
            output.write(json.dumps([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]) + "\\n")
    def close(self):
        pass

motion.KortexDriver = Driver
raise SystemExit(motion.main())
"""
    )
    return stub


def wait_for_twist(path, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists():
            commands = [json.loads(line) for line in path.read_text().splitlines()]
            if commands and predicate(commands[-1]):
                return commands[-1]
        time.sleep(0.02)
    raise AssertionError("Expected Kinova command not observed")


def test_virtual_controller_commands_mock_kinova_over_local_only_dds(tmp_path):
    from test_utils import ProcessManager

    stub = fake_kinova(tmp_path)
    env, apps = local_dds_env(tmp_path, {"Arm": "kortex"})
    twists = tmp_path / "twists.jsonl"
    env["PYTHONPATH"] += os.pathsep + str(MODULE_DIR / "src")
    env["TEST_KINOVA_TWISTS"] = str(twists)
    env["KORTEX_LIVE_WATCHDOG"] = "VERIFIED_KORTEX_CONNECTION_TIMEOUT_STOP"
    apps["Arm"] = [sys.executable, str(stub)]
    manager = ProcessManager(env, apps, cwd=MODULE_DIR)
    try:
        arm = manager.start_app_ready("Arm")
        arm_url = local_ui_url(arm, "Kinova Gen3 Kortex Arm listening on")
        controller = manager.start_app_ready("ArmController")
        controller_url = local_ui_url(controller, "Arm Controller listening on")
        wait_for_ui_data(
            controller_url,
            lambda data: (
                {badge["label"]: badge["value"] for badge in data["header_badges"]}.items()
                >= {
                    "Arm command subscribers": "MATCHED",
                    "Jaw command subscribers": "NO MATCH",
                }.items()
            ),
        )
        wait_for_ui_data(
            arm_url,
            lambda data: not data["control_groups"][0]["controls"][0]["disabled"],
            timeout=10,
        )
        assert invoke(arm_url, "rearm-motion", {})["result"]["armed"]
        wait_for_ui_data(arm_url, lambda data: data["feedback"]["readiness"] == "READY")
        assert invoke(controller_url, "teleop", {"axis": "X", "direction": "POSITIVE"})["ok"]
        wait_for_twist(twists, lambda command: command[0][0] > 0)
        assert invoke(controller_url, "teleop", {"axis": "X", "direction": "STOPPED"})["ok"]
        wait_for_twist(twists, lambda command: command == [[0.0] * 3, [0.0] * 3])
    finally:
        manager.shutdown_all()


def test_kortex_rearms_with_arm_only_stream_and_stops_on_its_loss(tmp_path):
    from MedTech import Geometry, Robot
    from test_utils import ProcessManager, wait_for_writer_match

    stub = fake_kinova(tmp_path)
    env, apps = local_dds_env(tmp_path, {"Arm": "kortex"})
    twists = tmp_path / "twists.jsonl"
    env["PYTHONPATH"] += os.pathsep + str(MODULE_DIR / "src")
    env["TEST_KINOVA_TWISTS"] = str(twists)
    env["KORTEX_LIVE_WATCHDOG"] = "VERIFIED_KORTEX_CONNECTION_TIMEOUT_STOP"
    apps["Arm"] = [sys.executable, str(stub)]
    utility = local_dds_utility(tmp_path)
    writer = utility.teleop_control.writer
    manager = ProcessManager(env, apps, cwd=MODULE_DIR)

    async def exercise(url):
        linear_x = [0.0]
        publishing = [True]

        async def publish():
            while True:
                if publishing[0]:
                    writer.write(
                        Robot.Arm.TeleopControl(
                            arm_id="arm-1",
                            linear_velocity=Geometry.Vector3(x=linear_x[0]),
                        )
                    )
                await asyncio.sleep(0.01)

        publisher = asyncio.create_task(publish())
        try:
            await asyncio.to_thread(
                wait_for_ui_data,
                url,
                lambda data: not data["control_groups"][0]["controls"][0]["disabled"],
            )
            result = await asyncio.to_thread(invoke, url, "rearm-motion", {})
            assert result["result"]["armed"]
            await asyncio.to_thread(
                wait_for_ui_data, url, lambda data: data["feedback"]["readiness"] == "READY"
            )
            jaw_writer = utility.tool_control.writer
            jaw_writer.write(Robot.Tool.ParallelJawControl(arm_id="arm-1", opening_rate=0.01))
            linear_x[0] = 0.001
            await asyncio.to_thread(wait_for_twist, twists, lambda command: command[0][0] > 0)
            await asyncio.sleep(0.15)
            assert jaw_writer.publication_matched_status.current_count == 0
            assert (await asyncio.to_thread(ui_data, url))["feedback"]["readiness"] == "READY"
            publishing[0] = False
            await asyncio.to_thread(
                wait_for_ui_data,
                url,
                lambda data: data["feedback"]["readiness"] == "NOT_READY",
            )
            await asyncio.to_thread(
                wait_for_twist, twists, lambda command: command == [[0.0] * 3, [0.0] * 3]
            )
            publishing[0] = True
            await asyncio.sleep(0.15)
            data = await asyncio.to_thread(ui_data, url)
            assert data["feedback"]["readiness"] == "NOT_READY"
            assert data["control_groups"][0]["controls"][0]["disabled"]
            linear_x[0] = 0.0
            await asyncio.to_thread(
                wait_for_ui_data,
                url,
                lambda data: not data["control_groups"][0]["controls"][0]["disabled"],
            )
            assert (await asyncio.to_thread(ui_data, url))["feedback"]["readiness"] == "NOT_READY"
        finally:
            publisher.cancel()
            with pytest.raises(asyncio.CancelledError):
                await publisher

    try:
        arm = manager.start_app_ready("Arm")
        url = local_ui_url(arm, "Kinova Gen3 Kortex Arm listening on")
        assert wait_for_writer_match(writer)
        asyncio.run(exercise(url))
    finally:
        manager.shutdown_all()
        utility.close()


def test_mock_falcon_commands_mock_kinova_over_local_only_dds(tmp_path):
    from test_utils import ProcessManager

    state, set_input = fake_falcon(tmp_path)
    stub = fake_kinova(tmp_path)
    env, apps = local_dds_env(tmp_path, {"Arm": "kortex", "ArmController": "falcon"})
    twists = tmp_path / "twists.jsonl"
    env["PYTHONPATH"] += os.pathsep + str(MODULE_DIR / "src")
    env["TEST_KINOVA_TWISTS"] = str(twists)
    env["TEST_FALCON_STATE"] = str(state)
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    env["KORTEX_LIVE_WATCHDOG"] = "VERIFIED_KORTEX_CONNECTION_TIMEOUT_STOP"
    apps["Arm"] = [sys.executable, str(stub)]
    manager = ProcessManager(env, apps, cwd=MODULE_DIR)
    try:
        arm = manager.start_app_ready("Arm")
        arm_url = local_ui_url(arm, "Kinova Gen3 Kortex Arm listening on")
        controller = manager.start_app_ready("ArmController")
        controller_url = local_ui_url(controller, "Novint Falcon Controller listening on")
        wait_for_ui_data(
            arm_url,
            lambda data: not data["control_groups"][0]["controls"][0]["disabled"],
            timeout=10,
        )
        assert invoke(arm_url, "rearm-motion", {})["result"]["armed"]
        wait_for_ui_data(
            controller_url,
            lambda data: data.get("control_instruction", "").startswith("Hold button 1"),
        )
        set_input("held")
        wait_for_ui_data(
            controller_url,
            lambda data: data.get("control_instruction", "").startswith("Translation active"),
        )
        set_input("move")
        wait_for_twist(twists, lambda command: command[0][0] > 0)
        set_input("released")
        wait_for_twist(twists, lambda command: command == [[0.0] * 3, [0.0] * 3])
    finally:
        manager.shutdown_all()


def test_controller_publishes_neutral_and_disarms_on_lost_input_or_pause(monkeypatch):
    import ArmControllerFalcon as falcon
    from MedTech import Device

    now = [1.0]
    monkeypatch.setattr(falcon.time, "monotonic", lambda: now[0])
    samples = [
        ((0.0, 0.0, 0.0), 0),
        ((0.0, 0.0, 0.0), 1),
        ((0.02, 0.0, 0.0), 1),
        None,
        ((0.0, 0.0, 0.0), 0),
        ((0.0, 0.0, 0.0), 1),
        ((0.02, 0.0, 0.0), 1),
        ((0.02, 0.0, 0.0), 1),
    ]
    app = ArmControllerFalconApp.__new__(ArmControllerFalconApp)
    app.control = FalconRelativeControl((-0.25, -0.25, 0.1), (0.25, 0.25, 0.6))
    app.last_input = None
    assert dict(app._input_descriptions()) == {
        "POSITION": "Waiting for input",
        "BUTTONS": "Waiting for input",
    }
    app.input_device = SimpleNamespace(read=lambda: samples.pop(0))
    app.status = Device.DeviceStatusKind.ON
    app.has_arm_status = True
    app.last_arm_readiness = "READY"
    app.last_telemetry = {"tcp_pose": {"position": {"x": 0.0, "y": 0.0, "z": 0.3}}}
    app.last_telemetry_time = 1.0
    reader = SimpleNamespace(subscription_matched_status=SimpleNamespace(current_count=1))
    app.arm_status_reader = reader
    app.arm_telemetry_reader = reader
    app.active_inputs = {"POSITION": False, "BUTTONS": False}
    arm_writes, jaw_writes = [], []
    app.teleop_writer = SimpleNamespace(write=arm_writes.append)
    app.tool_writer = SimpleNamespace(write=jaw_writes.append)
    app.ui = SimpleNamespace(update=lambda **_: None)
    app.view = lambda: {}
    app.write_status = lambda _: None

    for _ in range(3):
        rates, _ = app.read_controls()
        app.publish_rates(rates)
        now[0] += 0.02
    assert arm_writes[-1].linear_velocity.x > 0
    assert arm_writes[-1].angular_velocity.x == 0
    assert all(sample.opening_rate == 0 for sample in jaw_writes)
    descriptions = dict(app._input_descriptions())
    assert descriptions["POSITION"] == "X 0.0200, Y 0.0000, Z 0.0000 m"
    assert descriptions["BUTTONS"] == "Bitfield: 0x1 · button 1 is deadman"
    rates, _ = app.read_controls()
    app.publish_rates(rates)
    assert arm_writes[-1].linear_velocity.x == 0
    assert app.control.require_release
    assert dict(app._input_descriptions()) == descriptions
    for _ in range(3):
        now[0] += 0.02
        rates, _ = app.read_controls()
        app.publish_rates(rates)
    assert arm_writes[-1].linear_velocity.x > 0
    app.set_status(Device.DeviceStatusKind.PAUSED)
    assert arm_writes[-1].linear_velocity.x == 0
    app.set_status(Device.DeviceStatusKind.ON)
    assert app.control.require_release
    now[0] += 0.02
    rates, _ = app.read_controls()
    assert rates == app.zero_rates()


def test_repeated_start_requires_falcon_deadman_release():
    from MedTech import Device

    app = ArmControllerFalconApp.__new__(ArmControllerFalconApp)
    app.control = FalconRelativeControl((-0.25, -0.25, 0.1), (0.25, 0.25, 0.6))
    arm = (0.0, 0.0, 0.3)
    app.control.update(ZERO, 0, arm, True, 1.0)
    app.control.update(ZERO, 1, arm, True, 1.02)
    assert app.control.update((0.02, 0.0, 0.0), 1, arm, True, 1.04)[0] > 0
    app.status = Device.DeviceStatusKind.ON
    app.rates = app.zero_rates()
    arm_writes = []
    app.teleop_writer = SimpleNamespace(write=arm_writes.append)
    app.tool_writer = SimpleNamespace(write=lambda _: None)
    app.ui = SimpleNamespace(update=lambda **_: None, log=lambda *_: None)
    app.view = lambda: {}

    async def commands():
        yield SimpleNamespace(command=Device.DeviceCommandKind.START)

    app.command_reader = SimpleNamespace(take_data_async=commands)
    asyncio.run(app.receive_commands())

    assert app.control.require_release
    assert arm_writes[-1].linear_velocity.x == 0.0
    assert app.control.update((0.02, 0.0, 0.0), 1, arm, True, 1.06) == ZERO
    assert app.control.update((0.02, 0.0, 0.0), 0, arm, True, 1.08) == ZERO
    assert app.control.update((0.02, 0.0, 0.0), 1, arm, True, 1.10) == ZERO
    assert app.control.update((0.04, 0.0, 0.0), 1, arm, True, 1.12)[0] > 0


def test_telemetry_uses_processing_time_without_sample_metadata(monkeypatch):
    import ArmControllerFalcon as falcon
    from MedTech import Geometry, Robot

    monkeypatch.setattr(falcon.time, "monotonic", lambda: 100.0)
    sample = Robot.Arm.Telemetry(
        arm_id="arm-1",
        tcp_pose=Geometry.Pose(position=Geometry.Vector3(x=0.1)),
        parallel_jaw=None,
    )

    async def samples():
        yield sample

    app = ArmControllerFalconApp.__new__(ArmControllerFalconApp)
    app.control = FalconRelativeControl((-0.25, -0.25, 0.1), (0.25, 0.25, 0.6))
    app.arm_telemetry_reader = SimpleNamespace(take_data_async=samples)
    app.ui = SimpleNamespace(update=lambda **_: None)
    app.view = lambda: {}
    asyncio.run(app.receive_arm_telemetry())
    assert app.last_telemetry_time == 100.0
    assert app.last_telemetry["tcp_pose"]["position"]["x"] == pytest.approx(0.1)


@pytest.mark.parametrize("status_alive,telemetry_writers", [(False, 1), (True, 0), (True, 2)])
def test_ambiguous_or_missing_arm_feedback_disarms(monkeypatch, status_alive, telemetry_writers):
    import ArmControllerFalcon as falcon
    from MedTech import Device

    monkeypatch.setattr(falcon.time, "monotonic", lambda: 1.06)
    app = ArmControllerFalconApp.__new__(ArmControllerFalconApp)
    app.control = FalconRelativeControl((-0.25, -0.25, 0.1), (0.25, 0.25, 0.6))
    arm = (0.0, 0.0, 0.3)
    app.control.update(ZERO, 0, arm, True, 1.0)
    app.control.update(ZERO, 1, arm, True, 1.02)
    app.input_device = SimpleNamespace(read=lambda: ((0.02, 0.0, 0.0), 1))
    app.status = Device.DeviceStatusKind.ON
    app.has_arm_status = status_alive
    app.last_arm_readiness = "READY"
    app.last_telemetry = {"tcp_pose": {"position": dict(zip("xyz", arm))}}
    app.last_telemetry_time = 1.04
    app.arm_telemetry_reader = SimpleNamespace(
        subscription_matched_status=SimpleNamespace(current_count=telemetry_writers)
    )
    rates, _ = app.read_controls()
    assert rates == app.zero_rates()
    assert app.control.require_release


def test_falcon_tracks_arm_status_instance_with_other_device_writers(nonsecure_utility_app):
    import rti.connextdds as dds
    from MedTech import Device
    from test_utils import UtilityApp, wait_for_writer_match

    observer = nonsecure_utility_app
    other_writer = observer.device_status.writer
    cft = dds.ContentFilteredTopic(
        observer.device_status.topic, "falcon-arm-status-test", dds.Filter("device = 'ARM'")
    )
    reader = dds.DataReader(
        cft, observer.qos_provider.datareader_qos_from_profile("DataFlowLibrary::Status")
    )
    app = ArmControllerFalconApp.__new__(ArmControllerFalconApp)
    app.arm_status_reader = reader
    app.has_arm_status = False
    app._arm_status_handle = None
    app.last_arm_readiness = "NOT_READY"
    app.ui = SimpleNamespace(update=lambda **_: None)
    app.view = lambda: {}

    async def exercise():
        task = asyncio.create_task(app.receive_arm_status())
        try:
            with UtilityApp.make_non_secure() as arm:
                writer = arm.device_status.writer
                assert await asyncio.to_thread(wait_for_writer_match, writer)
                assert await asyncio.to_thread(wait_for_writer_match, other_writer)
                other_writer.write(Device.Status(device=Device.DeviceType.PATIENT_SENSOR))
                writer.write(
                    Device.Status(
                        device=Device.DeviceType.ARM,
                        readiness=Device.DeviceReadinessKind.READY,
                    )
                )
                async with asyncio.timeout(5):
                    while not app.has_arm_status:
                        await asyncio.sleep(0.01)
                assert app.last_arm_readiness == "READY"
                assert reader.subscription_matched_status.current_count >= 2
            async with asyncio.timeout(5):
                while app.has_arm_status:
                    await asyncio.sleep(0.01)
            assert app.last_arm_readiness == "READY"
            assert reader.subscription_matched_status.current_count >= 1
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            reader.close()

    asyncio.run(exercise())
