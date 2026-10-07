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
#include <array>
#include <atomic>
#include <gtkmm.h>
#include <gdkmm/screen.h>

#include "Types.hpp"

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
    dds::pub::DataWriter<SurgicalRobot::TeleopControl> teleop_writer =
            dds::core::null;
    dds::sub::DataReader<Orchestrator::DeviceCommand> cmd_reader =
            dds::core::null;
    rti::core::cond::AsyncWaitSet waitset_command;

    Common::DeviceStatus current_status;
    std::atomic<bool> demo_motion_enabled { false };
    std::atomic<unsigned int> demo_generation { 0 };

    struct DemoPathSegment {
        SurgicalRobot::TeleopDirections x_direction;
        SurgicalRobot::TeleopDirections y_direction;
        unsigned int ticks;
    };

    struct DemoToolSegment {
        SurgicalRobot::TeleopAxes axis;
        SurgicalRobot::TeleopDirections direction;
        unsigned int ticks;
    };

    static constexpr std::array<DemoPathSegment, 8> demo_path = { {
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

    static constexpr std::array<DemoToolSegment, 4> demo_tool_sequence = { {
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

    // GTK UI entities
    Gtk::Window *window = nullptr;
    Glib::RefPtr<Gtk::Application> app;
    std::map<std::string, sigc::connection> teleop_timers;
    Gtk::TextView *console = nullptr;

    // Initialize Connext participants, readers, and writers
    void initialize_connext()
    {
        // We need to register the types before we start creating DDS entities
        rti::domain::register_type<Orchestrator::DeviceCommand>();
        rti::domain::register_type<Common::DeviceStatus>();
        rti::domain::register_type<SurgicalRobot::MotorControl>();
        rti::domain::register_type<SurgicalRobot::TeleopControl>();
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
        teleop_writer = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<SurgicalRobot::TeleopControl>>(
                participant,
                std::string(TELEOP_CONTROL_DW));

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

    void write_teleop(SurgicalRobot::TeleopAxes axis,
                      SurgicalRobot::TeleopDirections direction)
    {
        if (current_status.status == Common::DeviceStatuses::ON) {
            if (direction != SurgicalRobot::TeleopDirections::STOPPED) {
                demo_motion_enabled.store(false);
            }
            publish_teleop(axis, direction);
        }
    }

    void publish_teleop(SurgicalRobot::TeleopAxes axis,
                        SurgicalRobot::TeleopDirections direction)
    {
        if (current_status.status == Common::DeviceStatuses::ON) {
            teleop_writer.write(SurgicalRobot::TeleopControl(axis, direction));
        }
    }

    void stop_teleop_jogs()
    {
        for (auto &timer : teleop_timers) {
            timer.second.disconnect();
        }
        teleop_timers.clear();
    }

    // Run a repeatable, slow planar sweep followed by wrist and gripper motion.
    void playing()
    {
        std::size_t path_index = 0;
        std::size_t tool_index = 0;
        unsigned int segment_tick = 0;
        bool tool_sequence = false;
        unsigned int observed_generation = demo_generation.load();
        bool was_running = false;

        while (current_status.status != Common::DeviceStatuses::OFF) {
            const bool running = demo_motion_enabled.load()
                    && current_status.status == Common::DeviceStatuses::ON;
            const unsigned int generation = demo_generation.load();

            if (!running) {
                was_running = false;
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                continue;
            }

            if (!was_running || generation != observed_generation) {
                path_index = 0;
                tool_index = 0;
                segment_tick = 0;
                tool_sequence = false;
                observed_generation = generation;
                was_running = true;
            }

            if (!tool_sequence) {
                const DemoPathSegment &segment = demo_path[path_index];
                if (segment.x_direction
                    != SurgicalRobot::TeleopDirections::STOPPED) {
                    publish_teleop(SurgicalRobot::TeleopAxes::X,
                                   segment.x_direction);
                }
                if (segment.y_direction
                    != SurgicalRobot::TeleopDirections::STOPPED) {
                    publish_teleop(SurgicalRobot::TeleopAxes::Y,
                                   segment.y_direction);
                }
                if (++segment_tick >= segment.ticks) {
                    segment_tick = 0;
                    if (++path_index >= demo_path.size()) {
                        path_index = 0;
                        tool_sequence = true;
                    }
                }
            } else {
                const DemoToolSegment &segment = demo_tool_sequence[tool_index];
                publish_teleop(segment.axis, segment.direction);
                if (++segment_tick >= segment.ticks) {
                    segment_tick = 0;
                    if (++tool_index >= demo_tool_sequence.size()) {
                        tool_index = 0;
                        tool_sequence = false;
                    }
                }
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(100));
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
                    demo_motion_enabled.store(false);
                    Glib::signal_idle().connect([this]() -> bool {
                        stop_teleop_jogs();
                        return false;
                    });
                    log_alert("Received PAUSE Command from Orchestrator");
                    current_status.status = Common::DeviceStatuses::PAUSED;
                } else if (sample.data().command
                           == Orchestrator::DeviceCommands::START) {
                    log_alert("Received START Command from Orchestrator");
                    current_status.status = Common::DeviceStatuses::ON;
                } else {  // shutdown
                    demo_motion_enabled.store(false);
                    Glib::signal_idle().connect([this]() -> bool {
                        stop_teleop_jogs();
                        return false;
                    });
                    log_alert("Received SHUTDOWN Command from Orchestrator");
                    std::cout << "Arm Controller shutting down" << std::endl;
                    current_status.status = Common::DeviceStatuses::OFF;
                    app->quit();
                }
            }
        }

        write_status();
    }

    // Start or stop the repeatable demo trajectory.
    void set_demo_motion(bool run_demo)
    {
        stop_teleop_jogs();
        if (run_demo) {
            demo_generation.fetch_add(1);
        }
        demo_motion_enabled.store(run_demo);
        if (run_demo)
            log_alert("Started smooth demo motion");
        else
            log_alert("Stopped demo motion");
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
                    Pango::FontDescription("DejaVu Sans Mono 10"));
        }

        Gtk::Button *run_demo = nullptr;
        builder->get_widget<Gtk::Button>("run_demo", run_demo);
        if (run_demo) {
            run_demo->signal_clicked().connect(
                    [this]() { set_demo_motion(true); });
        }

        Gtk::Button *stop_motion = nullptr;
        builder->get_widget<Gtk::Button>("stop_motion", stop_motion);
        if (stop_motion) {
            stop_motion->signal_clicked().connect(
                    [this]() { set_demo_motion(false); });
        }

        connect_teleop_buttons(builder);

        app->add_window(*window);
        window->set_visible(true);

        log_alert("Started Arm Controller");
    }

    // Handle window close event
    bool on_window_close(GdkEventAny *event)
    {
        std::cout << "Arm Controller UI closed, shutting down" << std::endl;
        current_status.status = Common::DeviceStatuses::OFF;
        demo_motion_enabled.store(false);
        stop_teleop_jogs();
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

    void connect_teleop_buttons(const Glib::RefPtr<Gtk::Builder> &builder)
    {
        auto connect_jog = [this, &builder](
                                   const std::string &button_name,
                                   SurgicalRobot::TeleopAxes axis,
                                   SurgicalRobot::TeleopDirections direction) {
            Gtk::Button *button = nullptr;
            builder->get_widget<Gtk::Button>(button_name, button);
            if (!button)
                return;

            button->signal_button_press_event().connect(
                    [this, axis, direction, button_name](
                            GdkEventButton *event) -> bool {
                        if (event->button == 1) {
                            auto previous = teleop_timers.find(button_name);
                            if (previous != teleop_timers.end()) {
                                previous->second.disconnect();
                                teleop_timers.erase(previous);
                            }
                            write_teleop(axis, direction);
                            teleop_timers[button_name] =
                                    Glib::signal_timeout().connect(
                                            [this, axis, direction]() -> bool {
                                                write_teleop(axis, direction);
                                                return true;
                                            },
                                            50);
                        }
                        return false;
                    },
                    false);

            button->signal_button_release_event().connect(
                    [this, axis, button_name](GdkEventButton *event) -> bool {
                        if (event->button == 1) {
                            auto timer = teleop_timers.find(button_name);
                            if (timer != teleop_timers.end()) {
                                timer->second.disconnect();
                                teleop_timers.erase(timer);
                            }
                            write_teleop(
                                    axis,
                                    SurgicalRobot::TeleopDirections::STOPPED);
                        }
                        return false;
                    },
                    false);
        };

        connect_jog("x_positive",
                    SurgicalRobot::TeleopAxes::X,
                    SurgicalRobot::TeleopDirections::POSITIVE);
        connect_jog("x_negative",
                    SurgicalRobot::TeleopAxes::X,
                    SurgicalRobot::TeleopDirections::NEGATIVE);
        connect_jog("y_positive",
                    SurgicalRobot::TeleopAxes::Y,
                    SurgicalRobot::TeleopDirections::POSITIVE);
        connect_jog("y_negative",
                    SurgicalRobot::TeleopAxes::Y,
                    SurgicalRobot::TeleopDirections::NEGATIVE);
        connect_jog("roll_left",
                    SurgicalRobot::TeleopAxes::ROLL,
                    SurgicalRobot::TeleopDirections::POSITIVE);
        connect_jog("roll_right",
                    SurgicalRobot::TeleopAxes::ROLL,
                    SurgicalRobot::TeleopDirections::NEGATIVE);
        connect_jog("gripper_open",
                    SurgicalRobot::TeleopAxes::GRIPPER,
                    SurgicalRobot::TeleopDirections::POSITIVE);
        connect_jog("gripper_close",
                    SurgicalRobot::TeleopAxes::GRIPPER,
                    SurgicalRobot::TeleopDirections::NEGATIVE);
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

int main(int argc, char const *argv[])
{
    SurgicalArmController arm_controller;
    arm_controller.run(argc, argv);
    return 0;
}
