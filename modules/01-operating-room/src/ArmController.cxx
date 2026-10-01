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
#include <rti/core/cond/AsyncWaitSet.hpp>

#include <thread>
#include <chrono>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <atomic>
#include <deque>
#include <csignal>
#include <ctime>
#include <map>
#include <sstream>


#include "Types.hpp"
#include "third_party/httplib.h"



using namespace DdsEntities::Constants;

namespace ArmControllerWebUi {

std::string json_escape(const std::string &s)
{
    std::string out;
    out.reserve(s.size() + 8);
    for (char c : s) {
        switch (c) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
            if (static_cast<unsigned char>(c) < 0x20) {
                char buf[8];
                std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                out += buf;
            } else {
                out += c;
            }
        }
    }
    return out;
}

std::string motor_to_id(SurgicalRobot::Motors motor)
{
    switch (motor) {
    case SurgicalRobot::Motors::BASE: return "BASE";
    case SurgicalRobot::Motors::SHOULDER: return "SHOULDER";
    case SurgicalRobot::Motors::ELBOW: return "ELBOW";
    case SurgicalRobot::Motors::WRIST: return "WRIST";
    case SurgicalRobot::Motors::HAND: return "HAND";
    default: return "UNKNOWN";
    }
}

bool id_to_motor(const std::string &id, SurgicalRobot::Motors &out)
{
    if (id == "BASE") {
        out = SurgicalRobot::Motors::BASE;
    } else if (id == "SHOULDER") {
        out = SurgicalRobot::Motors::SHOULDER;
    } else if (id == "ELBOW") {
        out = SurgicalRobot::Motors::ELBOW;
    } else if (id == "WRIST") {
        out = SurgicalRobot::Motors::WRIST;
    } else if (id == "HAND") {
        out = SurgicalRobot::Motors::HAND;
    } else {
        return false;
    }
    return true;
}

bool extract_json_string_field(
        const std::string &body,
        const std::string &key,
        std::string &out)
{
    std::string needle = "\"" + key + "\"";
    auto pos = body.find(needle);
    if (pos == std::string::npos) {
        return false;
    }
    pos = body.find(':', pos + needle.size());
    if (pos == std::string::npos) {
        return false;
    }
    // Skip whitespace to allow both string and literal (bool) values.
    auto val_start = body.find_first_not_of(" \t\r\n", pos + 1);
    if (val_start == std::string::npos) {
        return false;
    }
    if (body[val_start] == '"') {
        auto quote_end = body.find('"', val_start + 1);
        if (quote_end == std::string::npos) {
            return false;
        }
        out = body.substr(val_start + 1, quote_end - val_start - 1);
    } else {
        auto val_end = body.find_first_of(",}", val_start);
        if (val_end == std::string::npos) {
            return false;
        }
        out = body.substr(val_start, val_end - val_start);
    }
    return true;
}

}  // namespace ArmControllerWebUi

class ArmControllerWebApp {
public:
    ArmControllerWebApp(int port) : port(port)
    {
        rti::domain::register_type<Orchestrator::DeviceCommand>();
        rti::domain::register_type<Common::DeviceStatus>();
        rti::domain::register_type<SurgicalRobot::MotorControl>();
        rti::domain::register_type<Common::DeviceHeartbeat>();

        for (auto motor : { SurgicalRobot::Motors::BASE,
                            SurgicalRobot::Motors::SHOULDER,
                            SurgicalRobot::Motors::ELBOW,
                            SurgicalRobot::Motors::WRIST,
                            SurgicalRobot::Motors::HAND }) {
            motor_playing[motor] = false;
        }

        auto default_provider = dds::core::QosProvider::Default();
        dds::domain::DomainParticipant participant =
                default_provider.extensions().create_participant_from_config(
                        std::string(ARM_CONTROLLER_DP));

        status_writer = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Common::DeviceStatus>>(
                participant,
                std::string(STATUS_DW));
        hb_writer = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Common::DeviceHeartbeat>>(
                participant,
                std::string(HB_DW));
        arm_writer = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<SurgicalRobot::MotorControl>>(
                participant,
                std::string(MOTOR_CONTROL_DW));
        cmd_reader = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Orchestrator::DeviceCommand>>(
                participant,
                std::string(DEVICE_COMMAND_DR));

        cmd_read_condition = dds::sub::cond::ReadCondition(
                cmd_reader,
                dds::sub::status::DataState::any(),
                [this]() { process_command(); });
        waitset_command += cmd_read_condition;

        setup_http_routes();
    }

