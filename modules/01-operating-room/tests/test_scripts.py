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
"""Script and environment setup validation tests.

Ensures that ``xml_setup.setup_env()`` produces a correct environment
and that all referenced XML files actually exist.
"""

import os
import sys
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


# ---------------------------------------------------------------------------
# xml_setup error handling
# ---------------------------------------------------------------------------


class TestXmlSetupErrors:
    """xml_setup should handle error conditions gracefully."""

    @pytest.fixture(autouse=True)
    def _chdir(self, monkeypatch):
        monkeypatch.chdir(MODULE_DIR)

    def test_setup_env_fails_without_nddshome(self, monkeypatch):
        """setup_env should fail when NDDSHOME is not set."""
        monkeypatch.delenv("NDDSHOME", raising=False)
        import importlib

        import xml_setup

        importlib.reload(xml_setup)
        with pytest.raises((SystemExit, RuntimeError, Exception)):
            xml_setup.setup_env(security=False)

    def test_referenced_xml_files_are_not_empty(self):
        """All XML files referenced by NDDS_QOS_PROFILES should be non-empty."""
        import xml_setup

        env = xml_setup.setup_env(security=False)
        for path_str in env["NDDS_QOS_PROFILES"].split(";"):
            p = Path(path_str)
            assert p.stat().st_size > 0, f"XML file is empty: {p}"


# ---------------------------------------------------------------------------
# kill_all.py
# ---------------------------------------------------------------------------


class TestKillAll:
    """kill_all module should define target lists and a callable main()."""

    def test_unix_targets_is_nonempty_list(self):
        sys.path.insert(0, str(MODULE_DIR / "scripts"))
        import kill_all

        assert isinstance(kill_all.UNIX_TARGETS, list)
        assert len(kill_all.UNIX_TARGETS) > 0

    def test_windows_targets_is_nonempty_list(self):
        sys.path.insert(0, str(MODULE_DIR / "scripts"))
        import kill_all

        assert isinstance(kill_all.WINDOWS_TARGETS, list)
        assert len(kill_all.WINDOWS_TARGETS) > 0

    def test_main_is_callable(self):
        sys.path.insert(0, str(MODULE_DIR / "scripts"))
        import kill_all

        assert callable(kill_all.main)

    def test_main_runs_without_error(self):
        """main() should not raise even when no target processes are running."""
        sys.path.insert(0, str(MODULE_DIR / "scripts"))
        import kill_all

        # Should complete without error — pkill/taskkill exit non-zero when
        # no matching process exists, but main() ignores that.
        kill_all.main()
