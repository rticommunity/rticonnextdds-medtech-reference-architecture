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
        # Enable debug printing when XBOX_DEBUG=1 or XBOX_DEBUG=true in environment
        self.debug = os.getenv('XBOX_DEBUG', '0') in ('1', 'true', 'True')

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

        print(f"Starting XBox Controller, using joystick: {self.joystick.get_name()}")

        # Print detected joystick mapping for debugging
        num_axes = self.joystick.get_numaxes()
        num_buttons = self.joystick.get_numbuttons()
        num_hats = self.joystick.get_numhats()
        print(f"Joystick detected: axes={num_axes}, buttons={num_buttons}, hats={num_hats}")
        print("Controls:")
        print("  BASE <- D-pad X OR bumpers (L = CCW, R = CW)")
        print("  SHOULDER <- D-Pad Y or left stick X ")
        print("  ELBOW <- left stick Y ")
        print("  WRIST <- right stick Y ")
        print("  HAND <- right stick X or triggers (L = Open, R = Close)")
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


    def apply_deadzone(self, value, deadzone=0.1):
        """Return 0 if value is within deadzone, otherwise return value"""
        if abs(value) < deadzone:
            return 0.0
        return value


    def poll_joystick(self, joystick):
        clock = pygame.time.Clock()
        sample = SurgicalRobot.MotorControl
        deadzone = 0.2  # Adjust this threshold as needed

        try:
            num_buttons = joystick.get_numbuttons()
            num_axes = joystick.get_numaxes()
            debug_counter = 0
            debug_print_every = 6  # print ~10 times/sec at 60Hz if debug enabled

            while not self.stop_event.is_set():
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        return

                # Poll joystick for button states
                button_states = [joystick.get_button(i) for i in range(num_buttons)]
                # Poll joystick for axis states
                axis_states = [self.apply_deadzone(joystick.get_axis(i), deadzone) for i in range(num_axes)]

                # Xbox control layout mapping:
                # - D-pad X -> BASE
                # - D-pad Y -> SHOULDER
                # - Left stick X -> SHOULDER
                # - Left stick Y -> ELBOW
                # - Right stick Y -> WRIST
                # - Right stick X -> HAND
                # - BASE also controlled by left/right bumpers (buttons)
                # - HAND also controlled by triggers (axes with threshold)

                # Read D-pad (hat) if available
                num_hats = joystick.get_numhats()
                if num_hats > 0:
                    dpad_x, dpad_y = joystick.get_hat(0)
                else:
                    dpad_x = 0
                    dpad_y = 0

                # Left stick axes
                left_x = round(axis_states[0]) if num_axes > 0 else 0
                left_y = round(axis_states[1]) if num_axes > 1 else 0

                # Right stick axes
                right_x = round(axis_states[3]) if num_axes > 2 else 0
                right_y = round(axis_states[4]) if num_axes > 3 else 0

                # Triggers
                left_trigger = round(axis_states[2]) if num_axes > 4 else 0
                right_trigger = round(axis_states[5]) if num_axes > 5 else 0
                trigger_threshold = 0.2  # lower threshold for higher sensitivity

                # Bumpers (if present) — commonly buttons 4/5
                left_bumper = button_states[4] if num_buttons > 4 else 0
                right_bumper = button_states[5] if num_buttons > 5 else 0

                # Debug print button/axis states (throttled)
                if self.debug:
                    if debug_counter % debug_print_every == 0:
                        print(f"buttons={button_states} axes={axis_states} dpad=({dpad_x},{dpad_y}) left_x={left_x} left_y={left_y} right_x={right_x} right_y={right_y} lt={left_trigger:.2f} rt={right_trigger:.2f}")
                debug_counter += 1

                # BASE controlled by D-pad X OR bumpers
                if dpad_x < 0 or left_bumper:
                    sample.id = SurgicalRobot.Motors.BASE
                    sample.direction = SurgicalRobot.MotorDirections.DECREMENT
                    self.motor_control_writer.write(sample)
                elif dpad_x > 0 or right_bumper:
                    sample.id = SurgicalRobot.Motors.BASE
                    sample.direction = SurgicalRobot.MotorDirections.INCREMENT
                    self.motor_control_writer.write(sample)

                # SHOULDER controlled by left stick X or D-pad Y
                if left_x < 0 or dpad_y < 0:  # left or dpad down maps to DECREMENT
                    sample.id = SurgicalRobot.Motors.SHOULDER
                    sample.direction = SurgicalRobot.MotorDirections.DECREMENT
                    self.motor_control_writer.write(sample)
                elif left_x > 0 or dpad_y > 0:
                    sample.id = SurgicalRobot.Motors.SHOULDER
                    sample.direction = SurgicalRobot.MotorDirections.INCREMENT
                    self.motor_control_writer.write(sample)

                # ELBOW controlled by left stick Y
                if left_y < 0:
                    sample.id = SurgicalRobot.Motors.ELBOW
                    sample.direction = SurgicalRobot.MotorDirections.INCREMENT
                    self.motor_control_writer.write(sample)
                elif left_y > 0:
                    sample.id = SurgicalRobot.Motors.ELBOW
                    sample.direction = SurgicalRobot.MotorDirections.DECREMENT
                    self.motor_control_writer.write(sample)

                # WRIST controlled by right stick Y
                if right_y < 0:
                    sample.id = SurgicalRobot.Motors.WRIST
                    sample.direction = SurgicalRobot.MotorDirections.INCREMENT
                    self.motor_control_writer.write(sample)
                elif right_y > 0:
                    sample.id = SurgicalRobot.Motors.WRIST
                    sample.direction = SurgicalRobot.MotorDirections.DECREMENT
                    self.motor_control_writer.write(sample)

                # HAND controlled by right stick X or triggers
                if right_x < 0 or left_trigger > trigger_threshold:
                    sample.id = SurgicalRobot.Motors.HAND
                    sample.direction = SurgicalRobot.MotorDirections.DECREMENT
                    self.motor_control_writer.write(sample)
                elif right_x > 0 or right_trigger > trigger_threshold:
                    sample.id = SurgicalRobot.Motors.HAND
                    sample.direction = SurgicalRobot.MotorDirections.INCREMENT
                    self.motor_control_writer.write(sample)

                # Adjust the clock speed as needed
                clock.tick(60)

        except KeyboardInterrupt:
            pygame.quit()

    # Main function
    async def run(self):

        print("Starting XBox Controller")

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

        print("Shutting down XBox Controller")

        # Set status to off
        self.arm_status.status = Common.DeviceStatuses.OFF

        # Wait for all async tasks to finish
        await asyncio.gather(hb_task, sub_task)

        pygame.quit()

        print("XBox Controller shutdown complete.")


if __name__ == "__main__":
    thisapp = JoystickApp()
    asyncio.run(thisapp.run())
