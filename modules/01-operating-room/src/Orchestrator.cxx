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
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <atomic>
#include <vector>
#include <deque>
#include <csignal>
#include <ctime>
#include <map>
#include <sstream>


#include "Types.hpp"
#include "third_party/httplib.h"



using namespace DdsEntities::Constants;
#ifdef RTI_SECURITY_AVAILABLE
    #include "SecureLogUtils.hpp"
#endif

// Heartbeat listener to automatically monitor other applications
namespace WebUi {

std::string device_type_to_id(Common::DeviceType device)
{
    switch (device) {
    case Common::DeviceType::ARM: return "ARM";
    case Common::DeviceType::ARM_CONTROLLER: return "ARM_CONTROLLER";
    case Common::DeviceType::PATIENT_SENSOR: return "PATIENT_SENSOR";
    case Common::DeviceType::PATIENT_MONITOR: return "PATIENT_MONITOR";
    default: return "UNKNOWN";
    }
}

bool device_id_to_type(const std::string &id, Common::DeviceType &out)
{
    if (id == "ARM") {
        out = Common::DeviceType::ARM;
    } else if (id == "ARM_CONTROLLER") {
        out = Common::DeviceType::ARM_CONTROLLER;
    } else if (id == "PATIENT_SENSOR") {
        out = Common::DeviceType::PATIENT_SENSOR;
    } else if (id == "PATIENT_MONITOR") {
        out = Common::DeviceType::PATIENT_MONITOR;
    } else {
        return false;
    }
    return true;
}

std::string status_to_str(Common::DeviceStatuses status)
{
    switch (status) {
    case Common::DeviceStatuses::ON: return "ON";
    case Common::DeviceStatuses::PAUSED: return "PAUSED";
    case Common::DeviceStatuses::ERROR: return "ERROR";
    default: return "OFF";
    }
}

bool command_id_to_enum(
        const std::string &id,
        Orchestrator::DeviceCommands &out)
{
    if (id == "START") {
        out = Orchestrator::DeviceCommands::START;
    } else if (id == "PAUSE") {
        out = Orchestrator::DeviceCommands::PAUSE;
    } else if (id == "SHUTDOWN") {
        out = Orchestrator::DeviceCommands::SHUTDOWN;
    } else {
        return false;
    }
    return true;
}

// Minimal JSON string escaping — sufficient for our own status/log strings.
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

// Extracts the string value of a top-level "key":"value" pair from a small,
// flat JSON object. Not a general-purpose parser — only used to read the
// {"device": "...", "command": "..."} bodies this server's own frontend
// sends.
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
    auto quote_start = body.find('"', pos + 1);
    if (quote_start == std::string::npos) {
        return false;
    }
    auto quote_end = body.find('"', quote_start + 1);
    if (quote_end == std::string::npos) {
        return false;
    }
    out = body.substr(quote_start + 1, quote_end - quote_start - 1);
    return true;
}

}  // namespace WebUi

class WebHeartbeatListener
        : public dds::sub::NoOpDataReaderListener<Common::DeviceHeartbeat> {
public:
    WebHeartbeatListener(
            std::mutex &state_mutex,
            std::map<Common::DeviceType, std::string> &status_map,
            std::function<void(std::string)> log_alert)
            : state_mutex(state_mutex), status_map(status_map),
              log_alert(log_alert)
    {
    }

    void on_requested_deadline_missed(
            dds::sub::DataReader<Common::DeviceHeartbeat> &reader,
            const dds::core::status::RequestedDeadlineMissedStatus &status)
            override
    {
        Common::DeviceHeartbeat sample;
        reader.key_value(sample, status.last_instance_handle());

        std::string alert;
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            std::string &current = status_map[sample.device];
            if (current != "OFF") {
                current = "OFF";
                std::stringstream ss;
                ss << sample.device
                   << " is no longer sending heartbeats. Updating Status to OFF.";
                alert = ss.str();
            }
        }
        if (!alert.empty()) {
            log_alert(std::move(alert));
        }
    }

private:
    std::mutex &state_mutex;
    std::map<Common::DeviceType, std::string> &status_map;
    std::function<void(std::string)> log_alert;
};

class OrchestratorWebApp {
public:
    OrchestratorWebApp(int port) : port(port)
    {
        rti::domain::register_type<Orchestrator::DeviceCommand>();
        rti::domain::register_type<Common::DeviceStatus>();
        rti::domain::register_type<Common::DeviceHeartbeat>();

        for (auto device : { Common::DeviceType::ARM,
                             Common::DeviceType::ARM_CONTROLLER,
                             Common::DeviceType::PATIENT_SENSOR,
                             Common::DeviceType::PATIENT_MONITOR }) {
            device_status[device] = "OFF";
        }

        auto default_provider = dds::core::QosProvider::Default();

        participant =
                default_provider.extensions().create_participant_from_config(
                        std::string(ORCHESTRATOR_DP));

        command_writer = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Orchestrator::DeviceCommand>>(
                participant,
                std::string(DEVICE_COMMAND_DW));

        status_reader = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Common::DeviceStatus>>(
                participant,
                std::string(STATUS_DR));
        hb_reader = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Common::DeviceHeartbeat>>(
                participant,
                std::string(HB_DR));

        hb_listener = std::make_shared<WebHeartbeatListener>(
                state_mutex,
                device_status,
                [this](std::string msg) { log_alert(msg); });
        hb_reader.set_listener(hb_listener);

        status_read_condition = dds::sub::cond::ReadCondition(
                status_reader,
                dds::sub::status::DataState::any(),
                [this]() { process_status(); });
        waitset_status += status_read_condition;

#ifdef RTI_SECURITY_AVAILABLE
        security_enabled = SecureLogUtils::is_secure(participant);
        if (security_enabled) {
            securelog_reader = SecureLogUtils::setup_secure_log_reader(
                    std::bind(&OrchestratorWebApp::process_secure_log,
                              this,
                              std::placeholders::_1),
                    default_provider);
        }
#endif

        setup_http_routes();
        log_alert("Started Orchestrator (web mode)");
    }

