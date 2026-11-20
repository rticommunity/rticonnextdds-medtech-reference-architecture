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

"""Shared DDS test utilities for all modules.

Provides isolated QosProvider creation, process management, and efficient
WaitSet-based helpers for observing DDS communication in tests.
"""

from __future__ import annotations

import os
import selectors as _selectors
import signal
import subprocess
import sys
import threading as _threading
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import rti.connextdds as dds

from tools.medtech import platform_setup

_PROJECT_ROOT = platform_setup.PROJECT_ROOT
_SYSTEM_SRC = _PROJECT_ROOT / "system" / "src"
if str(_SYSTEM_SRC) not in sys.path:
    sys.path.insert(0, str(_SYSTEM_SRC))

_GENERATED_SYSTEM = platform_setup.generated_system_path()
sys.path.insert(0, str(_GENERATED_SYSTEM / "python"))
from MedTech import Device, Patient, Robot  # noqa: E402
from MedTechTypes import register_type  # noqa: E402

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------


# Timeouts for waiting on processes to become ready.
PROCESS_WAIT_TIMEOUT = 3.0
RTISERVICE_PROCESS_WAIT_TIMEOUT = 2.0


def disable_monitoring() -> None:
    """Disable RTI Monitoring Library 2.0 on the DomainParticipantFactory.

    Connext 7.7.0 enables monitoring by default.  When tests create secure
    participants in-process via an isolated QosProvider, the factory-level
    QoS that normally disables monitoring (loaded from NDDS_QOS_PROFILES) is
    absent.  Without this call the DDS runtime refuses to enable a secure
    participant whose monitoring channel is unsecured.

    Safe to call more than once — subsequent calls are no-ops.
    """
    factory_qos = dds.DomainParticipant.participant_factory_qos
    if not factory_qos.monitoring.enable:
        return
    factory_qos.monitoring.enable = False
    dds.DomainParticipant.participant_factory_qos = factory_qos


