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

#include <dds/core/QosProvider.hpp>
#include <dds/sub/DataReader.hpp>
#include <dds/sub/find.hpp>
#include <dds/pub/DataWriter.hpp>
#include <dds/pub/find.hpp>
#include <dds/core/ddscore.hpp>

#include <thread>
#include <chrono>
#include <unistd.h>
#include <cstring>

#include "Types.hpp"
#include "DdsUtils.hpp"

class PatientSensor {
public:
    void run()
    {
        // We need to register the types before we start creating DDS entities
        rti::domain::register_type<Orchestrator::DeviceCommand>();
        rti::domain::register_type<Common::DeviceStatus>();
        rti::domain::register_type<Common::DeviceHeartbeat>();
        rti::domain::register_type<PatientMonitor::Vitals>();

        // Connext will load XML files through the default provider from the
        // NDDS_QOS_PROFILES environment variable
        auto default_provider = dds::core::QosProvider::Default();

        dds::domain::DomainParticipant participant =
                default_provider.extensions().create_participant_from_config(
                        DdsUtils::patient_sensor_dp_fqn);

        // Initialize DataWriters
        dds::pub::DataWriter<PatientMonitor::Vitals> vitals_writer =
                rti::pub::find_datawriter_by_name<
                        dds::pub::DataWriter<PatientMonitor::Vitals>>(
                        participant,
                        DdsUtils::vitals_dw_fqn);

        dds::pub::DataWriter<Common::DeviceStatus> status_writer =
                rti::pub::find_datawriter_by_name<
                        dds::pub::DataWriter<Common::DeviceStatus>>(
                        participant,
                        DdsUtils::status_dw_fqn);

        dds::pub::DataWriter<Common::DeviceHeartbeat> hb_writer =
                rti::pub::find_datawriter_by_name<
                        dds::pub::DataWriter<Common::DeviceHeartbeat>>(
                        participant,
                        DdsUtils::hb_dw_fqn);

        // Initialize DataReader
        dds::sub::DataReader<Orchestrator::DeviceCommand> cmd_reader =
                rti::sub::find_datareader_by_name<
                        dds::sub::DataReader<Orchestrator::DeviceCommand>>(
                        participant,
                        DdsUtils::device_command_dr_fqn);

        current_status.device(Common::DeviceType::PATIENT_SENSOR);
        current_status.status(Common::DeviceStatuses::ON);

        // Read condition to process commands
        dds::sub::cond::ReadCondition command_read_condition(
                cmd_reader,
                dds::sub::status::DataState::any(),
                [this, &cmd_reader, &status_writer]() {
                    process_command(cmd_reader, status_writer);
                });

        dds::core::cond::WaitSet waitset_command;
        waitset_command += command_read_condition;

        std::cout << "Launching Patient Sensor" << std::endl;

        // Start heartbeat thread
        std::thread hb_thread(&PatientSensor::write_hb, this, hb_writer);
        write_status(status_writer);

        // Main loop
        while (current_status.status() != Common::DeviceStatuses::OFF) {
            waitset_command.dispatch(dds::core::Duration(1));
            write_vitals(vitals_writer);
        }

        hb_thread.join();
    }

private:
    Common::DeviceStatus current_status;

    // Function to publish vitals
    void write_vitals(
            dds::pub::DataWriter<PatientMonitor::Vitals> vitals_writer)
    {
        PatientMonitor::Vitals sample;
        sample.patient_id("ab1234");
        sample.hr(55 + rand() % 11);
        sample.spo2(90 + rand() % 11);
        sample.etco2(35 + rand() % 11);
        sample.nibp_s(115 + rand() % 11);
        sample.nibp_d(75 + rand() % 11);

        if (current_status.status() == Common::DeviceStatuses::ON)
            vitals_writer.write(sample);
    }

    // Function to publish heartbeats every 50ms
    void write_hb(dds::pub::DataWriter<Common::DeviceHeartbeat> hb_writer)
    {
        while (current_status.status() != Common::DeviceStatuses::OFF) {
            Common::DeviceHeartbeat hb(Common::DeviceType::PATIENT_SENSOR);
            hb_writer.write(hb);
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    }

    // Function to publish device status
    void write_status(dds::pub::DataWriter<Common::DeviceStatus> status_writer)
    {
        status_writer.write(current_status);
    }

    // Function to process commands sent from the Orchestrator
    void process_command(
            dds::sub::DataReader<Orchestrator::DeviceCommand> cmd_reader,
            dds::pub::DataWriter<Common::DeviceStatus> status_writer)
    {
        dds::sub::LoanedSamples<Orchestrator::DeviceCommand> samples =
                cmd_reader.take();

        for (const auto &sample : samples) {
            if (sample.info().valid()) {
                if (sample.data().command()
                    == Orchestrator::DeviceCommands::PAUSE) {
                    std::cout << "Pausing Patient Sensor" << std::endl;
                    current_status.status(Common::DeviceStatuses::PAUSED);
                } else if (
                        sample.data().command()
                        == Orchestrator::DeviceCommands::START) {
                    std::cout << "Starting Patient Sensor" << std::endl;
                    current_status.status(Common::DeviceStatuses::ON);
                } else {  // shutdown
                    std::cout << "Shutting Down Patient Sensor" << std::endl;
                    current_status.status(Common::DeviceStatuses::OFF);
                }
                write_status(status_writer);
            }
        }
    }
};

// Main function creates an instance of PatientMonitor and runs it
int main(int argc, char const *argv[])
{
    PatientSensor patient_sensor;
    patient_sensor.run();
    return 0;
}