    void run()
    {
        waitset_status.start();
        std::cout << "Orchestrator web UI listening on http://localhost:"
                   << port << "/" << std::endl;
        server.listen("0.0.0.0", port);
    }

    void stop()
    {
        server.stop();
    }

private:
    int port;
    std::mutex state_mutex;
    std::map<Common::DeviceType, std::string> device_status;
    std::deque<std::string> alerts;
    bool security_enabled = false;
    std::atomic<bool> security_threat { false };

    httplib::Server server;

    dds::domain::DomainParticipant participant = dds::core::null;
    dds::pub::DataWriter<Orchestrator::DeviceCommand> command_writer =
            dds::core::null;
    dds::sub::DataReader<Common::DeviceStatus> status_reader = dds::core::null;
    dds::sub::DataReader<Common::DeviceHeartbeat> hb_reader = dds::core::null;
    dds::sub::cond::ReadCondition status_read_condition = dds::core::null;
    rti::core::cond::AsyncWaitSet waitset_status;
    std::shared_ptr<WebHeartbeatListener> hb_listener;

#ifdef RTI_SECURITY_AVAILABLE
    SecureLogUtils::SecureLogReader securelog_reader = { dds::core::null,
                                                         dds::core::null };
#endif

    static constexpr size_t MAX_ALERTS = 200;

    void log_alert(std::string msg)
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

    void process_status()
    {
        dds::sub::LoanedSamples<Common::DeviceStatus> samples =
                status_reader.take();

        for (const auto &sample : samples) {
            if (sample.info().valid()) {
                std::string status_str = WebUi::status_to_str(
                        sample.data().status);
                {
                    std::lock_guard<std::mutex> lock(state_mutex);
                    device_status[sample.data().device] = status_str;
                }

                std::stringstream ss_log;
                ss_log << "Received " << sample.data().status
                       << " status message from " << sample.data().device;
                log_alert(ss_log.str());
            }
        }
    }

#ifdef RTI_SECURITY_AVAILABLE
    bool is_security_threat(const DDSSecurity::BuiltinLoggingTypeV2 &sample)
    {
        return static_cast<int32_t>(sample.severity)
                <= static_cast<int32_t>(
                        DDSSecurity::LoggingLevel::WARNING_LEVEL);
    }

    void process_secure_log(const SecureLogUtils::SecureLogType &log)
    {
        if (is_security_threat(log)) {
            std::stringstream ss;
            ss << "SECURITY THREAT [" << log.appname << "] " << log.message;
            log_alert(ss.str());
            security_threat = true;
        }
    }
#endif

    void setup_http_routes()
    {
        server.set_mount_point("/", "web");

        server.Get("/api/state", [this](
                                          const httplib::Request &,
                                          httplib::Response &res) {
            res.set_content(build_state_json(), "application/json");
        });

        server.Post(
                "/api/command",
                [this](const httplib::Request &req, httplib::Response &res) {
                    handle_command_request(req, res);
                });
    }

    std::string build_state_json()
    {
        std::lock_guard<std::mutex> lock(state_mutex);

        std::stringstream ss;
        ss << "{";

        ss << "\"security\":{";
        ss << "\"enabled\":" << (security_enabled ? "true" : "false") << ",";
        ss << "\"threat\":" << (security_threat.load() ? "true" : "false");
        ss << "},";

        ss << "\"devices\":[";
        bool first = true;
        for (auto const &kv : device_status) {
            if (!first) {
                ss << ",";
            }
            first = false;
            ss << "{\"id\":\"" << WebUi::device_type_to_id(kv.first) << "\","
               << "\"status\":\"" << WebUi::json_escape(kv.second) << "\"}";
        }
        ss << "],";

        ss << "\"alerts\":[";
        first = true;
        for (auto const &alert : alerts) {
            if (!first) {
                ss << ",";
            }
            first = false;
            ss << "\"" << WebUi::json_escape(alert) << "\"";
        }
        ss << "]";

        ss << "}";
        return ss.str();
    }

    void handle_command_request(
            const httplib::Request &req,
            httplib::Response &res)
    {
        std::string device_id;
        std::string command_id;
        if (!WebUi::extract_json_string_field(req.body, "device", device_id)
            || !WebUi::extract_json_string_field(
                    req.body,
                    "command",
                    command_id)) {
            res.status = 400;
            res.set_content("{\"error\":\"missing device/command\"}",
                            "application/json");
            return;
        }

        Common::DeviceType device;
        Orchestrator::DeviceCommands command;
        if (!WebUi::device_id_to_type(device_id, device)
            || !WebUi::command_id_to_enum(command_id, command)) {
            res.status = 400;
            res.set_content("{\"error\":\"unknown device/command\"}",
                            "application/json");
            return;
        }

        std::stringstream ss;
        ss << "Writing " << command << " to " << device;
        log_alert(ss.str());

        Orchestrator::DeviceCommand dds_command(device, command);
        command_writer.write(dds_command);

        res.set_content("{\"ok\":true}", "application/json");
    }
};

int main(int argc, char const *argv[])
{
    int web_port = 8090;
    for (int i = 1; i < argc; ++i) {
        std::string arg(argv[i]);
        if (arg == "--port" && i + 1 < argc) {
            web_port = std::atoi(argv[++i]);
        }
    }

    OrchestratorWebApp app(web_port);
    app.run();
    return 0;
}
