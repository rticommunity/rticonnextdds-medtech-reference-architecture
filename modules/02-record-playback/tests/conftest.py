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
"""Shared fixtures for Module 02 — Record/Playback tests.

Provides environment setup, process management for Recording/Replay Service,
and Module 01 application launchers. Auto-skips if RTI services are not found.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path bootstrapping
# ---------------------------------------------------------------------------
MODULE_DIR = Path(__file__).resolve().parent.parent  # modules/02-record-playback
REPO_ROOT = MODULE_DIR.parent.parent  # repo root
MODULE_01_DIR = MODULE_DIR.parent / "01-operating-room"
SYSTEM_ARCH_DIR = REPO_ROOT / "system_arch"

# Reuse centralized scripts package for platform detection and module config
sys.path.insert(0, str(REPO_ROOT / "resource" / "python"))

from scripts import module_runner  # noqa: E402

# ---------------------------------------------------------------------------
# Service detection
# ---------------------------------------------------------------------------


def _find_service_binary(name: str) -> str | None:
    """Return the path to an RTI service binary, or None if not found."""
    nddshome = os.environ.get("NDDSHOME", "")
    if not nddshome:
        return None
    candidate = Path(nddshome) / "bin" / name
    if candidate.is_file():
        return str(candidate)
    # Try with platform suffix on some installs
    for p in (Path(nddshome) / "bin").glob(f"{name}*"):
        if p.is_file() and p.stat().st_mode & 0o111:
            return str(p)
    return None


RECORDING_SERVICE = _find_service_binary("rtirecordingservice")
REPLAY_SERVICE = _find_service_binary("rtireplayservice")


def pytest_collection_modifyitems(config, items):
    """Auto-skip all tests if Recording/Replay Service is not available."""
    if RECORDING_SERVICE and REPLAY_SERVICE:
        return
    skip = pytest.mark.skip(reason="RTI Recording/Replay Service not found in NDDSHOME/bin/")
    for item in items:
        item.add_marker(skip)


# ---------------------------------------------------------------------------
# Process management (mirrors Module 01 ProcessManager)
# ---------------------------------------------------------------------------


class ProcessManager:
    """Launch and track child processes, ensuring cleanup on teardown."""

    def __init__(self, env: dict, apps: dict[str, list[str]], cwd: Path):
        self.env = env
        self.apps = apps
        self.cwd = cwd
        self._children: list[subprocess.Popen] = []

    def start(self, cmd, cwd: Path | None = None, **kwargs) -> subprocess.Popen:
        proc = subprocess.Popen(
            cmd if isinstance(cmd, list) else [cmd],
            env=self.env,
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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def dds_env():
    """Non-secure DDS environment configured from Module 01's module.json."""
    env, apps = module_runner.load_module_config(MODULE_01_DIR, flags={"security": False})
    return env, apps


@pytest.fixture(scope="session")
def dds_env_dict(dds_env):
    """Just the env dict (no apps) for passing to subprocess.run(env=...)."""
    env, _apps = dds_env
    return env


@pytest.fixture()
def proc_manager(dds_env):
    env, apps = dds_env
    pm = ProcessManager(env, apps, cwd=MODULE_DIR)
    yield pm
    pm.shutdown_all()


RECORDING_DIR = MODULE_DIR / "or_recording"


@pytest.fixture()
def clean_recording_dir():
    """Ensure recording directory is clean before and after tests."""
    if RECORDING_DIR.is_dir():
        shutil.rmtree(RECORDING_DIR)
    yield RECORDING_DIR
    if RECORDING_DIR.is_dir():
        shutil.rmtree(RECORDING_DIR)
