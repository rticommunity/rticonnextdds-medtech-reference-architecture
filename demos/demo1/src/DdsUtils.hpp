//
// (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
//
// RTI grants Licensee a license to use, modify, compile, and create derivative
// works of the software solely for use with RTI Connext DDS.  Licensee may
// redistribute copies of the software provided that all such copies are
// subject to this license. The software is provided "as is", with no warranty
// of any type, including any warranty for fitness for any purpose. RTI is
// under no obligation to maintain or support the software.  RTI shall not be
// liable for any incidental or consequential damages arising out of the use or
// inability to use the software.

#ifndef DDS_UTILS_H
#define DDS_UTILS_H

#include <string>
#include <dds/core/ddscore.hpp>
#include "Types.hpp"

using namespace DdsEntities::Constants;

// Define the DdsUtils namespace
namespace DdsUtils {
// Fully qualified name variables for DDS entities
inline const std::string arm_controller_dp_fqn =
        DP_LIBRARY_NAME + SEPARATOR + DP_ARM_CONTROLLER_NAME;
inline const std::string orchestrator_dp_fqn =
        DP_LIBRARY_NAME + SEPARATOR + DP_ORCHESTRATOR_NAME;
inline const std::string patient_sensor_dp_fqn =
        DP_LIBRARY_NAME + SEPARATOR + DP_PATIENT_SENSOR_NAME;

// DW / DR prefixes
inline const std::string dw_prefix = PUBLISHER_NAME + SEPARATOR + DW_PREFIX;
inline const std::string dr_prefix = SUBSCRIBER_NAME + SEPARATOR + DR_PREFIX;

// DWs / DRs names
inline const std::string status_dw_fqn = dw_prefix + ENDPOINT_DEVICE_STATUS_NAME;
inline const std::string status_dr_fqn = dr_prefix + ENDPOINT_DEVICE_STATUS_NAME;
inline const std::string hb_dw_fqn = dw_prefix + ENDPOINT_DEVICE_HEARTBEAT_NAME;
inline const std::string hb_dr_fqn = dr_prefix + ENDPOINT_DEVICE_HEARTBEAT_NAME;
inline const std::string motor_control_dw_fqn =
        dw_prefix + ENDPOINT_MOTOR_CONTROL_NAME;
inline const std::string device_command_dw_fqn =
        dw_prefix + ENDPOINT_DEVICE_COMMAND_NAME;
inline const std::string device_command_dr_fqn =
        dr_prefix + ENDPOINT_DEVICE_COMMAND_NAME;
inline const std::string vitals_dw_fqn = dw_prefix + ENDPOINT_VITALS_NAME;

// Simplifying how to register a type since we're using the same name
template <typename T>
void register_type()
{
    rti::domain::register_type<T>(dds::topic::topic_type_name<T>::value());
}
}  // namespace DdsUtils

#endif  // DDS_UTILS_H
