//
// (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
//
// RTI grants Licensee a license to use, modify, compile, and create derivative
// works of the software solely for use with RTI Connext DDS. The software is
// provided "as is", with no warranty of any type.

#include <dds/core/QosProvider.hpp>
#include <dds/core/ddscore.hpp>
#include <dds/pub/DataWriter.hpp>
#include <dds/pub/find.hpp>
#include <dds/sub/DataReader.hpp>
#include <dds/sub/find.hpp>
#include <dds/sub/cond/ReadCondition.hpp>

#include <array>
#include <atomic>
#include <chrono>
#include <ctime>
#include <exception>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <sstream>
#include <thread>
#include <tuple>

#include <rti/core/cond/AsyncWaitSet.hpp>

#include <rti_demo_ui/rti_demo_ui.hpp>

#include "DemoUiSupport.hpp"
#include "HeartbeatPresence.hpp"
#include "MedTech.hpp"
#include "ParticipantSecurity.hpp"

#ifdef RTI_SECURITY_AVAILABLE
    #include "SecureLog.hpp"
#endif

using namespace DdsEntities::Constants;
using namespace std::chrono_literals;
using rti::demo::ui::Json;

namespace {

struct UiEvent {
    std::string kind;
    std::string device;
    std::string command;
    std::string message;
};

std::string current_time()
{
    const auto now = std::time(nullptr);
    std::tm local_time { };
#ifdef _WIN32
    localtime_s(&local_time, &now);
#else
    localtime_r(&now, &local_time);
#endif
    std::ostringstream result;
    result << std::put_time(&local_time, "%H:%M:%S");
    return result.str();
}

std::string device_name(Device::DeviceType device)
{
    switch (device) {
    case Device::DeviceType::ARM:
        return "ARM";
    case Device::DeviceType::ARM_CONTROLLER:
        return "ARM_CONTROLLER";
    case Device::DeviceType::PATIENT_SENSOR:
        return "PATIENT_SENSOR";
    case Device::DeviceType::PATIENT_MONITOR:
        return "PATIENT_MONITOR";
    }
    return "UNKNOWN";
}

Device::DeviceType parse_device(const std::string &name)
{
    if (name == "ARM")
        return Device::DeviceType::ARM;
    if (name == "ARM_CONTROLLER")
        return Device::DeviceType::ARM_CONTROLLER;
    if (name == "PATIENT_SENSOR")
        return Device::DeviceType::PATIENT_SENSOR;
    return Device::DeviceType::PATIENT_MONITOR;
}

Device::DeviceCommands parse_command(const std::string &name)
{
    if (name == "START")
        return Device::DeviceCommands::START;
    if (name == "PAUSE")
        return Device::DeviceCommands::PAUSE;
    return Device::DeviceCommands::SHUTDOWN;
}

std::string status_name(Device::DeviceStatuses status)
{
    if (status == Device::DeviceStatuses::ON)
        return "ON";
    if (status == Device::DeviceStatuses::PAUSED)
        return "PAUSED";
    if (status == Device::DeviceStatuses::ERROR)
        return "ERROR";
    return "OFF";
}

Json orchestrator_view(
        const std::map<Device::DeviceType, std::string> &statuses,
        const std::map<Device::DeviceType, bool> &presence,
        Device::DeviceType selected_device,
        bool secure,
        bool security_threat,
        const Json &logs)
{
    const std::array devices = {
        Device::DeviceType::ARM,
        Device::DeviceType::ARM_CONTROLLER,
        Device::DeviceType::PATIENT_SENSOR,
        Device::DeviceType::PATIENT_MONITOR,
    };
    Json device_rows = Json::array();
    for (const auto device : devices) {
        const auto status = statuses.at(device);
        device_rows.push_back({
                { "name", device_name(device) },
                { "status", presence.at(device) ? status : "OFF" },
                { "selected", device == selected_device },
        });
    }

    Json command_controls = Json::array({
            { { "type", "button" },
              { "label", "▶  START" },
              { "command", "send-device-command" },
              { "payload", { { "command", "START" } } },
              { "className", "start-command" } },
            { { "type", "button" },
              { "label", "▮▮  PAUSE" },
              { "command", "send-device-command" },
              { "payload", { { "command", "PAUSE" } } },
              { "className", "pause-command" } },
            { { "type", "button" },
              { "label", "■  SHUT DOWN" },
              { "command", "send-device-command" },
              { "payload", { { "command", "SHUTDOWN" } } },
              { "className", "shutdown-command" } },
    });
    const std::string security_state = security_threat ? "THREAT DETECTED"
            : secure                                   ? "SECURITY: OK"
                                                       : "UNSECURE";
    return {
        { "kind", "orchestrator" },
        { "title", "System Orchestrator" },
        { "status", security_state },
        { "dds_security", secure },
        { "header_badges",
          security_threat ? Json::array({ { { "label", "Alert" },
                                            { "value", security_state },
                                            { "tone", "danger" } } })
                          : Json::array() },
        { "devices", device_rows },
        { "control_groups",
          Json::array({ { { "title", "" },
                          { "layout", "device-commands" },
                          { "controls", command_controls } } }) },
        { "selected_device", device_name(selected_device) },
        { "activity_title", "ALERTS" },
        { "show_activity_toggle", true },
        { "footer", false },
        { "logs", logs },
    };
}

class OrchestratorApp {
public:
    OrchestratorApp(rti::demo::ui::DemoUiApp &app,
                    medtech::ui::CommandQueue<UiEvent> &events,
                    std::atomic<bool> &stopping)
            : app_(app), events_(events), stopping_(stopping)
    {
        rti::domain::register_type<Device::Command>();
        rti::domain::register_type<Device::Status>();
        rti::domain::register_type<Device::Heartbeat>();

        provider_ = dds::core::QosProvider::Default();
        participant_ = provider_.extensions().create_participant_from_config(
                std::string(ORCHESTRATOR_DP));
        if (participant_ == dds::core::null)
            throw std::runtime_error("Missing DDS participant: "
                                     + std::string(ORCHESTRATOR_DP));
        command_writer_ = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Device::Command>>(
                participant_,
                std::string(DEVICE_COMMAND_DW));
        status_reader_ = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Device::Status>>(participant_,
                                                      std::string(STATUS_DR));
        heartbeat_reader_ = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Device::Heartbeat>>(participant_,
                                                         std::string(HB_DR));
        auto require_endpoint = [](const auto &endpoint, const auto &name) {
            if (endpoint == dds::core::null)
                throw std::runtime_error("Missing DDS endpoint: "
                                         + std::string(name));
        };
        require_endpoint(command_writer_, DEVICE_COMMAND_DW);
        require_endpoint(status_reader_, STATUS_DR);
        require_endpoint(heartbeat_reader_, HB_DR);
        heartbeat_monitor_ = std::make_unique<
                medtech::operating_room::HeartbeatPresenceMonitor>(
                heartbeat_reader_,
                [&events](Device::DeviceType device, bool is_present) {
                    events.push({
                            is_present ? "heartbeat-present" : "heartbeat-lost",
                            device_name(device),
                            { },
                            { },
                    });
                });
    }

