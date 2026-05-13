"""Pytest-only hooks and fixtures for Module 01 tests."""

import importlib
import os
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
RESOURCE_PYTHON_DIR = TESTS_DIR.parents[3] / "resource" / "python"

sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(RESOURCE_PYTHON_DIR))

module01_test_support = importlib.import_module("module01_test_support")
module_runner = importlib.import_module("scripts.module_runner")

MODULE_DIR = module01_test_support.MODULE_DIR
ProcessManager = module01_test_support.ProcessManager
SECURITY_DIR = module01_test_support.SECURITY_DIR
_has_display = module01_test_support._has_display
_security_artifacts_exist = module01_test_support._security_artifacts_exist
_security_plugin_available = module01_test_support._security_plugin_available


def pytest_collection_modifyitems(config, items):
    """Skip tests when prerequisites are missing."""
    skip_gui = pytest.mark.skip(
        reason="No graphical display available (need DISPLAY or WAYLAND_DISPLAY)",
    )
    skip_sec_artifacts = pytest.mark.skip(
        reason="Security artifacts not generated (run setup_security.py)",
    )
    skip_sec_plugin = pytest.mark.skip(
        reason="DDS Security runtime probe failed",
    )

    has_display = _has_display()
    module_items = [i for i in items if Path(i.fspath).is_relative_to(TESTS_DIR)]

    for item in module_items:
        if "gui" in item.keywords and not has_display:
            item.add_marker(skip_gui)
        if "secure" in item.keywords and not _security_artifacts_exist():
            item.add_marker(skip_sec_artifacts)
        elif "secure" in item.keywords and not _security_plugin_available():
            item.add_marker(skip_sec_plugin)


@pytest.fixture(scope="session")
def dds_env():
    """Session-scoped environment dict with NDDS_QOS_PROFILES configured (non-secure)."""
    env, apps = module_runner.load_module_config(MODULE_DIR, flags={"security": False})
    return env, apps


@pytest.fixture(scope="session")
def dds_env_secure():
    """Session-scoped environment dict with NDDS_QOS_PROFILES + DDS Security."""
    env, apps = module_runner.load_module_config(MODULE_DIR, flags={"security": True})
    env["RTI_SECURITY_ARTIFACTS_DIR"] = str(SECURITY_DIR)
    return env, apps


@pytest.fixture()
def proc_manager(dds_env):
    """Yield a ProcessManager wired to the non-secure DDS environment."""
    env, apps = dds_env
    pm = ProcessManager(env, apps)
    yield pm
    pm.shutdown_all()


@pytest.fixture(scope="class")
def class_proc_manager(dds_env):
    """Class-scoped ProcessManager for read-only test classes."""
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


@pytest.fixture()
def dds_participant(dds_env):
    """Create a lightweight DDS DomainParticipant for test observation."""
    import rti.connextdds as dds

    env, _apps = dds_env
    os.environ["NDDS_QOS_PROFILES"] = env["NDDS_QOS_PROFILES"]

    provider = dds.QosProvider.default
    participant_qos = provider.participant_qos_from_profile("DpQosLib::Test")
    participant = dds.DomainParticipant(domain_id=0, qos=participant_qos)
    yield participant
    participant.close()
