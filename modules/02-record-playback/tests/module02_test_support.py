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
import signal
import subprocess
import sys
import time
from pathlib import Path

# Reuse centralized scripts package for platform detection and module config
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent.parent / "resource" / "python")
)


# ---------------------------------------------------------------------------
# Path bootstrapping
# ---------------------------------------------------------------------------
MODULE_DIR = Path(__file__).resolve().parent.parent  # modules/02-record-playback
REPO_ROOT = MODULE_DIR.parent.parent  # repo root
MODULE_01_DIR = MODULE_DIR.parent / "01-operating-room"
SYSTEM_ARCH_DIR = REPO_ROOT / "system_arch"

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


def _kill_orphan_recording_services() -> None:
    """Best-effort cleanup for forked recording/replay service processes.

    RTI Recording Service can outlive its direct launcher process, so this
    reaps any service process tied to this module's XML config files.
    """
    result = subprocess.run(
        ["pgrep", "-af", "rtirecordingservice"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return

    markers = {
        str(MODULE_DIR / "RecordingServiceConfiguration.xml"),
        str(MODULE_DIR / "ReplayServiceConfiguration.xml"),
    }

    pids: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        pid_str, cmd = parts
        if any(marker in cmd for marker in markers):
            try:
                pids.append(int(pid_str))
            except ValueError:
                continue

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    time.sleep(0.5)

    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


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
        kwargs.setdefault("start_new_session", True)
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
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    p.terminate()
        deadline = time.monotonic() + 2
        for p in self._children:
            remaining = max(0, deadline - time.monotonic())
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    p.kill()
                p.wait(timeout=2)

        _kill_orphan_recording_services()
        self._children.clear()


def wait_for_process_ready(proc, timeout_sec: float = 5.0):
    """Wait until *proc* produces output, exits, or *timeout_sec* expires."""
    import selectors

    if proc.poll() is not None:
        return

    sel = selectors.DefaultSelector()
    try:
        for stream in (proc.stdout, proc.stderr):
            if stream and hasattr(stream, "fileno"):
                sel.register(stream, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return
            remaining = max(0, deadline - time.monotonic())
            if sel.get_map():
                events = sel.select(timeout=min(remaining, 0.25))
                if events:
                    return
            else:
                time.sleep(min(remaining, 0.25))
    finally:
        sel.close()


RECORDING_DIR = MODULE_DIR / "or_recording"
