#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from module01_test_support import MODULE_DIR

sys.path.insert(0, str(MODULE_DIR / "tools"))
sys.path.insert(0, str(MODULE_DIR / "src"))

import check_falcon  # noqa: E402
import check_kortex  # noqa: E402


@pytest.mark.parametrize("ready", [True, False])
def test_kinova_check_reports_health_and_only_reads_device(monkeypatch, capsys, ready):
    events = []

    class Device:
        def open(self):
            events.append("open")

        def read_health(self):
            events.append("health")
            return SimpleNamespace(
                arm_state=7, servoing_mode=2, fault_bank_a=0, fault_bank_b=0, ready=ready
            )

        def read_pose(self):
            events.append("pose")
            return ((0.1, 0.2, 0.3), (0.0, 0.0, 0.0, 1.0))

        def close(self):
            events.append("close")

    monkeypatch.setattr(check_kortex, "KortexDevice", Device)
    assert check_kortex.check() == (0 if ready else 1)
    assert events == ["open", "health", "pose", "close"]
    output = capsys.readouterr().out
    assert f"Motion adapter health criteria: {'PASS' if ready else 'NOT READY'}" in output
    if not ready:
        assert (
            "Expected servoing-ready state, single-level servoing, and clear fault banks" in output
        )
    assert "Watchdog, physical stop behavior and safety were not checked" in output


def test_kinova_check_closes_on_read_failure(monkeypatch):
    events = []
    device = SimpleNamespace(
        open=lambda: events.append("open"),
        read_health=lambda: (_ for _ in ()).throw(RuntimeError("health unavailable")),
        close=lambda: events.append("close"),
    )
    monkeypatch.setattr(check_kortex, "KortexDevice", lambda: device)
    with pytest.raises(RuntimeError, match="health unavailable"):
        check_kortex.check()
    assert events == ["open", "close"]


def test_falcon_check_runs_without_site_packages_or_dds(tmp_path):
    (tmp_path / "pynifalcon.py").write_text(
        """
from types import SimpleNamespace
class FalconDeviceBridge:
    def getCount(self): return 1
    def open(self, index): return index == 0
    def loadFirmware(self): return True
    def setHomingMode(self, enabled): pass
    def runIOLoop(self, flags): return True
    def isHomed(self): return True
    def getPosition(self): return SimpleNamespace(x=0.1, y=0.2, z=0.3)
    def getButtons(self): return 1
    def close(self): pass
"""
    )
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-S", str(MODULE_DIR / "tools" / "check_falcon.py")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Falcon connection and homing: OK" in result.stdout
    assert "button bitfield: 0x1" in result.stdout


def test_falcon_check_homes_only_when_requested(monkeypatch, capsys):
    class Device:
        homing_state = "WAITING"

        def open(self):
            return True

        def read(self):
            if self.homing_state == "HOMING":
                return ((0.1, 0.2, 0.3), 0)
            return None

        def start_homing(self):
            self.homing_state = "HOMING"
            return True

        def close(self):
            pass

    monkeypatch.setattr(check_falcon, "FalconInput", Device)
    monkeypatch.setattr(check_falcon.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="--home"):
        check_falcon.check()
    assert check_falcon.check(home=True) == 0
    assert "fully out" in capsys.readouterr().out


def test_kinova_check_runs_without_dds_or_motion_rpc():
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(MODULE_DIR / "src"), str(MODULE_DIR / "tools"))),
        "KORTEX_IP": "192.0.2.10",
        "KORTEX_USERNAME": "test",
        "KORTEX_PASSWORD": "test",
    }
    script = """
import sys
from types import SimpleNamespace as NS
import KortexDevice
import check_kortex
class Transport:
    def connect(self, ip, port): pass
    def disconnect(self): pass
class Session:
    def __init__(self, router): pass
    def CreateSession(self, info): pass
    def CloseSession(self): pass
class BaseClient:
    def __init__(self, router): pass
    def GetArmState(self, *, options): return NS(active_state=7)
    def GetServoingMode(self, *, options): return NS(servoing_mode=2)
class Cyclic:
    def __init__(self, router): pass
    def RefreshFeedback(self, *, options):
        return NS(base=NS(fault_bank_a=0, fault_bank_b=0,
            tool_pose_x=0.1, tool_pose_y=0.2, tool_pose_z=0.3,
            tool_pose_theta_x=0, tool_pose_theta_y=0, tool_pose_theta_z=0))
KortexDevice._load_kortex_api = lambda: NS(
    RouterClient=lambda transport: transport, RouterClientSendOptions=NS,
    SessionManager=Session, TCPTransport=Transport, UDPTransport=Transport,
    BaseClient=BaseClient, BaseCyclicClient=Cyclic,
    Session=NS(CreateSessionInfo=NS), Base=NS(SINGLE_LEVEL_SERVOING=2),
    Common=NS(ARMSTATE_IN_FAULT=4, ARMSTATE_SERVOING_READY=7))
sys.argv = ['check_kortex.py']
raise SystemExit(check_kortex.main())
"""
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Kinova connection: OK" in result.stdout
    assert "Motion adapter health criteria: PASS" in result.stdout


def test_check_failure_reports_error_and_closes(monkeypatch, capsys):
    events = []
    device = SimpleNamespace(
        open=lambda: events.append("open") or True,
        read=lambda: (_ for _ in ()).throw(RuntimeError("device not homed")),
        close=lambda: events.append("close"),
    )
    monkeypatch.setattr(check_falcon, "FalconInput", lambda: device)
    monkeypatch.setattr(sys, "argv", ["check_falcon.py"])
    assert check_falcon.main() == 1
    assert events == ["open", "close"]
    assert "Falcon check failed: device not homed" in capsys.readouterr().err