def security_plugin_available() -> bool:
    """Return True when the probe does not report a Security plugin load failure.

    Runs the check in a subprocess to avoid modifying global DDS state
    (logger, participant factory QoS) in the test process. Participant creation
    may fail because the probe deliberately does not supply security artifacts.
    Result is cached after the first call.
    """
    if not hasattr(security_plugin_available, "_cached"):
        _check_script = Path(__file__).resolve().parent / "check_security.py"
        result = subprocess.run(
            [sys.executable, str(_check_script)],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(
                f"Security plugin probe failed with exit code {result.returncode}:\n"
                f"{result.stderr or result.stdout}"
            )
        if result.returncode == 1:
            print(result.stderr or "Security plugin failed to load.", file=sys.stderr)
        security_plugin_available._cached = result.returncode == 0
    return security_plugin_available._cached


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------


class ProcessManager:
    """Launch and track child processes, ensuring cleanup on teardown."""

    def __init__(
        self,
        env: dict,
        apps: dict[str, list[str]],
        cwd: Path,
        shutdown_grace_sec: float = 2.0,
        shutdown_hook: Callable[[], None] | None = None,
    ):
        self.env = env
        self.apps = apps
        self.cwd = cwd
        self._shutdown_grace_sec = shutdown_grace_sec
        self._shutdown_hook = shutdown_hook
        self._children: list[subprocess.Popen] = []

    def start(
        self,
        cmd,
        cwd: Path | None = None,
        extra_env: dict | None = None,
        **kwargs,
    ) -> subprocess.Popen:
        """Start a subprocess tracked for cleanup."""
        if isinstance(cmd, str):
            cmd = [cmd]
        run_env = {**self.env, **(extra_env or {})}
        kwargs.setdefault("start_new_session", True)
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
        proc = subprocess.Popen(
            cmd,
            env=run_env,
            cwd=cwd or self.cwd,
            **kwargs,
        )
        self._children.append(proc)
        return proc

    def start_app(self, name: str, extra_env: dict | None = None, **kwargs) -> subprocess.Popen:
        """Start an application by its module.toml name."""
        cmd = self.apps[name]
        return self.start(cmd, extra_env=extra_env, **kwargs)

    def start_app_ready(
        self, name: str, *, extra_env: dict | None = None, timeout_sec: float | None = None
    ) -> subprocess.Popen:
        """Start an app, wait for readiness, and assert it's still running."""
        proc = self.start_app(name, extra_env=extra_env)
        wait_for_process_ready(proc, timeout_sec=timeout_sec or _default_process_timeout(name))
        assert proc.poll() is None, f"{name} exited early with code {proc.returncode}"
        return proc

    def start_apps_ready(self, apps: list[str | tuple[str, dict]]) -> dict[str, subprocess.Popen]:
        """Start multiple apps, wait for all in parallel, assert all alive.

        *apps* is a list of app names (str) or ``(name, extra_env)`` tuples.
        Returns ``{name: Popen}`` for all launched processes.
        """
        procs: dict[str, subprocess.Popen] = {}
        for app in apps:
            if isinstance(app, str):
                procs[app] = self.start_app(app)
            else:
                name, extra_env = app
                procs[name] = self.start_app(name, extra_env=extra_env)
        status = wait_for_processes_ready(procs)
        crashed = [n for n, alive in status.items() if not alive]
        assert not crashed, f"Apps exited early: {crashed}"
        return procs

    @property
    def children(self) -> list[subprocess.Popen]:
        """List of currently tracked child processes."""
        return self._children

    def shutdown_all(self):
        """Gracefully terminate then kill all tracked processes.

        Raises ``TimeoutError`` if any process survives SIGKILL.
        """
        if not self._children:
            return

        # SIGTERM all process groups
        for p in self._children:
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass

        # Wait for graceful exit within the grace period
        deadline = _time.monotonic() + self._shutdown_grace_sec
        stragglers = []
        for p in self._children:
            try:
                p.wait(timeout=max(0, deadline - _time.monotonic()))
            except subprocess.TimeoutExpired:
                stragglers.append(p)

        # SIGKILL stragglers, then reap
        for p in stragglers:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        for p in stragglers:
            try:
                p.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                raise TimeoutError(f"Process {p.pid} survived SIGKILL")

        if self._shutdown_hook:
            self._shutdown_hook()
        self._children.clear()


def wait_for_process_ready(proc, timeout_sec: float = 5.0):
    """Wait until *proc* produces output, exits, or *timeout_sec* expires.

    Returns as soon as any of these conditions is met:
    - The process writes to stdout or stderr (indicates successful startup).
    - The process exits (caller should check ``proc.returncode``).
    - The full *timeout_sec* elapses with the process still running.
    """
    if proc.poll() is not None:
        return

    sel = _selectors.DefaultSelector()
    try:
        for stream in (proc.stdout, proc.stderr):
            if stream and hasattr(stream, "fileno"):
                sel.register(stream, _selectors.EVENT_READ)
        deadline = _time.monotonic() + timeout_sec
        while _time.monotonic() < deadline:
            if proc.poll() is not None:
                return
            remaining = max(0, deadline - _time.monotonic())
            if sel.get_map():
                events = sel.select(timeout=min(remaining, 0.25))
                if events:
                    return  # output detected — process started
            else:
                _time.sleep(min(remaining, 0.25))
    finally:
        sel.close()


def _default_process_timeout(name: str) -> float:
    """Return the appropriate wait timeout based on process name."""
    if "Service" in name:
        return RTISERVICE_PROCESS_WAIT_TIMEOUT
    return PROCESS_WAIT_TIMEOUT


def wait_for_processes_ready(
    procs: dict[str, subprocess.Popen],
    timeout_fn: Callable[[str], float] = _default_process_timeout,
) -> dict[str, bool]:
    """Wait for multiple processes to become ready in parallel.

    Uses one thread per process so waits overlap.  Returns a dict of
    ``{name: is_running}`` where *is_running* is True if the process is
    still alive after the readiness wait.
    """
    threads = [
        _threading.Thread(
            target=wait_for_process_ready,
            args=(p, timeout_fn(name)),
        )
        for name, p in procs.items()
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return {name: p.poll() is None for name, p in procs.items()}


def wait_for_device_status(
    reader,
    expected_devices: set,
    device_statuses: Optional[list["Device.DeviceStatuses"]] = None,
    timeout_sec: float = 5.0,
) -> set:
    """Wait until all *expected_devices* have reported a DeviceStatus.

    Reads the current cache once, then waits for unread samples.
    Returns the set of DeviceType values seen.
    """
    seen: set = set()
    if timeout_sec <= 0:
        return seen

    def collect(samples):
        for data in samples:
            if device_statuses is None or data.status in device_statuses:
                seen.add(data.device)

    collect(reader.read_data())
    condition = dds.ReadCondition(reader, dds.DataState.new_data)
    waitset = dds.WaitSet()
    waitset += condition
    deadline = _time.monotonic() + timeout_sec
    try:
        while not expected_devices.issubset(seen):
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                break
            try:
                active = waitset.wait(dds.Duration.from_seconds(remaining))
            except dds.TimeoutError:
                break
            if not active:
                break
            collect(reader.select().condition(condition).read_data())
    finally:
        waitset -= condition
    return seen


def make_isolated_qos_provider(*xml_files: str) -> dds.QosProvider:
    """Create a QosProvider that loads only the specified XML files.

    Ignores NDDS_QOS_PROFILES and USER_QOS_PROFILES.xml to prevent
    cross-test XML namespace contamination.
    """
    params = dds.QosProviderParams()
    params.ignore_environment_profile = True
    params.ignore_user_profile = True
    params.url_profile = [str(Path(f).resolve()) for f in xml_files]
    return dds.QosProvider(params)


def wait_for_writer_match(writer, timeout_sec: float = 2.0, count: int = 1) -> bool:
    """Block until publication_matched_status.current_count > 0.

    Uses WaitSet + StatusCondition — no polling, no data writes needed.
    Returns True if matched within timeout, False otherwise.
    """
    if writer.publication_matched_status.current_count >= count:
        return True

    matched = False
    status_condition = dds.StatusCondition(writer)
    status_condition.enabled_statuses = dds.StatusMask.PUBLICATION_MATCHED

    def on_match(_):
        nonlocal matched
        if writer.publication_matched_status.current_count >= count:
            matched = True

    status_condition.set_handler(on_match)
    waitset = dds.WaitSet()
    waitset += status_condition

    remaining = timeout_sec
    while not matched and remaining > 0:
        start = _time.monotonic()
        try:
            waitset.dispatch(dds.Duration.from_seconds(remaining))
        except dds.TimeoutError:
            break
        remaining -= _time.monotonic() - start

    return matched or writer.publication_matched_status.current_count >= count


def wait_for_reader_match(reader, timeout_sec: float = 2.0, count: int = 1) -> bool:
    """Block until subscription_matched_status.current_count > 0.

    Useful for security tests where we only care whether a reader
    matched a writer (not about actual data).
    """
    if reader.subscription_matched_status.current_count >= count:
        return True

    matched = False
    status_condition = dds.StatusCondition(reader)
    status_condition.enabled_statuses = dds.StatusMask.SUBSCRIPTION_MATCHED

    def on_match(_):
        nonlocal matched
        if reader.subscription_matched_status.current_count >= count:
            matched = True

    status_condition.set_handler(on_match)
    waitset = dds.WaitSet()
    waitset += status_condition

    remaining = timeout_sec
    while not matched and remaining > 0:
        start = _time.monotonic()
        try:
            waitset.dispatch(dds.Duration.from_seconds(remaining))
        except dds.TimeoutError:
            break
        remaining -= _time.monotonic() - start

    return matched or reader.subscription_matched_status.current_count >= count


def wait_for_samples(
    reader,
    n: int = 1,
    timeout_sec: float = 2.0,
    filter_fn=None,
    read: bool = False,
) -> list:
    """Wait until N samples arrive on a reader, or timeout.

    Works with both typed DataReaders and DynamicData DataReaders.
    Reads or takes the current cache once, then waits for unread samples.
    Returns collected sample data objects (may be fewer than N on timeout).

    If *filter_fn* is provided, only samples for which ``filter_fn(sample)``
    returns True are counted toward *n* and included in the result.
    """
    results: list = []
    if n <= 0 or timeout_sec <= 0:
        return results

    def collect(samples):
        for data in samples:
            if filter_fn is None or filter_fn(data):
                results.append(data)

    collect(reader.read_data() if read else reader.take_data())
    condition = dds.ReadCondition(reader, dds.DataState.new_data)
    waitset = dds.WaitSet()
    waitset += condition
    deadline = _time.monotonic() + timeout_sec
    try:
        while len(results) < n:
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                break
            try:
                active = waitset.wait(dds.Duration.from_seconds(remaining))
            except dds.TimeoutError:
                break
            if not active:
                break
            selector = reader.select().condition(condition)
            collect(selector.read_data() if read else selector.take_data())
    finally:
        waitset -= condition
    return results


def check_no_deadline_missed(reader, timeout_sec: Optional[float] = None) -> bool:
    """Check whether any deadline missed status events occur on the reader.

    Waits for ``timeout_sec`` (default: 2x the configured deadline period).
    Returns True if no REQUESTED_DEADLINE_MISSED event fired before the
    timeout.  Returns False if a deadline miss was detected.
    """
    assert reader.qos.deadline.period != dds.Duration.infinite, (
        "Reader must have a finite deadline period for this check"
    )

    status_condition = dds.StatusCondition(reader)
    status_condition.enabled_statuses = dds.StatusMask.REQUESTED_DEADLINE_MISSED

    waitset = dds.WaitSet()
    waitset += status_condition

    if timeout_sec is None:
        timeout_sec = 2.0 * reader.qos.deadline.period.to_seconds()

    active_conditions = waitset.wait(dds.Duration.from_seconds(timeout_sec))
    if status_condition in active_conditions:
        return False  # Deadline missed event detected
    return True  # No deadline missed event detected within the timeout period


@dataclass
class UtilityApp:
    qos_provider: dds.QosProvider = field(default_factory=lambda: dds.QosProvider.default)
    dp_qos_profile: str = "DpQosLib::Test"
    participant: Optional[dds.DomainParticipant] = None
    dpf_qos: Optional[dds.DomainParticipantFactoryQos] = None
    _topics: dict[str, "UtilityApp.Topic"] = field(init=False, default_factory=dict)

    @classmethod
    def make_secure(cls, qos_profile: str = "DpQosLib::Test") -> "UtilityApp":
        """Factory method for a secure UtilityApp."""
        xml_files = [
            str(_GENERATED_SYSTEM / "xml" / "MedTech.xml"),
            str(_PROJECT_ROOT / "system" / "qos" / "Qos.xml"),
            str(_PROJECT_ROOT / "system" / "qos" / "SecureAppsQos.xml"),
            str(_PROJECT_ROOT / "system" / "model" / "DomainLibrary.xml"),
            str(_PROJECT_ROOT / "system" / "model" / "ParticipantLibrary.xml"),
        ]
        qos_provider = make_isolated_qos_provider(*xml_files)
        dpf_qos = dds.DomainParticipant.participant_factory_qos
        dpf_qos.monitoring.enable = False
        return cls(
            qos_provider=qos_provider,
            dp_qos_profile=qos_profile,
            dpf_qos=dpf_qos,
        )

    @classmethod
    def make_non_secure(cls, qos_profile: str = "DpQosLib::Test") -> "UtilityApp":
        """Factory method for a non-secure UtilityApp."""
        xml_files = [
            str(_GENERATED_SYSTEM / "xml" / "MedTech.xml"),
            str(_PROJECT_ROOT / "system" / "qos" / "Qos.xml"),
            str(_PROJECT_ROOT / "system" / "qos" / "NonSecureAppsQos.xml"),
            str(_PROJECT_ROOT / "system" / "model" / "DomainLibrary.xml"),
            str(_PROJECT_ROOT / "system" / "model" / "ParticipantLibrary.xml"),
        ]
        qos_provider = make_isolated_qos_provider(*xml_files)
        return cls(qos_provider=qos_provider, dp_qos_profile=qos_profile)

    def __post_init__(self):
        if not self.participant:
            if self.dpf_qos:
                restore_dpf_qos = dds.DomainParticipant.participant_factory_qos
                if restore_dpf_qos != self.dpf_qos:
                    dds.DomainParticipant.participant_factory_qos = self.dpf_qos
                else:
                    restore_dpf_qos = None
            else:
                restore_dpf_qos = None
            self.participant = dds.DomainParticipant(
                domain_id=0,
                qos=self.qos_provider.participant_qos_from_profile(self.dp_qos_profile),
            )
            self.participant.enable()
            if restore_dpf_qos:
                dds.DomainParticipant.participant_factory_qos = restore_dpf_qos

    def close(self) -> None:
        """Deterministically close the participant and all contained entities."""
        if self.participant is not None:
            self.participant.close()
            self.participant = None
            self._topics.clear()

    def __enter__(self) -> "UtilityApp":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @dataclass
    class Topic:
        qos_provider: dds.QosProvider
        participant: dds.DomainParticipant
        topic_name: str
        qos_profile: str
        type_cls: Optional[type]
        _topic: Optional[dds.Topic | dds.DynamicData.Topic] = field(init=False, default=None)
        _writer: Optional[dds.DataWriter | dds.DynamicData.DataWriter] = field(
            init=False, default=None
        )
        _reader: Optional[dds.DataReader | dds.DynamicData.DataReader] = field(
            init=False, default=None
        )

        @property
        def topic(self) -> dds.Topic | dds.DynamicData.Topic:
            if not self._topic:
                if self.type_cls is not None:
                    register_type(self.type_cls)
                    self._topic = dds.Topic(self.participant, self.topic_name, self.type_cls)
                else:
                    dynamic_type = self.qos_provider.type(self.topic_name)
                    self._topic = dds.DynamicData.Topic(
                        self.participant, self.topic_name, dynamic_type
                    )
                if not self._topic:
                    raise ValueError(f"Failed to create topic {self.topic_name}")
            return self._topic

        @property
        def writer(self) -> dds.DataWriter | dds.DynamicData.DataWriter:
            if not self._writer:
                topic = self.topic
                if isinstance(topic, dds.Topic):
                    self._writer = dds.DataWriter(
                        topic=topic,
                        qos=self.qos_provider.datawriter_qos_from_profile(self.qos_profile),
                    )
                else:
                    self._writer = dds.DynamicData.DataWriter(
                        topic=topic,
                        qos=self.qos_provider.datawriter_qos_from_profile(self.qos_profile),
                    )
                if not self._writer:
                    raise ValueError(f"Failed to create writer for topic {self.topic_name}")
            return self._writer

        @property
        def reader(self) -> dds.DataReader | dds.DynamicData.DataReader:
            if not self._reader:
                topic = self.topic
                if isinstance(topic, dds.Topic):
                    self._reader = dds.DataReader(
                        topic=topic,
                        qos=self.qos_provider.datareader_qos_from_profile(self.qos_profile),
                    )
                else:
                    self._reader = dds.DynamicData.DataReader(
                        topic=topic,
                        qos=self.qos_provider.datareader_qos_from_profile(self.qos_profile),
                    )
                if not self._reader:
                    raise ValueError(f"Failed to create reader for topic {self.topic_name}")
            return self._reader

    @property
    def teleop_control(self) -> Topic:
        if "teleop_control" not in self._topics:
            self._topics["teleop_control"] = self.Topic(
                qos_provider=self.qos_provider,
                participant=self.participant,
                topic_name=Robot.Arm.TOPIC_CONTROL,
                qos_profile="DataFlowLibrary::Control",
                type_cls=Robot.Arm.TeleopControl,
            )
        return self._topics["teleop_control"]

    @property
    def device_status(self) -> Topic:
        if "device_status" not in self._topics:
            self._topics["device_status"] = self.Topic(
                qos_provider=self.qos_provider,
                participant=self.participant,
                topic_name=Device.TOPIC_STATUS,
                qos_profile="DataFlowLibrary::Status",
                type_cls=Device.Status,
            )
        return self._topics["device_status"]

    @property
    def tool_control(self) -> Topic:
        if "tool_control" not in self._topics:
            self._topics["tool_control"] = self.Topic(
                qos_provider=self.qos_provider,
                participant=self.participant,
                topic_name=Robot.Tool.TOPIC_CONTROL,
                qos_profile="DataFlowLibrary::Control",
                type_cls=Robot.Tool.ParallelJawControl,
            )
        return self._topics["tool_control"]

    @property
    def arm_status(self) -> Topic:
        if "arm_status" not in self._topics:
            self._topics["arm_status"] = self.Topic(
                qos_provider=self.qos_provider,
                participant=self.participant,
                topic_name=Robot.Arm.TOPIC_STATUS,
                qos_profile="DataFlowLibrary::Status",
                type_cls=Robot.Arm.Status,
            )
        return self._topics["arm_status"]

    @property
    def arm_telemetry(self) -> Topic:
        if "arm_telemetry" not in self._topics:
            self._topics["arm_telemetry"] = self.Topic(
                qos_provider=self.qos_provider,
                participant=self.participant,
                topic_name=Robot.Arm.TOPIC_TELEMETRY,
                qos_profile="DataFlowLibrary::Telemetry",
                type_cls=Robot.Arm.Telemetry,
            )
        return self._topics["arm_telemetry"]

    @property
    def device_heartbeat(self) -> Topic:
        if "device_heartbeat" not in self._topics:
            self._topics["device_heartbeat"] = self.Topic(
                qos_provider=self.qos_provider,
                participant=self.participant,
                topic_name=Device.TOPIC_HEARTBEAT,
                qos_profile="DataFlowLibrary::Heartbeat",
                type_cls=Device.Heartbeat,
            )
        return self._topics["device_heartbeat"]

    @property
    def device_command(self) -> Topic:
        if "device_command" not in self._topics:
            self._topics["device_command"] = self.Topic(
                qos_provider=self.qos_provider,
                participant=self.participant,
                topic_name=Device.TOPIC_COMMAND,
                qos_profile="DataFlowLibrary::Command",
                type_cls=Device.Command,
            )
        return self._topics["device_command"]

    @property
    def vitals(self) -> Topic:
        if "vitals" not in self._topics:
            self._topics["vitals"] = self.Topic(
                qos_provider=self.qos_provider,
                participant=self.participant,
                topic_name=Patient.TOPIC_VITALS,
                qos_profile="DataFlowLibrary::Streaming",
                type_cls=Patient.Vitals,
            )
        return self._topics["vitals"]
