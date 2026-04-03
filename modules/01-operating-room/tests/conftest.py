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
MODULE_DIR = Path(__file__).resolve().parent.parent          # modules/01-operating-room
REPO_ROOT = MODULE_DIR.parent.parent                         # repo root
SCRIPTS_DIR = MODULE_DIR / "scripts"
SRC_DIR = MODULE_DIR / "src"
SYSTEM_ARCH_DIR = REPO_ROOT / "system_arch"
SECURITY_DIR = SYSTEM_ARCH_DIR / "security"

# Make scripts/ and system_arch/scripts/ importable
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SYSTEM_ARCH_DIR / "scripts"))

import platform_setup  # noqa: E402
import xml_setup       # noqa: E402

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
    signed_dir = SECURITY_DIR / "xml" / "signed"
    if not signed_dir.is_dir():
        return False
    # At minimum we need the governance and one participant's permissions
    return any(signed_dir.glob("*.p7s"))


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests based on environment capabilities."""
    skip_gui = pytest.mark.skip(reason="No graphical display available")
    skip_sec = pytest.mark.skip(reason="Security artifacts not generated (run setup_security.py)")

    has_display = _has_display()
    has_security = _security_artifacts_exist()

    for item in items:
        if "gui" in item.keywords and not has_display:
            item.add_marker(skip_gui)
        if "secure" in item.keywords and not has_security:
            item.add_marker(skip_sec)


# ---------------------------------------------------------------------------
# Environment fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def dds_env():
    """Session-scoped environment dict with NDDS_QOS_PROFILES configured (non-secure)."""
    original_cwd = os.getcwd()
    os.chdir(MODULE_DIR)
    try:
        env = xml_setup.setup_env(security=False)
    finally:
        os.chdir(original_cwd)
    return env


@pytest.fixture(scope="session")
def dds_env_secure():
    """Session-scoped environment dict with NDDS_QOS_PROFILES + DDS Security."""
    original_cwd = os.getcwd()
    os.chdir(MODULE_DIR)
    try:
        env = xml_setup.setup_env(security=True)
    finally:
        os.chdir(original_cwd)
    return env


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

class ProcessManager:
    """Launch and track child processes, ensuring cleanup on teardown."""

    def __init__(self, env: dict, cwd: Path = MODULE_DIR):
        self.env = env
        self.cwd = cwd
        self._children: list[subprocess.Popen] = []

    def start(self, cmd, extra_env: dict | None = None, **kwargs) -> subprocess.Popen:
        """Start a subprocess tracked for cleanup."""
        if isinstance(cmd, str):
            cmd = [cmd]
        run_env = {**self.env, **(extra_env or {})}
        proc = subprocess.Popen(
            cmd,
            env=run_env,
            cwd=self.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs,
        )
        self._children.append(proc)
        return proc

    def start_cpp(self, name: str, **kwargs) -> subprocess.Popen:
        """Start a compiled C++ application by name."""
        return self.start([platform_setup.find_executable(name)], **kwargs)

    def start_python(self, script: str, **kwargs) -> subprocess.Popen:
        """Start a Python application by script path (relative to module dir)."""
        extra_env = kwargs.pop("extra_env", None)
        return self.start(
            [sys.executable, str(SRC_DIR / script)],
            extra_env=extra_env,
            **kwargs,
        )

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
    pm = ProcessManager(dds_env)
    yield pm
    pm.shutdown_all()


@pytest.fixture()
def proc_manager_secure(dds_env_secure):
    """Yield a ProcessManager wired to the secure DDS environment."""
    pm = ProcessManager(dds_env_secure)
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

    # Ensure NDDS_QOS_PROFILES is set in this process for QosProvider to use
    os.environ["NDDS_QOS_PROFILES"] = dds_env["NDDS_QOS_PROFILES"]

    provider = dds.QosProvider.default
    participant_qos = provider.participant_qos_from_profile(
        "DpQosLib::Test"
    )
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
import sys, time, json
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
            val = getattr(s.data, "{extract_field or ''}") if "{extract_field or ''}" else str(s.data)
            collected.append(str(val))
    if len(collected) < {min_count}:
        time.sleep(0.1)

participant.close()
print(json.dumps(collected))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=dds_env_secure,
        cwd=MODULE_DIR,
        capture_output=True,
        text=True,
        timeout=int(timeout_sec) + 10,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Secure DDS subscriber subprocess failed "
            f"(exit {result.returncode}):\n{result.stderr}"
        )
    import json
    return json.loads(result.stdout.strip())


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
