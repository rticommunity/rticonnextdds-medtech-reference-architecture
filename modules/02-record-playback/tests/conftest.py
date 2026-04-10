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

# Reuse Module 01's scripts for environment setup and platform detection
sys.path.insert(0, str(MODULE_01_DIR / "scripts"))
sys.path.insert(0, str(SYSTEM_ARCH_DIR / "scripts"))

import platform_setup  # noqa: E402
import xml_setup  # noqa: E402

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

    def __init__(self, env: dict, cwd: Path):
        self.env = env
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

    def start_module01_cpp(self, name: str) -> subprocess.Popen:
        return self.start(
            [platform_setup.find_executable(name)],
            cwd=MODULE_01_DIR,
        )

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def dds_env():
    """Non-secure DDS environment configured from Module 01's xml_setup."""
    original_cwd = os.getcwd()
    os.chdir(MODULE_01_DIR)
    try:
        env = xml_setup.setup_env(security=False)
    finally:
        os.chdir(original_cwd)
    return env


@pytest.fixture()
def proc_manager(dds_env):
    pm = ProcessManager(dds_env, cwd=MODULE_DIR)
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
