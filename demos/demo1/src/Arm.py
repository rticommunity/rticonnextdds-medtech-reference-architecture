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

# UI imports
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from matplotlib.backends.backend_gtk3agg import (
    FigureCanvasGTK3Agg as FigureCanvas,
)
import matplotlib.pyplot as plt
import numpy as np

# Connext imports
import rti.connextdds as dds
import time, threading
from Types import Common, SurgicalRobot, Orchestrator
import DdsUtils

class ArmApp:
    def __init__(self):
        # Initialize dictionaries to track angles & update labels
        self.angles = {
            SurgicalRobot.Motors.BASE: 180.0,
            SurgicalRobot.Motors.SHOULDER: 180.0,
            SurgicalRobot.Motors.ELBOW: 180.0,
            SurgicalRobot.Motors.WRIST: 180.0,
            SurgicalRobot.Motors.HAND: 180.0,
        }
        self.labels = {
            SurgicalRobot.Motors.BASE: [None, None],
            SurgicalRobot.Motors.SHOULDER: [None, None],
            SurgicalRobot.Motors.ELBOW: [None, None],
            SurgicalRobot.Motors.WRIST: [None, None],
            SurgicalRobot.Motors.HAND: [None, None],
        }

        # Initialize historical data for graphing
        self.graph_angles = {
            SurgicalRobot.Motors.BASE: [180.0],
            SurgicalRobot.Motors.SHOULDER: [180.0],
            SurgicalRobot.Motors.ELBOW: [180.0],
            SurgicalRobot.Motors.WRIST: [180.0],
            SurgicalRobot.Motors.HAND: [180.0],
        }
        self.lines = {
            SurgicalRobot.Motors.BASE: None,
            SurgicalRobot.Motors.SHOULDER: None,
            SurgicalRobot.Motors.ELBOW: None,
            SurgicalRobot.Motors.WRIST: None,
            SurgicalRobot.Motors.HAND: None,
        }

        self.fig = None
        self.ax = None
        self.arm_status = None

    def write_hb(self, hb_writer):
        while self.arm_status.status != Common.DeviceStatuses.OFF:
            hb = Common.DeviceHeartbeat()
            hb.device = Common.DeviceType.ARM
            hb_writer.write(hb)
            time.sleep(0.05)

    def update_graphs(self):
        while self.arm_status.status != Common.DeviceStatuses.OFF:
            time.sleep(0.5)
            for motor in self.angles:
                self.graph_angles[motor].append(self.angles[motor])
                count = len(self.graph_angles[motor])
                if count < 20:
                    self.lines[motor][0].set_data(
                        np.arange(count), self.graph_angles[motor]
                    )
                else:
                    self.lines[motor][0].set_data(
                        np.arange(count - 20, count),
                        self.graph_angles[motor][-20:],
                    )
            self.ax.relim()
            self.ax.autoscale_view()
            self.fig.canvas.draw()

    def motor_handler(self, motor_reader):
        while self.arm_status.status != Common.DeviceStatuses.OFF:
            time.sleep(1)
            samples = motor_reader.take_data()
            for sample in samples:
                if self.arm_status.status == Common.DeviceStatuses.ON:
                    if (
                        sample.direction
                        == SurgicalRobot.MotorDirections.INCREMENT
                    ):
                        self.angles[sample.id] = (
                            self.angles[sample.id] + 0.5
                        ) % 360.0
                        self.labels[sample.id][1].set_text("INCREMENT")
                    elif (
                        sample.direction
                        == SurgicalRobot.MotorDirections.DECREMENT
                    ):
                        self.angles[sample.id] = (
                            self.angles[sample.id] - 0.5
                        ) % 360.0
                        self.labels[sample.id][1].set_text("DECREMENT")
                # update labels
                self.labels[sample.id][0].set_text(str(self.angles[sample.id]))

    def ui_setup(self):
        # graph setup
        self.fig, self.ax = plt.subplots()
        # Plot each line with a different color
        self.lines[SurgicalRobot.Motors.BASE] = self.ax.plot(
            self.graph_angles[SurgicalRobot.Motors.BASE],
            label="Base",
            color="blue",
        )
        self.lines[SurgicalRobot.Motors.SHOULDER] = self.ax.plot(
            self.graph_angles[SurgicalRobot.Motors.SHOULDER],
            label="Shoulder",
            color="green",
        )
        self.lines[SurgicalRobot.Motors.ELBOW] = self.ax.plot(
            self.graph_angles[SurgicalRobot.Motors.ELBOW],
            label="Elbow",
            color="red",
        )
        self.lines[SurgicalRobot.Motors.WRIST] = self.ax.plot(
            self.graph_angles[SurgicalRobot.Motors.WRIST],
            label="Wrist",
            color="purple",
        )
        self.lines[SurgicalRobot.Motors.HAND] = self.ax.plot(
            self.graph_angles[SurgicalRobot.Motors.HAND],
            label="Hand",
            color="orange",
        )
        # Add a legend
        self.ax.legend(loc = "upper right")
        # Add labels and title
        self.ax.set_xlabel("Samples")
        self.ax.set_ylabel("Angle (degrees)")
        self.ax.set_title("Arm Motor Angles")

        # UI
        builder = Gtk.Builder()
        builder.add_from_file("ui/arm.glade")

        # add labels to dictionary
        self.labels[SurgicalRobot.Motors.BASE][0] = builder.get_object(
            "base_angle"
        )
        self.labels[SurgicalRobot.Motors.BASE][1] = builder.get_object(
            "base_cmd"
        )
        self.labels[SurgicalRobot.Motors.SHOULDER][0] = builder.get_object(
            "shoulder_angle"
        )
        self.labels[SurgicalRobot.Motors.SHOULDER][1] = builder.get_object(
            "shoulder_cmd"
        )
        self.labels[SurgicalRobot.Motors.ELBOW][0] = builder.get_object(
            "elbow_angle"
        )
        self.labels[SurgicalRobot.Motors.ELBOW][1] = builder.get_object(
            "elbow_cmd"
        )
        self.labels[SurgicalRobot.Motors.WRIST][0] = builder.get_object(
            "wrist_angle"
        )
        self.labels[SurgicalRobot.Motors.WRIST][1] = builder.get_object(
            "wrist_cmd"
        )
        self.labels[SurgicalRobot.Motors.HAND][0] = builder.get_object(
            "hand_angle"
        )
        self.labels[SurgicalRobot.Motors.HAND][1] = builder.get_object(
            "hand_cmd"
        )

        # add graph
        graphbox = builder.get_object("graph")
        canvas = FigureCanvas(self.fig)  # a Gtk.DrawingArea
        canvas.set_size_request(800, 600)
        graphbox.add(canvas)
        window = builder.get_object("window")
        window.connect("destroy", self.on_window_destroy)
        window.show_all()

    def on_window_destroy(self, widget):
        print("Arm UI closed")
        Gtk.main_quit()  # This stops the GTK main loop

    def cmd_handler(self, _):
        samples = self.cmd_reader.take_data()
        for sample in samples:
            if sample.command == Orchestrator.DeviceCommands.START:
                print("Arm received Start Command, Turning on Arm")
                self.arm_status.status = Common.DeviceStatuses.ON
            elif sample.command == Orchestrator.DeviceCommands.PAUSE:
                print("Arm received Pause Command, Pausing Arm")
                self.arm_status.status = Common.DeviceStatuses.PAUSED
            else:
                print("Arm received Shutdown Command")
                self.arm_status.status = Common.DeviceStatuses.OFF
            self.status_writer.write(self.arm_status)

            if self.arm_status.status == Common.DeviceStatuses.OFF:
                Gtk.main_quit()

    def waitsets(self):
        while self.arm_status.status != Common.DeviceStatuses.OFF:
            self.cmd_waitset.dispatch(dds.Duration(1))

    def connext_setup(self):
        # Register DDS types
        DdsUtils.register_type(Common.DeviceStatus)
        DdsUtils.register_type(Common.DeviceHeartbeat)
        DdsUtils.register_type(Orchestrator.DeviceCommand)
        DdsUtils.register_type(SurgicalRobot.MotorControl)

        # Create QoS provider and participant
        qos_provider = dds.QosProvider.default
        participant = qos_provider.create_participant_from_config(DdsUtils.arm_dp_fqn)

        # Create DataWriters
        self.status_writer = dds.DataWriter(
            participant.find_datawriter(DdsUtils.status_dw_fqn)
        )
        self.hb_writer = dds.DataWriter(
            participant.find_datawriter(DdsUtils.device_hb_dw_fqn)
        )
        self.arm_status = Common.DeviceStatus(
            device=Common.DeviceType.ARM, status=Common.DeviceStatuses.ON
        )
        self.status_writer.write(self.arm_status)

        # Create DataReaders
        self.motor_control_reader = dds.DataReader(
            participant.find_datareader(DdsUtils.motor_control_dr_fqn)
        )
        self.cmd_reader = dds.DataReader(
            participant.find_datareader(DdsUtils.device_command_dr_fqn)
        )

        # Setup command handling and waitsets
        cmd_status_condition = dds.StatusCondition(self.cmd_reader)
        cmd_status_condition.enabled_statuses = dds.StatusMask.DATA_AVAILABLE
        cmd_status_condition.set_handler(self.cmd_handler)
        self.cmd_waitset = dds.WaitSet()
        self.cmd_waitset += cmd_status_condition

    def run(self):

        # Setup UI
        self.ui_setup()

        # setup Connext
        self.connext_setup()

        # Start threads
        hb_thread = threading.Thread(
            target=self.write_hb, args=[self.hb_writer]
        )
        graphs_thread = threading.Thread(target=self.update_graphs)
        sub_thread = threading.Thread(target=self.waitsets)
        motor_thread = threading.Thread(
            target=self.motor_handler, args=[self.motor_control_reader]
        )

        hb_thread.start()
        graphs_thread.start()
        sub_thread.start()
        motor_thread.start()

        print("Started Arm")

        Gtk.main()

        print("Shutting down Arm")

        # Set status to off and rejoin all threads
        self.arm_status.status = Common.DeviceStatuses.OFF
        hb_thread.join()
        graphs_thread.join()
        sub_thread.join()
        motor_thread.join()


if __name__ == "__main__":
    arm = ArmApp()
    arm.run()
