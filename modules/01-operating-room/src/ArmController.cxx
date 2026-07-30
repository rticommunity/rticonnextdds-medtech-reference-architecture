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
#include <gtkmm.h>
#include <gdkmm/screen.h>

#include "Types.hpp"
#include "third_party/httplib.h"

#ifdef __APPLE__
    #include "MacOsDockIcon.h"
#endif

#ifndef _WIN32
    #include <glib-unix.h>
#endif

using namespace DdsEntities::Constants;

class SurgicalArmController {
public:
    SurgicalArmController()
            : current_status(Common::DeviceType::ARM_CONTROLLER,
                             Common::DeviceStatuses::ON)
    {
        // Initialize Connext entities
        initialize_connext();
    }

    void run(int argc, char const *argv[])
    {
        // Start threads
        std::thread hb_thread(&SurgicalArmController::write_hb, this);
        std::thread play_thread(&SurgicalArmController::playing, this);
        waitset_command.start();
        write_status();

        // Run GTK UI
        app = Gtk::Application::create("armcontroller.armcontroller");
        app->signal_activate().connect(
                sigc::mem_fun(*this, &SurgicalArmController::ui_setup));

#ifndef _WIN32
        // Route SIGINT/SIGTERM through the GLib main loop so GTK functions
        // can be called safely from the callback.
        g_unix_signal_add(
                SIGINT,
                [](gpointer data) -> gboolean {
                    static_cast<SurgicalArmController *>(data)
                            ->window_close_from_signal();
                    return G_SOURCE_REMOVE;
                },
                this);
        g_unix_signal_add(
                SIGTERM,
                [](gpointer data) -> gboolean {
                    static_cast<SurgicalArmController *>(data)
                            ->window_close_from_signal();
                    return G_SOURCE_REMOVE;
                },
                this);
#endif

        app->run(argc, const_cast<char **>(argv));

        // Join threads before exiting
        hb_thread.join();
        play_thread.join();
    }

private:
    // Connext entities
    dds::pub::DataWriter<Common::DeviceStatus> status_writer = dds::core::null;
    dds::pub::DataWriter<Common::DeviceHeartbeat> hb_writer = dds::core::null;
    dds::pub::DataWriter<SurgicalRobot::MotorControl> arm_writer =
            dds::core::null;
    dds::sub::DataReader<Orchestrator::DeviceCommand> cmd_reader =
            dds::core::null;
    rti::core::cond::AsyncWaitSet waitset_command;

    Common::DeviceStatus current_status;

    // GTK UI entities
    Gtk::Window *window = nullptr;
    Glib::RefPtr<Gtk::Application> app;
    std::map<SurgicalRobot::Motors, Gtk::ToggleButton *> motor_play_btns;
    std::map<SurgicalRobot::Motors, Gtk::Label *> motor_dir_labels;
    std::map<std::string, sigc::connection> inc_dec_timers;
    Gtk::TextView *console = nullptr;

    // Initialize Connext participants, readers, and writers
    void initialize_connext()
    {
        // We need to register the types before we start creating DDS entities
        rti::domain::register_type<Orchestrator::DeviceCommand>();
        rti::domain::register_type<Common::DeviceStatus>();
        rti::domain::register_type<SurgicalRobot::MotorControl>();
        rti::domain::register_type<Common::DeviceHeartbeat>();

        // Connext will load XML files through the default provider from the
        // NDDS_QOS_PROFILES environment variable
        auto default_provider = dds::core::QosProvider::Default();

        dds::domain::DomainParticipant participant =
                default_provider.extensions().create_participant_from_config(
                        std::string(ARM_CONTROLLER_DP));

        // Initialize DataWriters
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

        // Initialize DataReader
        cmd_reader = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Orchestrator::DeviceCommand>>(
                participant,
                std::string(DEVICE_COMMAND_DR));

        // Setup command handling with a WaitSet
        dds::sub::cond::ReadCondition command_read_condition(
                cmd_reader,
                dds::sub::status::DataState::any(),
                [this]() { process_command(); });

        waitset_command += command_read_condition;
    }

    // Publish heartbeat every 50ms
    void write_hb()
    {
        while (current_status.status != Common::DeviceStatuses::OFF) {
            Common::DeviceHeartbeat hb(Common::DeviceType::ARM_CONTROLLER);
            hb_writer.write(hb);
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    }

    // Publish status
    void write_status()
    {
        status_writer.write(current_status);
    }

    // Write motor command
    void write_command(SurgicalRobot::Motors motor,
                       SurgicalRobot::MotorDirections dir)
    {
        if (current_status.status == Common::DeviceStatuses::ON) {
            SurgicalRobot::MotorControl sample(motor, dir);
            arm_writer.write(sample);
        }
    }

    // Publish random motor controls for the motors that have been marked as
    // playing
    void playing()
    {
        while (current_status.status != Common::DeviceStatuses::OFF) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            for (const auto &btn : motor_play_btns) {
                if (btn.second->get_active()) {
                    write_command(btn.first,
                                  static_cast<SurgicalRobot::MotorDirections>(
                                          rand() % 3));
                }
            }
        }
    }

