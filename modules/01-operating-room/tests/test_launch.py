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
import math
import re
import select
import signal
import subprocess
import time
from urllib.request import Request, urlopen

import pytest
from module01_test_support import MODULE_DIR, invoke, local_ui_url, ui_data, wait_for_ui_data
from test_utils import (
    ProcessManager,
    check_no_deadline_missed,
    wait_for_device_status,
    wait_for_samples,
    wait_for_writer_match,
)

from tools.medtech import module_runner


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


@pytest.mark.parametrize("app_name", ("ArmController", "Orchestrator"))
def test_cpp_app_startup_error_exits_with_failure(proc_manager, tmp_path, app_name):
    proc = proc_manager.start_app(
        app_name,
        extra_env={"NDDS_QOS_PROFILES": str(tmp_path / "missing-qos.xml")},
    )
    try:
        stdout, stderr = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        pytest.fail(f"{app_name} did not exit after its DDS setup failed")
    assert proc.returncode != 0, stdout.decode(errors="replace")
    assert f"{app_name} setup failed".encode() in stderr


@pytest.mark.parametrize("app_name", ("ArmController", "Orchestrator"))
def test_cpp_ui_startup_error_stops_worker_and_exits(proc_manager, app_name):
    proc = proc_manager.start_app(app_name, extra_env={"RTI_DEMO_UI_MODE": "invalid"})
    try:
        stdout, stderr = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        pytest.fail(f"{app_name} did not exit after its UI setup failed")
    assert proc.returncode != 0, stdout.decode(errors="replace")
    assert f"{app_name} UI failed".encode() in stderr
    assert b"terminate called after throwing" not in stderr


@pytest.mark.parametrize(
    ("app_name", "message"),
    (("Arm", "Arm setup or UI failed"), ("PatientMonitor", "Patient Monitor setup or UI failed")),
)
def test_python_app_startup_error_exits_with_failure(proc_manager, tmp_path, app_name, message):
    proc = proc_manager.start_app(
        app_name,
        extra_env={"NDDS_QOS_PROFILES": str(tmp_path / "missing-qos.xml")},
    )
    try:
        stdout, stderr = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        pytest.fail(f"{app_name} did not exit after its DDS setup failed")
    assert proc.returncode != 0, stdout.decode(errors="replace")
    assert message.encode() in stderr


