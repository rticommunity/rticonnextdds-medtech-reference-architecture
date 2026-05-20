"""Pytest-only hooks and fixtures for Module 04 tests."""

import importlib
import os
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
SYSTEM_ARCH_DIR = module04_test_support.SYSTEM_ARCH_DIR

from scripts.test_utils import (  # noqa: E402
    ProcessManager,
    disable_monitoring,
    has_display,
    security_plugin_available,
)


def _or_security_artifacts_exist() -> bool:
    """Check that Module 01 security artifacts exist."""
    domain_scope_dir = SYSTEM_ARCH_DIR / "security" / "domain_scope"
    return domain_scope_dir.is_dir() and any(domain_scope_dir.rglob("*.p7s"))


def _threat_artifacts_exist() -> bool:
    """Check that Module 04 threat security artifacts exist."""
    rogue_ca = MODULE_DIR / "security" / "ca" / "RogueCa" / "certs" / "RogueCa" / "RogueCa.crt"
    return rogue_ca.is_file()


@pytest.fixture(scope="session", autouse=True)
def _monitoring_off():
    """Disable RTI Monitoring 2.0 so in-process secure participants can be created."""
    disable_monitoring()


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
    _has_security_artifacts = _or_security_artifacts_exist() and _threat_artifacts_exist()

    module_items = [i for i in items if Path(i.fspath).is_relative_to(TESTS_DIR)]

    for item in module_items:
        if "gui" in item.keywords and not _has_display:
            item.add_marker(skip_gui)
        if "secure" in item.keywords and not _has_security_artifacts:
            item.add_marker(skip_sec_artifacts)
        elif "secure" in item.keywords and not __has_security_plugin:
            item.add_marker(skip_sec_plugin)


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
    # Propagate security artifact paths into os.environ so that in-process
    # DDS QosProvider calls can resolve $(THREAT_SECURITY_ARTIFACTS_DIR) and
    # $(RTI_SECURITY_ARTIFACTS_DIR) from ThreatQos.xml.  load_module_config
    # already resolved these to absolute paths via ${MODULE_DIR}/${SYSTEM_ARCH}.
    for key in ("THREAT_SECURITY_ARTIFACTS_DIR", "RTI_SECURITY_ARTIFACTS_DIR"):
        if key in env:
            os.environ[key] = env[key]
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


@pytest.fixture(scope="class")
def or_pm_secure_class(or_env_secure):
    """Class-scoped secure ProcessManager — reuses PatientSensor across tests."""
    env, apps = or_env_secure
    pm = ProcessManager(env, apps, cwd=MODULE_01_DIR)
    yield pm
    pm.shutdown_all()