    // Process received device commands from Orchestrator
    void process_command()
    {
        dds::sub::LoanedSamples<Orchestrator::DeviceCommand> samples =
                cmd_reader.take();

        for (const auto &sample : samples) {
            if (sample.info().valid()) {
                if (sample.data().command
                    == Orchestrator::DeviceCommands::PAUSE) {
                    log_alert("Received PAUSE Command from Orchestrator");
                    current_status.status = Common::DeviceStatuses::PAUSED;
                } else if (sample.data().command
                           == Orchestrator::DeviceCommands::START) {
                    log_alert("Received START Command from Orchestrator");
                    current_status.status = Common::DeviceStatuses::ON;
                } else {  // shutdown
                    log_alert("Received SHUTDOWN Command from Orchestrator");
                    std::cout << "Arm Controller shutting down" << std::endl;
                    current_status.status = Common::DeviceStatuses::OFF;
                    app->quit();
                }
            }
        }

        write_status();
    }

    // Logic for play all and stop all
    void set_all(bool play_all)
    {
        if (play_all)
            log_alert("Playing All");
        else
            log_alert("Stopping All");

        for (auto &btn : motor_play_btns) {
            btn.second->set_active(play_all);
        }
    }

    // Setup UI
    void ui_setup()
    {
        // Load CSS stylesheet
        auto css_provider = Gtk::CssProvider::create();
        try {
            css_provider->load_from_path("ui/armcontroller.css");
        } catch (const Glib::Error &e) {
            std::cerr << "Warning: could not load armcontroller.css: "
                      << e.what() << std::endl;
        }
        Gtk::StyleContext::add_provider_for_screen(
                Gdk::Screen::get_default(),
                css_provider,
                GTK_STYLE_PROVIDER_PRIORITY_USER);

        auto builder = Gtk::Builder::create_from_file("ui/armcontroller.glade");
        builder->get_widget<Gtk::Window>("window", window);

        // Load RTI logo into header and set as dock/taskbar icon
        {
            Gtk::Box *hdr = nullptr;
            builder->get_widget<Gtk::Box>("header_bar", hdr);
            try {
                auto pb = Gdk::Pixbuf::create_from_file(
                        "../../resource/images/rti_logo.png");
                window->set_icon(pb);
#ifdef __APPLE__
                set_macos_dock_icon(pb);
#endif
                if (hdr) {
                    auto scaled =
                            pb->scale_simple(56, 56, Gdk::INTERP_BILINEAR);
                    auto *logo = Gtk::manage(new Gtk::Image(scaled));
                    logo->set_visible(true);
                    logo->set_margin_end(8);
                    hdr->pack_start(*logo, false, false, 0);
                    hdr->reorder_child(*logo, 0);
                }
            } catch (...) {
            }
        }

        window->signal_delete_event().connect(
                sigc::mem_fun(*this, &SurgicalArmController::on_window_close));

        builder->get_widget<Gtk::ToggleButton>(
                "base_play",
                motor_play_btns[SurgicalRobot::Motors::BASE]);
        builder->get_widget<Gtk::ToggleButton>(
                "shoulder_play",
                motor_play_btns[SurgicalRobot::Motors::SHOULDER]);
        builder->get_widget<Gtk::ToggleButton>(
                "elbow_play",
                motor_play_btns[SurgicalRobot::Motors::ELBOW]);
        builder->get_widget<Gtk::ToggleButton>(
                "wrist_play",
                motor_play_btns[SurgicalRobot::Motors::WRIST]);
        builder->get_widget<Gtk::ToggleButton>(
                "hand_play",
                motor_play_btns[SurgicalRobot::Motors::HAND]);

        builder->get_widget<Gtk::TextView>("console", console);

        // Force dark background on the text view (CSS alone is unreliable
        // for GtkTextView internals in GTK3)
        {
            Gdk::RGBA bg, fg;
            bg.set("#060F0A");
            fg.set("#00CC66");
            console->override_background_color(bg);
            console->override_color(fg);
            console->override_font(
                    Pango::FontDescription("Courier New Bold 20"));
        }

        connect_buttons(builder);

        app->add_window(*window);
        window->set_visible(true);

        log_alert("Started Arm Controller");
    }

    // Handle window close event
    bool on_window_close(GdkEventAny *event)
    {
        std::cout << "Arm Controller UI closed, shutting down" << std::endl;
        current_status.status = Common::DeviceStatuses::OFF;
        return false;
    }

    // Close the window from within the GLib main loop (e.g. on SIGINT).
    void window_close_from_signal()
    {
        if (window)
            window->close();
        else if (app)
            app->quit();
    }

