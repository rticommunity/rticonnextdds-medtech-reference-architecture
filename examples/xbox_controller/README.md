# Xbox Controller — RTI MedTech Reference Architecture

This example implements an Xbox controller-based Arm controller for the RTI MedTech Reference Architecture. The controller reads an Xbox gamepad through `pygame`, publishes motor control commands to the DDS `MotorControl` topic, and participates as a first-class Arm device by publishing device status and heartbeats and responding to orchestrator commands.

See the project root [README](../../README.md) for overall architecture and how this example fits in.

## Contents

- [Example Description](#example-description)
- [Setup and Installation](#setup-and-installation)
- [Run the Example](#run-the-example)
- [Button and Stick Mappings](#button-and-stick-mappings)
- [Notes on Behavior](#notes-on-behavior)

## Example Description

This example implements an Xbox gamepad-based controller for the surgical robot arm. The system consists of:

### Main Application

The `xbox_controller.py` application reads Xbox controller input and publishes DDS messages:

- Registers DDS types (DeviceStatus, DeviceHeartbeat, DeviceCommand, MotorControl) with Connext using `DdsUtils`.
- Creates a DomainParticipant from the configured QoS profiles and finds the pre-configured DataWriters/DataReaders using the FQNs in `DdsUtils`.
- Publishes an initial `DeviceStatus` indicating the Arm is ON, and runs a background heartbeat writer thread publishing `DeviceHeartbeat` messages.
- Subscribes to `DeviceCommand` from the Orchestrator and reacts to START, PAUSE, and SHUTDOWN commands (updating `DeviceStatus` accordingly).
- Reads controller inputs via `pygame` (hats and stick axes) and writes `MotorControl` messages for commanded motors.

### Launch Script

The [`launch_arm_xbox.sh`](./launch_arm_xbox.sh) helper script starts the Xbox controller with the appropriate environment and QoS profiles.

## Setup and Installation

### 1. Install Dependencies

***This example is best run from a Docker container running the image from [containers/examples/](./../containers/examples/Dockerfile). Currently, the example is not designed to be run directly on a host machine and will fail to launch using the script.***

*Refer to [1. Prerequisites](./../README.md#1-prerequisites) to build and start the examples container.*

This example uses:

- Python 3
- [pygame](https://www.pygame.org/wiki/GettingStarted) (for controller input)
- [RTI Connext DDS Python API](https://community.rti.com/static/documentation/developers/get-started/pip-install.html#python-installation) (`rti.connextdds`)
- The repository `Types` and `DdsUtils` modules (included in [modules/01-operating-room/src](./../../modules/01-operating-room/src/))

## Run the Example

### 1. Connect Controller

Ensure your Xbox controller is connected and recognized by the OS.

### 2. Start the examples container

```bash
# Ensure $RTI_LICENSE_FILE is set, or the applications may fail to start.
docker run --rm -it \
    --network host \
    -e DISPLAY \
    -e SDL_AUDIODRIVER=dummy \
    --device=/dev/ttyUSB0 \
    --privileged \
    --hostname rtimedtech \
    --name rtimedtechra \
    -v $HOME/.Xauthority:/root/.Xauthority \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v $RTI_LICENSE_FILE:/root/rti_license.dat \
    connext:medtech_ra \
    bash
```

### 3. Start the Controller

Start the controller app using the provided script from the examples container:

```bash
cd ~/medtech_ra/modules/01-operating-room
./scripts/launch_arm_xbox.sh
```

>**Observe:** The controller will publish motor control commands based on gamepad input. The app acts like any other managed device in the architecture: it sends heartbeats and status updates and listens for orchestrator commands so the Orchestrator can start, pause, or shutdown the Arm as part of a larger scenario.

## Button and Stick Mappings

The Xbox controller inputs map to specific motor controls:

| Controller Input | Motor | Direction
| ---------------- | ----- | ---------
| D-pad X (left)   | `BASE` | decrement
| D-pad X (right)  | `BASE` | increment
| D-pad Y (up)     | `SHOULDER` | increment
| D-pad Y (down)   | `SHOULDER` | decrement
| Left stick X (left) | `WRIST` | decrement
| Left stick X (right) | `WRIST` | increment
| Left stick Y (up) | `ELBOW` | increment (polarity inverted)
| Left stick Y (down) | `ELBOW` | decrement (polarity inverted)
| Right stick Y (up) | `HAND` | increment
| Right stick Y (down) | `HAND` | decrement

*Note: The implementation inverts the Elbow polarity (up vs down) to match the intended motion (see `xbox_controller.py` for details).*

## Notes on Behavior

- The app publishes `MotorControl` messages based on axis/hats polarity.
- D-pad values are read from `joystick.get_hat(0)` when available; hat polarity may vary between controllers.
- If no controller is detected, the app exits with `No joystick detected.` Ensure your controller is connected and recognized by the OS.
- Button/hat/axis indices and polarity may differ between controllers. Use `joystick.get_numbuttons()`, `joystick.get_numhats()`, and `joystick.get_numaxes()` in an interactive session to verify.
- For headless/no-sound setups, use `-e SDL_AUDIODRIVER=dummy` in the docker command to suppress SDL sound initialization errors.
