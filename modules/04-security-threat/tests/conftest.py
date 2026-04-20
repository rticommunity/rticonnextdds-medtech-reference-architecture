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
"""Shared fixtures for Module 04 — Security Threat tests.

Provides environment setup for both Module 01 OR applications (in secure
and non-secure modes) and Module 04 threat applications.  Auto-skips if
security artifacts have not been generated.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path bootstrapping
# ---------------------------------------------------------------------------
MODULE_DIR = Path(__file__).resolve().parent.parent  # modules/04-security-threat
REPO_ROOT = MODULE_DIR.parent.parent
MODULE_01_DIR = MODULE_DIR.parent / "01-operating-room"
SYSTEM_ARCH_DIR = REPO_ROOT / "system_arch"
THREAT_SRC_DIR = MODULE_DIR / "src"
OR_SRC_DIR = MODULE_01_DIR / "src"

# Add centralized scripts package to import path
sys.path.insert(0, str(REPO_ROOT / "resource" / "python"))

from scripts import module_runner  # noqa: E402

# ---------------------------------------------------------------------------
# Auto-skip logic
# ---------------------------------------------------------------------------


def _or_security_artifacts_exist() -> bool:
    """Check that Module 01 security artifacts exist."""
    domain_scope_dir = SYSTEM_ARCH_DIR / "security" / "domain_scope"
    return domain_scope_dir.is_dir() and any(domain_scope_dir.rglob("*.p7s"))


def _threat_artifacts_exist() -> bool:
    """Check that Module 04 threat security artifacts exist."""
    rogue_ca = MODULE_DIR / "security" / "ca" / "RogueCa" / "certs" / "RogueCa" / "RogueCa.crt"
    return rogue_ca.is_file()


def _has_display() -> bool:
    if sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def pytest_collection_modifyitems(config, items):
    has_security = _or_security_artifacts_exist() and _threat_artifacts_exist()
    has_display = _has_display()

    skip_sec = pytest.mark.skip(
        reason="Security artifacts not generated (run setup_security.py and setup_threat_security.py)"
    )
    skip_gui = pytest.mark.skip(reason="No graphical display available")

    for item in items:
        if not has_security:
            item.add_marker(skip_sec)
        if "gui" in item.keywords and not has_display:
            item.add_marker(skip_gui)


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------


class ProcessManager:
    """Launch and track child processes, ensuring cleanup on teardown."""

    def __init__(self, env: dict, apps: dict[str, list[str]], cwd: Path):
        self.env = env
        self.apps = apps
        self.cwd = cwd
        self._children: list[subprocess.Popen] = []

    def start(self, cmd, cwd: Path | None = None, extra_env: dict | None = None, **kwargs) -> subprocess.Popen:
        run_env = {**self.env, **(extra_env or {})}
        proc = subprocess.Popen(
            cmd if isinstance(cmd, list) else [cmd],
            env=run_env,
            cwd=cwd or self.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs,
        )
        self._children.append(proc)
        return proc

    def start_app(self, name: str, **kwargs) -> subprocess.Popen:
        """Start an application by its module.json name."""
        return self.start(self.apps[name], **kwargs)

    def shutdown_all(self):
        for p in self._children:
            if p.poll() is None:
                p.terminate()
        deadline = time.monotonic() + 5
        for p in self._children:
            remaining = max(0, deadline - time.monotonic())
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=2)
        self._children.clear()


def wait_for_process_ready(proc, timeout_sec: float = 5.0):
    """Wait until *proc* survives for *timeout_sec* or exits early."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.25)


# ---------------------------------------------------------------------------
# Environment fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def or_env_nonsecure():
    """Module 01 OR env — non-secure mode."""
    env, apps = module_runner.load_module_config(MODULE_01_DIR, flags={"security": False})
    return env, apps


@pytest.fixture(scope="session")
def or_env_secure():
    """Module 01 OR env — secure mode."""
    env, apps = module_runner.load_module_config(MODULE_01_DIR, flags={"security": True})
    return env, apps


@pytest.fixture(scope="session")
def threat_env():
    """Module 04 threat app environment.

    Prepends Types.xml to NDDS_QOS_PROFILES so that type definitions are
    available to the XML parser when creating participants from config.
    """
    env, apps = module_runner.load_module_config(MODULE_DIR)
    # Types.xml is required for create_participant_from_config to resolve type_ref
    types_xml = str(SYSTEM_ARCH_DIR / "Types.xml")
    env["NDDS_QOS_PROFILES"] = types_xml + ";" + env["NDDS_QOS_PROFILES"]
    return env, apps


@pytest.fixture()
def or_pm_nonsecure(or_env_nonsecure):
    env, apps = or_env_nonsecure
    pm = ProcessManager(env, apps, cwd=MODULE_01_DIR)
    yield pm
    pm.shutdown_all()


@pytest.fixture()
def or_pm_secure(or_env_secure):
    env, apps = or_env_secure
    pm = ProcessManager(env, apps, cwd=MODULE_01_DIR)
    yield pm
    pm.shutdown_all()


# ---------------------------------------------------------------------------
# DDS observer subprocess helper
# ---------------------------------------------------------------------------


def run_dds_observer(
    env: dict,
    cwd: Path,
    topic_name: str,
    type_class: str,
    qos_profile: str,
    timeout_sec: float = 12.0,
    min_count: int = 1,
) -> list[dict]:
    """Run a DDS subscriber in a subprocess and return collected data.

    Uses a fresh process to avoid QosProvider XML namespace collisions.
    """
    script = f"""\
import sys, time, json
sys.path.insert(0, "{OR_SRC_DIR}")
import rti.connextdds as dds
from Types import {type_class}, idl

provider = dds.QosProvider.default
participant_qos = provider.participant_qos_from_profile("DpQosLib::Test")
participant = dds.DomainParticipant(domain_id=0, qos=participant_qos)

ts = idl.get_type_support({type_class})
dds.DomainParticipant.register_idl_type({type_class}, ts.type_name)
topic = dds.Topic(participant, "{topic_name}", {type_class})
dr_qos = provider.datareader_qos_from_profile("{qos_profile}")
subscriber = dds.Subscriber(participant)
reader = dds.DataReader(subscriber, topic, dr_qos)

collected = []
deadline = time.monotonic() + {timeout_sec}
while time.monotonic() < deadline and len(collected) < {min_count}:
    for s in reader.take():
        if s.info.valid:
            collected.append(str(s.data))
    if len(collected) < {min_count}:
        time.sleep(0.1)

participant.close()
print(json.dumps(collected))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=int(timeout_sec) + 10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"DDS observer failed (exit {result.returncode}):\n{result.stderr}")
    return json.loads(result.stdout.strip())
