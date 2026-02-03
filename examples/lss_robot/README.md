# LSS Robot — RTI MedTech Reference Architecture

This example implements a Robot Arm application that controls a LynxMotion
LSS serial-servo arm and publishes real servo telemetry to the MedTech
Reference Architecture. The application reads motor control commands from the
`MotorControl` topic and publishes `MotorTelemetry` samples on the
`topic/MotorTelemetry` topic on **domain 6**. It participates as a first-class
Arm device by publishing device status and heartbeats and responding to
Orchestrator commands.

See the project root [README.md](/README.md) for overall architecture and how this example fits
in.

Contents
- `src/lss_robot_app.py`: main application that controls LynxMotion servos and
  publishes telemetry.
- `launch_robot_app.sh`: helper script that sets up environment variables and
  starts the application.

Dependencies
- Python 3
- RTI Connext DDS Python API (`rti.connextdds`)
- LynxMotion LSS Python Library: https://github.com/Lynxmotion/LSS_PRO_Library_Python
- `rti.idl` (for telemetry struct mapping)
- The repository `Types` and `DdsUtils` modules (included under `examples`)

How it works (code overview)
- Declares `SurgicalRobot::MotorTelemetry` via a Python `idl.struct` mapping and
  assigns it to `SurgicalRobot.MotorTelemetry`.
- Registers DDS types (DeviceStatus, DeviceHeartbeat, DeviceCommand,
  MotorControl, MotorTelemetry) with Connext using `DdsUtils`.
- Uses a QoS-configured DomainParticipant (via `DdsUtils.arm_dp_fqn`) for the
  Arm domain and creates a second `DomainParticipant(6)` for publishing
  telemetry to `topic/MotorTelemetry`.
- Hardware setup: opens the LynxMotion serial bus and initializes `LSS(i)` for
  each servo, resets axes and moves servos to a safe initial position.
- Subscribes to `MotorControl` and applies INCREMENT/DECREMENT commands to
  physical servos, respecting per-servo speed (`maxrpm`) and movement limits.
- Reads physical servo state (position, speed, current, voltage, temperature)
  and publishes `MotorTelemetry` samples on domain 6 at a configurable
  frequency (default 0.5s).

Telemetry outputs and topic
- Topic: `topic/MotorTelemetry` on **domain 6**
- Published fields (per sample):
  - `id`: motor identifier (BASE, SHOULDER, ELBOW, WRIST, HAND)
  - `position_deg`: current servo position in degrees
  - `speed_rpm`, `current_mA`, `voltage_V`, `temp_c`
- Update frequency: 0.5 seconds by default (see `write_telemetry()` in the
  application).

Notes on behavior
- The app inverts ELBOW and WRIST directions when mapping control commands to
  physical movement to match the arm's mechanical conventions. Shoulder and
  elbow telemetry position may be inverted to align with the digital twin
  convention.
- Servo movement respects configured `limits` and `maxrpm` per axis to prevent
  unsafe motion.
- Ensure the serial port configured in the app (default `/dev/ttyUSB0`) is
  correct for your hardware and that the user has permission to access it.

Running
1. Ensure the NDDS_QOS_PROFILES environment variable (or other RTI configuration)
   points to the project's QoS XML files.
2. Install the LynxMotion LSS Python library and other dependencies (see the
   LynxMotion repo link above).
3. Start the app via the provided script:

```bash
./scripts/launch_robot_app.sh
```

Tips
- If you don't have the hardware available, run the `telemetry_bridge` Digital
  Twin example to simulate telemetry and validate orchestration and telemetry
  consumers before connecting the physical arm.
- Verify the serial port name and permissions (Linux: add your user to the
  appropriate group or use `udev` rules); on Windows set the correct COM port.
- Use conservative `maxrpm` and `limits` when first testing physical hardware.

Files
- See [/examples/lss_robot/lss_robot_app.py](lss_robot_app.py) for implementation details and the LynxMotion
  library link above for hardware driver information.
