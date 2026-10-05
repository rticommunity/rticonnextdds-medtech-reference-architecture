"""Launcher UI mode tests."""

from __future__ import annotations

import importlib
import json
import os
import signal
import subprocess
import sys
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
launch = importlib.import_module("launch")


def test_cloud_grid_uri_is_queued_without_a_desktop_browser(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDTECH_CLOUD", "1")
    monkeypatch.setattr(launch.tempfile, "gettempdir", lambda: str(tmp_path))
    uri = "vscode://rti.medtech-web-tabs/session?secure=1"
    launch._open_vscode_uri(uri)
    requests = list((tmp_path / f"medtech-web-tabs-{os.getuid()}" / "requests").iterdir())
    assert len(requests) == 1
    assert json.loads(requests[0].read_text()) == {"uri": uri}


def test_exited_child_closes_only_its_owned_tab(monkeypatch, tmp_path):
    uris = []
    monkeypatch.setattr(launch, "_open_vscode_uri", uris.append)
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=5)
    token = "a" * 32
    launch._watch_tab_closures([child], {0: token}, threading.Event(), tmp_path)
    assert uris == [f"vscode://rti.medtech-web-tabs/close-owned?closeToken={token}"]


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


@pytest.mark.parametrize("multi", [False, True])
@pytest.mark.parametrize(
    "failure", [OSError("second spawn failed"), KeyboardInterrupt(), SystemExit(7)]
)
def test_partial_launch_reaps_children_and_preserves_exception(
    monkeypatch, tmp_path, multi, failure
):
    popen = subprocess.Popen
    children = []
    unrelated = popen([sys.executable, "-c", "import time; time.sleep(60)"])

    def spawn(*args, **kwargs):
        if children:
            raise failure
        child = popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(launch.module_runner.subprocess, "Popen", spawn)
    command = [sys.executable, "-c", "import time; time.sleep(60)"]
    try:
        with pytest.raises(type(failure)) as caught:
            if multi:
                launch.module_runner.launch_multi([
                    ([command], tmp_path, os.environ.copy()),
                    ([command], tmp_path, os.environ.copy()),
                ])
            else:
                launch.module_runner.launch([command, command], tmp_path, os.environ.copy())
        assert caught.value is failure
        assert len(children) == 1
        assert children[0].returncode is not None
        assert unrelated.poll() is None
    finally:
        for child in [*children, unrelated]:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)


@pytest.mark.parametrize("stubborn", [False, True])
@pytest.mark.parametrize("failure", [RuntimeError("callback failed"), KeyboardInterrupt()])
def test_callback_failure_terminates_and_reaps_children(tmp_path, failure, stubborn):
    children = []
    handler = "signal.SIG_IGN" if stubborn else "lambda *_: os._exit(0)"
    command = [sys.executable, "-u", "-c",
               f"import os, signal; signal.signal(signal.SIGTERM, {handler}); "
               "print('ready', flush=True); signal.pause()"]

    def started(owned):
        children.extend(owned)
        for child in owned:
            assert child.stdout.readline().strip() == "ready"
        owned.clear()
        raise failure

    popen = subprocess.Popen

    def spawn(*args, **kwargs):
        return popen(*args, **kwargs, stdout=subprocess.PIPE, text=True)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(launch.module_runner.subprocess, "Popen", spawn)
        try:
            with pytest.raises(type(failure)) as caught:
                launch.module_runner.launch(
                    [command, command], tmp_path, os.environ.copy(), on_started=started
                )
            assert caught.value is failure
            assert len(children) == 2
            expected = -signal.SIGKILL if stubborn else 0
            assert [child.returncode for child in children] == [expected, expected]
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=5)
                child.stdout.close()


@pytest.mark.parametrize("multi", [False, True])
@pytest.mark.parametrize("failure", [RuntimeError("wait failed"), KeyboardInterrupt()])
def test_wait_failure_reaps_all_children(monkeypatch, tmp_path, multi, failure):
    popen = subprocess.Popen
    children = []

    def spawn(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        if len(children) == 1:
            wait = child.wait

            def fail_wait_once(*wait_args, **wait_kwargs):
                monkeypatch.setattr(child, "wait", wait)
                raise failure

            monkeypatch.setattr(child, "wait", fail_wait_once)
        return child

    monkeypatch.setattr(launch.module_runner.subprocess, "Popen", spawn)
    command = [sys.executable, "-c", "import time; time.sleep(60)"]
    try:
        with pytest.raises(type(failure)) as caught:
            if multi:
                launch.module_runner.launch_multi([([command, command], tmp_path, os.environ.copy())])
            else:
                launch.module_runner.launch([command, command], tmp_path, os.environ.copy())
        assert caught.value is failure
        assert len(children) == 2
        assert all(child.returncode is not None for child in children)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)


def test_cleanup_failure_does_not_mask_original_or_skip_other_children(monkeypatch, tmp_path):
    failure = RuntimeError("callback failed")
    cleanup_failure = OSError("terminate failed")
    children = []

    def started(owned):
        children.extend(owned)

        def terminate():
            raise cleanup_failure

        monkeypatch.setattr(owned[0], "terminate", terminate)
        raise failure

    command = [sys.executable, "-c", "import time; time.sleep(60)"]
    try:
        with pytest.raises(RuntimeError) as caught:
            launch.module_runner.launch(
                [command, command], tmp_path, os.environ.copy(), on_started=started
            )
        assert caught.value is failure
        assert "terminate failed" in failure.__notes__[0]
        assert all(child.returncode is not None for child in children)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_full_demo_supervisor_survives_child_exit_until_stop(tmp_path, stop_signal):
    code = (
        "import os, sys, signal; from pathlib import Path; from scripts import module_runner; "
        "from launch import _interrupt_launch; signal.signal(signal.SIGTERM, _interrupt_launch); "
        "\ntry:\n"
        " module_runner.launch([[sys.executable, '-c', 'print(\"child finished\", flush=True)']], "
        "Path.cwd(), dict(os.environ), keep_alive=True)\n"
        "except KeyboardInterrupt:\n pass"
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
