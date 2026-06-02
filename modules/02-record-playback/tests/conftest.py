"""Pytest-only hooks and fixtures for Module 02 tests."""

import importlib
import shutil
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
RESOURCE_PYTHON_DIR = TESTS_DIR.parents[3] / "resource" / "python"

sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(RESOURCE_PYTHON_DIR))

module02_test_support = importlib.import_module("module02_test_support")
module_runner = importlib.import_module("scripts.module_runner")

MODULE_01_DIR = module02_test_support.MODULE_01_DIR
MODULE_DIR = module02_test_support.MODULE_DIR
RECORDING_DIR = module02_test_support.RECORDING_DIR

from scripts.test_utils import ProcessManager  # noqa: E402

# Probe whether RTI services are available without loading full config.
_services_available = True
try:
    module_runner.load_module_config(MODULE_DIR, flags={"security": False})
except FileNotFoundError:
    _services_available = False


def pytest_collection_modifyitems(config, items):
    """Auto-skip @service-marked tests if Recording/Replay Service is not available."""
    if _services_available:
        return
    skip = pytest.mark.skip(reason="RTI Recording/Replay Service not found in NDDSHOME/bin/")
    for item in items:
        if Path(item.fspath).is_relative_to(TESTS_DIR) and "service" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def module01_env():
    """Non-secure DDS environment from Module 01 (operating-room apps)."""
    return module_runner.load_module_config(MODULE_01_DIR, flags={"security": False})


@pytest.fixture(scope="session")
def module02_env():
    """Non-secure DDS environment from Module 02 (recording/replay services)."""
    return module_runner.load_module_config(MODULE_DIR, flags={"security": False})


@pytest.fixture()
def or_proc_manager(module01_env):
    """ProcessManager for Module 01 operating-room apps (PatientSensor, etc.)."""
    env, apps = module01_env
    pm = ProcessManager(env, apps, cwd=MODULE_01_DIR)
    yield pm
    pm.shutdown_all()


@pytest.fixture()
def svc_proc_manager(module02_env):
    """ProcessManager for Module 02 recording/replay services."""
    env, apps = module02_env
    pm = ProcessManager(env, apps, cwd=MODULE_DIR)
    yield pm
    pm.shutdown_all()


@pytest.fixture()
def clean_recording_dir():
    """Ensure recording directory is clean before and after tests."""
    if RECORDING_DIR.is_dir():
        shutil.rmtree(RECORDING_DIR)
    yield RECORDING_DIR
    if RECORDING_DIR.is_dir():
        shutil.rmtree(RECORDING_DIR)
