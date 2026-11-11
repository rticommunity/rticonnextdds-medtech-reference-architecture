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
#include <vector>

#include <rti_demo_ui/rti_demo_ui.hpp>

#include "DemoUiCommandQueue.hpp"
#include "DemoUiRuntime.hpp"
#include "Types.hpp"

using namespace DdsEntities::Constants;
using namespace std::chrono_literals;
using rti::demo::ui::Json;

namespace {

struct UiCommand {
    std::string action;
    std::string axis;
    std::string direction;
};

struct TeleopAction {
    SurgicalRobot::TeleopAxes axis;
    SurgicalRobot::TeleopDirections direction;
};

SurgicalRobot::TeleopAxes parse_axis(const std::string &axis)
{
    if (axis == "X")
        return SurgicalRobot::TeleopAxes::X;
    if (axis == "Y")
        return SurgicalRobot::TeleopAxes::Y;
    if (axis == "ROLL")
        return SurgicalRobot::TeleopAxes::ROLL;
    return SurgicalRobot::TeleopAxes::GRIPPER;
}

SurgicalRobot::TeleopDirections parse_direction(const std::string &direction)
{
    if (direction == "POSITIVE")
        return SurgicalRobot::TeleopDirections::POSITIVE;
    if (direction == "NEGATIVE")
        return SurgicalRobot::TeleopDirections::NEGATIVE;
    return SurgicalRobot::TeleopDirections::STOPPED;
}

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
    Common::DeviceStatuses status = Common::DeviceStatuses::ON;

    void start_demo()
    {
        if (status != Common::DeviceStatuses::ON)
            return;
        demo_motion_enabled_ = true;
        reset_demo();
    }

    void stop_demo()
    {
        demo_motion_enabled_ = false;
    }

    void apply_device_command(Orchestrator::DeviceCommands command)
    {
        if (command == Orchestrator::DeviceCommands::START) {
            status = Common::DeviceStatuses::ON;
        } else if (command == Orchestrator::DeviceCommands::PAUSE) {
            status = Common::DeviceStatuses::PAUSED;
            stop_demo();
        } else {
            status = Common::DeviceStatuses::OFF;
            stop_demo();
        }
    }

    bool demo_enabled() const
    {
        return demo_motion_enabled_;
    }

    std::vector<TeleopAction> next_demo_actions()
    {
        if (!demo_motion_enabled_ || status != Common::DeviceStatuses::ON) {
            return { };
        }
        std::vector<TeleopAction> actions;
        if (!tool_sequence_) {
            const auto &segment = demo_path_[path_index_];
            if (segment.x != SurgicalRobot::TeleopDirections::STOPPED) {
                actions.push_back({ SurgicalRobot::TeleopAxes::X, segment.x });
            }
            if (segment.y != SurgicalRobot::TeleopDirections::STOPPED) {
                actions.push_back({ SurgicalRobot::TeleopAxes::Y, segment.y });
            }
            if (++segment_tick_ >= segment.ticks) {
                segment_tick_ = 0;
                if (++path_index_ >= demo_path_.size()) {
                    path_index_ = 0;
                    tool_sequence_ = true;
                }
            }
        } else {
            const auto &segment = demo_tool_sequence_[tool_index_];
            actions.push_back({ segment.axis, segment.direction });
            if (++segment_tick_ >= segment.ticks) {
                segment_tick_ = 0;
                if (++tool_index_ >= demo_tool_sequence_.size()) {
                    tool_index_ = 0;
                    tool_sequence_ = false;
                }
            }
        }
        return actions;
    }

private:
    struct PathSegment {
        SurgicalRobot::TeleopDirections x;
        SurgicalRobot::TeleopDirections y;
        unsigned int ticks;
    };
    struct ToolSegment {
        SurgicalRobot::TeleopAxes axis;
        SurgicalRobot::TeleopDirections direction;
        unsigned int ticks;
    };

