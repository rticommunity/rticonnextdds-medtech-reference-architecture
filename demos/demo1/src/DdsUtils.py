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
from Types import DdsEntities, idl


# Simplifying how to register a type since we're using the same name
def register_type(type):
    dds.DomainParticipant.register_idl_type(
        type, idl.get_type_support(type).type_name
    )


constants = DdsEntities.Constants

# DPs
arm_dp_fqn = (
    constants.DP_LIBRARY_NAME + constants.SEPARATOR + constants.DP_ARM_NAME
)
patient_monitor_dp_fqn = (
    constants.DP_LIBRARY_NAME
    + constants.SEPARATOR
    + constants.DP_PATIENT_MONITOR_NAME
)

# DW / DR prefixes
dw_prefix = (
    constants.PUBLISHER_NAME + constants.SEPARATOR + constants.DW_PREFIX
)
dr_prefix = (
    constants.SUBSCRIBER_NAME + constants.SEPARATOR + constants.DR_PREFIX
)

# DWs / DRs names
status_dw_fqn = dw_prefix + constants.ENDPOINT_DEVICE_STATUS_NAME
device_hb_dw_fqn = dw_prefix + constants.ENDPOINT_DEVICE_HEARTBEAT_NAME

motor_control_dr_fqn = dr_prefix + constants.ENDPOINT_MOTOR_CONTROL_NAME
device_command_dr_fqn = dr_prefix + constants.ENDPOINT_DEVICE_COMMAND_NAME
vitals_dr_fqn = dr_prefix + constants.ENDPOINT_VITALS_NAME
