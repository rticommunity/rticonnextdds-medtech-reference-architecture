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
#include <mutex>
#include <gtkmm.h>
#include <gdkmm/screen.h>

#include "Types.hpp"

using namespace DdsEntities::Constants;
// #include "SecureLogUtils.hpp"

// Heartbeat listener to automatically monitor other applications
class HeartbeatListener
        : public dds::sub::NoOpDataReaderListener<Common::DeviceHeartbeat> {
public:
    HeartbeatListener(
            std::map<Common::DeviceType, Gtk::Label *> &statMap,
            std::function<void(std::string)> logAlert)
            : stat_map(statMap), log_alert(logAlert)
    {
    }

    void on_requested_deadline_missed(
            dds::sub::DataReader<Common::DeviceHeartbeat> &reader,
            const dds::core::status::RequestedDeadlineMissedStatus &status)
            override
    {
        Common::DeviceHeartbeat sample;
        reader.key_value(sample, status.last_instance_handle());

        Gtk::Label *lbl = stat_map.at(sample.device());
        if (lbl->get_text() != "DeviceStatuses::OFF") {
            std::stringstream ss;
            ss << sample.device()
               << " is no longer sending heartbeats. Updating Status to OFF.";
            log_alert(ss.str());
            Glib::signal_idle().connect([lbl]() -> bool {
                lbl->set_text("DeviceStatuses::OFF");
                auto ctx = lbl->get_style_context();
                ctx->remove_class("status-on");
                ctx->remove_class("status-paused");
                ctx->add_class("status-off");
                return false;
            });
        }
    }

private:
    std::map<Common::DeviceType, Gtk::Label *> &stat_map;
    std::function<void(std::string)> log_alert;
};

// Main application class
class OrchestratorApp {
public:
    OrchestratorApp(int argc, char const *argv[]) : running(true)
    {
        // We need to register the types before we start creating DDS entities
        rti::domain::register_type<Orchestrator::DeviceCommand>();
        rti::domain::register_type<Common::DeviceStatus>();
        rti::domain::register_type<Common::DeviceHeartbeat>();

        // Connext will load XML files through the default provider from the
        // NDDS_QOS_PROFILES environment variable
        auto default_provider = dds::core::QosProvider::Default();

        participant =
                default_provider.extensions().create_participant_from_config(
                        ORCHESTRATOR_DP);

        // Initialize DataWriter
        command_writer = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Orchestrator::DeviceCommand>>(
                participant,
                DEVICE_COMMAND_DW);

        // Initialize DataReaders
        status_reader = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Common::DeviceStatus>>(
                participant,
                STATUS_DR);
        hb_reader = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Common::DeviceHeartbeat>>(
                participant,
                HB_DR);

        hb_listener = std::make_shared<HeartbeatListener>(
                stat_map,
                [this](std::string msg) { log_alert(msg); });
        hb_reader.set_listener(hb_listener);

        status_read_condition = dds::sub::cond::ReadCondition(
                status_reader,
                dds::sub::status::DataState::any(),
                [this]() { process_status(); });

        waitset_status += status_read_condition;

        // if (SecureLogUtils::is_secure(participant)) {
        //     securelog_reader = SecureLogUtils::setup_secure_log_reader(
        //         std::bind(&OrchestratorApp::process_secure_log, this, std::placeholders::_1),
        //         default_provider
        //     );
        // }

        app = Gtk::Application::create("orchestrator.orchestrator");
        app->signal_activate().connect([this]() { ui_setup(); });
    }

    void run()
    {
        app->run();
    }

private:
    // Member variables

    bool running;
    // UI
    Gtk::Window *window;
    Glib::RefPtr<Gtk::Application> app;
    std::map<Common::DeviceType, Gtk::Label *> stat_map;
    std::map<Common::DeviceType, Gtk::RadioButton *> device_map;
    Gtk::ScrolledWindow *scroll;
    Glib::RefPtr<Gtk::TextBuffer> buffer;
    // Gtk::Label *security_indicator = nullptr;
    // sigc::connection security_flash_connection;
    // bool security_flash_on = false;
    // int security_flash_ticks_remaining = 0;

    // Connext entities
    dds::domain::DomainParticipant participant = dds::core::null;
    dds::pub::DataWriter<Orchestrator::DeviceCommand> command_writer =
            dds::core::null;
    dds::sub::DataReader<Common::DeviceStatus> status_reader = dds::core::null;
    dds::sub::DataReader<Common::DeviceHeartbeat> hb_reader = dds::core::null;
    dds::sub::cond::ReadCondition status_read_condition = dds::core::null;
    rti::core::cond::AsyncWaitSet waitset_status;
    std::shared_ptr<HeartbeatListener> hb_listener;

