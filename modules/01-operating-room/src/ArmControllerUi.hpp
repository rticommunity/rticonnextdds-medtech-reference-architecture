/*
 * (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
 *
 * RTI grants Licensee a license to use, modify, compile, and create derivative
 * works of the software solely for use with RTI Connext DDS. Licensee may
 * redistribute copies of the software provided that all such copies are
 * subject to this license. The software is provided "as is", with no warranty
 * of any type, including any warranty for fitness for any purpose.
 */

#pragma once

#include <array>
#include <string>
#include <tuple>

#include "DemoUiSupport.hpp"
#include "MedTech.hpp"

namespace medtech::operating_room {

struct ArmControllerUiCommand {
    std::string action;
    std::string axis;
    std::string direction;
};

inline rti::demo::ui::Json arm_controller_view(
        Device::DeviceStatusKind device_status,
        bool secure,
        const rti::demo::ui::Json &demo,
        bool demo_ready,
        const rti::demo::ui::Json &logs,
        const rti::demo::ui::Json &feedback,
        bool arm_matched,
        bool jaw_matched)
{
    using rti::demo::ui::Json;
    const std::string status = device_status == Device::DeviceStatusKind::ON
            ? "ON"
            : device_status == Device::DeviceStatusKind::PAUSED ? "PAUSED"
                                                                : "OFF";
    const bool enabled = device_status == Device::DeviceStatusKind::ON;
    const bool status_known = feedback.at("status_known");
    const std::string readiness = feedback.at("readiness");
    const std::string readiness_badge =
            status_known ? readiness + " · LAST KNOWN" : "UNKNOWN";
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
    Json demo_controls = Json::array(
            { { { "type", "button" },
                { "label", "RUN DEMO" },
                { "command", "start-demo" },
                { "payload", Json::object() },
                { "style", "primary" },
                { "disabled",
                  !enabled || !demo_ready || demo.at("running").get<bool>() } },
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
        { "dds_security", secure },
        { "device_status", status },
        { "header_badges",
          Json::array(
                  { { { "label", "Arm readiness" },
                      { "value", readiness_badge },
                      { "tone",
                        readiness == "READY" && status_known ? "good"
                                                             : "warn" } },
                    { { "label", "Arm command subscribers" },
                      { "value", arm_matched ? "MATCHED" : "NO MATCH" },
                      { "tone", arm_matched ? "good" : "muted" } },
                    { { "label", "Jaw command subscribers" },
                      { "value", jaw_matched ? "MATCHED" : "NO MATCH" },
                      { "tone", jaw_matched ? "good" : "muted" } },
                    { { "label", "Demo" },
                      { "value",
                        demo.at("running").get<bool>()
                                ? "RUNNING · "
                                        + std::to_string(
                                                demo.at("cycles")
                                                        .get<unsigned int>())
                                        + " LOOPS"
                                : "IDLE" } } }) },
        { "control_intro",
          "Hold a direction for base-frame motion (+Z up). Release to command "
          "zero." },
        { "control_note",
          "Linear rates use m/s; angular rates use rad/s. Jaw buttons command "
          "signed gap rate in m/s. RUN DEMO requires fresh pose/jaw feedback "
          "and loops back to its starting position/gap. A manual jog takes "
          "over; STOP MOTION clears both demo and held jogs." },
        { "status", status },
        { "demo", demo },
        { "feedback", feedback },
        { "control_groups", control_groups },
        { "activity_title", "ALERTS" },
        { "footer", false },
        { "logs", logs },
    };
}

inline void configure_arm_controller_ui(
        rti::demo::ui::DemoUiApp &app,
        medtech::ui::CommandQueue<ArmControllerUiCommand> &commands)
{
    using namespace rti::demo::ui;
    const auto empty_object = Json { { "type", "object" },
                                     { "properties", Json::object() },
                                     { "additionalProperties", false } };
    app.register_command(
            "start-demo",
            CommandSchema(empty_object),
            [&commands](const Json &) {
                commands.push({ "start-demo", { }, { } });
                return Json { { "message", "Demo start requested" } };
            });
    app.register_command(
            "stop-demo",
            CommandSchema(empty_object),
            [&commands](const Json &) {
                commands.push({ "stop-demo", { }, { } });
                return Json { { "message", "Motion stop requested" } };
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
}

}  // namespace medtech::operating_room
