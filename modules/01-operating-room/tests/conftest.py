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
"""Shared fixtures for Module 01 — Digital Operating Room tests.

Provides environment setup, process management, DDS participant helpers,
and automatic skip logic for GUI / security markers.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path bootstrapping — mirror what the launch scripts do
# ---------------------------------------------------------------------------
MODULE_DIR = Path(__file__).resolve().parent.parent  # modules/01-operating-room
REPO_ROOT = MODULE_DIR.parent.parent  # repo root
SRC_DIR = MODULE_DIR / "src"
SYSTEM_ARCH_DIR = REPO_ROOT / "system_arch"
SECURITY_DIR = SYSTEM_ARCH_DIR / "security"

# Make resource/python/ importable — the `scripts` package contains
# module_runner (centralized since origin/main).
sys.path.insert(0, str(REPO_ROOT / "resource" / "python"))

from scripts import module_runner  # noqa: E402

# ---------------------------------------------------------------------------
# Auto-skip helpers for custom markers
# ---------------------------------------------------------------------------


def _has_display() -> bool:
    """Return True when a graphical display is likely available."""
    if sys.platform == "darwin":
        # macOS always has a WindowServer when logged in
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _security_artifacts_exist() -> bool:
    """Return True when setup_security.py has been run for module 01."""
    # Signed governance lives at  domain_scope/<scope>/governance/<name>/signed/<issuer>/<name>.p7s
    # Signed permissions live at  domain_scope/<scope>/permissions/<role>/signed/<issuer>/<role>.p7s
    domain_scope_dir = SECURITY_DIR / "domain_scope"
    if not domain_scope_dir.is_dir():
        return False
    # At minimum we need the governance and one participant's permissions
    return any(domain_scope_dir.rglob("*.p7s"))


def _security_plugin_available() -> bool:
    """Return True when the DDS Security plugin is fully usable.

    Requires:
    1. ``libnddssecurity`` shared library
    2. Bundled OpenSSL ``release/lib`` directory
    3. A valid ``rti_license.dat`` in NDDSHOME (Security Plugins are
       a licensed feature).
    """
    nddshome = os.environ.get("NDDSHOME")
    if not nddshome:
        return False
    nddshome_path = Path(nddshome)
    has_plugin = bool(list(nddshome_path.glob("lib/*/libnddssecurity.*")))
    has_openssl = any((arch / "release" / "lib").is_dir() for arch in nddshome_path.glob("third_party/openssl-*/*"))
    has_license = (nddshome_path / "rti_license.dat").is_file() and (
        (nddshome_path / "rti_license.dat").stat().st_size > 0
    )
    return has_plugin and has_openssl and has_license


def pytest_collection_modifyitems(config, items):
    """Fail tests when prerequisites are missing instead of silently skipping."""
    fail_gui = pytest.mark.xfail(
        reason="No graphical display available (need DISPLAY or WAYLAND_DISPLAY)",
        strict=True,
        run=False,
    )
    fail_sec_artifacts = pytest.mark.xfail(
        reason="Security artifacts not generated (run setup_security.py)",
        strict=True,
        run=False,
    )
    fail_sec_plugin = pytest.mark.xfail(
        reason="DDS Security plugin not fully installed (need libnddssecurity, OpenSSL, rti_license.dat)",
        strict=True,
        run=False,
    )

    has_display = _has_display()

    for item in items:
        if "gui" in item.keywords and not has_display:
            item.add_marker(fail_gui)
        if "secure" in item.keywords and not _security_artifacts_exist():
            item.add_marker(fail_sec_artifacts)
        elif "secure" in item.keywords and not _security_plugin_available():
            item.add_marker(fail_sec_plugin)


# ---------------------------------------------------------------------------
# Environment fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def dds_env():
    """Session-scoped environment dict with NDDS_QOS_PROFILES configured (non-secure)."""
    env, apps = module_runner.load_module_config(MODULE_DIR, flags={"security": False})
    return env, apps


@pytest.fixture(scope="session")
def dds_env_secure():
    """Session-scoped environment dict with NDDS_QOS_PROFILES + DDS Security."""
    env, apps = module_runner.load_module_config(MODULE_DIR, flags={"security": True})
    # Use absolute path so DDS file: URLs resolve regardless of CWD
    env["RTI_SECURITY_ARTIFACTS_DIR"] = str(SECURITY_DIR)
    return env, apps


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------


class ProcessManager:
    """Launch and track child processes, ensuring cleanup on teardown."""

    def __init__(self, env: dict, apps: dict[str, list[str]], cwd: Path = MODULE_DIR):
        self.env = env
        self.apps = apps
        self.cwd = cwd
        self._children: list[subprocess.Popen] = []

    def start(self, cmd, extra_env: dict | None = None, **kwargs) -> subprocess.Popen:
        """Start a subprocess tracked for cleanup."""
        if isinstance(cmd, str):
            cmd = [cmd]
        run_env = {**self.env, **(extra_env or {})}
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
        proc = subprocess.Popen(
            cmd,
            env=run_env,
            cwd=self.cwd,
            **kwargs,
        )
        self._children.append(proc)
        return proc

    def start_app(self, name: str, extra_env: dict | None = None, **kwargs) -> subprocess.Popen:
        """Start an application by its module.json name."""
        cmd = self.apps[name]
        return self.start(cmd, extra_env=extra_env, **kwargs)

    def shutdown_all(self):
        """Gracefully terminate then kill all tracked processes."""
        for p in self._children:
            if p.poll() is None:
                p.terminate()
        # Give processes 3 seconds to exit gracefully
        deadline = time.monotonic() + 3
        for p in self._children:
            remaining = max(0, deadline - time.monotonic())
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=2)
        self._children.clear()


@pytest.fixture()
def proc_manager(dds_env):
    """Yield a ProcessManager wired to the non-secure DDS environment."""
    env, apps = dds_env
    pm = ProcessManager(env, apps)
    yield pm
    pm.shutdown_all()


@pytest.fixture()
def proc_manager_secure(dds_env_secure):
    """Yield a ProcessManager wired to the secure DDS environment."""
    env, apps = dds_env_secure
    pm = ProcessManager(env, apps)
    yield pm
    pm.shutdown_all()


# ---------------------------------------------------------------------------
# DDS helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def dds_participant(dds_env):
    """Create a lightweight DDS DomainParticipant for test observation.

    Uses the programmatic API with the QoS profiles already loaded via
    NDDS_QOS_PROFILES so that type definitions resolve correctly.
    """
    import rti.connextdds as dds

    env, _apps = dds_env
    # Ensure NDDS_QOS_PROFILES is set in this process for QosProvider to use
    os.environ["NDDS_QOS_PROFILES"] = env["NDDS_QOS_PROFILES"]

    provider = dds.QosProvider.default
    participant_qos = provider.participant_qos_from_profile("DpQosLib::Test")
    participant = dds.DomainParticipant(domain_id=0, qos=participant_qos)
    yield participant
    participant.close()


def run_dds_subscriber_secure(
    dds_env_secure: dict,
    topic_name: str,
    type_module: str,
    type_class: str,
    qos_profile: str,
    timeout_sec: float = 15.0,
    min_count: int = 1,
    extract_field: str | None = None,
) -> list[str]:
    """Run a DDS subscriber in a **subprocess** and return collected data.

    The RTI XML parser has a global namespace that cannot be reset.  Once
    the non-secure profiles are loaded in this pytest process, we cannot
    load the secure set (they share ``Qos.xml`` which defines the same
    profile names).  Running the observer in a subprocess gives us a clean
    XML namespace.

    Returns a list of string representations of the collected samples
    (or values of *extract_field* if specified).
    """
    script = f"""\
