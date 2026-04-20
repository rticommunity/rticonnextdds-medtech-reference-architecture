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
"""Module config and environment setup validation tests.

Ensures that ``module_runner.load_module_config()`` produces a correct
environment and that all referenced XML files actually exist.
"""

import os
import sys
from pathlib import Path

import pytest
from conftest import MODULE_DIR, SECURITY_DIR, SYSTEM_ARCH_DIR
from scripts import module_runner, platform_setup

# ---------------------------------------------------------------------------
# module_runner.load_module_config()
# ---------------------------------------------------------------------------


class TestModuleConfig:
    """load_module_config() should return a well-formed environment dict."""

    def _get_env(self, security: bool = False) -> dict:
        env, _apps = module_runner.load_module_config(MODULE_DIR, flags={"security": security})
        return env

    def test_nonsecure_env_has_ndds_qos_profiles(self):
        env = self._get_env(security=False)
        assert "NDDS_QOS_PROFILES" in env

    def test_nonsecure_profiles_contain_qos_xml(self):
        env = self._get_env(security=False)
        profiles = env["NDDS_QOS_PROFILES"]
        assert "Qos.xml" in profiles

    def test_nonsecure_profiles_contain_nonsecure_qos(self):
        env = self._get_env(security=False)
        paths = env["NDDS_QOS_PROFILES"].split(";")
        basenames = [p.rsplit("/", 1)[-1].rsplit("\\\\", 1)[-1] for p in paths]
        assert "NonSecureAppsQos.xml" in basenames
        assert "SecureAppsQos.xml" not in basenames

    def test_secure_profiles_contain_secure_qos(self):
        env = self._get_env(security=True)
        paths = env["NDDS_QOS_PROFILES"].split(";")
        basenames = [p.rsplit("/", 1)[-1].rsplit("\\\\", 1)[-1] for p in paths]
        assert "SecureAppsQos.xml" in basenames
        assert "NonSecureAppsQos.xml" not in basenames

    def test_profiles_contain_domain_library(self):
        env = self._get_env(security=False)
        assert "DomainLibrary.xml" in env["NDDS_QOS_PROFILES"]

    def test_profiles_contain_participant_library(self):
        env = self._get_env(security=False)
        assert "ParticipantLibrary.xml" in env["NDDS_QOS_PROFILES"]

    def test_all_referenced_xml_files_exist(self):
        """Every path in NDDS_QOS_PROFILES should resolve to a real file."""
        env = self._get_env(security=False)
        for path_str in env["NDDS_QOS_PROFILES"].split(";"):
            path = Path(path_str)
            assert path.is_file(), f"Referenced XML does not exist: {path}"

    def test_secure_referenced_xml_files_exist(self):
        env = self._get_env(security=True)
        for path_str in env["NDDS_QOS_PROFILES"].split(";"):
            path = Path(path_str)
            assert path.is_file(), f"Referenced XML does not exist: {path}"


# ---------------------------------------------------------------------------
# platform_setup
# ---------------------------------------------------------------------------


class TestPlatformSetup:
    """platform_setup module should load and provide NDDSHOME."""

    def test_nddshome_is_set(self):
        nddshome = platform_setup.get_nddshome()
        assert nddshome, "NDDSHOME is not set"
        assert nddshome.is_dir(), f"NDDSHOME is not a directory: {nddshome}"

    def test_find_executable_returns_path(self):
        exe = platform_setup.find_executable("PatientSensor")
        assert exe, "find_executable returned empty for PatientSensor"


# ---------------------------------------------------------------------------
# module_runner error handling
# ---------------------------------------------------------------------------


class TestModuleConfigErrors:
    """load_module_config should handle error conditions gracefully."""

    def test_fails_without_nddshome(self, monkeypatch):
        """load_module_config should fail when NDDSHOME is not set."""
        monkeypatch.delenv("NDDSHOME", raising=False)
        with pytest.raises((EnvironmentError, Exception)):
            module_runner.load_module_config(MODULE_DIR, flags={"security": False})

    def test_referenced_xml_files_are_not_empty(self):
        """All XML files referenced by NDDS_QOS_PROFILES should be non-empty."""
        env, _apps = module_runner.load_module_config(MODULE_DIR, flags={"security": False})
        for path_str in env["NDDS_QOS_PROFILES"].split(";"):
            p = Path(path_str)
            assert p.stat().st_size > 0, f"XML file is empty: {p}"
