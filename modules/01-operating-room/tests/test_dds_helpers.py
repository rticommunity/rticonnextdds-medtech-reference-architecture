#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

import threading
import time
from types import SimpleNamespace

import pytest
import test_utils
from MedTech import Device
from test_utils import wait_for_device_status, wait_for_samples, wait_for_writer_match


def _status(device):
    return Device.Status(device=device, status=Device.DeviceStatuses.ON)


def test_security_probe_unexpected_failure_is_not_a_skip(monkeypatch):
    monkeypatch.delattr(test_utils.security_plugin_available, "_cached", raising=False)
    monkeypatch.setattr(
        test_utils.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2, stderr="probe crashed", stdout=""),
    )
    with pytest.raises(RuntimeError, match="probe crashed"):
        test_utils.security_plugin_available()


def test_read_samples_counts_each_cached_sample_once(nonsecure_utility_app):
    reader = nonsecure_utility_app.device_status.reader
    writer = nonsecure_utility_app.device_status.writer
    assert wait_for_writer_match(writer)
    writer.write(_status(Device.DeviceType.ARM))

    assert len(wait_for_samples(reader, n=1, read=True)) == 1
    assert len(wait_for_samples(reader, n=2, timeout_sec=0.25, read=True)) == 1

    timer = threading.Timer(0.1, writer.write, args=[_status(Device.DeviceType.PATIENT_SENSOR)])
    timer.start()
    try:
        samples = wait_for_samples(reader, n=2, timeout_sec=2, read=True)
    finally:
        timer.join()
    assert {sample.device for sample in samples} == {
        Device.DeviceType.ARM,
        Device.DeviceType.PATIENT_SENSOR,
    }


def test_status_wait_accepts_cached_and_unexpected_devices(nonsecure_utility_app):
    reader = nonsecure_utility_app.device_status.reader
    writer = nonsecure_utility_app.device_status.writer
    assert wait_for_writer_match(writer)
    writer.write(_status(Device.DeviceType.ARM))
    writer.write(_status(Device.DeviceType.PATIENT_SENSOR))
    assert len(wait_for_samples(reader, n=2, read=True)) == 2

    start = time.monotonic()
    seen = wait_for_device_status(reader, {Device.DeviceType.ARM}, timeout_sec=2)
    assert Device.DeviceType.ARM in seen
    assert time.monotonic() - start < 1

    timer = threading.Timer(0.1, writer.write, args=[_status(Device.DeviceType.PATIENT_MONITOR)])
    timer.start()
    try:
        seen = wait_for_device_status(
            reader, {Device.DeviceType.ARM, Device.DeviceType.PATIENT_MONITOR}, timeout_sec=2
        )
    finally:
        timer.join()
    assert {Device.DeviceType.ARM, Device.DeviceType.PATIENT_MONITOR}.issubset(seen)


def test_arm_readiness_cache_tracks_successful_publication():
    from Arm import ArmApp

    app = ArmApp.__new__(ArmApp)
    app._last_published_readiness = None
    written = []

    def write(sample):
        if not written:
            written.append("failed")
            raise RuntimeError("write failed")
        written.append(sample.readiness.name)

    app.arm_status_writer = SimpleNamespace(write=write)
    with pytest.raises(RuntimeError, match="write failed"):
        app.write_readiness("READY")
    app.write_readiness("READY")
    app.write_readiness("READY")
    assert written == ["failed", "READY"]