    // Connect buttons to their respective signal handlers.
    // INC/DEC buttons:
    //   - On press: deactivate AUTO for that joint, send one command
    //   immediately,
    //     then repeat at 20 Hz (every 50 ms) while held.
    //   - On release: stop repeating.
    //   - AUTO / PLAY ALL can re-enable automatic mode.
    void connect_buttons(const Glib::RefPtr<Gtk::Builder> &builder)
    {
        auto connect_inc_dec = [this, &builder](const std::string &btn_name,
                                                SurgicalRobot::Motors motor,
                                                SurgicalRobot::MotorDirections
                                                        direction) {
            Gtk::Button *button = nullptr;
            builder->get_widget<Gtk::Button>(btn_name, button);
            if (!button)
                return;

            button->signal_button_press_event().connect(
                    [this, motor, direction, btn_name](
                            GdkEventButton *ev) -> bool {
                        if (ev->button == 1) {
                            // Deactivate AUTO for this joint
                            motor_play_btns[motor]->set_active(false);
                            // Send one command right away
                            write_command(motor, direction);
                            // Start 20 Hz repeat timer
                            inc_dec_timers[btn_name] =
                                    Glib::signal_timeout().connect(
                                            [this, motor, direction]() -> bool {
                                                write_command(motor, direction);
                                                return true;
                                            },
                                            50);
                        }
                        return false;
                    },
                    false);

            button->signal_button_release_event().connect(
                    [this, btn_name](GdkEventButton *ev) -> bool {
                        if (ev->button == 1) {
                            auto it = inc_dec_timers.find(btn_name);
                            if (it != inc_dec_timers.end()) {
                                it->second.disconnect();
                                inc_dec_timers.erase(it);
                            }
                        }
                        return false;
                    },
                    false);
        };

        connect_inc_dec("base_inc",
                        SurgicalRobot::Motors::BASE,
                        SurgicalRobot::MotorDirections::INCREMENT);
        connect_inc_dec("base_dec",
                        SurgicalRobot::Motors::BASE,
                        SurgicalRobot::MotorDirections::DECREMENT);
        connect_inc_dec("shoulder_inc",
                        SurgicalRobot::Motors::SHOULDER,
                        SurgicalRobot::MotorDirections::INCREMENT);
        connect_inc_dec("shoulder_dec",
                        SurgicalRobot::Motors::SHOULDER,
                        SurgicalRobot::MotorDirections::DECREMENT);
        connect_inc_dec("elbow_inc",
                        SurgicalRobot::Motors::ELBOW,
                        SurgicalRobot::MotorDirections::INCREMENT);
        connect_inc_dec("elbow_dec",
                        SurgicalRobot::Motors::ELBOW,
                        SurgicalRobot::MotorDirections::DECREMENT);
        connect_inc_dec("wrist_inc",
                        SurgicalRobot::Motors::WRIST,
                        SurgicalRobot::MotorDirections::INCREMENT);
        connect_inc_dec("wrist_dec",
                        SurgicalRobot::Motors::WRIST,
                        SurgicalRobot::MotorDirections::DECREMENT);
        connect_inc_dec("hand_inc",
                        SurgicalRobot::Motors::HAND,
                        SurgicalRobot::MotorDirections::INCREMENT);
        connect_inc_dec("hand_dec",
                        SurgicalRobot::Motors::HAND,
                        SurgicalRobot::MotorDirections::DECREMENT);

        Gtk::Button *playall = nullptr;
        builder->get_widget<Gtk::Button>("playall", playall);
        if (playall) {
            playall->signal_clicked().connect([this]() { set_all(true); });
        }

        Gtk::Button *stopall = nullptr;
        builder->get_widget<Gtk::Button>("stopall", stopall);
        if (stopall) {
            stopall->signal_clicked().connect([this]() { set_all(false); });
        }
    }

    // Print message to the alerts console in the UI
    void log_alert(const std::string &msg)
    {
        Glib::RefPtr<Gtk::TextBuffer> buffer = console->get_buffer();
        Gtk::TextBuffer::iterator iter = buffer->end();

        std::time_t now = std::time(nullptr);
        std::tm *local_time = std::localtime(&now);
        char time_str[100];
        std::strftime(time_str,
                      sizeof(time_str),
                      "%Y-%m-%d %H:%M:%S",
                      local_time);

        std::stringstream ss;
        ss << "\n" << time_str << " - " << msg;
        buffer->insert(iter, ss.str());
    }
};

// ---------------------------------------------------------------------------
// Web mode (--web): headless equivalent of SurgicalArmController that serves
// a browser-based UI (static assets + JSON polling API) via an embedded HTTP
// server instead of a GTK window.
// ---------------------------------------------------------------------------

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
    bool web_mode = false;
    int web_port = 8091;
    for (int i = 1; i < argc; ++i) {
        std::string arg(argv[i]);
        if (arg == "--web") {
            web_mode = true;
        } else if (arg == "--port" && i + 1 < argc) {
            web_port = std::atoi(argv[++i]);
        }
    }

    if (web_mode) {
        ArmControllerWebApp app(web_port);
        app.run();
        return 0;
    }

    SurgicalArmController arm_controller;
    arm_controller.run(argc, argv);
    return 0;
}
