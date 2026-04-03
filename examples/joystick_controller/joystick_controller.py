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

import pygame
from enum import IntEnum
import asyncio, os, threading
import rti.connextdds as dds
import DdsUtils
from Types import Common, SurgicalRobot, Orchestrator

class Buttons(IntEnum):
    PRIMARY_LEFT = 3
    PRIMARY_RIGHT = 0
    SECONDARY_LEFT  = 4
    SECONDARY_RIGHT = 1

class JoystickApp:
    def __init__(self):
        self.arm_status = None
        self.joystick = None
        self.up_down = [SurgicalRobot.Motors.SHOULDER, SurgicalRobot.Motors.ELBOW, SurgicalRobot.Motors.WRIST]
        self.left_right = [SurgicalRobot.Motors.BASE, SurgicalRobot.Motors.HAND]
        self.stop_event = asyncio.Event()
        self.event_loop = asyncio.new_event_loop()

    def __del__(self):
        self.event_loop.close()  # Final cleanup


    async def joystick_setup(self):
        pygame.init()
        pygame.joystick.init()

        # Check if joystick is available
        if pygame.joystick.get_count() < 1:
            print("No joystick detected.")
            pygame.quit()
            return False

        # Initialize joystick
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()

        print(f"Starting Joystick Controller, using joystick: {self.joystick.get_name()}")

        # Print detected joystick mapping for debugging
        num_axes = self.joystick.get_numaxes()
        num_buttons = self.joystick.get_numbuttons()
        num_hats = self.joystick.get_numhats()
        print(f"Joystick detected: axes={num_axes}, buttons={num_buttons}, hats={num_hats}")
        print("Controls:")
        print("  BASE <- X (L = CCW, R = CW)")
        print("  SHOULDER <- Y + Left Primary Button")
        print("  ELBOW <- Y + Right Primary Button")
        print("  WRIST <- Y + Left Secondary Button")
        print("  HAND <- X + Right Secondary Button (L = Open, R = Close)")
        return True


    async def connext_setup(self):
        # Register DDS types, using a function from DdsUtils.py
        DdsUtils.register_type(Common.DeviceStatus)
        DdsUtils.register_type(Common.DeviceHeartbeat)
        DdsUtils.register_type(Orchestrator.DeviceCommand)
        DdsUtils.register_type(SurgicalRobot.MotorControl)

        # Connext will load XML files through the default provider from the
        # NDDS_QOS_PROFILES environment variable
        qos_provider = dds.QosProvider.default

        participant = qos_provider.create_participant_from_config(DdsUtils.arm_controller_dp_fqn)

        # Initialize DataWriters
        self.status_writer = dds.DataWriter(
            participant.find_datawriter(DdsUtils.status_dw_fqn)
        )
        self.hb_writer = dds.DataWriter(
            participant.find_datawriter(DdsUtils.device_hb_dw_fqn)
        )
        self.motor_control_writer = dds.DataWriter(
            participant.find_datawriter(DdsUtils.motor_control_dw_fqn)
        )
        self.arm_status = Common.DeviceStatus(
            device=Common.DeviceType.ARM, status=Common.DeviceStatuses.ON
        )
        self.status_writer.write(self.arm_status)

        # Initialize DataReaders
        self.cmd_reader = dds.DataReader(
            participant.find_datareader(DdsUtils.device_command_dr_fqn)
        )

        # Setup command handling and waitsets
        cmd_status_condition = dds.StatusCondition(self.cmd_reader)
        cmd_status_condition.enabled_statuses = dds.StatusMask.DATA_AVAILABLE
        cmd_status_condition.set_handler(self.cmd_handler)
        self.cmd_waitset = dds.WaitSet()
        self.cmd_waitset += cmd_status_condition

        print("Connext DDS setup complete.")


    async def write_hb(self, hb_writer):
        while not self.stop_event.is_set():
            hb = Common.DeviceHeartbeat()
            hb.device = Common.DeviceType.ARM
            hb_writer.write(hb)
            await asyncio.sleep(0.05)  # 20Hz heartbeat


    async def waitsets(self):
        while not self.stop_event.is_set():
            await self.cmd_waitset.dispatch_async(dds.Duration(1))


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


    def poll_joystick(self, joystick):
        clock = pygame.time.Clock()
        sample = SurgicalRobot.MotorControl

        try:
            num_buttons = joystick.get_numbuttons()
            num_axes = joystick.get_numaxes()
            target = SurgicalRobot.Motors.BASE

            while not self.stop_event.is_set():
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        return

                # Poll joystick for button states
                button_states = [joystick.get_button(i) for i in range(num_buttons)]
                # Poll joystick for axis states
                axis_states = [joystick.get_axis(i) for i in range(num_axes)]

                target = SurgicalRobot.Motors.BASE

                if button_states[Buttons.PRIMARY_LEFT]:
                    target = SurgicalRobot.Motors.SHOULDER
                elif button_states[Buttons.PRIMARY_RIGHT]:
                    target = SurgicalRobot.Motors.ELBOW
                elif button_states[Buttons.SECONDARY_LEFT]:
                    target = SurgicalRobot.Motors.WRIST
                elif button_states[Buttons.SECONDARY_RIGHT]:
                    target = SurgicalRobot.Motors.HAND

                # Left/right
                if target in self.left_right:
                    if int(axis_states[0]) < 0: # left
                        sample.id = target
                        sample.direction = SurgicalRobot.MotorDirections.DECREMENT
                        self.motor_control_writer.write(sample)
                    elif round(axis_states[0]) > 0: # right
                        sample.id = target
                        sample.direction = SurgicalRobot.MotorDirections.INCREMENT
                        self.motor_control_writer.write(sample)
                elif target in self.up_down:
                    if int(axis_states[1]) < 0: # up
                        sample.id = target
                        sample.direction = SurgicalRobot.MotorDirections.INCREMENT
                        self.motor_control_writer.write(sample)
                    elif round(axis_states[1]) > 0: # down
                        sample.id = target
                        sample.direction = SurgicalRobot.MotorDirections.DECREMENT
                        self.motor_control_writer.write(sample)

                # Adjust the clock speed as needed
                clock.tick(60)

        except KeyboardInterrupt:
            pygame.quit()

    # Main function
    async def run(self):

        print("Starting Joystick Controller")

        threading.Thread(target=self.event_loop.run_forever, daemon=True).start()

        joystick_ok, _ = await asyncio.gather( self.joystick_setup(), self.connext_setup(), return_exceptions=True )
        if not joystick_ok:
            print("Joystick setup failed, exiting.")
            return

        # Start tasks
        hb_task = asyncio.create_task(self.write_hb(self.hb_writer))
        sub_task = asyncio.create_task(self.waitsets())

        # Poll joystick for button and axis states
        self.poll_joystick(self.joystick)

        print("Shutting down Joystick Controller")

        # Set status to off
        self.arm_status.status = Common.DeviceStatuses.OFF

        # Wait for all async tasks to finish
        await asyncio.gather(hb_task, sub_task)

        pygame.quit()

        print("Joystick Controller shutdown complete.")


if __name__ == "__main__":
    thisapp = JoystickApp()
    asyncio.run(thisapp.run())
