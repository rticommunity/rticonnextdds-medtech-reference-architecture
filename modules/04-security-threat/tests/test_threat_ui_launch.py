#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Smoke tests for the Module 04 browser UI processes."""

from __future__ import annotations

import select
from unittest.mock import Mock

import pytest
import rti.connextdds as dds
from module04_test_support import MODULE_DIR, THREAT_SRC_DIR
from scripts.test_utils import (
    ProcessManager,
    UtilityApp,
    make_isolated_qos_provider,
    register_type,
    wait_for_samples,
    wait_for_writer_match,
)


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


@pytest.mark.parametrize("failure_stage", ("initialization", "step", "view"))
def test_preview_failure_does_not_prevent_real_dds_publication(
    monkeypatch, threat_env, failure_stage
):
    monkeypatch.syspath_prepend(str(THREAT_SRC_DIR))
    import ArmKinematics
    import ThreatInjector
    from MedTech import Device, Robot

    class FailedPreview:
        def __init__(self):
            if failure_stage == "initialization":
                raise RuntimeError("injected preview initialization failure")

        def step(self, *_args):
            if failure_stage == "step":
                raise ArmKinematics.ArmSimulationError("injected preview step failure")

        def view(self):
            if failure_stage == "view":
                raise RuntimeError("injected preview view failure")
            return {}

    monkeypatch.setattr(ArmKinematics, "ArmModel", FailedPreview)
    ui = Mock()
    application = ThreatInjector.ThreatInjectorApplication(None, ui)
    provider = make_isolated_qos_provider(*threat_env[0]["NDDS_QOS_PROFILES"].split(";"))
    for data_type in (Device.Status, Device.Command, Robot.Arm.TeleopControl):
        register_type(data_type)
    application.dds.participant = provider.create_participant_from_config(
        "ThreatParticipantLibrary::dp/ThreatInjector/Unsecure"
    )
    try:
        application.dds.teleop_writer = dds.DataWriter(
            application.dds.participant.find_datawriter("p/publisher::dw/TeleopControl")
        )
        application.dds.participant.enable()
        with UtilityApp.make_non_secure() as observer:
            reader = observer.teleop_control.reader
            assert wait_for_writer_match(application.dds.teleop_writer)
            for _ in range(3):
                application._inject_once()
                samples = wait_for_samples(reader, n=1, timeout_sec=2)
                assert samples, "Preview failure prevented TeleopControl publication"
                assert samples[-1].linear_velocity.x == pytest.approx(0.02)
            preview = application.view()["arm"]
            assert preview["active"] is False
            assert f"injected preview {failure_stage} failure" in preview["error"]
            warnings = [
                call for call in ui.log.call_args_list if "preview unavailable" in call.args[0]
            ]
            assert len(warnings) == 1
    finally:
        application.dds.close()
