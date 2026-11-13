#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.
"""Launch / smoke tests for Module 01 applications.

Verifies that each application starts without crashing.
GUI applications are marked so they can be skipped on headless systems.
"""

import importlib
import json
import re
import select
import signal
import time
from urllib.request import Request, urlopen

import pytest
from module01_test_support import MODULE_DIR
from scripts import module_runner
from scripts.test_utils import (
    ProcessManager,
    wait_for_device_status,
    wait_for_samples,
)


class TestPatientSensor:
    """PatientSensor is a headless C++ app — no display needed."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc_manager.start_app_ready("PatientSensor")

    def test_prints_launch_message(self, proc_manager):
        proc = proc_manager.start_app_ready("PatientSensor")
        # Read whatever is available, non-blocking
        out = (
            proc.stdout.read1(4096).decode(errors="replace")
            if hasattr(proc.stdout, "read1")
            else b""
        )
        # Fallback: terminate and capture
        if not out:
            proc.terminate()
            stdout, _ = proc.communicate(timeout=5)
            out = stdout.decode(errors="replace")
        assert "Launching Patient Sensor" in out


class TestOrchestrator:
    """Orchestrator serves the RTI Demo UI browser frontend."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc_manager.start_app_ready("Orchestrator")

    @pytest.mark.parametrize("app_name", ("ArmController", "Orchestrator"))
    def test_ctrl_c_shuts_down_cleanly(self, proc_manager, app_name):
        proc = proc_manager.start_app_ready(app_name)
        assert proc.stdout is not None
        readable, _, _ = select.select([proc.stdout], [], [], 3)
        assert readable, f"{app_name} did not print its browser URL"
        line = proc.stdout.readline().decode(errors="replace").strip()
        assert "listening on http://127.0.0.1:" in line, line

        proc.send_signal(signal.SIGINT)
        stdout, stderr = proc.communicate(timeout=5)
        assert proc.returncode == 0, stdout.decode(errors="replace") + stderr.decode(
            errors="replace"
        )
        assert b"terminate called after throwing" not in stdout + stderr


class TestArmController:
    """ArmController serves the RTI Demo UI browser frontend."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc_manager.start_app_ready("ArmController")

    @pytest.mark.parametrize("variant", ("simulated", "xbox"))
    def test_readiness_remains_known_when_unchanged_and_telemetry_can_go_stale(self, variant):
        env, apps = module_runner.load_module_config(
            MODULE_DIR,
            flags={"security": False},
            variants={"ArmController": variant},
        )
        manager = ProcessManager(env, apps, cwd=MODULE_DIR)
        try:
            arm = manager.start_app_ready("Arm")
            controller = manager.start_app_ready(
                "ArmController", extra_env={"SDL_VIDEODRIVER": "dummy"}
            )
            assert controller.stdout is not None
            deadline = time.monotonic() + 5
            url = None
            output = ""
            while time.monotonic() < deadline:
                readable, _, _ = select.select([controller.stdout], [], [], 0.25)
                if readable:
                    output += controller.stdout.read1(4096).decode()
                    match = re.search(r"https?://127\.0\.0\.1:\d+/", output)
                    if match:
                        url = match.group(0).rstrip("/")
                        break
            assert url is not None

            if variant == "xbox":
                with urlopen(f"{url}/api/state", timeout=2) as response:
                    inputs = json.load(response)["data"]["inputs"]
                labels = [item["label"] for item in inputs]
                assert labels.count("LT / RT") == 1
                assert labels.count("LB") == 1
                assert labels.count("A / B") == 1
                assert "LEFT TRIGGER" not in labels and "RIGHT TRIGGER" not in labels

            def feedback():
                with urlopen(f"{url}/api/state", timeout=2) as response:
                    return json.load(response)["data"].get("feedback", {})

            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = feedback()
                if state.get("status_known") and state.get("readiness") == "READY":
                    break
                time.sleep(0.05)
            else:
                pytest.fail("Controller did not observe READY")
            time.sleep(1)
            state = feedback()
            assert state["status_known"]
            assert state["readiness"] == "READY"
            assert state["freshness"]["telemetry"]

            arm.terminate()
            arm.wait(timeout=5)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = feedback()
                if not state["freshness"]["telemetry"]:
                    break
                time.sleep(0.05)
            assert not state["freshness"]["telemetry"]
            assert state["status_known"]
            assert state["readiness"] in {"READY", "NOT_READY"}
        finally:
            manager.shutdown_all()

    def test_unreleased_jog_command_times_out(self, proc_manager):
        proc = proc_manager.start_app_ready("ArmController")
        assert proc.stdout is not None
        readable, _, _ = select.select([proc.stdout], [], [], 3)
        assert readable, "ArmController did not print its browser URL"
        line = proc.stdout.readline().decode(errors="replace").strip()
        assert line.startswith("Arm Controller listening on"), line
        match = re.search(r"https?://127\.0\.0\.1:\d+", line)
        assert match, f"ArmController printed no local URL: {line}"
        base_url = match.group(0)

        deadline = time.monotonic() + 3
        angular_directions = {}
        while time.monotonic() < deadline:
            with urlopen(f"{base_url}/api/state", timeout=2) as response:
                state = json.load(response)
            groups = state.get("data", {}).get("control_groups", [])
            tool_controls = [control for group in groups for control in group["controls"]]
            angular_directions = {
                control["label"]: control["direction"]
                for control in tool_controls
                if control.get("axis") == "ANGULAR_Z"
            }
            if angular_directions:
                break
            time.sleep(0.05)
        assert set(angular_directions.values()) == {"POSITIVE", "NEGATIVE"}

        with urlopen(f"{base_url}/api/command-capability", timeout=2) as response:
            capability = json.load(response)["capability"]
        request = Request(
            f"{base_url}/api/commands/teleop",
            data=json.dumps({"axis": "ANGULAR_Z", "direction": "POSITIVE"}).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": base_url,
                "X-RTI-Demo-Command-Capability": capability,
            },
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            assert json.load(response)["ok"]

        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            with urlopen(f"{base_url}/api/state", timeout=2) as response:
                state = json.load(response)
            if any(
                "Jog input timed out" in entry["message"] for entry in state["data"].get("logs", [])
            ):
                return
            time.sleep(0.1)
        pytest.fail("ArmController did not stop an unreleased jog command")


class TestPatientMonitor:
    """PatientMonitor serves the RTI Demo UI browser frontend."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc_manager.start_app_ready("PatientMonitor")