class TestArmController:
    @pytest.mark.parametrize("variant", ("simulated", "xbox"))
    def test_controller_reads_only_arm_device_readiness(self, nonsecure_utility_app, variant):
        from MedTech import Device, Geometry, Robot

        env, apps = module_runner.load_module_config(
            MODULE_DIR,
            flags={"security": False},
            variants={"ArmController": variant},
        )
        manager = ProcessManager(env, apps, cwd=MODULE_DIR)
        try:
            controller = manager.start_app_ready(
                "ArmController", extra_env={"SDL_VIDEODRIVER": "dummy"}
            )
            assert controller.stdout is not None
            deadline = time.monotonic() + 5
            output = ""
            url = None
            while time.monotonic() < deadline:
                readable, _, _ = select.select([controller.stdout], [], [], 0.25)
                if readable:
                    output += controller.stdout.read1(4096).decode()
                    match = re.search(r"https?://127\.0\.0\.1:\d+", output)
                    if match:
                        url = match.group(0)
                        break
            assert url is not None, output
            status_writer = nonsecure_utility_app.device_status.writer
            telemetry_writer = nonsecure_utility_app.arm_telemetry.writer
            assert wait_for_writer_match(status_writer)
            assert wait_for_writer_match(telemetry_writer)
            other_status = Device.Status(
                device=Device.DeviceType.PATIENT_SENSOR,
                status=Device.DeviceStatusKind.ON,
                readiness=Device.DeviceReadinessKind.READY,
            )
            arm_status = Device.Status(
                device=Device.DeviceType.ARM,
                status=Device.DeviceStatusKind.ERROR,
                readiness=Device.DeviceReadinessKind.FAULTED,
            )
            telemetry = Robot.Arm.Telemetry(
                arm_id="arm-1",
                tcp_pose=Geometry.Pose(position=Geometry.Vector3(0.3, 0.0, 0.3)),
                parallel_jaw=Robot.Tool.ParallelJawState(opening_width=0.02),
            )
            status_writer.write(other_status)
            time.sleep(0.2)
            assert not ui_data(url)["feedback"]["status_known"]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                status_writer.write(arm_status)
                telemetry_writer.write(telemetry)
                feedback = ui_data(url)["feedback"]
                if feedback["status_known"] and feedback["readiness"] == "FAULTED":
                    break
                time.sleep(0.05)
            else:
                pytest.fail("Controller did not observe the arm's device readiness")
            status_writer.write(other_status)
            time.sleep(0.2)
            assert ui_data(url)["feedback"]["readiness"] == "FAULTED"
            if variant == "simulated":
                telemetry_writer.write(telemetry)
                assert invoke(url, "start-demo", {})["ok"]
                state = wait_for_ui_data(
                    url,
                    lambda data: any("Cannot start demo" in row["message"] for row in data["logs"]),
                )
                assert not state["demo"]["running"]
        finally:
            manager.shutdown_all()

    """ArmController serves the RTI Demo UI browser frontend."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc_manager.start_app_ready("ArmController")

    def test_showcase_is_bounded_and_manual_takeover_can_be_stopped(
        self, proc_manager, nonsecure_utility_app
    ):
        reader = nonsecure_utility_app.teleop_control.reader
        tool_reader = nonsecure_utility_app.tool_control.reader
        proc_manager.start_app_ready("Arm")
        controller = proc_manager.start_app_ready("ArmController")
        url = local_ui_url(controller, "Arm Controller listening on")
        initial = wait_for_ui_data(
            url,
            lambda data: (
                data.get("feedback", {}).get("freshness", {}).get("telemetry")
                and data["feedback"]["position"] is not None
                and data["feedback"]["opening_width"] is not None
            ),
        )["feedback"]
        origin = tuple(initial["position"][axis] for axis in "xyz")
        orientation = tuple(initial["orientation"][axis] for axis in "xyzw")
        gap = initial["opening_width"]
        assert invoke(url, "start-demo", {})["ok"]
        wait_for_ui_data(url, lambda data: data["demo"]["running"])
        assert invoke(url, "teleop", {"axis": "X", "direction": "STOPPED"})["ok"]

        cycles = 0
        largest_excursion = 0.0
        largest_gap_change = 0.0
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and cycles < 3:
            state = ui_data(url)
            feedback = state["feedback"]
            position = tuple(feedback["position"][axis] for axis in "xyz")
            distance = math.dist(position, origin)
            gap_change = abs(feedback["opening_width"] - gap)
            actual_orientation = tuple(feedback["orientation"][axis] for axis in "xyzw")
            assert abs(sum(a * b for a, b in zip(orientation, actual_orientation))) >= math.cos(
                0.01 / 2
            ), "Translation/jaw showcase accumulated orientation drift"
            largest_excursion = max(largest_excursion, distance)
            largest_gap_change = max(largest_gap_change, gap_change)
            assert distance < 0.025, state
            assert gap_change < 0.010, state
            if state["demo"]["cycles"] > cycles:
                cycles = state["demo"]["cycles"]
                assert distance <= 0.0012, state
                assert gap_change <= 0.0006, state
            assert state["demo"]["running"], state["logs"]
            time.sleep(0.05)
        assert cycles >= 3, state
        assert largest_excursion > 0.012, "Showcase did not actually translate"
        assert largest_gap_change > 0.006, "Showcase did not actually move the jaws"

        assert invoke(url, "teleop", {"axis": "Y", "direction": "POSITIVE"})["ok"]
        wait_for_ui_data(url, lambda data: not data["demo"]["running"])
        assert wait_for_samples(
            reader, n=1, timeout_sec=2, filter_fn=lambda sample: sample.linear_velocity.y > 0.04
        ), "Manual jog did not take over from demo"
        reader.take()
        tool_reader.take()
        assert invoke(url, "stop-demo", {})["ok"]
        assert wait_for_samples(
            reader,
            n=1,
            timeout_sec=0.8,
            filter_fn=lambda sample: all(
                getattr(sample.linear_velocity, axis) == 0
                and getattr(sample.angular_velocity, axis) == 0
                for axis in "xyz"
            ),
        ), "STOP MOTION did not publish zero before the input timeout"
        assert wait_for_samples(
            tool_reader, n=1, timeout_sec=0.5, filter_fn=lambda sample: sample.opening_rate == 0
        )
        time.sleep(0.2)
        stopped = ui_data(url)["feedback"]["position"]
        time.sleep(0.35)
        held = ui_data(url)["feedback"]["position"]
        assert math.dist(tuple(stopped.values()), tuple(held.values())) < 0.0005

        from MedTech import Device

        writer = nonsecure_utility_app.device_command.writer
        assert wait_for_writer_match(writer)
        assert invoke(url, "start-demo", {})["ok"]
        wait_for_ui_data(url, lambda data: data["demo"]["running"])
        assert wait_for_samples(
            reader, n=1, timeout_sec=2, filter_fn=lambda sample: sample.linear_velocity.x < 0
        )
        reader.take()
        writer.write(
            Device.Command(
                device=Device.DeviceType.ARM_CONTROLLER, command=Device.DeviceCommandKind.PAUSE
            )
        )
        assert wait_for_samples(
            reader,
            n=1,
            timeout_sec=0.8,
            filter_fn=lambda sample: all(
                getattr(sample.linear_velocity, axis) == 0 for axis in "xyz"
            ),
        ), "PAUSE ceased publication without an explicit zero command"
        paused = wait_for_ui_data(url, lambda data: data["status"] == "PAUSED")
        assert not paused["demo"]["running"]
        assert invoke(url, "teleop", {"axis": "X", "direction": "POSITIVE"})["ok"]
        wait_for_ui_data(
            url,
            lambda data: any("Ignored jog" in entry["message"] for entry in data["logs"]),
        )
        writer.write(
            Device.Command(
                device=Device.DeviceType.ARM_CONTROLLER, command=Device.DeviceCommandKind.START
            )
        )
        resumed = wait_for_ui_data(url, lambda data: data["status"] == "ON")
        assert not resumed["demo"]["running"]
        reader.take()
        samples = wait_for_samples(reader, n=5, timeout_sec=1)
        assert len(samples) >= 5
        assert all(
            getattr(sample.linear_velocity, axis) == 0
            and getattr(sample.angular_velocity, axis) == 0
            for sample in samples
            for axis in "xyz"
        ), "START resumed a cancelled demo or a jog submitted while paused"

    @pytest.mark.parametrize("feedback_loss", ("stale", "incomplete", "unreachable"))
    def test_demo_cancels_when_feedback_cannot_support_motion(
        self, proc_manager, nonsecure_utility_app, feedback_loss
    ):
        from MedTech import Geometry, Robot

        writer = nonsecure_utility_app.arm_telemetry.writer
        reader = nonsecure_utility_app.teleop_control.reader
        controller = proc_manager.start_app_ready("ArmController")
        url = local_ui_url(controller, "Arm Controller listening on")
        assert wait_for_writer_match(writer)
        telemetry = Robot.Arm.Telemetry(
            arm_id="arm-1",
            tcp_pose=Geometry.Pose(position=Geometry.Vector3(0.3, 0.0, 0.3)),
            parallel_jaw=Robot.Tool.ParallelJawState(opening_width=0.02),
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            writer.write(telemetry)
            state = ui_data(url)
            if state.get("feedback", {}).get("freshness", {}).get("telemetry"):
                break
            time.sleep(0.05)
        assert state["feedback"]["freshness"]["telemetry"], state
        assert invoke(url, "start-demo", {})["ok"]
        assert wait_for_samples(
            reader, n=1, timeout_sec=2, filter_fn=lambda sample: sample.linear_velocity.x < 0
        )
        if feedback_loss == "incomplete":
            telemetry.parallel_jaw = None
        reader.take()
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if feedback_loss != "stale":
                writer.write(telemetry)
            state = ui_data(url)
            if not state["demo"]["running"]:
                break
            time.sleep(0.05)
        assert not state["demo"]["running"], state
        message = "timed out" if feedback_loss == "unreachable" else "feedback unavailable"
        assert any(message in entry["message"] for entry in state["logs"])
        assert wait_for_samples(
            reader,
            n=1,
            timeout_sec=0.5,
            filter_fn=lambda sample: all(
                getattr(sample.linear_velocity, axis) == 0 for axis in "xyz"
            ),
        ), "Demo cancellation did not command zero"

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
            device_statuses=[Device.DeviceStatusKind.ON],
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
                device_statuses=[Device.DeviceStatusKind.ON],
                timeout_sec=10,
            )
            assert Device.DeviceType.ARM_CONTROLLER in seen
            assert proc.poll() is None
            heartbeats = wait_for_samples(
                nonsecure_utility_app.device_heartbeat.reader,
                n=3,
                timeout_sec=3,
                filter_fn=lambda sample: sample.device == Device.DeviceType.ARM_CONTROLLER,
            )
            assert len(heartbeats) >= 3
            assert check_no_deadline_missed(nonsecure_utility_app.device_heartbeat.reader)
        finally:
            manager.shutdown_all()
