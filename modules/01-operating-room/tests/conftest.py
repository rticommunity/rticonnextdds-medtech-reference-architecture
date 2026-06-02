"""Pytest-only hooks and fixtures for Module 01 tests."""

import importlib
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
SECURITY_DIR = module01_test_support.SECURITY_DIR

from scripts.test_utils import (  # noqa: E402
    ProcessManager,
    UtilityApp,
    has_display,
    security_plugin_available,
)


def _security_artifacts_exist() -> bool:
    """Return True when setup_security.py has been run for module 01."""
    domain_scope_dir = SECURITY_DIR / "domain_scope"
    if not domain_scope_dir.is_dir():
        return False
    return any(domain_scope_dir.rglob("*.p7s"))


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

    _has_display = has_display()
    __has_security_plugin = security_plugin_available()
    _has_security_artifacts = _security_artifacts_exist()

    module_items = [i for i in items if Path(i.fspath).is_relative_to(TESTS_DIR)]

    for item in module_items:
        if "gui" in item.keywords and not _has_display:
            item.add_marker(skip_gui)
        if "secure" in item.keywords and not _has_security_artifacts:
            item.add_marker(skip_sec_artifacts)
        elif "secure" in item.keywords and not __has_security_plugin:
            item.add_marker(skip_sec_plugin)


@pytest.fixture(scope="session")
def dds_env():
    """Session-scoped environment for non-secure subprocess launches."""
    env, apps = module_runner.load_module_config(MODULE_DIR, flags={"security": False})
    return env, apps


@pytest.fixture(scope="session")
def dds_env_secure():
    """Session-scoped environment for secure subprocess launches."""
    env, apps = module_runner.load_module_config(MODULE_DIR, flags={"security": True})
    env["RTI_SECURITY_ARTIFACTS_DIR"] = str(SECURITY_DIR)
    return env, apps


@pytest.fixture()
def proc_manager(dds_env):
    """Yield a ProcessManager wired to the non-secure DDS environment."""
    env, apps = dds_env
    pm = ProcessManager(env, apps, cwd=MODULE_DIR)
    yield pm
    pm.shutdown_all()


@pytest.fixture(scope="class")
def class_proc_manager(dds_env):
    """Class-scoped ProcessManager for read-only test classes."""
    env, apps = dds_env
    pm = ProcessManager(env, apps, cwd=MODULE_DIR)
    yield pm
    pm.shutdown_all()


@pytest.fixture()
def proc_manager_secure(dds_env_secure):
    """Yield a ProcessManager wired to the secure DDS environment."""
    env, apps = dds_env_secure
    pm = ProcessManager(env, apps, cwd=MODULE_DIR)
    yield pm
    pm.shutdown_all()


@pytest.fixture()
def nonsecure_utility_app():
    """Create a UtilityApp for in-process DDS observation."""
    app = UtilityApp.make_non_secure()
    yield app
    app.close()