    // Connext secure logging entities
    // SecureLogUtils::SecureLogReader securelog_reader = {dds::core::null, dds::core::null};

    void log_alert(std::string msg)
    {
        Glib::signal_idle().connect([this, msg]() -> bool {
            Gtk::TextBuffer::iterator iter = buffer->end();

            // timestamp
            std::time_t now = std::time(nullptr);
            std::tm *local_time = std::localtime(&now);
            char time_str[100];
            std::strftime(
                    time_str,
                    sizeof(time_str),
                    "%Y-%m-%d %H:%M:%S",
                    local_time);

            // write to buffer
            std::stringstream ss;
            ss << "\n" << time_str << " - " << msg;
            buffer->insert(iter, ss.str());

            // scroll window down
            auto v_adjustment = scroll->get_vadjustment();
            v_adjustment->set_value(
                    v_adjustment->get_upper() - v_adjustment->get_page_size());

            return false;
        });
    }

    void btn_handler(Orchestrator::DeviceCommands cmd)
    {
        Common::DeviceType device;

        for (auto const &btn : device_map) {
            if (btn.second->get_active()) {
                device = btn.first;
                break;
            }
        }

        std::stringstream ss;
        ss << "Writing " << cmd << " to " << device;
        log_alert(ss.str());

        Orchestrator::DeviceCommand command(device, cmd);
        command_writer.write(command);
    }

    // void set_security_indicator_ok()
    // {
    //     if (security_indicator == nullptr) {
    //         return;
    //     }

    //     auto ctx = security_indicator->get_style_context();
    //     ctx->remove_class("security-threat-on");
    //     ctx->remove_class("security-threat-off");
    //     ctx->add_class("security-ok");
    //     security_indicator->set_text("SECURITY: OK");
    // }

    // void trigger_security_flash()
    // {
    //     Glib::signal_idle().connect([this]() -> bool {
    //         if (security_indicator == nullptr) {
    //             return false;
    //         }

    //         // Keep flashing for ~8s after the latest threat event.
    //         security_flash_ticks_remaining = 16;

    //         if (security_flash_connection.connected()) {
    //             return false;
    //         }

    //         security_flash_on = false;
    //         security_flash_connection = Glib::signal_timeout().connect(
    //                 [this]() -> bool {
    //                     if (security_indicator == nullptr) {
    //                         return false;
    //                     }

    //                     auto ctx = security_indicator->get_style_context();
    //                     ctx->remove_class("security-ok");
    //                     ctx->remove_class("security-threat-on");
    //                     ctx->remove_class("security-threat-off");

    //                     security_flash_on = !security_flash_on;
    //                     if (security_flash_on) {
    //                         security_indicator->set_text("SECURITY THREAT");
    //                         ctx->add_class("security-threat-on");
    //                     } else {
    //                         security_indicator->set_text("SECURITY THREAT");
    //                         ctx->add_class("security-threat-off");
    //                     }

    //                     --security_flash_ticks_remaining;
    //                     if (security_flash_ticks_remaining <= 0) {
    //                         set_security_indicator_ok();
    //                         security_flash_connection.disconnect();
    //                         return false;
    //                     }

    //                     return true;
    //                 },
    //                 500);

    //         return false;
    //     });
    // }

    // bool is_security_threat(const DDSSecurity::BuiltinLoggingTypeV2 &sample)
    // {
    //     return static_cast<int32_t>(sample.severity())
    //     // return sample.value<int32_t>("severity")
    //             <= static_cast<int32_t>(DDSSecurity::LoggingLevel::WARNING_LEVEL);
    // }

    // void process_secure_log(const SecureLogUtils::SecureLogType& log)
    // {
    //     if (is_security_threat(log)) {
    //         std::stringstream ss;
    //         ss << "SECURITY THREAT [" << log.appname() << "] " << log.message();
    //         log_alert(ss.str());
    //         trigger_security_flash();
    //     }
    // }

    void process_status()
    {
        dds::sub::LoanedSamples<Common::DeviceStatus> samples =
                status_reader.take();

        for (const auto &sample : samples) {
            if (sample.info().valid()) {
                // update the label
                std::stringstream ss_label;
                ss_label << sample.data().status();
                Gtk::Label *lbl = stat_map.at(sample.data().device());
                lbl->set_text(ss_label.str());
                apply_status_class(lbl, ss_label.str());

                // print alert
                std::stringstream ss_log;
                ss_log << "Received " << sample.data().status()
                       << " status message from " << sample.data().device();
                log_alert(ss_log.str());
            }
        }
    }