    void run()
    {
        std::map<Device::DeviceType, std::string> statuses;
        std::map<Device::DeviceType, bool> presence;
        for (const auto device : {
                     Device::DeviceType::ARM,
                     Device::DeviceType::ARM_CONTROLLER,
                     Device::DeviceType::PATIENT_SENSOR,
                     Device::DeviceType::PATIENT_MONITOR,
             }) {
            statuses[device] = "OFF";
            presence[device] = false;
        }

        auto selected_device = Device::DeviceType::ARM;
        Json logs = Json::array();
        const bool secure =
                medtech::operating_room::participant_security_enabled(
                        participant_);
        auto security_threat_until = std::chrono::steady_clock::time_point { };
        auto append_log = [&](std::string message,
                              const std::string &level = "info") {
            logs.push_back({
                    { "time", current_time() },
                    { "message", std::move(message) },
                    { "level", level },
            });
            if (logs.size() > 80)
                logs.erase(logs.begin());
        };

#ifdef RTI_SECURITY_AVAILABLE
        SecureLog::SecureLogReader securelog_reader = { dds::core::null,
                                                        dds::core::null };
        if (secure) {
            securelog_reader = SecureLog::setup_secure_log_reader(
                    [this](const SecureLog::SecureLogType &sample) {
                        const auto severity =
                                static_cast<int32_t>(sample.severity);
                        if (severity <= static_cast<int32_t>(
                                    DDSSecurity::LoggingLevel::WARNING_LEVEL)) {
                            events_.push({
                                    "security",
                                    { },
                                    { },
                                    "SECURITY THREAT [" + sample.appname + "] "
                                            + sample.message,
                            });
                        }
                    },
                    provider_);
        }
#endif

        auto publish_view = [&]() {
            const bool security_threat =
                    std::chrono::steady_clock::now() < security_threat_until;
            app_.set_data(orchestrator_view(statuses,
                                            presence,
                                            selected_device,
                                            secure,
                                            security_threat,
                                            logs));
        };
        append_log("Started Orchestrator");

        heartbeat_monitor_->start();
        participant_.enable();
        publish_view();
        while (!stopping_.load()) {
            while (auto event = events_.try_pop()) {
                if (event->kind == "command") {
                    const auto command = parse_command(event->command);
                    command_writer_.write(
                            Device::Command(selected_device, command));
                    append_log("Writing " + event->command + " to "
                               + device_name(selected_device));
                } else if (event->kind == "select-device") {
                    selected_device = parse_device(event->device);
                    append_log("Selected " + device_name(selected_device));
                } else if (event->kind == "security") {
                    append_log(event->message, "blocked");
                    security_threat_until =
                            std::chrono::steady_clock::now() + 8s;
                } else if (event->kind == "heartbeat-present") {
                    const auto device = parse_device(event->device);
                    presence[device] = true;
                    append_log(device_name(device)
                               + " resumed sending heartbeats");
                } else if (event->kind == "heartbeat-lost") {
                    const auto device = parse_device(event->device);
                    presence[device] = false;
                    append_log(
                        device_name(device)
                                + " stopped sending heartbeats; marking it OFF",
                        "warn");
                }
            }

            for (const auto &sample : status_reader_.take()) {
                if (!sample.info().valid())
                    continue;
                const auto device = sample.data().device;
                const auto status = status_name(sample.data().status);
                statuses[device] = status;
                append_log("Received " + status + " status from "
                           + device_name(device));
            }

            publish_view();
            std::this_thread::sleep_for(50ms);
        }
        heartbeat_monitor_->stop();

        append_log("Orchestrator is shutting down");
        publish_view();
    }

private:
    rti::demo::ui::DemoUiApp &app_;
    medtech::ui::CommandQueue<UiEvent> &events_;
    std::atomic<bool> &stopping_;
    dds::core::QosProvider provider_ = dds::core::null;
    dds::domain::DomainParticipant participant_ = dds::core::null;
    dds::pub::DataWriter<Device::Command> command_writer_ = dds::core::null;
    dds::sub::DataReader<Device::Status> status_reader_ = dds::core::null;
    dds::sub::DataReader<Device::Heartbeat> heartbeat_reader_ = dds::core::null;
    std::unique_ptr<medtech::operating_room::HeartbeatPresenceMonitor>
            heartbeat_monitor_;
};

void configure_ui(rti::demo::ui::DemoUiApp &app,
                  medtech::ui::CommandQueue<UiEvent> &events)
{
    using namespace rti::demo::ui;
    app.register_command(
            "select-device",
            CommandSchema(Json {
                    { "type", "object" },
                    { "properties",
                      Json { { "device",
                               Json { { "type", "string" },
                                      { "enum",
                                        Json::array({ "ARM",
                                                      "ARM_CONTROLLER",
                                                      "PATIENT_SENSOR",
                                                      "PATIENT_"
                                                      "MONITOR" }) } } } } },
                    { "required", Json::array({ "device" }) },
                    { "additionalProperties", false } }),
            [&events](const Json &payload) {
                events.push({
                        "select-device",
                        payload.at("device").get<std::string>(),
                        { },
                        { },
                });
                return Json { { "message", "Device selected" } };
            });
    app.register_command(
            "send-device-command",
            CommandSchema({ { "type", "object" },
                            { "properties",
                              { { "command",
                                  { { "type", "string" },
                                    { "enum",
                                      Json::array({ "START",
                                                    "PAUSE",
                                                    "SHUTDOWN" }) } } } } },
                            { "required", Json::array({ "command" }) },
                            { "additionalProperties", false } }),
            [&events](const Json &payload) {
                events.push({
                        "command",
                        { },
                        payload.at("command").get<std::string>(),
                        { },
                });
                return Json { { "message", "Device command queued" } };
            });
}

}  // namespace

