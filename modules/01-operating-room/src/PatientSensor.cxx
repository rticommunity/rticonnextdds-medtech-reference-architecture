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
#include <dds/core/cond/WaitSet.hpp>
#include <dds/sub/DataReader.hpp>
#include <dds/sub/find.hpp>
#include <dds/sub/cond/ReadCondition.hpp>
#include <dds/pub/DataWriter.hpp>
#include <dds/pub/find.hpp>
#include <dds/core/ddscore.hpp>

#include <chrono>
#include <cstring>
#include <csignal>
#include <stdexcept>

#include "HeartbeatPresence.hpp"
#include "MedTech.hpp"

using namespace DdsEntities::Constants;

static volatile std::sig_atomic_t g_shutdown = 0;

static void handle_signal(int)
{
    g_shutdown = 1;
}

class PatientSensorApp {
public:
    PatientSensorApp()
    {
        rti::domain::register_type<Device::Command>();
        rti::domain::register_type<Device::Status>();
        rti::domain::register_type<Device::Heartbeat>();
        rti::domain::register_type<Patient::Vitals>();

        auto default_provider = dds::core::QosProvider::Default();
        participant_ =
                default_provider.extensions().create_participant_from_config(
                        std::string(PATIENT_SENSOR_DP));
        if (participant_ == dds::core::null)
            throw std::runtime_error("Missing DDS participant: "
                                     + std::string(PATIENT_SENSOR_DP));
        vitals_writer_ = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Patient::Vitals>>(participant_,
                                                       std::string(VITALS_DW));
        status_writer_ = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Device::Status>>(participant_,
                                                      std::string(STATUS_DW));
        heartbeat_writer_ = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Device::Heartbeat>>(participant_,
                                                         std::string(HB_DW));
        command_reader_ = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Device::Command>>(
                participant_,
                std::string(DEVICE_COMMAND_DR));

        auto require_endpoint = [](const auto &endpoint, const auto &name) {
            if (endpoint == dds::core::null)
                throw std::runtime_error("Missing DDS endpoint: "
                                         + std::string(name));
        };
        require_endpoint(vitals_writer_, VITALS_DW);
        require_endpoint(status_writer_, STATUS_DW);
        require_endpoint(heartbeat_writer_, HB_DW);
        require_endpoint(command_reader_, DEVICE_COMMAND_DR);

        current_status_.device = Device::DeviceType::PATIENT_SENSOR;
        status_ = Device::DeviceStatuses::ON;

        command_read_condition_ = dds::sub::cond::ReadCondition(
                command_reader_,
                dds::sub::status::DataState::any(),
                [this]() { process_command(); });
        command_waitset_ += command_read_condition_;
    }

    void run()
    {
        participant_.enable();
        std::cout << "Launching Patient Sensor" << std::endl;

        medtech::operating_room::HeartbeatPublisher heartbeat(
                heartbeat_writer_,
                Device::DeviceType::PATIENT_SENSOR);
        write_status();

        heartbeat.start();
        while (!g_shutdown && !heartbeat.failed()
               && status_ != Device::DeviceStatuses::OFF) {
            command_waitset_.dispatch(dds::core::Duration(1));
            write_vitals();
        }

        heartbeat.stop();
        if (heartbeat.failed())
            throw std::runtime_error("Patient Sensor heartbeat worker failed");

        if (g_shutdown) {
            std::cout << "Shutting Down Patient Sensor (signal)" << std::endl;
            status_ = Device::DeviceStatuses::OFF;
            write_status();
        }
    }

private:
    dds::domain::DomainParticipant participant_ = dds::core::null;
    dds::pub::DataWriter<Patient::Vitals> vitals_writer_ = dds::core::null;
    dds::pub::DataWriter<Device::Status> status_writer_ = dds::core::null;
    dds::pub::DataWriter<Device::Heartbeat> heartbeat_writer_ = dds::core::null;
    dds::sub::DataReader<Device::Command> command_reader_ = dds::core::null;
    dds::sub::cond::ReadCondition command_read_condition_ = dds::core::null;
    dds::core::cond::WaitSet command_waitset_;
    Device::Status current_status_;
    Device::DeviceStatuses status_ { Device::DeviceStatuses::OFF };

    void write_vitals()
    {
        Patient::Vitals sample;
        sample.patient_id = "ab1234";
        sample.hr = 55 + rand() % 11;
        sample.spo2 = 90 + rand() % 11;
        sample.etco2 = 35 + rand() % 11;
        sample.nibp_s = 115 + rand() % 11;
        sample.nibp_d = 75 + rand() % 11;

        if (status_ == Device::DeviceStatuses::ON)
            vitals_writer_.write(sample);
    }

    void write_status()
    {
        current_status_.status = status_;
        status_writer_.write(current_status_);
    }

    void process_command()
    {
        dds::sub::LoanedSamples<Device::Command> samples =
                command_reader_.take();

        for (const auto &sample : samples) {
            if (sample.info().valid()) {
                if (sample.data().command == Device::DeviceCommands::PAUSE) {
                    std::cout << "Pausing Patient Sensor" << std::endl;
                    status_ = Device::DeviceStatuses::PAUSED;
                } else if (sample.data().command
                           == Device::DeviceCommands::START) {
                    std::cout << "Starting Patient Sensor" << std::endl;
                    status_ = Device::DeviceStatuses::ON;
                } else {  // shutdown
                    std::cout << "Shutting Down Patient Sensor" << std::endl;
                    status_ = Device::DeviceStatuses::OFF;
                }
                write_status();
            }
        }
    }
};

int main(int argc, char const *argv[])
{
    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);
    try {
        PatientSensorApp patient_sensor;
        patient_sensor.run();
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "Patient Sensor failed: " << error.what() << std::endl;
    } catch (...) {
        std::cerr << "Patient Sensor failed with an unknown exception"
                  << std::endl;
    }
    return 1;
}
