"""Launcher UI mode tests."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
launch = importlib.import_module("launch")


class _ImmediateTimer:
    def __init__(self, delay, callback, args):
        self.callback = callback
        self.args = args

    def start(self):
        self.callback(*self.args)


def test_vscode_mode_adds_web_arguments_and_opens_editor_tab(monkeypatch):
    commands = [["/tmp/Arm.py"]]
    launched_commands = []
    monkeypatch.setattr(launch.threading, "Timer", _ImmediateTimer)
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
    monkeypatch.setattr(launch.threading, "Timer", _ImmediateTimer)
    monkeypatch.setattr(launch.webbrowser, "open_new_tab", opened_urls.append)

    launch._apply_web_flag("01-operating-room", commands)

    assert commands == [["/tmp/PatientMonitor.py", "--web", "--port", "8093"]]
    assert opened_urls == ["http://localhost:8093/"]


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
