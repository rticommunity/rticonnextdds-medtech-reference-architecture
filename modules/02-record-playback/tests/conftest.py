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
ProcessManager = module02_test_support.ProcessManager
RECORDING_DIR = module02_test_support.RECORDING_DIR
RECORDING_SERVICE = module02_test_support.RECORDING_SERVICE
REPLAY_SERVICE = module02_test_support.REPLAY_SERVICE


def pytest_collection_modifyitems(config, items):
    """Auto-skip all tests if Recording/Replay Service is not available."""
    if RECORDING_SERVICE and REPLAY_SERVICE:
        return
    skip = pytest.mark.skip(reason="RTI Recording/Replay Service not found in NDDSHOME/bin/")
    for item in items:
        item.add_marker(skip)


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


@pytest.fixture()
def clean_recording_dir():
    """Ensure recording directory is clean before and after tests."""
    if RECORDING_DIR.is_dir():
        shutil.rmtree(RECORDING_DIR)
    yield RECORDING_DIR
    if RECORDING_DIR.is_dir():
        shutil.rmtree(RECORDING_DIR)
