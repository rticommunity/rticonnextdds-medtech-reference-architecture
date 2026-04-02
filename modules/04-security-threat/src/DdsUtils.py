# 
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
# 
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

import sys
import os

# Module 01 src/ is the authoritative location for Types.py and the shared
# register_type helper.  Add it to the path so both are importable here.
_OR_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "01-operating-room", "src")
if _OR_SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(_OR_SRC))

import rti.connextdds as dds
from Types import DdsEntities, idl, SurgicalRobot, Orchestrator, PatientMonitor


# Simplifying how to register a type since we're using the same name
# (same implementation as modules/01-operating-room/src/DdsUtils.py)
# Connext raises dds.Error if the type is already registered (e.g. on mode
# switch); the existing registration is valid so we ignore it.
def register_type(type):
    try:
        dds.DomainParticipant.register_idl_type(
            type, idl.get_type_support(type).type_name
        )
    except dds.Error:
        pass


def register_all_types():
    """Register all IDL types used by threat participants."""
    for t in (SurgicalRobot.MotorControl, Orchestrator.DeviceCommand,
              PatientMonitor.Vitals):
        register_type(t)

# ─── Threat Participant Library ──────────────────────────────────────────────

# Injector DPs
INJECTOR_UNSECURE_DP     = "ThreatParticipantLibrary::dp/ThreatInjector/Unsecure"
INJECTOR_ROGUE_CA_DP     = "ThreatParticipantLibrary::dp/ThreatInjector/RogueCA"
INJECTOR_FORGED_PERMS_DP = "ThreatParticipantLibrary::dp/ThreatInjector/ForgedPerms"
INJECTOR_EXPIRED_CERT_DP = "ThreatParticipantLibrary::dp/ThreatInjector/ExpiredCert"

# Exfiltrator DPs
EXFILTRATOR_UNSECURE_DP     = "ThreatParticipantLibrary::dp/ThreatExfiltrator/Unsecure"
EXFILTRATOR_ROGUE_CA_DP     = "ThreatParticipantLibrary::dp/ThreatExfiltrator/RogueCA"
EXFILTRATOR_FORGED_PERMS_DP = "ThreatParticipantLibrary::dp/ThreatExfiltrator/ForgedPerms"
EXFILTRATOR_EXPIRED_CERT_DP = "ThreatParticipantLibrary::dp/ThreatExfiltrator/ExpiredCert"
