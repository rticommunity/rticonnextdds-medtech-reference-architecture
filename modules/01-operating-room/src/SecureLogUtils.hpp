//
// (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
//
// RTI grants Licensee a license to use, modify, compile, and create derivative
// works of the software solely for use with RTI Connext DDS.  Licensee may
// redistribute copies of the software provided that all such copies are
// subject to this license. The software is provided "as is", with no warranty
// of any type, including any warranty for fitness for any purpose. RTI is
// under no obligation to maintain or support the software.  RTI shall not be
// liable for any incidental or consequential damages arising out of the use or
// inability to use the software.

#ifndef SECURE_LOG_UTILS_H
#define SECURE_LOG_UTILS_H


#include <string>
#include <dds/domain/DomainParticipant.hpp>
#include <rti/core/policy/CorePolicy.hpp>
#include <dds/sub/DataReader.hpp>
#include <dds/sub/find.hpp>
#include <rti/sub/SampleProcessor.hpp>
#include "Types.hpp"

using namespace DdsEntities::Constants;
#include "builtin_logging_type.hpp"


// Define the SecureLogUtils namespace
namespace SecureLogUtils {

using SecureLogType = DDSSecurity::BuiltinLoggingTypeV2;
using SecureLogHandler = std::function<void(const SecureLogType&)>;
using SecureLogReader = std::pair<dds::sub::DataReader<SecureLogType>, rti::sub::SampleProcessor>;

bool is_secure(const dds::domain::DomainParticipant& participant)
{
    if (participant == dds::core::null) {
        throw std::runtime_error("Participant must be created to determine if secure.");
    }
    return participant.qos().policy<rti::core::policy::Property>().exists("com.rti.serv.load_plugin");
}

SecureLogReader setup_secure_log_reader(
    SecureLogHandler log_handler,
    dds::core::QosProvider qos_provider = dds::core::QosProvider::Default()
)
{
    try {
        rti::domain::register_type<SecureLogType>();
    } catch (const std::exception& e) {
        std::cerr << "Failed to register internal secure logging type: " << e.what() << std::endl;
    }

    // Initialize Participant
    dds::domain::DomainParticipant securelog_participant =
        qos_provider.extensions().create_participant_from_config(
                SECURELOG_READER_DP);
    if (securelog_participant == dds::core::null) {
        throw std::runtime_error("Failed to lookup secure log reader participant");
    }

    // Initialize DataReader
    dds::sub::DataReader<SecureLogType> securelog_reader = 
        rti::sub::find_datareader_by_name<
            dds::sub::DataReader<SecureLogType>>(
                securelog_participant,
                SECURELOG_DR);
    if (securelog_reader == dds::core::null) {
        throw std::runtime_error("Failed to lookup secure log reader datareader");
    }

    rti::sub::SampleProcessor securelog_processor;
    securelog_processor.attach_reader(
        securelog_reader,
        [log_handler](const rti::sub::LoanedSample<SecureLogType>&sample) {
            if (sample.info().valid()) {
                log_handler(sample.data());
            }
        }
    );

    return {securelog_reader, securelog_processor};
}

}  // namespace SecureLogUtils

#endif // SECURE_LOG_UTILS_H