import sys, os, time, json
sys.path.insert(0, "src")
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
            val = getattr(s.data, "{extract_field or ""}") if "{extract_field or ""}" else str(s.data)
            collected.append(str(val))
    if len(collected) < {min_count}:
        time.sleep(0.1)

participant.close()
print(json.dumps(collected))
"""
    # The pip rti.connext package bundles its own libnddsc.so (loaded via RPATH),
    # which may lack trust-plugin symbols needed by the system-installed
    # libnddssecurity.so.  LD_PRELOAD forces the system Connext core library
    # so that dlopen("libnddssecurity.so") can resolve all symbols.
    sub_env = dict(dds_env_secure)
    nddshome = os.environ.get("NDDSHOME", "")
    if nddshome and sys.platform == "linux":
        nddshome_path = Path(nddshome)
        preload_libs = []
        for lib_name in ("libnddsc.so", "libnddscpp2.so"):
            candidates = list(nddshome_path.glob(f"lib/*/{lib_name}"))
            if candidates:
                preload_libs.append(str(candidates[0]))
        if preload_libs:
            sub_env["LD_PRELOAD"] = ":".join(preload_libs)

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=sub_env,
        cwd=MODULE_DIR,
        capture_output=True,
        text=True,
        timeout=int(timeout_sec) + 10,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Secure DDS subscriber subprocess failed (exit {result.returncode}):\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    import json

    # DDS security may print warnings to stdout after our JSON line.
    # Extract only lines that look like JSON arrays.
    lines = [line for line in result.stdout.strip().splitlines() if line.startswith("[")]
    if not lines:
        raise RuntimeError(f"No JSON output from secure subscriber.\nstdout: {result.stdout}\nstderr: {result.stderr}")
    return json.loads(lines[0])


def wait_for_data(reader, timeout_sec: float = 5.0, min_count: int = 1):
    """Poll a DataReader until *min_count* samples arrive or *timeout_sec* expires.

    Returns the list of collected data samples (may be empty on timeout).
    """
    import rti.connextdds as dds

    collected = []
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline and len(collected) < min_count:
        samples = reader.take()
        for s in samples:
            if s.info.valid:
                collected.append(s.data)
        if len(collected) < min_count:
            time.sleep(0.1)
    return collected


def wait_for_process_ready(proc, timeout_sec: float = 5.0):
    """Wait until *proc* survives for *timeout_sec* or exits early.

    Polls ``proc.poll()`` every 250ms.  Returns as soon as either:
    - The process exits (caller should check ``proc.returncode``).
    - The full *timeout_sec* elapses with the process still running (success
      for smoke tests — the process survived its startup window).
    """
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.25)


def wait_for_device_status(
    reader,
    expected_devices: set,
    timeout_sec: float = 30.0,
):
    """Poll a DeviceStatus DataReader until all *expected_devices* have reported.

    Returns the set of DeviceType values seen.
    """
    seen = set()
    deadline = time.monotonic() + timeout_sec
    while seen != expected_devices and time.monotonic() < deadline:
        for sample in reader.take():
            if sample.info.valid:
                seen.add(sample.data.device)
        time.sleep(0.25)
    return seen


_registered_types: set[str] = set()


def _register_type_once(type_cls):
    """Register an IDL type, skipping if already registered."""
    import rti.connextdds as dds
    from Types import idl

    type_name = idl.get_type_support(type_cls).type_name
    if type_name in _registered_types:
        return
    try:
        dds.DomainParticipant.register_idl_type(type_cls, type_name)
    except dds.Error:
        pass  # already registered at the DDS level
    _registered_types.add(type_name)


def create_reader(participant, topic_name: str, type_cls, qos_profile: str):
    """Create a DataReader on *participant* for the given topic and type."""
    import rti.connextdds as dds

    _register_type_once(type_cls)

    provider = dds.QosProvider.default
    topic = dds.Topic(participant, topic_name, type_cls)
    dr_qos = provider.datareader_qos_from_profile(qos_profile)
    subscriber = dds.Subscriber(participant)
    return dds.DataReader(subscriber, topic, dr_qos)


def create_writer(participant, topic_name: str, type_cls, qos_profile: str):
    """Create a DataWriter on *participant* for the given topic and type."""
    import rti.connextdds as dds

    _register_type_once(type_cls)

    provider = dds.QosProvider.default
    topic = dds.Topic(participant, topic_name, type_cls)
    dw_qos = provider.datawriter_qos_from_profile(qos_profile)
    publisher = dds.Publisher(participant)
    return dds.DataWriter(publisher, topic, dw_qos)