    void run()
    {
        waitset_command.start();
        write_status();
        log_alert("Started Arm Controller (web mode)");

        std::thread hb_thread(&ArmControllerWebApp::write_hb, this);
        std::thread play_thread(&ArmControllerWebApp::playing, this);

        std::cout << "Arm Controller web UI listening on http://localhost:"
                   << port << "/" << std::endl;
        server.listen("0.0.0.0", port);

        hb_thread.join();
        play_thread.join();
    }

private:
    int port;
    std::mutex state_mutex;
    Common::DeviceStatus current_status { Common::DeviceType::ARM_CONTROLLER,
                                          Common::DeviceStatuses::ON };
    std::map<SurgicalRobot::Motors, bool> motor_playing;
    std::deque<std::string> alerts;
    static constexpr size_t MAX_ALERTS = 200;

    httplib::Server server;

    dds::pub::DataWriter<Common::DeviceStatus> status_writer = dds::core::null;
    dds::pub::DataWriter<Common::DeviceHeartbeat> hb_writer = dds::core::null;
    dds::pub::DataWriter<SurgicalRobot::MotorControl> arm_writer =
            dds::core::null;
    dds::sub::DataReader<Orchestrator::DeviceCommand> cmd_reader =
            dds::core::null;
    dds::sub::cond::ReadCondition cmd_read_condition = dds::core::null;
    rti::core::cond::AsyncWaitSet waitset_command;

    void log_alert(const std::string &msg)
    {
        std::time_t now = std::time(nullptr);
        std::tm *local_time = std::localtime(&now);
        char time_str[100];
        std::strftime(
                time_str,
                sizeof(time_str),
                "%Y-%m-%d %H:%M:%S",
                local_time);

        std::stringstream ss;
        ss << time_str << " - " << msg;

        std::lock_guard<std::mutex> lock(state_mutex);
        alerts.push_back(ss.str());
        while (alerts.size() > MAX_ALERTS) {
            alerts.pop_front();
        }
    }

    void write_hb()
    {
        while (current_status.status != Common::DeviceStatuses::OFF) {
            Common::DeviceHeartbeat hb(Common::DeviceType::ARM_CONTROLLER);
            hb_writer.write(hb);
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    }

    void write_status()
    {
        std::lock_guard<std::mutex> lock(state_mutex);
        status_writer.write(current_status);
    }

    void write_command(
            SurgicalRobot::Motors motor,
            SurgicalRobot::MotorDirections dir)
    {
        std::lock_guard<std::mutex> lock(state_mutex);
        if (current_status.status == Common::DeviceStatuses::ON) {
            SurgicalRobot::MotorControl sample(motor, dir);
            arm_writer.write(sample);
        }
    }

    void playing()
    {
        while (current_status.status != Common::DeviceStatuses::OFF) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            std::vector<SurgicalRobot::Motors> active_motors;
            {
                std::lock_guard<std::mutex> lock(state_mutex);
                for (auto const &kv : motor_playing) {
                    if (kv.second) {
                        active_motors.push_back(kv.first);
                    }
                }
            }
            for (auto motor : active_motors) {
                write_command(
                        motor,
                        static_cast<SurgicalRobot::MotorDirections>(
                                rand() % 3));
            }
        }
    }

    void process_command()
    {
        dds::sub::LoanedSamples<Orchestrator::DeviceCommand> samples =
                cmd_reader.take();

        for (const auto &sample : samples) {
            if (sample.info().valid()) {
                // log_alert() acquires state_mutex itself, so it must be
                // called before/without holding the lock here to avoid a
                // self-deadlock (std::mutex is not recursive).
                if (sample.data().command
                    == Orchestrator::DeviceCommands::PAUSE) {
                    log_alert("Received PAUSE Command from Orchestrator");
                    std::lock_guard<std::mutex> lock(state_mutex);
                    current_status.status = Common::DeviceStatuses::PAUSED;
                } else if (sample.data().command
                           == Orchestrator::DeviceCommands::START) {
                    log_alert("Received START Command from Orchestrator");
                    std::lock_guard<std::mutex> lock(state_mutex);
                    current_status.status = Common::DeviceStatuses::ON;
                } else {
                    log_alert("Received SHUTDOWN Command from Orchestrator");
                    std::cout << "Arm Controller shutting down" << std::endl;
                    {
                        std::lock_guard<std::mutex> lock(state_mutex);
                        current_status.status = Common::DeviceStatuses::OFF;
                    }
                    server.stop();
                }
            }
        }

        write_status();
    }

