"""Pytest-only hooks and fixtures for Module 04 tests."""

import importlib
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
RESOURCE_PYTHON_DIR = TESTS_DIR.parents[3] / "resource" / "python"

sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(RESOURCE_PYTHON_DIR))

module04_test_support = importlib.import_module("module04_test_support")
module_runner = importlib.import_module("scripts.module_runner")

MODULE_01_DIR = module04_test_support.MODULE_01_DIR
MODULE_DIR = module04_test_support.MODULE_DIR
ProcessManager = module04_test_support.ProcessManager
SYSTEM_ARCH_DIR = module04_test_support.SYSTEM_ARCH_DIR
_has_display = module04_test_support._has_display
_or_security_artifacts_exist = module04_test_support._or_security_artifacts_exist
_threat_artifacts_exist = module04_test_support._threat_artifacts_exist


def pytest_collection_modifyitems(config, items):
    has_security = _or_security_artifacts_exist() and _threat_artifacts_exist()
    has_display = _has_display()

    skip_sec = pytest.mark.skip(
        reason="Security artifacts not generated "
        "(run setup_security.py and setup_threat_security.py)"
    )
    skip_gui = pytest.mark.skip(reason="No graphical display available")

    for item in items:
        if not has_security:
            item.add_marker(skip_sec)
        if "gui" in item.keywords and not has_display:
            item.add_marker(skip_gui)


@pytest.fixture(scope="session")
def or_env_nonsecure():
    """Module 01 OR env — non-secure mode."""
    env, apps = module_runner.load_module_config(MODULE_01_DIR, flags={"security": False})
    return env, apps


@pytest.fixture(scope="session")
def or_env_secure():
    """Module 01 OR env — secure mode."""
    env, apps = module_runner.load_module_config(MODULE_01_DIR, flags={"security": True})
    return env, apps


@pytest.fixture(scope="session")
def threat_env():
    """Module 04 threat app environment with Types.xml prepended."""
    env, apps = module_runner.load_module_config(MODULE_DIR)
    types_xml = str(SYSTEM_ARCH_DIR / "Types.xml")
    env["NDDS_QOS_PROFILES"] = types_xml + ";" + env["NDDS_QOS_PROFILES"]
    return env, apps


@pytest.fixture()
def or_pm_nonsecure(or_env_nonsecure):
    env, apps = or_env_nonsecure
    pm = ProcessManager(env, apps, cwd=MODULE_01_DIR)
    yield pm
    pm.shutdown_all()


@pytest.fixture()
def or_pm_secure(or_env_secure):
    env, apps = or_env_secure
    pm = ProcessManager(env, apps, cwd=MODULE_01_DIR)
    yield pm
    pm.shutdown_all()
