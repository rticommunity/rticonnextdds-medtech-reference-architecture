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
#include <vector>

#include <rti_demo_ui/rti_demo_ui.hpp>

#include "ArmControllerUi.hpp"
#include "DemoUiSupport.hpp"
#include "HeartbeatPresence.hpp"
#include "MedTech.hpp"

using namespace DdsEntities::Constants;
using namespace std::chrono_literals;
using medtech::operating_room::arm_controller_view;
using medtech::operating_room::ArmControllerUiCommand;
using medtech::operating_room::configure_arm_controller_ui;
using rti::demo::ui::Json;

namespace {

constexpr const char *ARM_ID = "arm-1";
constexpr double MAX_LINEAR_SPEED = 0.05;
constexpr double MAX_ANGULAR_SPEED = 0.5;
constexpr double MAX_OPENING_RATE = 0.02;
constexpr auto INPUT_TIMEOUT = 1500ms;
constexpr auto CONTROL_PERIOD = 20ms;
constexpr auto FEEDBACK_STALE = 500ms;

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

    bool start_demo(const Geometry::Pose &pose, double jaw_width)
    {
        if (status != Device::DeviceStatuses::ON)
            return false;
        stop_manual();
        demo_origin_ = pose.position;
        demo_jaw_origin_ = jaw_width;
        demo_jaw_excursion_ = jaw_width <= 0.03 ? 0.008 : -0.008;
        demo_motion_enabled_ = true;
        demo_phase_ = 0;
        demo_cycles_ = 0;
        demo_phase_started_ = std::chrono::steady_clock::now();
        demo_return_hold_until_ = demo_phase_started_;
        return true;
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
        if (direction == "STOPPED") {
            return held_axes_.erase(axis) > 0;
        }
        stop_demo();
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

    VelocityTarget rates_for_tick(const Geometry::Pose &pose, double jaw_width)
    {
        if (status != Device::DeviceStatuses::ON)
            return { };
        if (demo_motion_enabled_)
            return next_demo_rates(pose, jaw_width);

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

    unsigned int demo_cycles() const
    {
        return demo_cycles_;
    }

    bool demo_timed_out(std::chrono::steady_clock::time_point now) const
    {
        return demo_motion_enabled_ && now - demo_phase_started_ > 4s;
    }

private:
    struct HeldAxis {
        double direction;
        std::chrono::steady_clock::time_point last_refresh;
    };

    struct DemoWaypoint {
        double x;
        double y;
        double z;
        double jaw_fraction;
    };

    // Offsets from achieved pose at RUN DEMO, not integrated command estimates.
    static constexpr std::array<DemoWaypoint, 4> DEMO_WAYPOINTS = { {
            { -0.012, 0.010, 0.008, 1.0 },
            { -0.012, -0.010, 0.008, 0.0 },
            { 0.0, -0.010, 0.0, 1.0 },
            { },
    } };

    bool demo_motion_enabled_ = false;
    std::size_t demo_phase_ = 0;
    unsigned int demo_cycles_ = 0;
    std::chrono::steady_clock::time_point demo_phase_started_;
    std::chrono::steady_clock::time_point demo_return_hold_until_;
    Geometry::Vector3 demo_origin_;
    double demo_jaw_origin_ = 0.0;
    double demo_jaw_excursion_ = 0.0;
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

    VelocityTarget next_demo_rates(const Geometry::Pose &pose, double jaw_width)
    {
        const auto now = std::chrono::steady_clock::now();
        if (now < demo_return_hold_until_)
            return { };
        const auto &waypoint = DEMO_WAYPOINTS[demo_phase_];
        VelocityTarget error;
        error.x = demo_origin_.x + waypoint.x - pose.position.x;
        error.y = demo_origin_.y + waypoint.y - pose.position.y;
        error.z = demo_origin_.z + waypoint.z - pose.position.z;
        error.jaw = demo_jaw_origin_
                + waypoint.jaw_fraction * demo_jaw_excursion_ - jaw_width;
        const double distance = std::sqrt(error.x * error.x + error.y * error.y
                                          + error.z * error.z);
        if (distance <= 0.0007 && std::abs(error.jaw) <= 0.0004) {
            if (++demo_phase_ >= DEMO_WAYPOINTS.size()) {
                demo_phase_ = 0;
                ++demo_cycles_;
                demo_return_hold_until_ = now + 400ms;
            }
            demo_phase_started_ = now;
            return { };
        }
        VelocityTarget target;
        target.x = error.x * 4.0;
        target.y = error.y * 4.0;
        target.z = error.z * 4.0;
        normalize_group(target.x, target.y, target.z, 0.018);
        target.jaw = std::clamp(error.jaw * 4.0, -0.01, 0.01);
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

    bool demo_ready() const
    {
        return has_telemetry && has_pose && has_jaw_width
                && readiness != "FAULT"
                && std::chrono::steady_clock::now() - telemetry_received
                <= FEEDBACK_STALE
                && std::isfinite(pose.position.x)
                && std::isfinite(pose.position.y)
                && std::isfinite(pose.position.z) && std::isfinite(jaw_width)
                && jaw_width >= 0.0 && jaw_width <= 0.06;
    }

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

class ArmControllerApp {
public:
    ArmControllerApp(
            rti::demo::ui::DemoUiApp &app,
            medtech::ui::CommandQueue<ArmControllerUiCommand> &commands,
            std::atomic<bool> &stopping)
            : app_(app), commands_(commands), stopping_(stopping)
    {
        rti::domain::register_type<Device::Command>();
        rti::domain::register_type<Device::Status>();
        rti::domain::register_type<Device::Heartbeat>();
        rti::domain::register_type<Robot::Arm::TeleopControl>();
        rti::domain::register_type<Robot::Tool::ParallelJawControl>();
        rti::domain::register_type<Robot::Arm::Status>();
        rti::domain::register_type<Robot::Arm::Telemetry>();

        auto provider = dds::core::QosProvider::Default();
        participant_ = provider.extensions().create_participant_from_config(
                std::string(ARM_CONTROLLER_DP));
        status_writer_ = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Device::Status>>(participant_,
                                                      std::string(STATUS_DW));
        heartbeat_writer_ = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Device::Heartbeat>>(participant_,
                                                         std::string(HB_DW));
        teleop_writer_ = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Robot::Arm::TeleopControl>>(
                participant_,
                std::string(TELEOP_CONTROL_DW));
        tool_writer_ = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Robot::Tool::ParallelJawControl>>(
                participant_,
                std::string(TOOL_CONTROL_DW));
        command_reader_ = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Device::Command>>(
                participant_,
                std::string(DEVICE_COMMAND_DR));
        arm_status_reader_ = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Robot::Arm::Status>>(
                participant_,
                std::string(ARM_STATUS_DR));
        arm_telemetry_reader_ = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Robot::Arm::Telemetry>>(
                participant_,
                std::string(ARM_TELEMETRY_DR));

        auto require_endpoint = [](const auto &endpoint, const auto &name) {
            if (endpoint == dds::core::null) {
                throw std::runtime_error(
                        std::string(
                                "ArmController DDS configuration is missing "
                                "endpoint: ")
                        + std::string(name));
            }
        };
        require_endpoint(status_writer_, STATUS_DW);
        require_endpoint(heartbeat_writer_, HB_DW);
        require_endpoint(teleop_writer_, TELEOP_CONTROL_DW);
        require_endpoint(tool_writer_, TOOL_CONTROL_DW);
        require_endpoint(command_reader_, DEVICE_COMMAND_DR);
        require_endpoint(arm_status_reader_, ARM_STATUS_DR);
        require_endpoint(arm_telemetry_reader_, ARM_TELEMETRY_DR);
    }

    void run()
    {
        auto &app = app_;
        auto &commands = commands_;
        auto &stopping = stopping_;
        participant_.enable();

        medtech::operating_room::HeartbeatPublisher heartbeat(
                heartbeat_writer_,
                Device::DeviceType::ARM_CONTROLLER);
        ArmControllerLogic logic;
        ArmFeedback feedback;
        Device::Status status(Device::DeviceType::ARM_CONTROLLER, logic.status);
        status_writer_.write(status);
        Json logs = Json::array();
        auto update_view = [&]() {
            app.set_data(
                    arm_controller_view(logic.status,
                                        { { "running", logic.demo_enabled() },
                                          { "cycles", logic.demo_cycles() } },
                                        feedback.demo_ready(),
                                        logs,
                                        feedback.view()));
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
        heartbeat.start();
        auto now = std::chrono::steady_clock::now();
        auto next_control = now;
        auto next_ui_refresh = now;

        while (!stopping.load() && !heartbeat.failed()
               && logic.status != Device::DeviceStatuses::OFF) {
            while (auto intent = commands.try_pop()) {
                if (intent->action == "start-demo") {
                    if (feedback.demo_ready()
                        && logic.start_demo(feedback.pose,
                                            feedback.jaw_width)) {
                        log("Started feedback-anchored demo motion", "ok");
                    } else {
                        log("Cannot start demo: controller must be ON with "
                            "fresh, complete arm feedback and no arm fault",
                            "warn");
                    }
                } else if (intent->action == "stop-demo") {
                    logic.stop_demo();
                    logic.stop_manual();
                    log("Stopped all motion");
                } else if (intent->action == "teleop") {
                    if (logic.status != Device::DeviceStatuses::ON) {
                        log("Ignored jog while controller is not ON", "warn");
                        continue;
                    }
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

            for (const auto &sample : command_reader_.take()) {
                if (!sample.info().valid())
                    continue;
                logic.apply_device_command(sample.data().command);
                if (logic.status != Device::DeviceStatuses::ON)
                    publish_target(teleop_writer_, tool_writer_, { });
                status.status = logic.status;
                status_writer_.write(status);
                update_view();
                log("Received a device command from Orchestrator");
            }

            for (const auto &sample : arm_status_reader_.take()) {
                if (!sample.info().valid() || sample.data().arm_id != ARM_ID)
                    continue;
                feedback.readiness = readiness_name(sample.data().readiness);
                feedback.has_status = true;
            }
            for (const auto &sample : arm_telemetry_reader_.take()) {
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
            if (logic.demo_enabled()
                && (!feedback.demo_ready() || logic.demo_timed_out(now))) {
                logic.stop_demo();
                log(feedback.demo_ready()
                            ? "Demo waypoint timed out; stopped motion"
                            : "Demo feedback unavailable or arm fault; stopped "
                              "motion",
                    "warn");
            }
            for (const auto &axis : logic.expire_manual_inputs(now)) {
                log("Jog input timed out; stopped " + axis + " axis", "warn");
            }
            if (logic.status == Device::DeviceStatuses::ON
                && now >= next_control) {
                publish_target(teleop_writer_,
                               tool_writer_,
                               logic.rates_for_tick(feedback.pose,
                                                    feedback.jaw_width));
                next_control = now + CONTROL_PERIOD;
            }
            if (now >= next_ui_refresh) {
                update_view();
                next_ui_refresh = now + 200ms;
            }
            std::this_thread::sleep_for(5ms);
        }

        publish_target(teleop_writer_, tool_writer_, { });
        heartbeat.stop();
        if (heartbeat.failed())
            throw std::runtime_error("Arm Controller heartbeat worker failed");
        status.status = Device::DeviceStatuses::OFF;
        status_writer_.write(status);
        log("Arm Controller is shutting down");
        app.stop();
    }

private:
    rti::demo::ui::DemoUiApp &app_;
    medtech::ui::CommandQueue<ArmControllerUiCommand> &commands_;
    std::atomic<bool> &stopping_;
    dds::domain::DomainParticipant participant_ = dds::core::null;
    dds::pub::DataWriter<Device::Status> status_writer_ = dds::core::null;
    dds::pub::DataWriter<Device::Heartbeat> heartbeat_writer_ = dds::core::null;
    dds::pub::DataWriter<Robot::Arm::TeleopControl> teleop_writer_ =
            dds::core::null;
    dds::pub::DataWriter<Robot::Tool::ParallelJawControl> tool_writer_ =
            dds::core::null;
    dds::sub::DataReader<Device::Command> command_reader_ = dds::core::null;
    dds::sub::DataReader<Robot::Arm::Status> arm_status_reader_ =
            dds::core::null;
    dds::sub::DataReader<Robot::Arm::Telemetry> arm_telemetry_reader_ =
            dds::core::null;
};

}  // namespace

int main()
{
    using namespace rti::demo::ui;
    try {
        DemoUiApp app("Arm Controller",
                      0,
                      "127.0.0.1",
                      std::filesystem::path(RTI_DEMO_UI_WEB_ROOT),
                      Theme::dark,
                      Layout::automatic,
                      std::string("Arm Controller listening on"));
        medtech::ui::CommandQueue<ArmControllerUiCommand> commands;
        configure_arm_controller_ui(app, commands);
        std::atomic<bool> stopping = false;
        ArmControllerApp application(app, commands, stopping);
        bool worker_failed = false;
        std::thread dds_worker([&]() {
            try {
                application.run();
            } catch (const std::runtime_error &error) {
                // The UI loop may stop before the DDS worker observes shutdown.
                if (medtech::ui::is_model_stopped_error(error)) {
                    stopping.store(true);
                } else {
                    std::cerr << "ArmController DDS worker failed: "
                              << error.what() << std::endl;
                    worker_failed = true;
                }
            } catch (const std::exception &error) {
                std::cerr << "ArmController DDS worker failed: " << error.what()
                          << std::endl;
                worker_failed = true;
            } catch (...) {
                std::cerr << "ArmController DDS worker failed with an unknown "
                             "exception"
                          << std::endl;
                worker_failed = true;
            }
            if (worker_failed) {
                stopping.store(true);
                try {
                    app.stop();
                } catch (const std::exception &error) {
                    std::cerr << "ArmController UI shutdown failed: "
                              << error.what() << std::endl;
                } catch (...) {
                    std::cerr << "ArmController UI shutdown failed with an "
                                 "unknown exception"
                              << std::endl;
                }
            }
        });
        bool ui_succeeded = false;
        try {
            ui_succeeded = medtech::ui::run(app,
                                            1400,
                                            900,
                                            medtech::ui::native_icon_path());
        } catch (const std::exception &error) {
            std::cerr << "ArmController UI failed: " << error.what()
                      << std::endl;
        } catch (...) {
            std::cerr << "ArmController UI failed with an unknown exception"
                      << std::endl;
        }
        stopping.store(true);
        dds_worker.join();
        return worker_failed || !ui_succeeded ? 1 : 0;
    } catch (const std::exception &error) {
        std::cerr << "ArmController setup failed: " << error.what()
                  << std::endl;
    } catch (...) {
        std::cerr << "ArmController setup failed with an unknown exception"
                  << std::endl;
    }
    return 1;
}
