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
"""XML configuration validation tests for Module 02.

Verifies that RecordingServiceConfiguration.xml and
ReplayServiceConfiguration.xml are well-formed and contain expected elements.
"""

from pathlib import Path
from xml.etree import ElementTree

MODULE_DIR = Path(__file__).resolve().parent.parent  # modules/02-record-playback


class TestRecordingXml:
    """RecordingServiceConfiguration.xml should be well-formed and complete."""

    CONFIG = MODULE_DIR / "RecordingServiceConfiguration.xml"

    def test_file_exists(self):
        assert self.CONFIG.is_file(), f"Missing: {self.CONFIG}"

    def test_parses_without_error(self):
        ElementTree.parse(self.CONFIG)

    def test_contains_recording_service_element(self):
        tree = ElementTree.parse(self.CONFIG)
        root = tree.getroot()
        assert root.find("recording_service") is not None

    def test_recording_service_has_session(self):
        tree = ElementTree.parse(self.CONFIG)
        rec = tree.getroot().find("recording_service")
        assert rec.find("session") is not None

    def test_records_vitals_topic(self):
        tree = ElementTree.parse(self.CONFIG)
        session = tree.getroot().find("recording_service/session")
        topic_names = [t.findtext("topic_name") for t in session.findall("topic")]
        assert "t/Vitals" in topic_names

    def test_records_motor_control_topic(self):
        tree = ElementTree.parse(self.CONFIG)
        session = tree.getroot().find("recording_service/session")
        topic_names = [t.findtext("topic_name") for t in session.findall("topic")]
        assert "t/MotorControl" in topic_names


class TestReplayXml:
    """ReplayServiceConfiguration.xml should be well-formed and complete."""

    CONFIG = MODULE_DIR / "ReplayServiceConfiguration.xml"

    def test_file_exists(self):
        assert self.CONFIG.is_file(), f"Missing: {self.CONFIG}"

    def test_parses_without_error(self):
        ElementTree.parse(self.CONFIG)

    def test_contains_replay_service_element(self):
        tree = ElementTree.parse(self.CONFIG)
        root = tree.getroot()
        assert root.find("replay_service") is not None

    def test_replay_service_has_playback(self):
        tree = ElementTree.parse(self.CONFIG)
        rep = tree.getroot().find("replay_service")
        assert rep.find("playback") is not None

    def test_looping_is_enabled(self):
        tree = ElementTree.parse(self.CONFIG)
        looping = tree.getroot().findtext("replay_service/playback/enable_looping")
        assert looping == "true"
