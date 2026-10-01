"""Launcher UI mode tests."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
launch = importlib.import_module("launch")


def test_cloud_uri_is_queued_without_desktop_browser(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDTECH_CLOUD", "1")
    monkeypatch.setattr(launch.tempfile, "gettempdir", lambda: str(tmp_path))
    uri = "vscode://rti.medtech-web-tabs/open?url=http%3A%2F%2Flocalhost%3A8092%2F&title=Arm"
    launch._open_vscode_uri(uri)
    requests = list((tmp_path / f"medtech-web-tabs-{os.getuid()}" / "requests").iterdir())
    assert len(requests) == 1
    assert requests[0].suffix == ".json"
    assert json.loads(requests[0].read_text()) == {"uri": uri}


def test_tab_close_kills_only_its_owned_process(tmp_path):
    children = [
        subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"], stdin=subprocess.PIPE
        )
        for _ in range(2)
    ]
    stopped = threading.Event()
    watcher = threading.Thread(
        target=launch._watch_tab_closures,
        args=(children, {0: "arm-token", 1: "monitor-token"}, stopped, tmp_path),
    )
    watcher.start()
    try:
        (tmp_path / "arm-token.close").touch()
        assert children[0].wait(timeout=5) != 0
        assert children[1].poll() is None
    finally:
        stopped.set()
        watcher.join(timeout=5)
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
            child.stdin.close()


def test_module_runner_reports_owned_children(tmp_path):
    children = []
    launch.module_runner.launch(
        [[sys.executable, "-c", "pass"]], tmp_path, os.environ.copy(), on_started=children.extend
    )
    assert len(children) == 1
    assert children[0].returncode == 0


class _ImmediateThread:
    def __init__(self, target, args, daemon):
        self.callback = target
        self.args = args

    def start(self):
        self.callback(*self.args)


def test_vscode_mode_adds_web_arguments_and_opens_editor_tab(monkeypatch):
    commands = [["/tmp/Arm.py"]]
    launched_commands = []
    monkeypatch.setattr(launch.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(
        launch.urllib.request, "urlopen", lambda url, timeout: nullcontext(SimpleNamespace(status=200))
    )
    monkeypatch.setattr(launch.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        launch.subprocess, "run", lambda command, check: launched_commands.append((command, check))
    )

    launch._apply_web_flag("01-operating-room", commands, vscode=True)

    assert commands == [["/tmp/Arm.py", "--web", "--port", "8092"]]
    assert launched_commands == [
        (
            [
                "open",
                "-a",
                "Visual Studio Code",
                "vscode://rti.medtech-web-tabs/open?url=http%3A%2F%2Flocalhost%3A8092%2F&title=Arm",
            ],
            False,
        )
    ]


def test_web_mode_keeps_opening_browser_tabs(monkeypatch):
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


def test_vscode_tab_receives_its_own_close_token(monkeypatch):
    commands = [["/tmp/PatientSensor"], ["/tmp/Arm.py"], ["/tmp/PatientMonitor.py"]]
    tokens = {}
    uris = []
    monkeypatch.setattr(launch.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(
        launch.urllib.request,
        "urlopen",
        lambda url, timeout: nullcontext(SimpleNamespace(status=200)),
    )
    monkeypatch.setattr(launch, "_open_vscode_uri", uris.append)
    launch._apply_web_flag("01-operating-room", commands, vscode=True, close_tokens=tokens)
    assert set(tokens) == {1, 2}
    assert tokens[1] != tokens[2]
    for uri, index, title in zip(uris, [1, 2], ["Arm", "PatientMonitor"]):
        query = launch.urllib.parse.parse_qs(launch.urllib.parse.urlparse(uri).query)
        assert query["closeToken"] == [tokens[index]]
        assert query["title"] == [title]


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


def test_close_vscode_tabs_sends_close_uri(monkeypatch):
    launched_commands = []
    monkeypatch.setattr(launch.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        launch.subprocess, "run", lambda command, check: launched_commands.append((command, check))
    )

    launch._close_vscode_tabs()

    assert launched_commands == [
        (["open", "-a", "Visual Studio Code", "vscode://rti.medtech-web-tabs/close"], False)
    ]
