"""Verify that every existing scenario resolves to browser-based applications."""

import importlib
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
launcher = importlib.import_module("launch")

EXPECTED_PORTS = {
    "or-all": {8090, 8091, 8092, 8093},
    "or-gui": {8092, 8093},
    "or-headless": {8090, 8091},
    "record": {8090, 8091, 8092, 8093},
    "replay": {8092, 8093},
    "teleop-or-side": {8090, 8092, 8093},
    "teleop-controller-side": {8091},
    "security-threat": {8090, 8091, 8092, 8093, 8094, 8095},
    "threat-inject": {8090, 8091, 8092, 8093, 8094},
    "threat-exfiltrate": {8090, 8091, 8092, 8093, 8095},
}


@pytest.mark.parametrize("security", [False, True])
@pytest.mark.parametrize("scenario", EXPECTED_PORTS)
def test_all_scenarios_keep_their_web_interfaces(scenario, security, monkeypatch):
    setup = launcher.module_runner.platform_setup
    monkeypatch.setattr(setup, "get_nddshome", lambda: Path("/sdk"))
    monkeypatch.setattr(setup, "setup_library_env", lambda *_: None)
    monkeypatch.setattr(setup, "find_executable", lambda name: f"/build/{name}")
    monkeypatch.setattr(setup, "find_service_binary", lambda name: Path("/sdk/bin") / name)
    assert set(launcher.SCENARIOS) == set(EXPECTED_PORTS)
    specs = [
        launcher._resolve_module(module, apps, security)
        for module, apps in launcher.SCENARIOS[scenario]["modules"]
    ]
    urls = launcher._web_urls(specs)
    ports = [int(launcher.urllib.parse.urlsplit(url).port) for _, url in urls]
    assert set(ports) == EXPECTED_PORTS[scenario]
    assert len(ports) == len(set(ports))
    profiles = ";".join(env["NDDS_QOS_PROFILES"] for _, _, env in specs)
    assert ("SecureAppsQos.xml" if security else "NonSecureAppsQos.xml") in profiles
    services = [
        Path(command[0]).name
        for commands, _, _ in specs
        for command in commands
        if command[0].startswith("/sdk/bin/")
    ]
    assert services == {
        "record": ["rtirecordingservice"],
        "replay": ["rtireplayservice"],
        "teleop-or-side": ["rtiroutingservice"],
        "teleop-controller-side": ["rtiroutingservice"],
    }.get(scenario, [])


def test_no_browser_option_prints_cloud_proxy_urls(monkeypatch, capsys):
    monkeypatch.setenv("MEDTECH_CLOUD", "1")
    monkeypatch.setenv("MEDTECH_CLOUD_URL", "https://example.test/workspaces/test/ide/")
    run = Mock()
    browser = Mock()
    monkeypatch.setattr(launcher.module_runner, "launch_multi", run)
    monkeypatch.setattr(launcher.webbrowser, "open_new_tab", browser)
    specs = [([["/build/Orchestrator", "--port", "8090"]], ROOT, {})]
    launcher._launch_specs(specs, no_browser=True)
    assert "https://example.test/workspaces/test/ide/proxy/8090/" in capsys.readouterr().out
    run.assert_called_once_with(specs)
    browser.assert_not_called()


def test_spawn_failure_stops_already_started_processes(monkeypatch):
    child = Mock()
    child.poll.return_value = None
    monkeypatch.setattr(
        launcher.module_runner.subprocess,
        "Popen",
        Mock(side_effect=[child, FileNotFoundError("missing application")]),
    )
    with pytest.raises(FileNotFoundError, match="missing application"):
        launcher.module_runner.launch_multi([([["first"], ["missing"]], ROOT, {})])
    child.terminate.assert_called_once()
    child.wait.assert_called_once()


def test_failed_web_process_stops_other_scenario_processes(monkeypatch):
    running = Mock()
    running.poll.return_value = None
    failed = Mock(args=["failed-web-app"])
    failed.poll.return_value = 1
    monkeypatch.setattr(
        launcher.module_runner.subprocess,
        "Popen",
        Mock(side_effect=[running, failed]),
    )
    with pytest.raises(subprocess.CalledProcessError):
        launcher.module_runner.launch_multi([([["running"], ["failed"]], ROOT, {})])
    running.terminate.assert_called_once()
