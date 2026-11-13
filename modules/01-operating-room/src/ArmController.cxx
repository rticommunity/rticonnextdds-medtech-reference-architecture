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

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <ctime>
#include <exception>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <tuple>
#include <vector>

#include <rti_demo_ui/rti_demo_ui.hpp>

#include "DemoUiCommandQueue.hpp"
#include "DemoUiRuntime.hpp"
#include "MedTech.hpp"

using namespace DdsEntities::Constants;
using namespace std::chrono_literals;
using rti::demo::ui::Json;

namespace {

constexpr const char *ARM_ID = "arm-1";
constexpr double MAX_LINEAR_SPEED = 0.05;
constexpr double MAX_ANGULAR_SPEED = 0.5;
constexpr double MAX_OPENING_RATE = 0.02;
constexpr auto INPUT_TIMEOUT = 1500ms;
constexpr auto CONTROL_PERIOD = 20ms;
constexpr auto FEEDBACK_STALE = 500ms;

struct UiCommand {
    std::string action;
    std::string axis;
    std::string direction;
};

struct VelocityTarget {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
    double angular_x = 0.0;
    double angular_y = 0.0;
    double angular_z = 0.0;
    double jaw = 0.0;
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

class ArmControllerLogic {
public:
    Device::DeviceStatuses status = Device::DeviceStatuses::ON;

    void start_demo()
    {
        if (status != Device::DeviceStatuses::ON)
            return;
        demo_motion_enabled_ = true;
        demo_phase_ = 0;
        demo_phase_tick_ = 0;
    }

    void stop_demo()
    {
        demo_motion_enabled_ = false;
    }

    void stop_manual()
    {
        held_axes_.clear();
    }

    void apply_device_command(Device::DeviceCommands command)
    {
        if (command == Device::DeviceCommands::START) {
            status = Device::DeviceStatuses::ON;
        } else if (command == Device::DeviceCommands::PAUSE) {
            status = Device::DeviceStatuses::PAUSED;
            stop_demo();
            stop_manual();
        } else {
            status = Device::DeviceStatuses::OFF;
            stop_demo();
            stop_manual();
        }
    }

    bool apply_manual(const std::string &axis, const std::string &direction)
    {
        stop_demo();
        if (direction == "STOPPED") {
            return held_axes_.erase(axis) > 0;
        }
        const double signed_direction = direction == "POSITIVE" ? 1.0 : -1.0;
        const auto now = std::chrono::steady_clock::now();
        const auto found = held_axes_.find(axis);
        const bool changed = found == held_axes_.end()
                || found->second.direction != signed_direction;
        held_axes_[axis] = { signed_direction, now };
        return changed;
    }

    std::vector<std::string> expire_manual_inputs(
            std::chrono::steady_clock::time_point now)
    {
        std::vector<std::string> expired;
        for (auto held = held_axes_.begin(); held != held_axes_.end();) {
            if (now - held->second.last_refresh > INPUT_TIMEOUT) {
                expired.push_back(held->first);
                held = held_axes_.erase(held);
            } else {
                ++held;
            }
        }
        return expired;
    }

    VelocityTarget rates_for_tick()
    {
        if (status != Device::DeviceStatuses::ON)
            return { };
        if (demo_motion_enabled_)
            return next_demo_rates();

        VelocityTarget target;
        for (const auto &[axis, held] : held_axes_) {
            if (axis == "X")
                target.x += held.direction * MAX_LINEAR_SPEED;
            else if (axis == "Y")
                target.y += held.direction * MAX_LINEAR_SPEED;
            else if (axis == "Z")
                target.z += held.direction * MAX_LINEAR_SPEED;
            else if (axis == "ANGULAR_X")
                target.angular_x += held.direction * MAX_ANGULAR_SPEED;
            else if (axis == "ANGULAR_Y")
                target.angular_y += held.direction * MAX_ANGULAR_SPEED;
            else if (axis == "ANGULAR_Z")
                target.angular_z += held.direction * MAX_ANGULAR_SPEED;
            else if (axis == "JAW")
                target.jaw += held.direction * MAX_OPENING_RATE;
        }
        normalize_group(target.x, target.y, target.z, MAX_LINEAR_SPEED);
        normalize_group(target.angular_x,
                        target.angular_y,
                        target.angular_z,
                        MAX_ANGULAR_SPEED);
        target.jaw =
                std::clamp(target.jaw, -MAX_OPENING_RATE, MAX_OPENING_RATE);
        return target;
    }

