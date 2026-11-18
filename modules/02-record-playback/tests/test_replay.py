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
"""Replay Service tests for Module 02.

Records data first, then launches Replay Service and verifies that a
DDS subscriber receives the replayed samples.
"""

import math
import time

import pytest


@pytest.mark.service
@pytest.mark.slow
class TestReplay:
    """RTI Replay Service should re-publish recorded data."""

    def test_replay_produces_vitals(self, or_proc_manager, svc_proc_manager, clean_recording_dir):
        """Replay Service should publish t/patient/vitals from a recording."""
        from scripts.test_utils import UtilityApp, wait_for_reader_match, wait_for_samples

        # ── Phase 1: Record some data ─────────────────────────────────
        ps = or_proc_manager.start_app_ready("PatientSensor")

        rec_proc = svc_proc_manager.start_app_ready("RecordingService")
        time.sleep(3)

        # Kill PatientSensor and Recording Service to finalize the recording
        or_proc_manager.shutdown_all()
        svc_proc_manager.shutdown_all()

        assert rec_proc.poll() is not None, "Recording Service did not exit"
        assert ps.poll() is not None, "PatientSensor did not exit"

        db_file = clean_recording_dir / "or_recording_database.dat"
        assert db_file.is_file(), "Recording phase failed — no database"

        # ── Phase 2: Replay and verify data arrives ───────────────────

        with UtilityApp.make_non_secure() as app:
            reader = app.vitals.reader

            # Start Replay Service
            svc_proc_manager.start_app_ready("ReplayService")

            assert wait_for_reader_match(reader, timeout_sec=1), (
                "Vitals reader never matched Replay Service"
            )
            samples = wait_for_samples(reader, n=1, timeout_sec=3)

            assert len(samples) >= 1, "No vitals received from Replay Service"

    def test_replayed_arm_and_jaw_rates_drive_then_hold(
        self, or_proc_manager, svc_proc_manager, clean_recording_dir
    ):
        from MedTech import Geometry, Robot
        from scripts.test_utils import (
            UtilityApp,
            wait_for_reader_match,
            wait_for_samples,
            wait_for_writer_match,
        )

        with UtilityApp.make_non_secure() as source:
            arm_writer = source.teleop_control.writer
            tool_writer = source.tool_control.writer
            svc_proc_manager.start_app_ready("RecordingService")
            assert wait_for_writer_match(arm_writer, timeout_sec=5)
            assert wait_for_writer_match(tool_writer, timeout_sec=5)
            arm = Robot.Arm.TeleopControl(arm_id="arm-1", linear_velocity=Geometry.Vector3(x=0.01))
            tool = Robot.Tool.ParallelJawControl(arm_id="arm-1", opening_rate=0.01)
            until = time.monotonic() + 0.6
            while time.monotonic() < until:
                arm_writer.write(arm)
                tool_writer.write(tool)
                time.sleep(0.02)
            svc_proc_manager.shutdown_all()

        with UtilityApp.make_non_secure() as observer:
            telemetry = observer.arm_telemetry.reader
            or_proc_manager.start_app_ready("Arm")
            assert wait_for_reader_match(telemetry, timeout_sec=5)
            initial = wait_for_samples(telemetry, n=1, timeout_sec=2)[-1]
            svc_proc_manager.start_app_ready("ReplayService")

            def position(sample):
                point = sample.tcp_pose.position
                return (point.x, point.y, point.z)

            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                observed = wait_for_samples(telemetry, n=1, timeout_sec=2)[-1]
                if (
                    math.dist(position(initial), position(observed)) > 0.0005
                    and observed.parallel_jaw.opening_width
                    > initial.parallel_jaw.opening_width + 0.0005
                ):
                    break
            else:
                pytest.fail("Replayed arm and tool commands did not produce observed motion")

            svc_proc_manager.shutdown_all()
            settled = wait_for_samples(telemetry, n=9, timeout_sec=2)[-1]
            held = wait_for_samples(telemetry, n=4, timeout_sec=2)[-1]
            assert position(held) == pytest.approx(position(settled), abs=1e-8)
            assert held.parallel_jaw.opening_width == pytest.approx(
                settled.parallel_jaw.opening_width, abs=1e-8
            )
