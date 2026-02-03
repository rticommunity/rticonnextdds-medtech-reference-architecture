# Joystick Controller — RTI MedTech Reference Architecture

This example implements a joystick-based Arm controller for the RTI MedTech
Reference Architecture. The controller reads a standard gamepad/joystick through
`pygame`, publishes motor control commands to the DDS `MotorControl` topic,
and participates as a first-class Arm device by publishing device status and
heartbeats and responding to orchestrator commands.

See the project root [README](/README.md) for overall architecture and how this 
example fits in.

Contents
- `joystick_controller.py`: main application that reads joystick input and
  publishes DDS messages.
- `launch_arm_joystick.sh`: helper script to start the joystick controller with
  the appropriate environment and QoS profiles.

Dependencies
- Python 3
- `pygame` (for joystick input)
- RTI Connext DDS Python API (`rti.connextdds`)
- The repository `Types` and `DdsUtils` modules (included under `examples`)

How it works (code overview)
- Registers DDS types (DeviceStatus, DeviceHeartbeat, DeviceCommand,
  MotorControl) with Connext using `DdsUtils`.
- Creates a DomainParticipant from the configured QoS profiles and finds the
  pre-configured DataWriters/DataReaders using the FQNs in `DdsUtils`.
- Publishes an initial `DeviceStatus` indicating the Arm is ON, and runs a
  background heartbeat writer thread publishing `DeviceHeartbeat` messages.
- Subscribes to `DeviceCommand` from the Orchestrator and reacts to START,
  PAUSE, and SHUTDOWN commands (updating `DeviceStatus` accordingly).
- Reads joystick buttons and axes via `pygame` and writes `MotorControl`
  messages for commanded motors.

Button and stick mappings
- X-Axis (left / right): controls `BASE` servo (left => decrement, right => increment)
- `PRIMARY_LEFT` (button index 3) + Y-Axis (up / down): controls `SHOULDER`
- `PRIMARY_RIGHT` (button index 0) + Y-Axis (up / down): controls `ELBOW`
- `SECONDARY_LEFT` (button index 4) + Y-Axis (up / down): controls `WRIST`
- `SECONDARY_RIGHT` (button index 1) + X-Axis (left / right): controls `HAND`

Notes on behavior
- The app publishes `MotorControl` messages based on axis polarity and the
  currently active target motor (determined by the pressed modifier button).
- The controller also acts like any other managed device in the architecture:
  it sends heartbeats and status updates and listens for orchestrator commands
  so the Orchestrator can start, pause, or shutdown the Arm as part of a
  larger scenario.

Running
1. Ensure the NDDS_QOS_PROFILES environment variable (or other RTI configuration)
   points to the project's QoS XML files.
2. Install dependencies: `pip install pygame` and ensure the RTI Connext DDS
   Python bindings are available.
3. Start the controller using the provided script:

```bash
./scripts/launch_arm_joystick.sh
```

Tips
- If no joystick is detected the app exits with `No joystick detected.` Ensure
  your joystick/gamepad is connected and recognized by the OS.
- Button indices are based on the joystick used when this example was written;
  indexes may differ between controllers. Use `joystick.get_numbuttons()` and
  `joystick.get_axis()` in an interactive session to verify.

Files
- See [/examples/joystick_controller/joystick_controller.py](joystick_controller.py)
  for the implementation.

