#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software solely for use with RTI Connext DDS. The Software is
# provided "as is", with no warranty of any type.
"""License-free checks for the Python API/SDK compatibility preflight."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "resource" / "python"))
sys.path.insert(0, str(PROJECT_ROOT / "system" / "security"))
import rti  # noqa: E402
import security_tree  # noqa: E402
from scripts import check_connext_install  # noqa: E402


def test_python_api_version_is_pinned_exactly():
    assert check_connext_install.project_python_api_version() == "7.7.0"


@pytest.mark.parametrize(
    ("installed", "namespace_available", "message"),
    (
        ([], False, "distribution is missing"),
        ([("rti.connext", "7.6.0")], True, "pyproject.toml requires"),
        (
            [("rti.connext", "7.7.0"), ("rti.connext", "7.7.0")],
            True,
            "duplicate installations",
        ),
        (
            [("rti.connext", "7.7.0"), ("rti.connext.activated", "7.7.0")],
            True,
            "unsupported commercial",
        ),
        ([("rti.connext", "7.7.0")], False, "import namespace is missing"),
    ),
)
def test_python_api_mismatch_diagnostics(installed, namespace_available, message):
    errors = check_connext_install.python_api_errors("7.7.0", installed, namespace_available)
    assert any(message in error for error in errors)


def test_sdk_and_generator_must_match_python_api_pin():
    errors = check_connext_install.sdk_compatibility_errors(
        expected_version="7.7.0",
        sdk_version="7.6.0",
        generator_output="INFO rtiddsgen version 4.6.0",
        declared_versions={"CONNEXT_VERSION": "7.6.0"},
    )
    assert any("SDK 7.6.0" in error for error in errors)
    assert any("rtiddsgen 4.6.0" in error for error in errors)
    assert any("CONNEXT_VERSION=7.6.0" in error for error in errors)


def test_unversioned_sdk_path_is_diagnosed(tmp_path):
    with pytest.raises(check_connext_install.PreflightError, match="Cannot determine"):
        check_connext_install.sdk_version_from_home(tmp_path)


def test_security_version_detection_does_not_hide_api_errors(monkeypatch):
    class BrokenProductVersion:
        @property
        def current(self):
            raise RuntimeError("Connext version unavailable")

    dds_module = ModuleType("rti.connextdds")
    dds_module.ProductVersion = BrokenProductVersion()
    monkeypatch.setitem(sys.modules, "rti.connextdds", dds_module)
    monkeypatch.setattr(rti, "connextdds", dds_module, raising=False)

    with pytest.raises(RuntimeError, match="Connext version unavailable"):
        security_tree.detect_connext_version()


def test_sdk_version_must_match_docker_and_ci_declarations():
    expected = check_connext_install.project_python_api_version()
    dockerfile = (PROJECT_ROOT / "tests" / "docker" / "Dockerfile").read_text(encoding="utf-8")
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    docker_version = re.search(r"^ARG CONNEXT_VERSION=(\S+)$", dockerfile, re.MULTILINE)
    ci_version = re.search(r'^\s+CONNEXT_VERSION:\s+"([^"]+)"$', workflow, re.MULTILINE)
    assert docker_version, "Dockerfile must declare its Connext SDK version"
    assert ci_version, "CI must declare its Connext SDK version"
    assert docker_version.group(1) == expected
    assert ci_version.group(1) == expected
