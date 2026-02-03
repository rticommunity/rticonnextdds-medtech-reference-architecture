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

# Robot Arm application which controls the LynxMotion arm, and publishes telemetry data 

import time, threading
import rti.connextdds as dds
import DdsUtils
from Types import Common, SurgicalRobot, Orchestrator
import rti.idl as idl
# LynxMotion Serial Servo (LSS) library imports - https://github.com/Lynxmotion/LSS_PRO_Library_Python
import lss
import lss_const as lssc


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

class RobotApp:
    def __init__(self):
        self.stop_event = threading.Event()

        self.lss_port = "/dev/ttyUSB0" # For Linux/Unix platforms
        # self.lss_port = "COM230" # For windows platforms
        self.lss_baud = lssc.LSS_DefaultBaud
        self.arm_status = None

        self.maxrpm = [5,3,5,5,5] # How fast each servo should spin
        self.limits = [(-90,180),(-30,75),(-90,15),(-85,65),(-90,-2)] # Movement limits for each servo
        self.servolist = []


    def get_motor_pos(self, motor_id):
        return int(self.servolist[motor_id].getPosition()) / 10.0


    def robot_setup(self):
        # Create and open a serial port
        lss.initBus(self.lss_port, self.lss_baud)

        for i in range(1,6):
            self.servolist.append(lss.LSS(i))

        for i in [0, 1, 2, 3, 4]:
            print(f"Resetting axis: {i}")
            servo = self.servolist[i]
            servo.reset()
            time.sleep(1)
            servo.move(0) # go to initial position

        time.sleep(2)

        for i in [0, 1, 2, 3, 4]:
            self.servolist[i].move(0) # go to initial position

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
        while self.arm_status.status != Common.DeviceStatuses.OFF:
            hb = Common.DeviceHeartbeat()
            hb.device = Common.DeviceType.ARM
            hb_writer.write(hb)
            time.sleep(0.05)


    def write_telemetry(self):
        writer = dds.DataWriter(self.participant_6.implicit_publisher, self.telemetry_topic)
        while not self.stop_event.is_set():
            for i in range(5):
                servo = self.servolist[i]
                try:  # Sometimes get NoneType from lss.get...
                    sample = SurgicalRobot.MotorTelemetry
                    sample.id = i
                    sample.position_deg = int(servo.getPosition()) / 10.0
                    if sample.id == SurgicalRobot.Motors.SHOULDER or sample.id == SurgicalRobot.Motors.ELBOW:
                        # Invert the position for the SHOULDER and ELBOW servos (Digital twin uses opposite convention)
                        sample.position_deg = -sample.position_deg
                    sample.speed_rpm = int(servo.getSpeedRPM())
                    sample.current_mA = int(servo.getCurrent())
                    sample.voltage_V = int(servo.getVoltage()) / 1000.0
                    sample.temp_c = int(servo.getTemperature()) / 10.0
                    writer.write(sample)
                except:
                    pass

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
        for sample in samples:

            motor_id = sample.id
            direction = sample.direction
            delta = 0

            # Invert direction for ELBOW and WRIST to match physical movement
            if motor_id == SurgicalRobot.Motors.ELBOW or motor_id == SurgicalRobot.Motors.WRIST:
                if direction == SurgicalRobot.MotorDirections.INCREMENT:
                    direction = SurgicalRobot.MotorDirections.DECREMENT
                elif direction == SurgicalRobot.MotorDirections.DECREMENT:
                    direction = SurgicalRobot.MotorDirections.INCREMENT               
                
            try: # Sometimes get NoneType from lss.get...
                pos = self.get_motor_pos(motor_id)
            except:
                continue

            if direction == SurgicalRobot.MotorDirections.INCREMENT:
                delta = self.maxrpm[motor_id]
                if pos+delta >= self.limits[motor_id][1]:
                    delta = 0
            elif direction == SurgicalRobot.MotorDirections.DECREMENT:
                delta = -self.maxrpm[motor_id]
                if pos+delta <= self.limits[motor_id][0]:
                    delta = 0

            #print(f"Delta is {delta}, new position is {pos+delta}")

            if delta != 0: 
                rpm = self.maxrpm[motor_id]
                if direction == SurgicalRobot.MotorDirections.DECREMENT and SurgicalRobot.Motors.ELBOW == 2:
                    rpm = rpm / 1.5

                self.servolist[motor_id].setMaxSpeedRPM(rpm)
                self.servolist[motor_id].move((pos+delta) * 10)


    # Main function
    def run(self):

        print("Starting Robot Controller")

        # setup robot hardware
        self.robot_setup()

        # setup Connext
        self.connext_setup()

        # Start threads
        hb_thread = threading.Thread(target=self.write_hb, args=[self.hb_writer])
        telemetry_thread = threading.Thread(target=self.write_telemetry)

        hb_thread.start()
        telemetry_thread.start()        

        try:
            while self.arm_status.status != Common.DeviceStatuses.OFF:
                self.general_waitset.dispatch(dds.Duration(1))
        except KeyboardInterrupt:
            self.stop_event.set()

        print("Shutting down Robot Controller")

        # Set status to off
        self.arm_status.status = Common.DeviceStatuses.OFF

        # Rejoin all threads
        telemetry_thread.join()
        hb_thread.join()

        print("Robot Controller shutdown complete.")

if __name__ == "__main__":
    thisapp = RobotApp()
    thisapp.run()
