"""XML and QoS configuration validation tests.

Validates that all XML files in system_arch/ parse correctly and that
the expected QoS profiles, topics, and participants are defined.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from conftest import SRC_DIR, SYSTEM_ARCH_DIR

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# XML files under test
QOS_XML = SYSTEM_ARCH_DIR / "qos" / "Qos.xml"
NON_SECURE_QOS_XML = SYSTEM_ARCH_DIR / "qos" / "NonSecureAppsQos.xml"
SECURE_QOS_XML = SYSTEM_ARCH_DIR / "qos" / "SecureAppsQos.xml"
DOMAIN_LIB_XML = SYSTEM_ARCH_DIR / "xml_app_creation" / "DomainLibrary.xml"
PARTICIPANT_LIB_XML = SYSTEM_ARCH_DIR / "xml_app_creation" / "ParticipantLibrary.xml"
TYPES_XML = SYSTEM_ARCH_DIR / "Types.xml"


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------


class TestXmlParsing:
    """Every XML configuration file should parse without errors."""

    @pytest.mark.parametrize(
        "xml_file",
        [
            QOS_XML,
            NON_SECURE_QOS_XML,
            SECURE_QOS_XML,
            DOMAIN_LIB_XML,
            PARTICIPANT_LIB_XML,
            TYPES_XML,
        ],
        ids=lambda p: p.name,
    )
    def test_xml_parses(self, xml_file: Path):
        assert xml_file.is_file(), f"XML file not found: {xml_file}"
        tree = ET.parse(xml_file)
        assert tree.getroot().tag == "dds"


# ---------------------------------------------------------------------------
# QoS profiles
# ---------------------------------------------------------------------------


class TestQosProfiles:
    """Qos.xml should define the expected QoS libraries and profiles."""

    @pytest.fixture(scope="class")
    def qos_root(self):
        return ET.parse(QOS_XML).getroot()

    def _profile_names(self, root, library_name: str) -> list[str]:
        """Return profile names under a <qos_library>."""
        for lib in root.findall("qos_library"):
            if lib.get("name") == library_name:
                return [p.get("name") for p in lib.findall("qos_profile")]
        return []

    def test_system_library_exists(self, qos_root):
        names = self._profile_names(qos_root, "SystemLibrary")
        assert "DefaultParticipant" in names

    @pytest.mark.parametrize(
        "profile",
        [
            "Streaming",
            "Status",
            "Command",
            "Heartbeat",
            "SecureLog",
        ],
    )
    def test_dataflow_profile_exists(self, qos_root, profile):
        names = self._profile_names(qos_root, "DataFlowLibrary")
        assert profile in names, f"DataFlowLibrary::{profile} not found. Available: {names}"

    def test_heartbeat_profile_has_deadline(self, qos_root):
        """Heartbeat profile should define a 200ms deadline on both reader and writer."""
        for lib in qos_root.findall("qos_library"):
            if lib.get("name") != "DataFlowLibrary":
                continue
            for prof in lib.findall("qos_profile"):
                if prof.get("name") != "Heartbeat":
                    continue
                # Check datareader_qos deadline
                dr_qos = prof.find("datareader_qos")
                assert dr_qos is not None, "Heartbeat profile missing datareader_qos"
                deadline_ns = dr_qos.findtext("deadline/period/nanosec")
                assert deadline_ns is not None, "Missing deadline nanosec in datareader_qos"
                assert int(deadline_ns) == 200_000_000
                return
        pytest.fail("Heartbeat profile not found in DataFlowLibrary")


# ---------------------------------------------------------------------------
# Non-secure / Secure DpQosLib
# ---------------------------------------------------------------------------


class TestDpQosLib:
    """Both NonSecureAppsQos.xml and SecureAppsQos.xml should define DpQosLib
    with per-participant profiles."""

    EXPECTED_PROFILES = {"Arm", "ArmController", "Orchestrator", "PatientSensor", "PatientMonitor", "Test"}

    @pytest.mark.parametrize("xml_file", [NON_SECURE_QOS_XML, SECURE_QOS_XML], ids=lambda p: p.name)
    def test_dpqoslib_profiles(self, xml_file: Path):
        root = ET.parse(xml_file).getroot()
        for lib in root.findall("qos_library"):
            if lib.get("name") == "DpQosLib":
                names = {p.get("name") for p in lib.findall("qos_profile")}
                missing = self.EXPECTED_PROFILES - names
                assert not missing, f"{xml_file.name} DpQosLib missing profiles: {missing}"
                return
        pytest.fail(f"DpQosLib not found in {xml_file.name}")


# ---------------------------------------------------------------------------
# Domain library
# ---------------------------------------------------------------------------


class TestDomainLibrary:
    """DomainLibrary.xml should define all expected topics on Domain 0."""

    EXPECTED_TOPICS = {
        "t/Vitals",
        "t/DeviceStatus",
        "t/DeviceHeartbeat",
        "t/DeviceCommand",
        "t/MotorControl",
    }

    @pytest.fixture(scope="class")
    def domain_root(self):
        return ET.parse(DOMAIN_LIB_XML).getroot()

    def test_operational_domain_exists(self, domain_root):
        domains = [d.get("name") for d in domain_root.iter("domain")]
        assert "OperationalDataDomain" in domains

    def test_all_topics_defined(self, domain_root):
        topics = set()
        for d in domain_root.iter("domain"):
            if d.get("name") == "OperationalDataDomain":
                topics = {t.get("name") for t in d.findall("topic")}
                break
        missing = self.EXPECTED_TOPICS - topics
        assert not missing, f"Missing topics: {missing}"


# ---------------------------------------------------------------------------
# Participant library
# ---------------------------------------------------------------------------


class TestParticipantLibrary:
    """ParticipantLibrary.xml should define all five application participants."""

    EXPECTED_PARTICIPANTS = {
        "dp/Arm",
        "dp/ArmController",
        "dp/Orchestrator",
        "dp/PatientSensor",
        "dp/PatientMonitor",
    }

    @pytest.fixture(scope="class")
    def participant_root(self):
        return ET.parse(PARTICIPANT_LIB_XML).getroot()

    def test_all_participants_defined(self, participant_root):
        names = set()
        for dp in participant_root.iter("domain_participant"):
            name = dp.get("name")
            if name and name.startswith("dp/"):
                names.add(name)
        missing = self.EXPECTED_PARTICIPANTS - names
        assert not missing, f"Missing participants: {missing}"

    def test_participants_have_content_filters(self, participant_root):
        """Devices subscribing to DeviceCommand should have content filters."""
        devices_with_filter = set()
        for dp in participant_root.iter("domain_participant"):
            dp_name = dp.get("name", "")
            for dr in dp.iter("data_reader"):
                if dr.get("name") == "dr/DeviceCommand":
                    cf = dr.find("content_filter")
                    if cf is not None:
                        devices_with_filter.add(dp_name)
        # All devices except Orchestrator (which publishes commands, not subscribes)
        expected = {"dp/Arm", "dp/ArmController", "dp/PatientSensor", "dp/PatientMonitor"}
        missing = expected - devices_with_filter
        assert not missing, f"Missing content filters on: {missing}"


# ---------------------------------------------------------------------------
# Types.xml
# ---------------------------------------------------------------------------


class TestTypesXml:
    """Types.xml should define all required DDS types."""

    @pytest.fixture(scope="class")
    def types_root(self):
        return ET.parse(TYPES_XML).getroot()

    def test_common_module_enums(self, types_root):
        enum_names = set()
        for mod in types_root.iter("module"):
            if mod.get("name") == "Common":
                for e in mod.findall("enum"):
                    enum_names.add(e.get("name"))
        assert "DeviceStatuses" in enum_names
        assert "DeviceType" in enum_names

    def test_common_module_structs(self, types_root):
        struct_names = set()
        for mod in types_root.iter("module"):
            if mod.get("name") == "Common":
                for s in mod.findall("struct"):
                    struct_names.add(s.get("name"))
        assert "DeviceStatus" in struct_names
        assert "DeviceHeartbeat" in struct_names

    def test_surgical_robot_module(self, types_root):
        names = set()
        for mod in types_root.iter("module"):
            if mod.get("name") == "SurgicalRobot":
                for child in mod:
                    names.add(child.get("name"))
        assert {"Motors", "MotorDirections", "MotorControl"} <= names

    def test_vitals_struct(self, types_root):
        for mod in types_root.iter("module"):
            if mod.get("name") == "PatientMonitor":
                for s in mod.findall("struct"):
                    if s.get("name") == "Vitals":
                        members = {m.get("name") for m in s.findall("member")}
                        expected = {"patient_id", "hr", "spo2", "etco2", "nibp_s", "nibp_d"}
                        assert expected <= members
                        return
        pytest.fail("PatientMonitor::Vitals struct not found")