    // Switches status-on/status-paused/status-off CSS class on a label
    void apply_status_class(Gtk::Label *lbl, const std::string &status_str)
    {
        auto ctx = lbl->get_style_context();
        ctx->remove_class("status-on");
        ctx->remove_class("status-paused");
        ctx->remove_class("status-off");
        if (status_str.find("ON") != std::string::npos) {
            ctx->add_class("status-on");
        } else if (status_str.find("PAUSED") != std::string::npos) {
            ctx->add_class("status-paused");
        } else {
            ctx->add_class("status-off");
        }
    }

    void ui_setup()
    {
        // Load CSS stylesheet
        auto css_provider = Gtk::CssProvider::create();
        try {
            css_provider->load_from_path("ui/orchestrator.css");
        } catch (const Glib::Error &e) {
            std::cerr << "Warning: could not load orchestrator.css: " << e.what() << std::endl;
        }
        Gtk::StyleContext::add_provider_for_screen(
                Gdk::Screen::get_default(),
                css_provider,
                GTK_STYLE_PROVIDER_PRIORITY_USER);

        auto builder = Gtk::Builder::create_from_file("ui/orchestrator.glade");
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

                // security_indicator = Gtk::manage(new Gtk::Label(""));
                // {
                //     auto ctx = security_indicator->get_style_context();
                //     ctx->add_class("security-indicator");
                //     if (SecureLogUtils::is_secure(participant)) {
                //         ctx->add_class("security-ok");
                //         security_indicator->set_text("SECURITY: OK");
                //     } else {
                //         ctx->add_class("security-unsecure");
                //         security_indicator->set_text("UNSECURE MODE");
                //     }
                // }
                // security_indicator->set_margin_start(10);
                // security_indicator->set_margin_end(4);
                // security_indicator->set_visible(true);
                // hdr->pack_end(*security_indicator, false, false, 0);
            }
        }

        window->signal_delete_event().connect([this](GdkEventAny *event) {
            std::cout << "Orchestrator UI closed" << std::endl;
            running = false;
            return false;
        });

        builder->get_widget<Gtk::Label>(
                "arm_label",
                stat_map[Common::DeviceType::ARM]);
        builder->get_widget<Gtk::Label>(
                "armctrl_label",
                stat_map[Common::DeviceType::ARM_CONTROLLER]);
        builder->get_widget<Gtk::Label>(
                "p_sensor_label",
                stat_map[Common::DeviceType::PATIENT_SENSOR]);
        builder->get_widget<Gtk::Label>(
                "p_monitor_label",
                stat_map[Common::DeviceType::PATIENT_MONITOR]);

        builder->get_widget<Gtk::RadioButton>(
                "arm",
                device_map[Common::DeviceType::ARM]);
        builder->get_widget<Gtk::RadioButton>(
                "armctrl",
                device_map[Common::DeviceType::ARM_CONTROLLER]);
        builder->get_widget<Gtk::RadioButton>(
                "p_sensor",
                device_map[Common::DeviceType::PATIENT_SENSOR]);
        builder->get_widget<Gtk::RadioButton>(
                "p_monitor",
                device_map[Common::DeviceType::PATIENT_MONITOR]);

        Gtk::TextView *console;
        builder->get_widget<Gtk::TextView>("console", console);
        buffer = console->get_buffer();

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

        builder->get_widget<Gtk::ScrolledWindow>("scroll", scroll);

        Gtk::Button *start;
        Orchestrator::DeviceCommands startmsg =
                Orchestrator::DeviceCommands::START;
        builder->get_widget<Gtk::Button>("start", start);
        start->signal_clicked().connect(
                [this, startmsg]() { btn_handler(startmsg); });

        Gtk::Button *pause;
        Orchestrator::DeviceCommands pausemsg =
                Orchestrator::DeviceCommands::PAUSE;
        builder->get_widget<Gtk::Button>("pause", pause);
        pause->signal_clicked().connect(
                [this, pausemsg]() { btn_handler(pausemsg); });

        Gtk::Button *off;
        Orchestrator::DeviceCommands offmsg =
                Orchestrator::DeviceCommands::SHUTDOWN;
        builder->get_widget<Gtk::Button>("off", off);
        off->signal_clicked().connect(
                [this, offmsg]() { btn_handler(offmsg); });

        app->add_window(*window);
        window->set_visible(true);
        log_alert("Started Orchestrator");

        waitset_status.start();
    }
};

int main(int argc, char const *argv[])
{
    OrchestratorApp app(argc, argv);
    app.run();
    return 0;
}