    void setup_http_routes()
    {
        server.set_mount_point("/", "web-armcontroller");

        server.Get("/api/state", [this](
                                          const httplib::Request &,
                                          httplib::Response &res) {
            res.set_content(build_state_json(), "application/json");
        });

        server.Post(
                "/api/motor",
                [this](const httplib::Request &req, httplib::Response &res) {
                    handle_motor_request(req, res);
                });

        server.Post(
                "/api/play",
                [this](const httplib::Request &req, httplib::Response &res) {
                    handle_play_request(req, res);
                });

        server.Post(
                "/api/play_all",
                [this](const httplib::Request &req, httplib::Response &res) {
                    handle_play_all_request(req, res);
                });
    }

    std::string build_state_json()
    {
        std::lock_guard<std::mutex> lock(state_mutex);

        std::stringstream ss;
        ss << "{";
        ss << "\"status\":\""
           << (current_status.status == Common::DeviceStatuses::ON
                       ? "ON"
                       : current_status.status
                                       == Common::DeviceStatuses::PAUSED
                               ? "PAUSED"
                               : "OFF")
           << "\",";

        ss << "\"motors\":[";
        bool first = true;
        for (auto const &kv : motor_playing) {
            if (!first) {
                ss << ",";
            }
            first = false;
            ss << "{\"id\":\""
               << ArmControllerWebUi::motor_to_id(kv.first) << "\","
               << "\"playing\":" << (kv.second ? "true" : "false") << "}";
        }
        ss << "],";

        ss << "\"alerts\":[";
        first = true;
        for (auto const &alert : alerts) {
            if (!first) {
                ss << ",";
            }
            first = false;
            ss << "\"" << ArmControllerWebUi::json_escape(alert) << "\"";
        }
        ss << "]";
        ss << "}";
        return ss.str();
    }

    void handle_motor_request(
            const httplib::Request &req,
            httplib::Response &res)
    {
        std::string motor_id;
        std::string action;
        if (!ArmControllerWebUi::extract_json_string_field(
                    req.body,
                    "motor",
                    motor_id)
            || !ArmControllerWebUi::extract_json_string_field(
                    req.body,
                    "action",
                    action)) {
            res.status = 400;
            res.set_content("{\"error\":\"missing motor/action\"}",
                            "application/json");
            return;
        }

        SurgicalRobot::Motors motor;
        if (!ArmControllerWebUi::id_to_motor(motor_id, motor)) {
            res.status = 400;
            res.set_content("{\"error\":\"unknown motor\"}",
                            "application/json");
            return;
        }

        SurgicalRobot::MotorDirections dir;
        if (action == "inc") {
            dir = SurgicalRobot::MotorDirections::INCREMENT;
        } else if (action == "dec") {
            dir = SurgicalRobot::MotorDirections::DECREMENT;
        } else {
            res.status = 400;
            res.set_content("{\"error\":\"unknown action\"}",
                            "application/json");
            return;
        }

        // Manual jog deactivates AUTO/play mode for that joint, mirroring
        // the GTK UI's behavior.
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            motor_playing[motor] = false;
        }
        write_command(motor, dir);

        res.set_content("{\"ok\":true}", "application/json");
    }

    void handle_play_request(
            const httplib::Request &req,
            httplib::Response &res)
    {
        std::string motor_id;
        std::string active_str;
        if (!ArmControllerWebUi::extract_json_string_field(
                    req.body,
                    "motor",
                    motor_id)
            || !ArmControllerWebUi::extract_json_string_field(
                    req.body,
                    "active",
                    active_str)) {
            res.status = 400;
            res.set_content("{\"error\":\"missing motor/active\"}",
                            "application/json");
            return;
        }

        SurgicalRobot::Motors motor;
        if (!ArmControllerWebUi::id_to_motor(motor_id, motor)) {
            res.status = 400;
            res.set_content("{\"error\":\"unknown motor\"}",
                            "application/json");
            return;
        }

        bool active = (active_str == "true");
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            motor_playing[motor] = active;
        }

        res.set_content("{\"ok\":true}", "application/json");
    }

    void handle_play_all_request(
            const httplib::Request &req,
            httplib::Response &res)
    {
        std::string active_str;
        if (!ArmControllerWebUi::extract_json_string_field(
                    req.body,
                    "active",
                    active_str)) {
            res.status = 400;
            res.set_content("{\"error\":\"missing active\"}",
                            "application/json");
            return;
        }

        bool active = (active_str == "true");
        log_alert(active ? "Playing All" : "Stopping All");
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            for (auto &kv : motor_playing) {
                kv.second = active;
            }
        }

        res.set_content("{\"ok\":true}", "application/json");
    }
};

int main(int argc, char const *argv[])
{
    int web_port = 8091;
    for (int i = 1; i < argc; ++i) {
        std::string arg(argv[i]);
        if (arg == "--port" && i + 1 < argc) {
            web_port = std::atoi(argv[++i]);
        }
    }

    ArmControllerWebApp app(web_port);
    app.run();
    return 0;
}
