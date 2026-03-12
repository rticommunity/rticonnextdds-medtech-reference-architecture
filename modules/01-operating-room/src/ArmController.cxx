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
#include <gtkmm.h>
#include <gdkmm/screen.h>

#include "Types.hpp"
#include "DdsUtils.hpp"

class SurgicalArmController {
public:
    SurgicalArmController()
            : current_status(
                      Common::DeviceType::ARM_CONTROLLER,
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
                        DdsUtils::arm_controller_dp_fqn);

        // Initialize DataWriters
        status_writer = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Common::DeviceStatus>>(
                participant,
                DdsUtils::status_dw_fqn);
        hb_writer = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Common::DeviceHeartbeat>>(
                participant,
                DdsUtils::hb_dw_fqn);
        arm_writer = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<SurgicalRobot::MotorControl>>(
                participant,
                DdsUtils::motor_control_dw_fqn);

        // Initialize DataReader
        cmd_reader = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Orchestrator::DeviceCommand>>(
                participant,
                DdsUtils::device_command_dr_fqn);

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
        while (current_status.status() != Common::DeviceStatuses::OFF) {
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
    void write_command(
            SurgicalRobot::Motors motor,
            SurgicalRobot::MotorDirections dir)
    {
        if (current_status.status() == Common::DeviceStatuses::ON) {
            SurgicalRobot::MotorControl sample(motor, dir);
            arm_writer.write(sample);
        }
    }

    // Publish random motor controls for the motors that have been marked as
    // playing
    void playing()
    {
        while (current_status.status() != Common::DeviceStatuses::OFF) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            for (const auto &btn : motor_play_btns) {
                if (btn.second->get_active()) {
                    write_command(
                            btn.first,
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
                if (sample.data().command()
                    == Orchestrator::DeviceCommands::PAUSE) {
                    log_alert("Received PAUSE Command from Orchestrator");
                    current_status.status(Common::DeviceStatuses::PAUSED);
                } else if (
                        sample.data().command()
                        == Orchestrator::DeviceCommands::START) {
                    log_alert("Received START Command from Orchestrator");
                    current_status.status(Common::DeviceStatuses::ON);
                } else {  // shutdown
                    log_alert("Received SHUTDOWN Command from Orchestrator");
                    std::cout << "Arm Controller shutting down" << std::endl;
                    current_status.status(Common::DeviceStatuses::OFF);
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
            std::cerr << "Warning: could not load armcontroller.css: " << e.what() << std::endl;
        }
        Gtk::StyleContext::add_provider_for_screen(
                Gdk::Screen::get_default(),
                css_provider,
                GTK_STYLE_PROVIDER_PRIORITY_USER);

        auto builder = Gtk::Builder::create_from_file("ui/armcontroller.glade");
        builder->get_widget<Gtk::Window>("window", window);

        // Load RTI logo into header
        {
            Gtk::Box *hdr = nullptr;
            builder->get_widget<Gtk::Box>("header_bar", hdr);
            if (hdr) {
                try {
                    auto pb = Gdk::Pixbuf::create_from_file("../../resource/images/rti_logo.ico");
                    auto scaled = pb->scale_simple(56, 56, Gdk::INTERP_BILINEAR);
                    auto *logo = Gtk::manage(new Gtk::Image(scaled));
                    logo->set_visible(true);
                    logo->set_margin_end(8);
                    hdr->pack_start(*logo, false, false, 0);
                    hdr->reorder_child(*logo, 0);
                } catch (...) {}
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
        current_status.status(Common::DeviceStatuses::OFF);
        return false;
    }

    // Connect buttons to their respective signal handlers.
    // INC/DEC buttons:
    //   - On press: deactivate AUTO for that joint, send one command immediately,
    //     then repeat at 20 Hz (every 50 ms) while held.
    //   - On release: stop repeating.
    //   - AUTO / PLAY ALL can re-enable automatic mode.
    void connect_buttons(const Glib::RefPtr<Gtk::Builder> &builder)
    {
        auto connect_inc_dec =
                [this, &builder](
                        const std::string &btn_name,
                        SurgicalRobot::Motors motor,
                        SurgicalRobot::MotorDirections direction) {
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
                                                    [this,
                                                     motor,
                                                     direction]() -> bool {
                                                        write_command(
                                                                motor,
                                                                direction);
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

        connect_inc_dec(
                "base_inc",
                SurgicalRobot::Motors::BASE,
                SurgicalRobot::MotorDirections::INCREMENT);
        connect_inc_dec(
                "base_dec",
                SurgicalRobot::Motors::BASE,
                SurgicalRobot::MotorDirections::DECREMENT);
        connect_inc_dec(
                "shoulder_inc",
                SurgicalRobot::Motors::SHOULDER,
                SurgicalRobot::MotorDirections::INCREMENT);
        connect_inc_dec(
                "shoulder_dec",
                SurgicalRobot::Motors::SHOULDER,
                SurgicalRobot::MotorDirections::DECREMENT);
        connect_inc_dec(
                "elbow_inc",
                SurgicalRobot::Motors::ELBOW,
                SurgicalRobot::MotorDirections::INCREMENT);
        connect_inc_dec(
                "elbow_dec",
                SurgicalRobot::Motors::ELBOW,
                SurgicalRobot::MotorDirections::DECREMENT);
        connect_inc_dec(
                "wrist_inc",
                SurgicalRobot::Motors::WRIST,
                SurgicalRobot::MotorDirections::INCREMENT);
        connect_inc_dec(
                "wrist_dec",
                SurgicalRobot::Motors::WRIST,
                SurgicalRobot::MotorDirections::DECREMENT);
        connect_inc_dec(
                "hand_inc",
                SurgicalRobot::Motors::HAND,
                SurgicalRobot::MotorDirections::INCREMENT);
        connect_inc_dec(
                "hand_dec",
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
        std::strftime(
                time_str,
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
