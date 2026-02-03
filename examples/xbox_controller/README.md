
# XBox Controller — RTI MedTech Reference Architecture

This example implements an XBox controller-based Arm controller for the RTI
MedTech Reference Architecture. The controller reads an XBox gamepad through
`pygame`, publishes motor control commands to the DDS `MotorControl` topic,
and participates as a first-class Arm device by publishing device status and
heartbeats and responding to orchestrator commands.

See the project root [README](/README.md) for overall architecture and how this 
example fits in.

Contents
- `xbox_controller.py`: main application that reads XBox controller input and
  publishes DDS messages.
- `launch_arm_xbox.sh`: helper script to start the XBox controller with the
  appropriate environment and QoS profiles.

Dependencies
- Python 3
- `pygame` (for controller input)
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
- Reads controller inputs via `pygame` (hats and stick axes) and writes
  `MotorControl` messages for commanded motors.

Button and stick mappings
- Direction Pad (D-pad) X (left / right): controls `BASE` servo
- Direction Pad (D-pad) Y (up / down): controls `SHOULDER` servo
- Left stick X (left / right): controls `WRIST` servo
- Left stick Y (up / down): controls `ELBOW` servo
  - Note: the implementation inverts the Elbow polarity (up vs down) to
    match the intended motion (see `xbox_controller.py` for details).
- Right stick Y (up / down): controls `HAND` servo

Notes on behavior
- The app publishes `MotorControl` messages based on axis/hats polarity.
- D-pad values are read from `joystick.get_hat(0)` when available; hat
  polarity may vary between controllers.
- The controller acts like any other managed device in the architecture: it
  sends heartbeats and status updates and listens for orchestrator commands so
  the Orchestrator can start, pause, or shutdown the Arm as part of a larger
  scenario.

Running
1. Ensure the NDDS_QOS_PROFILES environment variable (or other RTI configuration)
   points to the project's QoS XML files.
2. Install dependencies: `pip install pygame` and ensure the RTI Connext DDS
   Python bindings are available.
3. Start the controller using the provided script:

```bash
./scripts/launch_arm_xbox.sh
```

Tips
- If no controller is detected the app exits with `No joystick detected.` Ensure
  your controller is connected and recognized by the OS.
- Button/hat/axis indices and polarity may differ between controllers. Use
  `joystick.get_numbuttons()`, `joystick.get_numhats()`, and `joystick.get_numaxes()`
  in an interactive session to verify.
- For headless/no-sound setups, use `-e SDL_AUDIODRIVER=dummy` in the docker
  command to suppress SDL sound initialization errors.

Files
- See [/examples/xbox_controller/xbox_controller.py](xbox_controller.py)
  for the implementation.
    