int main()
{
    using namespace rti::demo::ui;
    try {
        DemoUiApp app("System Orchestrator",
                      0,
                      "127.0.0.1",
                      std::filesystem::path(RTI_DEMO_UI_WEB_ROOT),
                      Theme::dark,
                      Layout::automatic,
                      std::string("System Orchestrator listening on"));
        medtech::ui::CommandQueue<UiEvent> events;
        configure_ui(app, events);
        std::atomic<bool> stopping = false;
        OrchestratorApp application(app, events, stopping);
        bool worker_failed = false;
        std::thread dds_worker([&]() {
            try {
                application.run();
            } catch (const std::runtime_error &error) {
                if (medtech::ui::is_model_stopped_error(error)) {
                    stopping.store(true);
                } else {
                    std::cerr << "Orchestrator DDS worker failed: "
                              << error.what() << std::endl;
                    worker_failed = true;
                }
            } catch (const std::exception &error) {
                std::cerr << "Orchestrator DDS worker failed: " << error.what()
                          << std::endl;
                worker_failed = true;
            } catch (...) {
                std::cerr << "Orchestrator DDS worker failed with an unknown "
                             "exception"
                          << std::endl;
                worker_failed = true;
            }
            if (worker_failed) {
                stopping.store(true);
                try {
                    app.stop();
                } catch (const std::exception &error) {
                    std::cerr << "Orchestrator UI shutdown failed: "
                              << error.what() << std::endl;
                } catch (...) {
                    std::cerr << "Orchestrator UI shutdown failed with an "
                                 "unknown exception"
                              << std::endl;
                }
            }
        });
        bool ui_succeeded = false;
        try {
            ui_succeeded = medtech::ui::run(app,
                                            1600,
                                            950,
                                            medtech::ui::native_icon_path());
        } catch (const std::exception &error) {
            std::cerr << "Orchestrator UI failed: " << error.what()
                      << std::endl;
        } catch (...) {
            std::cerr << "Orchestrator UI failed with an unknown exception"
                      << std::endl;
        }
        stopping.store(true);
        dds_worker.join();
        return worker_failed || !ui_succeeded ? 1 : 0;
    } catch (const std::exception &error) {
        std::cerr << "Orchestrator setup failed: " << error.what() << std::endl;
    } catch (...) {
        std::cerr << "Orchestrator setup failed with an unknown exception"
                  << std::endl;
    }
    return 1;
}
