//
// (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
// Licensed under the terms in LICENSE.
#pragma once

#include <dds/domain/DomainParticipant.hpp>
#include <rti/core/policy/CorePolicy.hpp>

namespace medtech::operating_room {

inline bool participant_security_enabled(
        const dds::domain::DomainParticipant &participant)
{
    return participant.qos().policy<rti::core::policy::Property>().exists(
            "com.rti.serv.load_plugin");
}

}  // namespace medtech::operating_room
