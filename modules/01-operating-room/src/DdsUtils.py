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

import rti.connextdds as dds
from Types import idl


# Simplifying how to register a type since we're using the same name
def register_type(data_type):
    dds.DomainParticipant.register_idl_type(data_type, idl.get_type_support(data_type).type_name)


def vitals_from_sample(sample):
    """Map a generated DDS Vitals sample to application-owned values."""
    return {
        "heart_rate": float(sample.hr),
        "spo2": float(sample.spo2),
        "etco2": float(sample.etco2),
        "nibp_s": float(sample.nibp_s),
        "nibp_d": float(sample.nibp_d),
    }