    static constexpr std::array<PathSegment, 8> demo_path_ = { {
            { SurgicalRobot::TeleopDirections::POSITIVE,
              SurgicalRobot::TeleopDirections::STOPPED,
              6 },
            { SurgicalRobot::TeleopDirections::POSITIVE,
              SurgicalRobot::TeleopDirections::POSITIVE,
              4 },
            { SurgicalRobot::TeleopDirections::STOPPED,
              SurgicalRobot::TeleopDirections::POSITIVE,
              6 },
            { SurgicalRobot::TeleopDirections::NEGATIVE,
              SurgicalRobot::TeleopDirections::POSITIVE,
              4 },
            { SurgicalRobot::TeleopDirections::NEGATIVE,
              SurgicalRobot::TeleopDirections::STOPPED,
              6 },
            { SurgicalRobot::TeleopDirections::NEGATIVE,
              SurgicalRobot::TeleopDirections::NEGATIVE,
              4 },
            { SurgicalRobot::TeleopDirections::STOPPED,
              SurgicalRobot::TeleopDirections::NEGATIVE,
              6 },
            { SurgicalRobot::TeleopDirections::POSITIVE,
              SurgicalRobot::TeleopDirections::NEGATIVE,
              4 },
    } };
    static constexpr std::array<ToolSegment, 4> demo_tool_sequence_ = { {
            { SurgicalRobot::TeleopAxes::ROLL,
              SurgicalRobot::TeleopDirections::POSITIVE,
              24 },
            { SurgicalRobot::TeleopAxes::ROLL,
              SurgicalRobot::TeleopDirections::NEGATIVE,
              24 },
            { SurgicalRobot::TeleopAxes::GRIPPER,
              SurgicalRobot::TeleopDirections::NEGATIVE,
              22 },
            { SurgicalRobot::TeleopAxes::GRIPPER,
              SurgicalRobot::TeleopDirections::POSITIVE,
              22 },
    } };

    bool demo_motion_enabled_ = false;
    bool tool_sequence_ = false;
    std::size_t path_index_ = 0;
    std::size_t tool_index_ = 0;
    unsigned int segment_tick_ = 0;

    void reset_demo()
    {
        path_index_ = 0;
        tool_index_ = 0;
        segment_tick_ = 0;
        tool_sequence_ = false;
    }
};

Json arm_controller_view(const ArmControllerLogic &logic, const Json &logs)
{
    const std::string status = logic.status == Common::DeviceStatuses::ON ? "ON"
            : logic.status == Common::DeviceStatuses::PAUSED ? "PAUSED"
                                                             : "OFF";
    const bool enabled = logic.status == Common::DeviceStatuses::ON;
    Json jog_controls = Json::array();
    for (const auto &[axis, label, direction] :
         std::array<std::tuple<std::string, std::string, std::string>, 4> { {
                 { "ROLL", "↶  ROLL LEFT", "POSITIVE" },
                 { "ROLL", "↷  ROLL RIGHT", "NEGATIVE" },
                 { "GRIPPER", "CLOSE GRIPPER", "NEGATIVE" },
                 { "GRIPPER", "OPEN GRIPPER", "POSITIVE" },
         } }) {
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
            { { "title", "PLANAR POSITION" },
              { "layout", "planar-pad" },
              { "controls",
                Json::array({ Json { { "type", "dpad" },
                                     { "command", "teleop" },
                                     { "disabled", !enabled } } }) } });
    control_groups.push_back({ { "title", "TOOL CONTROLS" },
                               { "layout", "tool-controls" },
                               { "controls", jog_controls } });
    control_groups.push_back({ { "title", "DEMO MOTION" },
                               { "layout", "demo-controls" },
                               { "controls", demo_controls } });
    return {
        { "kind", "arm-controller" },
        { "title", "Arm Controller" },
        { "header_badges",
          Json::array(
                  { { { "label", "Command QoS" }, { "value", "ACTIVE" } } }) },
        { "control_intro",
          "Hold a direction to jog the simulated tool tip; release to stop." },
        { "control_note",
          "X/Y uses a simplified planar two-link model. Wrist roll and "
          "gripper are separate controls." },
        { "status", status },
        { "control_groups", control_groups },
        { "activity_title", "ALERTS" },
        { "footer", false },
        { "logs", logs },
    };
}