    bool demo_enabled() const
    {
        return demo_motion_enabled_;
    }

private:
    struct HeldAxis {
        double direction;
        std::chrono::steady_clock::time_point last_refresh;
    };

    static constexpr std::array<VelocityTarget, 12> DEMO_PHASES = { {
            { 0.018, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0 },
            { 0.0, 0.018, 0.0, 0.0, 0.0, 0.0, 0.0 },
            { 0.0, 0.0, 0.018, 0.0, 0.0, 0.0, 0.0 },
            { -0.018, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0 },
            { 0.0, 0.0, 0.0, 0.12, 0.0, 0.0, 0.0 },
            { 0.0, 0.0, 0.0, 0.0, 0.12, 0.0, 0.0 },
            { 0.0, 0.0, 0.0, 0.0, 0.0, 0.12, 0.0 },
            { 0.0, 0.0, 0.0, -0.12, 0.0, 0.0, 0.0 },
            { 0.0, 0.0, 0.0, 0.0, -0.12, 0.0, 0.0 },
            { 0.0, 0.0, 0.0, 0.0, 0.0, -0.12, 0.0 },
            { 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.01 },
            { 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.01 },
    } };
    static constexpr unsigned int DEMO_PHASE_TICKS = 25;

    bool demo_motion_enabled_ = false;
    std::size_t demo_phase_ = 0;
    unsigned int demo_phase_tick_ = 0;
    std::map<std::string, HeldAxis> held_axes_;

    static void normalize_group(double &x, double &y, double &z, double limit)
    {
        const double magnitude = std::sqrt(x * x + y * y + z * z);
        if (magnitude > limit) {
            const double scale = limit / magnitude;
            x *= scale;
            y *= scale;
            z *= scale;
        }
    }

    VelocityTarget next_demo_rates()
    {
        const auto target = DEMO_PHASES[demo_phase_];
        if (++demo_phase_tick_ >= DEMO_PHASE_TICKS) {
            demo_phase_tick_ = 0;
            if (++demo_phase_ >= DEMO_PHASES.size())
                demo_phase_ = 0;
        }
        return target;
    }
};

struct ArmFeedback {
    std::string readiness = "NOT_READY";
    std::chrono::steady_clock::time_point telemetry_received;
    bool has_status = false;
    bool has_telemetry = false;
    bool has_pose = false;
    bool has_jaw_width = false;
    Geometry::Pose pose;
    double jaw_width = 0.0;

