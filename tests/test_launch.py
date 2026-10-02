"""Launcher UI mode tests."""

from __future__ import annotations

import importlib
import os
import signal
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
launch = importlib.import_module("launch")


def test_cloud_web_mode_does_not_open_a_container_browser(monkeypatch):
    monkeypatch.setenv("MEDTECH_CLOUD", "1")
    commands = [["/tmp/Arm.py"]]
    monkeypatch.setattr(launch.threading, "Thread", lambda **kwargs: pytest.fail("cloud opened browser"))
    launch._apply_web_flag("01-operating-room", commands)
    assert commands == [["/tmp/Arm.py", "--web", "--port", "8092"]]


def test_module_runner_reports_owned_children(tmp_path):
    children = []
    launch.module_runner.launch(
        [[sys.executable, "-c", "pass"]], tmp_path, os.environ.copy(), on_started=children.extend
    )
    assert len(children) == 1
    assert children[0].returncode == 0


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_full_demo_supervisor_survives_child_exit_until_stop(tmp_path, stop_signal):
    code = (
        "import os, sys, signal; from pathlib import Path; from scripts import module_runner; "
        "from launch import _interrupt_launch; signal.signal(signal.SIGTERM, _interrupt_launch); "
        "module_runner.launch([[sys.executable, '-c', 'print(\"child finished\", flush=True)']], "
        "Path.cwd(), dict(os.environ), keep_alive=True)"
    )
    supervisor = subprocess.Popen(
        [sys.executable, "-c", code], cwd=tmp_path, stdout=subprocess.PIPE, text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(PROJECT_ROOT), str(PROJECT_ROOT / "resource" / "python")])},
    )
    try:
        assert supervisor.stdout.readline().strip() == "child finished"
        with pytest.raises(subprocess.TimeoutExpired):
            supervisor.wait(timeout=0.2)
        supervisor.send_signal(stop_signal)
        assert supervisor.wait(timeout=5) == 0
    finally:
        if supervisor.poll() is None:
            supervisor.kill()
        supervisor.wait(timeout=5)
        supervisor.stdout.close()


class _ImmediateThread:
    def __init__(self, target, args, daemon):
        self.callback = target
        self.args = args

    def start(self):
        self.callback(*self.args)


def test_web_mode_keeps_opening_browser_tabs(monkeypatch):
    monkeypatch.setenv("MEDTECH_CLOUD", "0")
    commands = [["/tmp/PatientMonitor.py"]]
    opened_urls = []
    monkeypatch.setattr(launch.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(
        launch.urllib.request, "urlopen", lambda url, timeout: nullcontext(SimpleNamespace(status=200))
    )
    monkeypatch.setattr(launch.webbrowser, "open_new_tab", opened_urls.append)

    launch._apply_web_flag("01-operating-room", commands)

    assert commands == [["/tmp/PatientMonitor.py", "--web", "--port", "8093"]]
    assert opened_urls == ["http://localhost:8093/"]


def test_web_tab_waits_for_server_before_opening(monkeypatch):
    requests = []
    opened_urls = []

    def urlopen(url, timeout):
        requests.append(url)
        if len(requests) < 3:
            raise URLError("server not listening yet")
        return nullcontext(SimpleNamespace(status=200))

    monkeypatch.setattr(launch.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(launch.time, "sleep", lambda seconds: None)

    launch._open_when_ready("http://localhost:8092/", opened_urls.append)

    assert len(requests) == 3
    assert opened_urls == ["http://localhost:8092/"]


def test_stop_script_only_stops_its_checkout_and_can_run_twice(tmp_path):
    tutorial = tmp_path / "tutorial"
    tutorial.mkdir()
    stop_script = tutorial / "stop_all.sh"
    stop_script.write_text((PROJECT_ROOT.parent / "tutorial" / "stop_all.sh").read_text())
    owned_script = tmp_path / "medtech-reference-architecture" / "modules" / "01-operating-room" / "src" / "Arm.py"
    owned_script.parent.mkdir(parents=True)
    unrelated_script = tmp_path / "unrelated" / "Arm.py"
    unrelated_script.parent.mkdir()
    code = 'import sys; print("ready", flush=True); sys.stdin.buffer.read()'
    children = []
    try:
        for script in [owned_script, unrelated_script]:
            script.write_text(code)
            child = subprocess.Popen(
                [sys.executable, str(script)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, text=True,
            )
            children.append(child)
            assert child.stdout.readline().strip() == "ready"
        result = subprocess.run(["bash", str(stop_script)], capture_output=True, text=True, check=True)
        assert "Stopped 1" in result.stdout
        assert children[0].wait(timeout=5) != 0
        assert children[1].poll() is None
        result = subprocess.run(["bash", str(stop_script)], capture_output=True, text=True, check=True)
        assert "No Digital Operating Room processes running" in result.stdout
        assert children[1].poll() is None
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
            child.stdin.close()
            child.stdout.close()