class TestArm:
    """Arm serves the RTI Demo UI browser frontend."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc_manager.start_app_ready("Arm")

    def test_ctrl_c_shuts_down_cleanly(self, proc_manager):
        proc = proc_manager.start_app_ready("Arm")
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)
        stdout, stderr = proc.communicate(timeout=5)
        assert proc.returncode == 0
        assert b"KeyboardInterrupt" not in stdout + stderr


class TestAllApps:
    """Launch all five applications simultaneously."""

    def test_all_apps_launch_together(self, proc_manager, nonsecure_utility_app):
        from MedTech import Device

        proc_manager.start_apps_ready(
            [
                "PatientSensor",
                "Orchestrator",
                "ArmController",
                "PatientMonitor",
                "Arm",
            ]
        )

        # Wait for all 4 device-type apps to report DeviceStatus
        # (Orchestrator doesn't publish DeviceStatus — it's the controller)
        status_reader = nonsecure_utility_app.device_status.reader
        expected = {
            Device.DeviceType.PATIENT_SENSOR,
            Device.DeviceType.ARM_CONTROLLER,
            Device.DeviceType.ARM,
            Device.DeviceType.PATIENT_MONITOR,
        }
        seen = wait_for_device_status(
            status_reader,
            expected,
            device_statuses=[Device.DeviceStatuses.ON],
            timeout_sec=30,
        )
        assert seen == expected, (
            f"Not all apps came online. Missing: {set(d.name for d in expected - seen)}"
        )


class TestArmControllerGamepad:
    """The optional gamepad variant uses the same DDS device role."""

    def test_sigterm_shuts_down_cleanly(self):
        pytest.importorskip("pygame")
        importlib.import_module("pygame._sdl2.controller")

        env, apps = module_runner.load_module_config(
            MODULE_DIR,
            flags={"security": False},
            variants={"ArmController": "xbox"},
        )
        manager = ProcessManager(env, apps, cwd=MODULE_DIR)
        try:
            proc = manager.start_app_ready(
                "ArmController",
                extra_env={"SDL_VIDEODRIVER": "dummy"},
            )
            proc.send_signal(signal.SIGTERM)
            stdout, stderr = proc.communicate(timeout=5)
            assert proc.returncode == 0, stdout + stderr
            assert b"Xbox Arm Controller stopped" in stdout
            assert b"DemoUiApp: model is stopped" not in stdout + stderr
        finally:
            manager.shutdown_all()

    def test_starts_without_controller_and_reports_status(self, nonsecure_utility_app):
        pytest.importorskip("pygame")
        importlib.import_module("pygame._sdl2.controller")

        from MedTech import Device

        env, apps = module_runner.load_module_config(
            MODULE_DIR,
            flags={"security": False},
            variants={"ArmController": "xbox"},
        )
        manager = ProcessManager(env, apps, cwd=MODULE_DIR)
        try:
            proc = manager.start_app_ready(
                "ArmController",
                extra_env={
                    "SDL_VIDEODRIVER": "dummy",
                },
            )
            seen = wait_for_device_status(
                nonsecure_utility_app.device_status.reader,
                expected_devices={Device.DeviceType.ARM_CONTROLLER},
                device_statuses=[Device.DeviceStatuses.ON],
                timeout_sec=10,
            )
            assert Device.DeviceType.ARM_CONTROLLER in seen
            assert proc.poll() is None
            heartbeats = wait_for_samples(
                nonsecure_utility_app.device_heartbeat.reader,
                n=1,
                timeout_sec=2,
            )
            assert any(sample.device == Device.DeviceType.ARM_CONTROLLER for sample in heartbeats)
        finally:
            manager.shutdown_all()
