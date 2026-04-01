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

import vector.canoe
from application_layer import SurgicalRobot
import time, random

@vector.canoe.measurement_script
class telemetry:
    def __init__(self):
        self.angles = {
            SurgicalRobot.Motors.BASE : 0.0, 
            SurgicalRobot.Motors.SHOULDER : 0.0, 
            SurgicalRobot.Motors.ELBOW : 0.0, 
            SurgicalRobot.Motors.WRIST : 0.0, 
            SurgicalRobot.Motors.HAND : 0.0}
        self.step : float = 1.0

    # Called before measurement start to perform necessary initializations,
    # e.g. to create objects. During measurement, few additional objects
    # should be created to prevent garbage collection runs in time-critical
    # simulations.
    def initialize(self):
        pass
             
    #Notification that the measurement starts.
    def start(self):
        pass
    
    #Notification that the measurement ends.
    def stop(self):
        pass
    
    # Cleanup after the measurement. Complement to Initialize. This is not
    # a "Dispose" method; your object should still be usable afterwards.
    def shutdown(self):
        pass

    def get_motor_name(self, motor : SurgicalRobot.Motors_module.Motors) -> str:
        # Determine a readable name for the motor enum/member in a robust way
        try:
            motor_name = motor.name
        except Exception:
            try:
                motor_name = SurgicalRobot.Motors_module.Motors(motor).name
            except Exception:
                try:
                    motor_name = SurgicalRobot.Motors_module.Motors[motor].__name__
                except Exception:
                    motor_name = str(motor)
        return motor_name

    def normalize_angle(self, angle: float) -> float:
        """Normalize an angle (degrees) to the range [-180.0, 180.0].

        Uses the standard shift-modulo-shift trick so values wrap cleanly.
        """
        return ((angle + 180.0) % 360.0) - 180.0
    
    def update_motor_pos(self, motor : SurgicalRobot.Motors_module.Motors, target_position : int):
        # Update the motor position to the target position in single degree steps
        motor_data = SurgicalRobot.MotorControl_module.MotorControl()
        motor_data.id = motor
        current_position = int(self.angles[motor])
        
        while current_position != target_position:
            if current_position < target_position:
                motor_data.direction = SurgicalRobot.MotorDirections.INCREMENT
                current_position += 1
            else: 
                motor_data.direction = SurgicalRobot.MotorDirections.DECREMENT
                current_position -= 1
            
            self.angles[motor] = float(current_position)
            SurgicalRobot.Controller.motorData = motor_data

        vector.canoe.write(f"Updated {self.get_motor_name(motor)} Motor - position: {target_position}")

    def update_helper_pos(self, motor : SurgicalRobot.Motors_module.Motors, position=None):
        # Synchronize the panel helper positions if needed from the motor telemetry updates.
        if position is None:
            position = self.angles[motor]

        # Use structural pattern matching (switch) for clarity and efficiency
        match motor:
            case SurgicalRobot.Motors.BASE:
                if SurgicalRobot.panelHelper.base_position_deg != position:
                    SurgicalRobot.panelHelper.base_position_deg = position
            case SurgicalRobot.Motors.SHOULDER:
                if SurgicalRobot.panelHelper.shoulder_position_deg != position:
                    SurgicalRobot.panelHelper.shoulder_position_deg = position
            case SurgicalRobot.Motors.ELBOW:
                if SurgicalRobot.panelHelper.elbow_position_deg != position:
                    SurgicalRobot.panelHelper.elbow_position_deg = position
            case SurgicalRobot.Motors.WRIST:
                if SurgicalRobot.panelHelper.wrist_position_deg != position:
                    SurgicalRobot.panelHelper.wrist_position_deg = position
            case SurgicalRobot.Motors.HAND:
                if SurgicalRobot.panelHelper.hand_position_deg != position:
                    SurgicalRobot.panelHelper.hand_position_deg = position
            case _:
                # Unknown motor value — do nowt
                pass


    @vector.canoe.on_update(SurgicalRobot.Receiver.motorData)
    def on_motorData_update(self):
        # Handle incoming motor control commands, translate to telemetry updates for the digital twin
        motor_sample = SurgicalRobot.Receiver.motorData.copy()
        
        try:
            motor_id = SurgicalRobot.Motors(motor_sample.id._value)
        except ValueError as e:
            vector.canoe.write(f"Invalid motor enum: {motor_sample.id}, error: {e}")
            return
                
        try:
            direction = SurgicalRobot.MotorDirections(motor_sample.direction._value)            
        except ValueError as e:
            vector.canoe.write(f"Invalid direction enum: {motor_sample.direction}, error: {e}")
            return
        
        motor_name = self.get_motor_name(motor_id)        
        vector.canoe.write(f"Received update - motor: {motor_name}, direction: {str(direction)}")
                
        if SurgicalRobot.MotorDirections.INCREMENT == direction:
            self.angles[motor_id] = self.normalize_angle(self.angles[motor_id] + self.step)
        elif SurgicalRobot.MotorDirections.DECREMENT == direction:
            self.angles[motor_id] = self.normalize_angle(self.angles[motor_id] - self.step)
                        
        telemetry = SurgicalRobot.MotorTelemetry_module.MotorTelemetry()
        telemetry.id = motor_id
        telemetry.position_deg = self.angles[motor_id]
        telemetry.current_mA = round(random.uniform(1,1.5),2)
        telemetry.voltage_V = round(random.uniform(12,12.5),2)
        telemetry.temp_c = round(random.uniform(26,29.0),2)
        vector.canoe.write(f"Sent telemetry update - motor: {motor_name}, position: {telemetry.position_deg}")

        SurgicalRobot.Sender.telemetryData = telemetry

        self.update_helper_pos(motor_id)
        
    
    @vector.canoe.on_update(SurgicalRobot.panelHelper.base_position_deg)
    def on_base_pos_update(self):
        self.update_motor_pos(SurgicalRobot.Motors.BASE, int(SurgicalRobot.panelHelper.base_position_deg.copy()))

    @vector.canoe.on_update(SurgicalRobot.panelHelper.shoulder_position_deg)
    def on_shoulder_pos_update(self):
        self.update_motor_pos(SurgicalRobot.Motors.SHOULDER, int(SurgicalRobot.panelHelper.shoulder_position_deg.copy()))

    @vector.canoe.on_update(SurgicalRobot.panelHelper.elbow_position_deg)
    def on_elbow_pos_update(self):
        self.update_motor_pos(SurgicalRobot.Motors.ELBOW, int(SurgicalRobot.panelHelper.elbow_position_deg.copy()))        

    @vector.canoe.on_update(SurgicalRobot.panelHelper.wrist_position_deg)
    def on_wrist_pos_update(self):
        self.update_motor_pos(SurgicalRobot.Motors.WRIST, int(SurgicalRobot.panelHelper.wrist_position_deg.copy()))    

    @vector.canoe.on_update(SurgicalRobot.panelHelper.hand_position_deg)
    def on_hand_pos_update(self):
        self.update_motor_pos(SurgicalRobot.Motors.HAND, int(SurgicalRobot.panelHelper.hand_position_deg.copy()))

    
            
        