void run_control(rti::demo::ui::DemoUiApp &app,
                 medtech::ui::CommandQueue<UiCommand> &commands,
                 std::atomic<bool> &stopping)
{
    rti::domain::register_type<Orchestrator::DeviceCommand>();
    rti::domain::register_type<Common::DeviceStatus>();
    rti::domain::register_type<Common::DeviceHeartbeat>();
    rti::domain::register_type<SurgicalRobot::TeleopControl>();

    auto provider = dds::core::QosProvider::Default();
    dds::domain::DomainParticipant participant =
            provider.extensions().create_participant_from_config(
                    std::string(ARM_CONTROLLER_DP));
    auto status_writer = rti::pub::find_datawriter_by_name<
            dds::pub::DataWriter<Common::DeviceStatus>>(participant,
                                                        std::string(STATUS_DW));
    auto heartbeat_writer = rti::pub::find_datawriter_by_name<
            dds::pub::DataWriter<Common::DeviceHeartbeat>>(participant,
                                                           std::string(HB_DW));
    auto teleop_writer = rti::pub::find_datawriter_by_name<
            dds::pub::DataWriter<SurgicalRobot::TeleopControl>>(
            participant,
            std::string(TELEOP_CONTROL_DW));
    auto command_reader = rti::sub::find_datareader_by_name<
            dds::sub::DataReader<Orchestrator::DeviceCommand>>(
            participant,
            std::string(DEVICE_COMMAND_DR));

    ArmControllerLogic logic;
    struct HeldAxis {
        SurgicalRobot::TeleopDirections direction;
        std::chrono::steady_clock::time_point last_refresh;
    };
    std::map<SurgicalRobot::TeleopAxes, HeldAxis> held_axes;
    Common::DeviceStatus status(Common::DeviceType::ARM_CONTROLLER,
                                logic.status);
    status_writer.write(status);
    Json logs = Json::array();
    auto log = [&](const std::string &message,
                   const std::string &level = "info") {
        logs.push_back({ { "time", current_time() },
                         { "message", message },
                         { "level", level } });
        if (logs.size() > 80)
            logs.erase(logs.begin());
        app.set_data(arm_controller_view(logic, logs));
    };
    app.set_data(arm_controller_view(logic, logs));
    log("Arm Controller is online");
    auto next_heartbeat = std::chrono::steady_clock::now();
    auto next_demo_tick = next_heartbeat;
    auto next_manual_publish = next_heartbeat;
    auto stop_held_axes = [&]() {
        for (const auto &[axis, _] : held_axes) {
            teleop_writer.write(SurgicalRobot::TeleopControl(
                    axis,
                    SurgicalRobot::TeleopDirections::STOPPED));
        }
        held_axes.clear();
    };

    while (!stopping.load() && logic.status != Common::DeviceStatuses::OFF) {
        while (auto intent = commands.try_pop()) {
            if (intent->action == "start-demo") {
                logic.start_demo();
                stop_held_axes();
                log("Started smooth demo motion", "ok");
            } else if (intent->action == "stop-demo") {
                logic.stop_demo();
                log("Stopped demo motion");
            } else if (intent->action == "teleop") {
                logic.stop_demo();
                const auto axis = parse_axis(intent->axis);
                const auto direction = parse_direction(intent->direction);
                if (direction == SurgicalRobot::TeleopDirections::STOPPED) {
                    const bool was_held = held_axes.erase(axis) > 0;
                    teleop_writer.write(
                            SurgicalRobot::TeleopControl(axis, direction));
                    if (was_held) {
                        log("Released " + intent->axis + " jog");
                    }
                } else {
                    const auto now = std::chrono::steady_clock::now();
                    auto [held, inserted] =
                            held_axes.try_emplace(axis,
                                                  HeldAxis { direction, now });
                    const bool direction_changed =
                            !inserted && held->second.direction != direction;
                    held->second.direction = direction;
                    held->second.last_refresh = now;
                    if (inserted || direction_changed) {
                        log("Started " + intent->direction + " " + intent->axis
                            + " jog");
                    }
                }
            }
        }

        for (const auto &sample : command_reader.take()) {
            if (!sample.info().valid())
                continue;
            logic.apply_device_command(sample.data().command);
            if (logic.status != Common::DeviceStatuses::ON) {
                stop_held_axes();
            }
            status.status = logic.status;
            status_writer.write(status);
            log("Received a device command from Orchestrator");
        }

        const auto now = std::chrono::steady_clock::now();
        for (auto held = held_axes.begin(); held != held_axes.end();) {
            if (now - held->second.last_refresh > 1500ms) {
                const auto axis = held->first;
                held = held_axes.erase(held);
                teleop_writer.write(SurgicalRobot::TeleopControl(
                        axis,
                        SurgicalRobot::TeleopDirections::STOPPED));
                log("Jog input timed out; stopped "
                            + std::string(
                                    axis == SurgicalRobot::TeleopAxes::X ? "X"
                                            : axis
                                                    == SurgicalRobot::
                                                            TeleopAxes::Y
                                            ? "Y"
                                            : axis
                                                    == SurgicalRobot::
                                                            TeleopAxes::ROLL
                                            ? "ROLL"
                                            : "GRIPPER")
                            + " axis",
                    "warn");
            } else {
                ++held;
            }
        }
        if (now >= next_heartbeat) {
            heartbeat_writer.write(Common::DeviceHeartbeat(
                    Common::DeviceType::ARM_CONTROLLER));
            next_heartbeat = now + 50ms;
        }
        if (logic.status == Common::DeviceStatuses::ON) {
            if (now >= next_demo_tick) {
                for (const auto &action : logic.next_demo_actions()) {
                    teleop_writer.write(
                            SurgicalRobot::TeleopControl(action.axis,
                                                         action.direction));
                }
                next_demo_tick = now + 100ms;
            }
            if (now >= next_manual_publish) {
                for (const auto &[axis, held] : held_axes) {
                    teleop_writer.write(
                            SurgicalRobot::TeleopControl(axis, held.direction));
                }
                next_manual_publish = now + 20ms;
            }
        }
        std::this_thread::sleep_for(10ms);
    }

    status.status = Common::DeviceStatuses::OFF;
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
                                Json::array(
                                        { "X", "Y", "ROLL", "GRIPPER" }) } } },
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
