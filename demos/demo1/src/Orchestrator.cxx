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

#include "Types.hpp"
#include "DdsUtils.hpp"

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

        if (stat_map.at(sample.device())->get_text() != "DeviceStatuses::OFF") {
            std::stringstream ss;
            ss << sample.device()
               << " is no longer sending heartbeats. Updating Status to OFF.";
            log_alert(ss.str());
            stat_map.at(sample.device())->set_text("DeviceStatuses::OFF");
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
        // Register types
        DdsUtils::register_type<Orchestrator::DeviceCommand>();
        DdsUtils::register_type<Common::DeviceStatus>();
        DdsUtils::register_type<Common::DeviceHeartbeat>();

        // Create DomainParticipant
        rti::domain::DomainParticipantConfigParams params;
        auto default_provider = dds::core::QosProvider::Default();
        participant =
                default_provider.extensions().create_participant_from_config(
                        DdsUtils::orchestrator_dp_fqn,
                        params);

        // Create DataWriters and DataReaders
        command_writer = rti::pub::find_datawriter_by_name<
                dds::pub::DataWriter<Orchestrator::DeviceCommand>>(
                participant,
                DdsUtils::device_command_dw_fqn);
        status_reader = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Common::DeviceStatus>>(
                participant,
                DdsUtils::status_dr_fqn);
        hb_reader = rti::sub::find_datareader_by_name<
                dds::sub::DataReader<Common::DeviceHeartbeat>>(
                participant,
                DdsUtils::hb_dr_fqn);

        hb_listener = std::make_shared<HeartbeatListener>(
                stat_map,
                [this](std::string msg) { log_alert(msg); });
        hb_reader.set_listener(hb_listener);

        status_read_condition = dds::sub::cond::ReadCondition(
                status_reader,
                dds::sub::status::DataState::any(),
                [this]() { process_status(); });

        waitset_status += status_read_condition;

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

    // Connext entities
    dds::domain::DomainParticipant participant = dds::core::null;
    dds::pub::DataWriter<Orchestrator::DeviceCommand> command_writer =
            dds::core::null;
    dds::sub::DataReader<Common::DeviceStatus> status_reader = dds::core::null;
    dds::sub::DataReader<Common::DeviceHeartbeat> hb_reader = dds::core::null;
    dds::sub::cond::ReadCondition status_read_condition = dds::core::null;
    rti::core::cond::AsyncWaitSet waitset_status;
    std::shared_ptr<HeartbeatListener> hb_listener;

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

    void process_status()
    {
        dds::sub::LoanedSamples<Common::DeviceStatus> samples =
                status_reader.take();

        for (const auto &sample : samples) {
            if (sample.info().valid()) {
                // update the label
                std::stringstream ss_label;
                ss_label << sample.data().status();
                stat_map.at(sample.data().device())->set_text(ss_label.str());

                // print alert
                std::stringstream ss_log;
                ss_log << "Received " << sample.data().status()
                       << " status message from " << sample.data().device();
                log_alert(ss_log.str());
            }
        }
    }

    void ui_setup()
    {
        auto builder = Gtk::Builder::create_from_file("ui/orchestrator.glade");
        builder->get_widget<Gtk::Window>("window", window);

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
