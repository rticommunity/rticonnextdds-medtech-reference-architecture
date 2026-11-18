#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Smoke tests for the Module 04 browser UI processes."""

from __future__ import annotations

import select

import pytest
from module04_test_support import MODULE_DIR
from scripts.test_utils import ProcessManager


@pytest.mark.parametrize("app_name", ("ThreatInjector", "ThreatExfiltrator"))
def test_threat_app_serves_local_browser_ui(app_name, threat_env):
    env, apps = threat_env
    display_name = {
        "ThreatInjector": "Threat Injector",
        "ThreatExfiltrator": "Threat Exfiltrator",
    }[app_name]
    manager = ProcessManager(env, apps, cwd=MODULE_DIR)
    try:
        process = manager.start_app_ready(app_name)
        assert process.stdout is not None
        readable, _, _ = select.select([process.stdout], [], [], 3)
        assert readable, f"{app_name} did not print its browser URL"
        line = process.stdout.readline().decode(errors="replace").strip()
        assert line.startswith(f"{display_name} listening on"), line
        assert "http://127.0.0.1:" in line
    finally:
        manager.shutdown_all()
