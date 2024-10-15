# 
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
# 
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

# UI
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
import numpy as np
from matplotlib.backends.backend_gtk3agg import (
    FigureCanvasGTK3Agg as FigureCanvas,
)
import matplotlib.pyplot as plt

# other imports
import rti.connextdds as dds
from Types import Common, PatientMonitor, Orchestrator
import DdsUtils
import time, threading


class PatientMonitorApp:
    def __init__(self):
        self.pm_status = None
        self.labels = [None, None, None, None]
        self.hrs = []
        self.spo2s = []
        self.etco2s = []
        self.nibp_ss = []
        self.nibp_ds = []
        self.fig = None
        self.ax = None
        self.lines = [None, None, None, None, None]
        self.status_writer = None
        self.hb_writer = None
        self.vitals_reader = None
        self.cmd_reader = None

    def write_hb(self):
        while self.pm_status.status != Common.DeviceStatuses.OFF:
            hb = Common.DeviceHeartbeat()
            hb.device = Common.DeviceType.PATIENT_MONITOR
            self.hb_writer.write(hb)
            time.sleep(0.05)

    def ui_setup(self):
        self.fig, self.ax = plt.subplots()
        self.lines[0] = self.ax.plot(self.hrs, label="Heart Rate", color="red")
        self.lines[1] = self.ax.plot(self.spo2s, label="SpO2", color="blue")
        self.lines[2] = self.ax.plot(self.etco2s, label="EtCO2", color="green")
        self.lines[3] = self.ax.plot(
            self.nibp_ss, label="NiBP - S", color="orange"
        )
        self.lines[4] = self.ax.plot(
            self.nibp_ds, label="NiBP - D", color="pink"
        )
        self.ax.legend(loc = "upper right")
        self.ax.set_xlabel("Samples")
        self.ax.set_ylabel("Value")
        self.ax.set_title("Patient Monitor Graph")

        builder = Gtk.Builder()
        builder.add_from_file("ui/patientmonitor.glade")

        self.labels[0] = builder.get_object("hr")
        self.labels[1] = builder.get_object("spo2")
        self.labels[2] = builder.get_object("etco2")
        self.labels[3] = builder.get_object("nibp")

        graphbox = builder.get_object("graph")
        canvas = FigureCanvas(self.fig)
        canvas.set_size_request(800, 600)
        graphbox.add(canvas)

        window = builder.get_object("window")
        window.connect("destroy", self.on_window_destroy)
        window.show_all()

    def on_window_destroy(self, widget):
        print("Patient Monitor UI closed")
        Gtk.main_quit()

    def vitals_handler(self, _):
        samples = self.vitals_reader.take_data()
        if self.pm_status.status == Common.DeviceStatuses.ON:
            for sample in samples:
                self.labels[0].set_text(str(sample.hr))
                self.labels[1].set_text(str(sample.spo2))
                self.labels[2].set_text(str(sample.etco2))
                self.labels[3].set_text(f"{sample.nibp_s} / {sample.nibp_d}")

                self.hrs.append(sample.hr)
                self.spo2s.append(sample.spo2)
                self.etco2s.append(sample.etco2)
                self.nibp_ss.append(sample.nibp_s)
                self.nibp_ds.append(sample.nibp_d)

                if len(self.hrs) < 20:
                    self.lines[0][0].set_data(
                        np.arange(len(self.hrs)), self.hrs
                    )
                    self.lines[1][0].set_data(
                        np.arange(len(self.spo2s)), self.spo2s
                    )
                    self.lines[2][0].set_data(
                        np.arange(len(self.etco2s)), self.etco2s
                    )
                    self.lines[3][0].set_data(
                        np.arange(len(self.nibp_ss)), self.nibp_ss
                    )
                    self.lines[4][0].set_data(
                        np.arange(len(self.nibp_ds)), self.nibp_ds
                    )
                else:
                    self.lines[0][0].set_data(
                        np.arange(len(self.hrs) - 20, len(self.hrs)),
                        self.hrs[-20:],
                    )
                    self.lines[1][0].set_data(
                        np.arange(len(self.spo2s) - 20, len(self.spo2s)),
                        self.spo2s[-20:],
                    )
                    self.lines[2][0].set_data(
                        np.arange(len(self.etco2s) - 20, len(self.etco2s)),
                        self.etco2s[-20:],
                    )
                    self.lines[3][0].set_data(
                        np.arange(len(self.nibp_ss) - 20, len(self.nibp_ss)),
                        self.nibp_ss[-20:],
                    )
                    self.lines[4][0].set_data(
                        np.arange(len(self.nibp_ds) - 20, len(self.nibp_ds)),
                        self.nibp_ds[-20:],
                    )

                self.ax.relim()
                self.ax.autoscale_view()
                self.fig.canvas.draw()

    def cmd_handler(self, _):
        samples = self.cmd_reader.take_data()
        for sample in samples:
            if sample.command == Orchestrator.DeviceCommands.START:
                print(
                    "Patient Monitor received Start command, Turning on Patient Monitor"
                )
                self.pm_status.status = Common.DeviceStatuses.ON
            elif sample.command == Orchestrator.DeviceCommands.PAUSE:
                print(
                    "Patient Monitor received Pause Command, Pausing Patient Monitor"
                )
                self.pm_status.status = Common.DeviceStatuses.PAUSED
            else:
                print("Patient Monitor received Shutdown Command")
                self.pm_status.status = Common.DeviceStatuses.OFF
            self.status_writer.write(self.pm_status)

            if self.pm_status.status == Common.DeviceStatuses.OFF:
                Gtk.main_quit()

    def waitsets(self):
        vitals_status_condition = dds.StatusCondition(self.vitals_reader)
        vitals_status_condition.enabled_statuses = (
            dds.StatusMask.DATA_AVAILABLE
        )
        vitals_status_condition.set_handler(self.vitals_handler)
        vitals_waitset = dds.WaitSet()
        vitals_waitset += vitals_status_condition

        cmd_status_condition = dds.StatusCondition(self.cmd_reader)
        cmd_status_condition.enabled_statuses = dds.StatusMask.DATA_AVAILABLE
        cmd_status_condition.set_handler(self.cmd_handler)
        cmd_waitset = dds.WaitSet()
        cmd_waitset += cmd_status_condition

        while self.pm_status.status != Common.DeviceStatuses.OFF:
            vitals_waitset.dispatch(dds.Duration(1))
            cmd_waitset.dispatch(dds.Duration(1))

    def connext_setup(self):
        # Register DDS types, using a function from DdsUtils.py
        DdsUtils.register_type(Common.DeviceStatus)
        DdsUtils.register_type(Common.DeviceHeartbeat)
        DdsUtils.register_type(Orchestrator.DeviceCommand)
        DdsUtils.register_type(PatientMonitor.Vitals)

        # Connext will load XML files through the default provider from the
        # NDDS_QOS_PROFILES environment variable
        qos_provider = dds.QosProvider.default

        participant = qos_provider.create_participant_from_config(
            DdsUtils.patient_monitor_dp_fqn
        )

        # Initialize DataWriters
        self.status_writer = dds.DataWriter(
            participant.find_datawriter(DdsUtils.status_dw_fqn)
        )
        self.hb_writer = dds.DataWriter(
            participant.find_datawriter(DdsUtils.device_hb_dw_fqn)
        )

        # Initialize DataReaders
        self.vitals_reader = dds.DataReader(
            participant.find_datareader(DdsUtils.vitals_dr_fqn)
        )
        self.cmd_reader = dds.DataReader(
            participant.find_datareader(DdsUtils.device_command_dr_fqn)
        )

        self.pm_status = Common.DeviceStatus(
            device=Common.DeviceType.PATIENT_MONITOR,
            status=Common.DeviceStatuses.ON,
        )
        self.status_writer.write(self.pm_status)

    def run(self):
        self.ui_setup()
        self.connext_setup()

        hb_thread = threading.Thread(target=self.write_hb)
        sub_thread = threading.Thread(target=self.waitsets)
        hb_thread.start()
        sub_thread.start()

        print("Started Patient Monitor")

        Gtk.main()

        print("Shutting down Patient Monitor")
        self.pm_status.status = Common.DeviceStatuses.OFF
        hb_thread.join()
        sub_thread.join()


if __name__ == "__main__":
    monitor = PatientMonitorApp()
    monitor.run()
