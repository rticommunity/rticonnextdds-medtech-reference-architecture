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

#include <array>
#include <atomic>
#include <chrono>
#include <ctime>
#include <exception>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <thread>
#include <tuple>

#include <rti_demo_ui/rti_demo_ui.hpp>

#include "DemoUiCommandQueue.hpp"
#include "DemoUiRuntime.hpp"
#include "MedTech.hpp"

#ifdef RTI_SECURITY_AVAILABLE
    #include "SecureLogUtils.hpp"
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
        const std::map<Device::DeviceType,
                       std::chrono::steady_clock::time_point> &heartbeats,
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
        const auto heartbeat = heartbeats.find(device);
        const bool recent = heartbeat != heartbeats.end()
                && std::chrono::steady_clock::now() - heartbeat->second < 200ms;
        device_rows.push_back({
                { "name", device_name(device) },
                { "status", recent ? status : "OFF" },
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
        { "header_badges",
          Json::array({ { { "label", "Security" },
                          { "value", security_state },
                          { "tone",
                            security_threat  ? "danger"
                                    : secure ? "good"
                                             : "warn" } },
                        { { "label", "Status QoS · Command QoS" },
                          { "value", "ACTIVE" } } }) },
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

void run_control(rti::demo::ui::DemoUiApp &app,
                 medtech::ui::CommandQueue<UiEvent> &events,
                 std::atomic<bool> &stopping)
{
    rti::domain::register_type<Device::Command>();
    rti::domain::register_type<Device::Status>();
    rti::domain::register_type<Device::Heartbeat>();

    auto provider = dds::core::QosProvider::Default();
    auto participant = provider.extensions().create_participant_from_config(
            std::string(ORCHESTRATOR_DP));
    auto command_writer = rti::pub::find_datawriter_by_name<
            dds::pub::DataWriter<Device::Command>>(
            participant,
            std::string(DEVICE_COMMAND_DW));
    auto status_reader = rti::sub::find_datareader_by_name<
            dds::sub::DataReader<Device::Status>>(participant,
                                                  std::string(STATUS_DR));
    auto heartbeat_reader = rti::sub::find_datareader_by_name<
            dds::sub::DataReader<Device::Heartbeat>>(participant,
                                                     std::string(HB_DR));

    std::map<Device::DeviceType, std::string> statuses;
    std::map<Device::DeviceType, std::chrono::steady_clock::time_point>
            heartbeats;
    for (const auto device : {
                 Device::DeviceType::ARM,
                 Device::DeviceType::ARM_CONTROLLER,
                 Device::DeviceType::PATIENT_SENSOR,
                 Device::DeviceType::PATIENT_MONITOR,
         }) {
        statuses[device] = "OFF";
    }
    auto selected_device = Device::DeviceType::ARM;
    Json logs = Json::array();
    auto secure = false;
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
    secure = SecureLogUtils::is_secure(participant);
    SecureLogUtils::SecureLogReader securelog_reader = { dds::core::null,
                                                         dds::core::null };
    if (secure) {
        securelog_reader = SecureLogUtils::setup_secure_log_reader(
                [&events](const SecureLogUtils::SecureLogType &sample) {
                    const auto severity = static_cast<int32_t>(sample.severity);
                    if (severity <= static_cast<int32_t>(
                                DDSSecurity::LoggingLevel::WARNING_LEVEL)) {
                        events.push({
                                "security",
                                { },
                                { },
                                "SECURITY THREAT [" + sample.appname + "] "
                                        + sample.message,
                        });
                    }
                },
                provider);
    }
#endif

    auto publish_view = [&]() {
        const bool security_threat =
                std::chrono::steady_clock::now() < security_threat_until;
        app.set_data(orchestrator_view(statuses,
                                       heartbeats,
                                       selected_device,
                                       secure,
                                       security_threat,
                                       logs));
    };
    append_log("Started Orchestrator");
    publish_view();

    while (!stopping.load()) {
        while (auto event = events.try_pop()) {
            if (event->kind == "command") {
                const auto command = parse_command(event->command);
                command_writer.write(Device::Command(selected_device, command));
                append_log("Writing " + event->command + " to "
                           + device_name(selected_device));
            } else if (event->kind == "select-device") {
                selected_device = parse_device(event->device);
                append_log("Selected " + device_name(selected_device));
            } else if (event->kind == "security") {
                append_log(event->message, "blocked");
                security_threat_until = std::chrono::steady_clock::now() + 8s;
            }
        }

        for (const auto &sample : status_reader.take()) {
            if (!sample.info().valid())
                continue;
            const auto device = sample.data().device;
            const auto status = status_name(sample.data().status);
            statuses[device] = status;
            append_log("Received " + status + " status from "
                       + device_name(device));
        }
        for (const auto &sample : heartbeat_reader.take()) {
            if (!sample.info().valid())
                continue;
            heartbeats[sample.data().device] = std::chrono::steady_clock::now();
        }

        for (auto &[device, last_seen] : heartbeats) {
            if (std::chrono::steady_clock::now() - last_seen >= 200ms
                && statuses[device] != "OFF") {
                statuses[device] = "OFF";
                append_log(
                        device_name(device)
                                + " stopped sending heartbeats; marking it OFF",
                        "warn");
            }
        }
        publish_view();
        std::this_thread::sleep_for(50ms);
    }
    append_log("Orchestrator is shutting down");
    publish_view();
}

}  // namespace

int main()
{
    using namespace rti::demo::ui;
    DemoUiApp app("System Orchestrator",
                  0,
                  "127.0.0.1",
                  std::filesystem::path(RTI_DEMO_UI_WEB_ROOT),
                  Theme::dark,
                  Layout::automatic,
                  std::string("System Orchestrator listening on"));
    medtech::ui::CommandQueue<UiEvent> events;
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

    std::atomic<bool> stopping = false;
    std::exception_ptr worker_error;
    std::thread dds_worker([&]() {
        try {
            run_control(app, events, stopping);
        } catch (const std::runtime_error &error) {
            if (medtech::ui::is_model_stopped_error(error)) {
                stopping.store(true);
            } else {
                worker_error = std::current_exception();
                app.stop();
            }
        } catch (...) {
            worker_error = std::current_exception();
            app.stop();
        }
    });
    try {
        medtech::ui::run(app, 1600, 950, medtech::ui::native_icon_path());
    } catch (...) {
        stopping.store(true);
        dds_worker.join();
        throw;
    }
    stopping.store(true);
    dds_worker.join();
    if (worker_error)
        std::rethrow_exception(worker_error);
    return 0;
}
