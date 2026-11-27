"""Live browser endpoints on private test ports and a separate DDS domain."""

import importlib
import json
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "resource/python"))
module_runner = importlib.import_module("scripts.module_runner")


def _request(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.load(response)


def _wait_for(check, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError("Browser/DDS state did not reach the expected value")


@pytest.fixture(scope="module")
def web_apps(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("web-apps")
    domain_file = ROOT / "system_arch/xml_app_creation/DomainLibrary.xml"
    private_domain = tmp_path / "DomainLibrary.xml"
    private_domain.write_text(
        domain_file.read_text().replace(
            'domain_id="0"', f'domain_id="{100 + secrets.randbelow(100)}"'
        )
    )
    processes = []
    logs = []
    urls = {}
    try:
        for module in ("01-operating-room", "04-security-threat"):
            directory = ROOT / "modules" / module
            env, apps = module_runner.load_module_config(directory, flags={"security": False})
            env["NDDS_QOS_PROFILES"] = env["NDDS_QOS_PROFILES"].replace(
                str(domain_file), str(private_domain)
            )
            env["PYTHONUNBUFFERED"] = "1"
            for name, command in apps.items():
                if "--port" in command:
                    with socket.socket() as reservation:
                        reservation.bind(("127.0.0.1", 0))
                        port = reservation.getsockname()[1]
                    command[command.index("--port") + 1] = str(port)
                    urls[name] = f"http://127.0.0.1:{port}/"
                log = tmp_path / f"{name}.log"
                stream = log.open("wb")
                logs.append(stream)
                process = subprocess.Popen(
                    command,
                    cwd=directory,
                    env=env,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                )
                processes.append((process, log))

        def ready():
            for process, log in processes:
                assert process.poll() is None, log.read_text()
            try:
                if not all(_request(url + "api/state") for url in urls.values()):
                    return False
                devices = _request(urls["Orchestrator"] + "api/state")["devices"]
                return len(devices) == 4 and all(device["status"] == "ON" for device in devices)
            except (OSError, urllib.error.URLError):
                return False

        _wait_for(ready)
        yield urls
    finally:
        module_runner._shutdown([process for process, _ in processes])
        for stream in logs:
            stream.close()


def test_all_six_browser_interfaces_serve_live_state_and_assets(web_apps):
    assert set(web_apps) == {
        "ArmController",
        "Orchestrator",
        "Arm",
        "PatientMonitor",
        "ThreatInjector",
        "ThreatExfiltrator",
    }
    for url in web_apps.values():
        assert _request(url + "api/state")
        for asset in ("", "app.js", "style.css"):
            with urllib.request.urlopen(url + asset, timeout=2) as response:
                assert response.status == 200
                assert response.read()


def test_browser_control_updates_real_dds_motor_state(web_apps):
    controller = web_apps["ArmController"]
    arm = web_apps["Arm"]
    initial = _request(arm + "api/state")["angles"]["ELBOW"]
    _request(controller + "api/motor", {"motor": "ELBOW", "action": "inc"})
    _wait_for(lambda: _request(arm + "api/state")["angles"]["ELBOW"] != initial)


def test_sensor_pause_and_start_reach_patient_monitor(web_apps):
    monitor = web_apps["PatientMonitor"]
    orchestrator = web_apps["Orchestrator"]
    _wait_for(lambda: not _request(monitor + "api/state")["data_stale"])
    _request(orchestrator + "api/command", {"device": "PATIENT_SENSOR", "command": "PAUSE"})
    try:
        _wait_for(lambda: _request(monitor + "api/state")["data_stale"])
    finally:
        _request(orchestrator + "api/command", {"device": "PATIENT_SENSOR", "command": "START"})
    _wait_for(lambda: not _request(monitor + "api/state")["data_stale"])


def test_exfiltrator_browser_uses_real_dds_and_stop_clears_state(web_apps):
    url = web_apps["ThreatExfiltrator"]
    _request(url + "api/command", {"action": "mode", "mode": "UNSECURE"})
    try:
        state = _wait_for(
            lambda: state if (state := _request(url + "api/state"))["vitals"] else None
        )
        assert state["vitals"]["hr"] > 0
        assert state["status"] == "ACCESS GRANTED"
    finally:
        stopped = _request(url + "api/command", {"action": "stop"})
    assert stopped["status"] == "IDLE"
    assert stopped["vitals"] is None


def test_injector_browser_preserves_one_shot_commands(web_apps):
    injector = web_apps["ThreatInjector"]
    arm = web_apps["Arm"]
    orchestrator = web_apps["Orchestrator"]
    _request(injector + "api/command", {"action": "mode", "mode": "UNSECURE"})
    try:
        _wait_for(lambda: _request(injector + "api/state")["status"] == "ACCESS GRANTED")
        _request(injector + "api/command", {"action": "attack", "attack": "CMD INJECT (PAUSE)"})
        launched = _request(injector + "api/command", {"action": "launch"})
        assert launched["attacking"] is False
        _wait_for(lambda: _request(arm + "api/state")["status"] == "PAUSED")
    finally:
        _request(injector + "api/command", {"action": "stop"})
        _request(orchestrator + "api/command", {"device": "ARM", "command": "START"})
    _wait_for(lambda: _request(arm + "api/state")["status"] == "ON")
