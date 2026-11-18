"""Exercise HTTP command validation and explicit error responses."""

import importlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules/01-operating-room/src"))
start_web_server = importlib.import_module("web_server_utils").start_web_server


@pytest.fixture
def server(tmp_path):
    received = []

    def command(payload):
        if payload.get("action") == "blocked":
            raise RuntimeError("DDS access blocked")
        received.append(payload)
        return {"ok": True}

    httpd = start_web_server(tmp_path, lambda: {"status": "IDLE"}, 0, command)
    yield f"http://127.0.0.1:{httpd.server_port}/", received
    httpd.shutdown()
    httpd.server_close()


@pytest.mark.parametrize(
    "body,content_type",
    [
        (b"[]", "application/json"),
        (b"{invalid", "application/json"),
        (b'{"action":"stop"}', "text/plain"),
        (b" " * 16385, "application/json"),
    ],
)
def test_invalid_commands_are_rejected(server, body, content_type):
    base, received = server
    request = urllib.request.Request(
        base + "api/command",
        data=body,
        headers={"Content-Type": content_type},
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 400
    assert json.load(error.value)["error"]
    assert received == []


def test_command_failure_is_not_reported_as_success(server):
    base, _ = server
    request = urllib.request.Request(
        base + "api/command",
        data=b'{"action":"blocked"}',
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 409
    assert json.load(error.value) == {"error": "DDS access blocked"}
