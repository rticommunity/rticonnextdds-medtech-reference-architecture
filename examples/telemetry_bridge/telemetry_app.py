# 
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
# 
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

# Simple bridge application to publish telemetry data to the MedTech Reference Architecture from the MotorControl topic
import sys

import time, threading, random
import rti.connextdds as dds
import DdsUtils
from Types import Common, SurgicalRobot, Orchestrator
import rti.idl as idl


@idl.struct(
    type_annotations = [idl.type_name("SurgicalRobot::MotorTelemetry")],

    member_annotations = {
        'id': [idl.key, idl.default(0),],
    }
)
class SurgicalRobot_MotorTelemetry:
    id: SurgicalRobot.Motors = SurgicalRobot.Motors.BASE
    position_deg: idl.float32 = 0.0
    speed_rpm: idl.float32 = 0.0
    current_mA: idl.float32 = 0.0
    voltage_V: idl.float32 = 0.0
    temp_c: idl.float32 = 0.0

SurgicalRobot.MotorTelemetry = SurgicalRobot_MotorTelemetry

class DigitalTwinApp:
    def __init__(self):
        self.angles = {SurgicalRobot.Motors.BASE : 180.0, 
          SurgicalRobot.Motors.SHOULDER : 180.0, 
          SurgicalRobot.Motors.ELBOW : 180.0, 
          SurgicalRobot.Motors.WRIST : 180.0, 
          SurgicalRobot.Motors.HAND : 180.0}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()

    def connext_setup(self):
        # Register DDS types, using a function from DdsUtils.py
        DdsUtils.register_type(Common.DeviceStatus)
        DdsUtils.register_type(Common.DeviceHeartbeat)
        DdsUtils.register_type(Orchestrator.DeviceCommand)
        DdsUtils.register_type(SurgicalRobot.MotorControl)
        DdsUtils.register_type(SurgicalRobot.MotorTelemetry)

        # Connext will load XML files through the default provider from the
        # NDDS_QOS_PROFILES environment variable
        qos_provider = dds.QosProvider.default

        participant = qos_provider.create_participant_from_config(DdsUtils.arm_dp_fqn)

        # Create a second participant for telemetry topic on the telemetry domain (6)
        self.participant_6 = dds.DomainParticipant(6)
        self.telemetry_topic = dds.Topic(self.participant_6, "topic/MotorTelemetry", SurgicalRobot.MotorTelemetry)

        # Initialize DataWriters
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

        # Initialize DataReaders
        self.motor_control_reader = dds.DataReader(
            participant.find_datareader(DdsUtils.motor_control_dr_fqn)
        )
        self.cmd_reader = dds.DataReader(
            participant.find_datareader(DdsUtils.device_command_dr_fqn)
        )

        # Setup command condition
        cmd_status_condition = dds.StatusCondition(self.cmd_reader)
        cmd_status_condition.enabled_statuses = dds.StatusMask.DATA_AVAILABLE
        cmd_status_condition.set_handler(self.cmd_handler)

        # Setup motor control condition
        motor_status_condition = dds.StatusCondition(self.motor_control_reader)
        motor_status_condition.enabled_statuses = dds.StatusMask.DATA_AVAILABLE
        motor_status_condition.set_handler(self.motor_handler)

        self.general_waitset = dds.WaitSet()
        self.general_waitset += cmd_status_condition
        self.general_waitset += motor_status_condition


    def write_hb(self, hb_writer):
        while not self.stop_event.is_set():
            hb = Common.DeviceHeartbeat()
            hb.device = Common.DeviceType.ARM
            hb_writer.write(hb)
            time.sleep(0.05)


    def write_telemetry(self):
        writer = dds.DataWriter(self.participant_6.implicit_publisher, self.telemetry_topic)
        while not self.stop_event.is_set():
            with self.lock:
                for motor in self.angles:
                    sample = SurgicalRobot.MotorTelemetry
                    sample.id = motor
                    sample.position_deg = self.angles[motor]
                    sample.current_mA = round(random.uniform(1,1.5),2)
                    sample.voltage_V = round(random.uniform(12,12.1),2)
                    sample.temp_c = round(random.uniform(26,27.0),2)
                    writer.write(sample)
            time.sleep(0.5) # Change this delay to adjust telemetry update frequency


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
                self.stop_event.set()

            self.status_writer.write(self.arm_status)


    def motor_handler(self, _):
        samples = self.motor_control_reader.take_data()
        with self.lock:
            for sample in samples:
                if(sample.direction == SurgicalRobot.MotorDirections.INCREMENT): 
                    self.angles[sample.id] = (self.angles[sample.id] + 1) % 360.0
                elif(sample.direction == SurgicalRobot.MotorDirections.DECREMENT): 
                    self.angles[sample.id] = (self.angles[sample.id] - 1) % 360.0        

            
    # Main function
    def run(self):

        print("Starting DigitalTwin Controller")

        # setup Connext
        self.connext_setup()

        # Start threads
        hb_thread = threading.Thread(target=self.write_hb, args=[self.hb_writer])
        telemetry_thread = threading.Thread(target=self.write_telemetry)

        hb_thread.start()
        telemetry_thread.start()        

        try:
            while not self.stop_event.is_set():
                self.general_waitset.dispatch(dds.Duration(1))
        except KeyboardInterrupt:
            self.stop_event.set()

        print("Shutting down DigitalTwin Controller")

        # Set status to off
        self.arm_status.status = Common.DeviceStatuses.OFF

        # Rejoin all threads
        telemetry_thread.join()
        hb_thread.join()

        print("DigitalTwin Controller shutdown complete.")

if __name__ == "__main__":
    thisapp = DigitalTwinApp()
    thisapp.run()