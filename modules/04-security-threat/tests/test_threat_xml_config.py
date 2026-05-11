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
"""XML configuration validation tests for Module 04.

Verifies that ThreatParticipants.xml and ThreatQos.xml are well-formed
and contain the expected participant and QoS definitions.
"""

from pathlib import Path
from xml.etree import ElementTree

MODULE_DIR = Path(__file__).resolve().parent.parent  # modules/04-security-threat
XML_DIR = MODULE_DIR / "xml_config"

EXPECTED_INJECTOR_MODES = {"Unsecure", "RogueCA", "ForgedPerms", "ExpiredCert"}
EXPECTED_EXFILTRATOR_MODES = {"Unsecure", "RogueCA", "ForgedPerms", "ExpiredCert"}


class TestThreatParticipantsXml:
    """ThreatParticipants.xml should be well-formed and define all modes."""

    CONFIG = XML_DIR / "ThreatParticipants.xml"

    def test_file_exists(self):
        assert self.CONFIG.is_file(), f"Missing: {self.CONFIG}"

    def test_parses_without_error(self):
        ElementTree.parse(self.CONFIG)

    def test_contains_participant_library(self):
        tree = ElementTree.parse(self.CONFIG)
        root = tree.getroot()
        assert root.find("domain_participant_library") is not None

    def test_all_injector_modes_defined(self):
        tree = ElementTree.parse(self.CONFIG)
        lib = tree.getroot().find("domain_participant_library")
        dp_names = {dp.get("name") for dp in lib.findall("domain_participant")}
        for mode in EXPECTED_INJECTOR_MODES:
            assert f"dp/ThreatInjector/{mode}" in dp_names, f"Missing injector mode: {mode}"

    def test_all_exfiltrator_modes_defined(self):
        tree = ElementTree.parse(self.CONFIG)
        lib = tree.getroot().find("domain_participant_library")
        dp_names = {dp.get("name") for dp in lib.findall("domain_participant")}
        for mode in EXPECTED_EXFILTRATOR_MODES:
            assert f"dp/ThreatExfiltrator/{mode}" in dp_names, f"Missing exfiltrator mode: {mode}"

    def test_injectors_have_publishers(self):
        tree = ElementTree.parse(self.CONFIG)
        lib = tree.getroot().find("domain_participant_library")
        for dp in lib.findall("domain_participant"):
            if dp.get("name", "").startswith("dp/ThreatInjector/"):
                assert dp.find("publisher") is not None, f"{dp.get('name')} missing publisher"

    def test_exfiltrators_have_subscribers(self):
        tree = ElementTree.parse(self.CONFIG)
        lib = tree.getroot().find("domain_participant_library")
        for dp in lib.findall("domain_participant"):
            if dp.get("name", "").startswith("dp/ThreatExfiltrator/"):
                assert dp.find("subscriber") is not None, f"{dp.get('name')} missing subscriber"


class TestThreatQosXml:
    """ThreatQos.xml should be well-formed and define security QoS profiles."""

    CONFIG = XML_DIR / "ThreatQos.xml"

    def test_file_exists(self):
        assert self.CONFIG.is_file(), f"Missing: {self.CONFIG}"

    def test_parses_without_error(self):
        ElementTree.parse(self.CONFIG)

    def test_contains_qos_library(self):
        tree = ElementTree.parse(self.CONFIG)
        root = tree.getroot()
        assert root.find("qos_library") is not None

    def test_has_configuration_variables(self):
        tree = ElementTree.parse(self.CONFIG)
        root = tree.getroot()
        assert root.find("configuration_variables") is not None
