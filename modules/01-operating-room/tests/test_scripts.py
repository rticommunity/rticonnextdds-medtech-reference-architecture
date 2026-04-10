"""Script and environment setup validation tests.

Ensures that ``xml_setup.setup_env()`` produces a correct environment
and that all referenced XML files actually exist.
"""

import os
from pathlib import Path

import pytest
from conftest import MODULE_DIR, SECURITY_DIR, SYSTEM_ARCH_DIR

# ---------------------------------------------------------------------------
# xml_setup.setup_env()
# ---------------------------------------------------------------------------


class TestXmlSetup:
    """xml_setup.setup_env() should return a well-formed environment dict."""

    @pytest.fixture(autouse=True)
    def _chdir(self, monkeypatch):
        """Switch cwd to module directory — xml_setup uses relative paths."""
        monkeypatch.chdir(MODULE_DIR)

    def _get_setup(self, security: bool = False) -> dict:
        import xml_setup

        return xml_setup.setup_env(security=security)

    def test_nonsecure_env_has_ndds_qos_profiles(self):
        env = self._get_setup(security=False)
        assert "NDDS_QOS_PROFILES" in env

    def test_nonsecure_profiles_contain_qos_xml(self):
        env = self._get_setup(security=False)
        profiles = env["NDDS_QOS_PROFILES"]
        assert "Qos.xml" in profiles

    def test_nonsecure_profiles_contain_nonsecure_qos(self):
        env = self._get_setup(security=False)
        paths = env["NDDS_QOS_PROFILES"].split(";")
        basenames = [p.rsplit("/", 1)[-1] for p in paths]
        assert "NonSecureAppsQos.xml" in basenames
        assert "SecureAppsQos.xml" not in basenames

    def test_secure_profiles_contain_secure_qos(self):
        env = self._get_setup(security=True)
        paths = env["NDDS_QOS_PROFILES"].split(";")
        basenames = [p.rsplit("/", 1)[-1] for p in paths]
        assert "SecureAppsQos.xml" in basenames
        assert "NonSecureAppsQos.xml" not in basenames

    def test_profiles_contain_domain_library(self):
        env = self._get_setup(security=False)
        assert "DomainLibrary.xml" in env["NDDS_QOS_PROFILES"]

    def test_profiles_contain_participant_library(self):
        env = self._get_setup(security=False)
        assert "ParticipantLibrary.xml" in env["NDDS_QOS_PROFILES"]

    def test_all_referenced_xml_files_exist(self):
        """Every path in NDDS_QOS_PROFILES should resolve to a real file."""
        env = self._get_setup(security=False)
        for path_str in env["NDDS_QOS_PROFILES"].split(";"):
            path = Path(path_str)
            assert path.is_file(), f"Referenced XML does not exist: {path}"

    def test_secure_referenced_xml_files_exist(self):
        env = self._get_setup(security=True)
        for path_str in env["NDDS_QOS_PROFILES"].split(";"):
            path = Path(path_str)
            assert path.is_file(), f"Referenced XML does not exist: {path}"


# ---------------------------------------------------------------------------
# platform_setup
# ---------------------------------------------------------------------------


class TestPlatformSetup:
    """platform_setup module should load and provide NDDSHOME."""

    def test_nddshome_is_set(self):
        import platform_setup

        nddshome = platform_setup.check_nddshome()
        assert nddshome, "NDDSHOME is not set"
        assert os.path.isdir(nddshome), f"NDDSHOME is not a directory: {nddshome}"

    def test_find_executable_returns_path(self):
        import platform_setup

        exe = platform_setup.find_executable("PatientSensor")
        assert exe, "find_executable returned empty for PatientSensor"
