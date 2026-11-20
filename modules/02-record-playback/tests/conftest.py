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

"""Pytest-only hooks and fixtures for Module 02 tests."""

import importlib
import os
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(TESTS_DIR))

module02_test_support = importlib.import_module("module02_test_support")
MODULE_01_DIR = module02_test_support.MODULE_01_DIR
MODULE_DIR = module02_test_support.MODULE_DIR
prepare_test_recording_workspace = module02_test_support.prepare_test_recording_workspace


def _services_available() -> bool:
    nddshome = os.environ.get("NDDSHOME")
    if not nddshome:
        return False

    service_bin_dir = Path(nddshome) / "bin"
    suffixes = ("", ".bat", ".exe")
    return all(
        any((service_bin_dir / f"{service}{suffix}").is_file() for suffix in suffixes)
        for service in ("rtirecordingservice", "rtireplayservice")
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip @service-marked tests if Recording/Replay Service is not available."""
    service_items = [
        item
        for item in items
        if Path(item.fspath).is_relative_to(TESTS_DIR) and "service" in item.keywords
    ]
    if not service_items or _services_available():
        return
    skip = pytest.mark.skip(reason="RTI Recording/Replay Service not found in NDDSHOME/bin/")
    for item in service_items:
        item.add_marker(skip)


@pytest.fixture(scope="session")
def module01_env():
    """Non-secure DDS environment from Module 01 (operating-room apps)."""
    from tools.medtech import module_runner

    return module_runner.load_module_config(MODULE_01_DIR, flags={"security": False})


@pytest.fixture(scope="session")
def module02_env():
    """Non-secure DDS environment from Module 02 (recording/replay services)."""
    from tools.medtech import module_runner

    return module_runner.load_module_config(MODULE_DIR, flags={"security": False})


@pytest.fixture()
def or_proc_manager(module01_env):
    """ProcessManager for Module 01 operating-room apps (PatientSensor, etc.)."""
    from test_utils import ProcessManager

    env, apps = module01_env
    pm = ProcessManager(env, apps, cwd=MODULE_01_DIR)
    yield pm
    pm.shutdown_all()


@pytest.fixture()
def recording_workspace(tmp_path):
    """Copy operator service configs into this test's temporary working directory."""
    return prepare_test_recording_workspace(tmp_path)


@pytest.fixture()
def svc_proc_manager(module02_env, recording_workspace):
    """ProcessManager for Module 02 recording/replay services."""
    from test_utils import ProcessManager

    env, apps = module02_env
    pm = ProcessManager(env, apps, cwd=recording_workspace)
    yield pm
    pm.shutdown_all()


@pytest.fixture()
def clean_recording_dir(recording_workspace):
    """Return recording output in pytest-managed temporary storage."""
    return recording_workspace / "or_recording"