    Json view() const
    {
        const auto now = std::chrono::steady_clock::now();
        const bool telemetry_fresh =
                has_telemetry && now - telemetry_received <= FEEDBACK_STALE;
        Json pose_json = nullptr;
        if (has_pose) {
            pose_json = {
                { "position",
                  { { "x", pose.position.x },
                    { "y", pose.position.y },
                    { "z", pose.position.z } } },
                { "orientation",
                  { { "x", pose.orientation.x },
                    { "y", pose.orientation.y },
                    { "z", pose.orientation.z },
                    { "w", pose.orientation.w } } },
            };
        }
        return {
            { "readiness", readiness },
            { "status_known", has_status },
            { "position", has_pose ? pose_json.at("position") : Json(nullptr) },
            { "orientation",
              has_pose ? pose_json.at("orientation") : Json(nullptr) },
            { "opening_width",
              has_jaw_width ? Json(jaw_width) : Json(nullptr) },
            { "freshness", { { "telemetry", telemetry_fresh } } },
        };
    }
};

Json arm_controller_view(const ArmControllerLogic &logic,
                         const Json &logs,
                         const ArmFeedback &feedback)
{
    const std::string status = logic.status == Device::DeviceStatuses::ON ? "ON"
            : logic.status == Device::DeviceStatuses::PAUSED ? "PAUSED"
                                                             : "OFF";
    const bool enabled = logic.status == Device::DeviceStatuses::ON;
    const std::string readiness_badge = feedback.has_status
            ? feedback.readiness + " · LAST KNOWN"
            : "UNKNOWN";
    Json jog_controls = Json::array();
    const std::array<std::tuple<std::string, std::string, std::string>, 14>
            controls = { {
                    { "X", "X −", "NEGATIVE" },
                    { "X", "X +", "POSITIVE" },
                    { "Y", "Y −", "NEGATIVE" },
                    { "Y", "Y +", "POSITIVE" },
                    { "Z", "Z −", "NEGATIVE" },
                    { "Z", "Z +", "POSITIVE" },
                    { "ANGULAR_X", "ROTATE X −", "NEGATIVE" },
                    { "ANGULAR_X", "ROTATE X +", "POSITIVE" },
                    { "ANGULAR_Y", "ROTATE Y −", "NEGATIVE" },
                    { "ANGULAR_Y", "ROTATE Y +", "POSITIVE" },
                    { "ANGULAR_Z", "ROTATE Z −", "NEGATIVE" },
                    { "ANGULAR_Z", "ROTATE Z +", "POSITIVE" },
                    { "JAW", "CLOSE JAWS", "NEGATIVE" },
                    { "JAW", "OPEN JAWS", "POSITIVE" },
            } };
    for (const auto &[axis, label, direction] : controls) {
        jog_controls.push_back({ { "type", "hold" },
                                 { "label", label },
                                 { "className", "tool-control" },
                                 { "command", "teleop" },
                                 { "axis", axis },
                                 { "direction", direction },
                                 { "disabled", !enabled } });
    }
    Json demo_controls = Json::array({ { { "type", "button" },
                                         { "label", "RUN DEMO" },
                                         { "command", "start-demo" },
                                         { "payload", Json::object() },
                                         { "style", "primary" },
                                         { "disabled", !enabled } },
                                       { { "type", "button" },
                                         { "label", "STOP MOTION" },
                                         { "command", "stop-demo" },
                                         { "payload", Json::object() },
                                         { "style", "danger" } } });
    Json control_groups = Json::array();
    control_groups.push_back(
            { { "title", "BASE X / Y MOTION" },
              { "layout", "planar-pad" },
              { "controls",
                Json::array({ Json { { "type", "dpad" },
                                     { "command", "teleop" },
                                     { "disabled", !enabled } } }) } });
    control_groups.push_back({ { "title", "BASE TRANSLATION / ROTATION" },
                               { "layout", "tool-controls" },
                               { "controls", jog_controls } });
    control_groups.push_back({ { "title", "DEMO MOTION" },
                               { "layout", "demo-controls" },
                               { "controls", demo_controls } });
    return {
        { "kind", "arm-controller" },
        { "title", "Arm Controller" },
        { "header_badges",
          Json::array({ { { "label", "Command QoS" }, { "value", "ACTIVE" } },
                        { { "label", "Control frame" },
                          { "value", "BASE (+Z UP)" } },
                        { { "label", "Arm readiness" },
                          { "value", readiness_badge },
                          { "tone",
                            feedback.readiness == "READY" && feedback.has_status
                                    ? "good"
                                    : "warn" } } }) },
        { "control_intro",
          "Hold a direction for base-frame motion (+Z up). Release to command "
          "zero." },
        { "control_note",
          "Linear rates use m/s; angular rates use rad/s. Jaw buttons command "
          "signed gap rate in m/s." },
        { "status", status },
        { "feedback", feedback.view() },
        { "control_groups", control_groups },
        { "activity_title", "ALERTS" },
        { "footer", false },
        { "logs", logs },
    };
}

std::string readiness_name(Robot::Arm::Readiness readiness)
{
    if (readiness == Robot::Arm::Readiness::READY)
        return "READY";
    if (readiness == Robot::Arm::Readiness::FAULT)
        return "FAULT";
    return "NOT_READY";
}

void publish_target(
        dds::pub::DataWriter<Robot::Arm::TeleopControl> &teleop_writer,
        dds::pub::DataWriter<Robot::Tool::ParallelJawControl> &tool_writer,
        const VelocityTarget &target)
{
    teleop_writer.write(Robot::Arm::TeleopControl(
            ARM_ID,
            Geometry::Vector3(target.x, target.y, target.z),
            Geometry::Vector3(target.angular_x,
                              target.angular_y,
                              target.angular_z)));
    tool_writer.write(Robot::Tool::ParallelJawControl(ARM_ID, target.jaw));
}

void run_control(rti::demo::ui::DemoUiApp &app,
                 medtech::ui::CommandQueue<UiCommand> &commands,
                 std::atomic<bool> &stopping)
{
    rti::domain::register_type<Device::Command>();
    rti::domain::register_type<Device::Status>();
    rti::domain::register_type<Device::Heartbeat>();
    rti::domain::register_type<Robot::Arm::TeleopControl>();
    rti::domain::register_type<Robot::Tool::ParallelJawControl>();
    rti::domain::register_type<Robot::Arm::Status>();
    rti::domain::register_type<Robot::Arm::Telemetry>();

    auto provider = dds::core::QosProvider::Default();
    dds::domain::DomainParticipant participant =
            provider.extensions().create_participant_from_config(
                    std::string(ARM_CONTROLLER_DP));
    auto status_writer = rti::pub::find_datawriter_by_name<
            dds::pub::DataWriter<Device::Status>>(participant,
                                                  std::string(STATUS_DW));
    auto heartbeat_writer = rti::pub::find_datawriter_by_name<
            dds::pub::DataWriter<Device::Heartbeat>>(participant,
                                                     std::string(HB_DW));
    auto teleop_writer = rti::pub::find_datawriter_by_name<
            dds::pub::DataWriter<Robot::Arm::TeleopControl>>(
            participant,
            std::string(TELEOP_CONTROL_DW));
    auto tool_writer = rti::pub::find_datawriter_by_name<
            dds::pub::DataWriter<Robot::Tool::ParallelJawControl>>(
            participant,
            std::string(TOOL_CONTROL_DW));
    auto command_reader = rti::sub::find_datareader_by_name<
            dds::sub::DataReader<Device::Command>>(
            participant,
            std::string(DEVICE_COMMAND_DR));
    auto arm_status_reader = rti::sub::find_datareader_by_name<
            dds::sub::DataReader<Robot::Arm::Status>>(
            participant,
            std::string(ARM_STATUS_DR));
    auto arm_telemetry_reader = rti::sub::find_datareader_by_name<
            dds::sub::DataReader<Robot::Arm::Telemetry>>(
            participant,
            std::string(ARM_TELEMETRY_DR));

    auto require_endpoint = [](const auto &endpoint, const auto &name) {
        if (endpoint == dds::core::null) {
            throw std::runtime_error(
                    std::string("ArmController DDS configuration is missing "
                                "endpoint: ")
                    + std::string(name));
        }
    };
    require_endpoint(status_writer, STATUS_DW);
    require_endpoint(heartbeat_writer, HB_DW);
    require_endpoint(teleop_writer, TELEOP_CONTROL_DW);
    require_endpoint(tool_writer, TOOL_CONTROL_DW);
    require_endpoint(command_reader, DEVICE_COMMAND_DR);
    require_endpoint(arm_status_reader, ARM_STATUS_DR);
    require_endpoint(arm_telemetry_reader, ARM_TELEMETRY_DR);

    ArmControllerLogic logic;
    ArmFeedback feedback;
    Device::Status status(Device::DeviceType::ARM_CONTROLLER, logic.status);
    status_writer.write(status);
    Json logs = Json::array();
    auto update_view = [&]() {
        app.set_data(arm_controller_view(logic, logs, feedback));
    };
    auto log = [&](const std::string &message,
                   const std::string &level = "info") {
        logs.push_back({ { "time", current_time() },
                         { "message", message },
                         { "level", level } });
        if (logs.size() > 80)
            logs.erase(logs.begin());
        update_view();
    };
    update_view();
    log("Arm Controller is online");
    auto now = std::chrono::steady_clock::now();
    auto next_heartbeat = now;
    auto next_control = now;
    auto next_ui_refresh = now;

    while (!stopping.load() && logic.status != Device::DeviceStatuses::OFF) {
        while (auto intent = commands.try_pop()) {
            if (intent->action == "start-demo") {
                logic.start_demo();
                logic.stop_manual();
                log("Started bounded 3D demo motion", "ok");
            } else if (intent->action == "stop-demo") {
                logic.stop_demo();
                log("Stopped demo motion");
            } else if (intent->action == "teleop") {
                const bool changed =
                        logic.apply_manual(intent->axis, intent->direction);
                if (!changed)
                    continue;
                if (intent->direction == "STOPPED") {
                    log("Released " + intent->axis + " jog");
                } else {
                    log("Started " + intent->direction + " " + intent->axis
                        + " jog");
                }
            }
        }

        for (const auto &sample : command_reader.take()) {
            if (!sample.info().valid())
                continue;
            logic.apply_device_command(sample.data().command);
            status.status = logic.status;
            status_writer.write(status);
            update_view();
            log("Received a device command from Orchestrator");
        }

        for (const auto &sample : arm_status_reader.take()) {
            if (!sample.info().valid() || sample.data().arm_id != ARM_ID)
                continue;
            feedback.readiness = readiness_name(sample.data().readiness);
            feedback.has_status = true;
        }
        for (const auto &sample : arm_telemetry_reader.take()) {
            if (!sample.info().valid() || sample.data().arm_id != ARM_ID)
                continue;
            const auto &telemetry = sample.data();
            feedback.telemetry_received = std::chrono::steady_clock::now();
            feedback.has_telemetry = true;
            feedback.has_pose = telemetry.tcp_pose.has_value();
            if (feedback.has_pose)
                feedback.pose = *telemetry.tcp_pose;
            feedback.has_jaw_width = telemetry.parallel_jaw.has_value();
            if (feedback.has_jaw_width)
                feedback.jaw_width = telemetry.parallel_jaw->opening_width;
        }

        now = std::chrono::steady_clock::now();
        for (const auto &axis : logic.expire_manual_inputs(now)) {
            log("Jog input timed out; stopped " + axis + " axis", "warn");
        }
        if (now >= next_heartbeat) {
            heartbeat_writer.write(
                    Device::Heartbeat(Device::DeviceType::ARM_CONTROLLER));
            next_heartbeat = now + 50ms;
        }
        if (logic.status == Device::DeviceStatuses::ON && now >= next_control) {
            publish_target(teleop_writer, tool_writer, logic.rates_for_tick());
            next_control = now + CONTROL_PERIOD;
        }
        if (now >= next_ui_refresh) {
            update_view();
            next_ui_refresh = now + 200ms;
        }
        std::this_thread::sleep_for(5ms);
    }

    status.status = Device::DeviceStatuses::OFF;
    status_writer.write(status);
    log("Arm Controller is shutting down");
    app.stop();
}

}  // namespace

int main()
{
    using namespace rti::demo::ui;
    DemoUiApp app("Arm Controller",
                  0,
                  "127.0.0.1",
                  std::filesystem::path(RTI_DEMO_UI_WEB_ROOT),
                  Theme::dark,
                  Layout::automatic,
                  std::string("Arm Controller listening on"));
    medtech::ui::CommandQueue<UiCommand> commands;
    const auto empty_object = Json { { "type", "object" },
                                     { "properties", Json::object() },
                                     { "additionalProperties", false } };
    app.register_command(
            "start-demo",
            CommandSchema(empty_object),
            [&commands](const Json &) {
                commands.push({ "start-demo", { }, { } });
                return Json { { "message", "Demo trajectory started" } };
            });
    app.register_command(
            "stop-demo",
            CommandSchema(empty_object),
            [&commands](const Json &) {
                commands.push({ "stop-demo", { }, { } });
                return Json { { "message", "Demo motion stopped" } };
            });
    app.register_command(
            "teleop",
            CommandSchema(
                    { { "type", "object" },
                      { "properties",
                        { { "axis",
                            { { "type", "string" },
                              { "enum",
                                Json::array({ "X",
                                              "Y",
                                              "Z",
                                              "ANGULAR_X",
                                              "ANGULAR_Y",
                                              "ANGULAR_Z",
                                              "JAW" }) } } },
                          { "direction",
                            { { "type", "string" },
                              { "enum",
                                Json::array({ "POSITIVE",
                                              "NEGATIVE",
                                              "STOPPED" }) } } } } },
                      { "required", Json::array({ "axis", "direction" }) },
                      { "additionalProperties", false } }),
            [&commands](const Json &payload) {
                commands.push({ "teleop",
                                payload.at("axis"),
                                payload.at("direction") });
                return Json { { "message", "Teleoperation intent queued" } };
            });

    std::atomic<bool> stopping = false;
    std::exception_ptr worker_error;
    std::thread dds_worker([&]() {
        try {
            run_control(app, commands, stopping);
        } catch (const std::runtime_error &error) {
            // The UI loop may stop before the DDS worker observes shutdown.
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
        medtech::ui::run(app, 1400, 900, medtech::ui::native_icon_path());
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
