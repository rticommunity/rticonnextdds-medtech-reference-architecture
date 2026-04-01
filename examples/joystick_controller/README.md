# Joystick Controller — RTI MedTech Reference Architecture

This example implements a joystick-based Arm controller for the RTI MedTech Reference Architecture. The controller reads a standard gamepad/joystick through `pygame`, publishes motor control commands to the DDS `MotorControl` topic, and participates as a first-class Arm device by publishing device status and heartbeats and responding to orchestrator commands.

See the project root [README](../../README.md) for overall architecture and how this example fits in.

## Contents

- [Example Description](#example-description)
- [Setup and Installation](#setup-and-installation)
- [Run the Example](#run-the-example)
- [Button and Stick Mappings](#button-and-stick-mappings)
- [Notes on Behavior](#notes-on-behavior)

## Example Description

This example implements a joystick-based controller for the surgical robot arm. The system consists of:

### Main Application

The `joystick_controller.py` application reads joystick input and publishes DDS messages:

- Registers DDS types (DeviceStatus, DeviceHeartbeat, DeviceCommand, MotorControl) with Connext using `DdsUtils`.
- Creates a DomainParticipant from the configured QoS profiles and finds the pre-configured DataWriters/DataReaders using the FQNs in `DdsUtils`.
- Publishes an initial `DeviceStatus` indicating the Arm is ON, and runs a background heartbeat writer thread publishing `DeviceHeartbeat` messages.
- Subscribes to `DeviceCommand` from the Orchestrator and reacts to START, PAUSE, and SHUTDOWN commands (updating `DeviceStatus` accordingly).
- Reads joystick buttons and axes via `pygame` and writes `MotorControl` messages for commanded motors.

### Launch Script

The `launch_arm_joystick.sh` helper script starts the joystick controller with the appropriate environment and QoS profiles.

## Setup and Installation

### 1. Install Dependencies

***This example is best run from a Docker container running the image from [containers/examples/](./../containers/examples/Dockerfile). Currently, the example is not designed to be run directly on a host machine and will fail to launch using the script.***

*Refer to [1. Prerequisites](./../README.md#1-prerequisites) to build and start the examples container.*

This example uses:

- Python 3
- [pygame](https://www.pygame.org/wiki/GettingStarted) (for joystick input)
- [RTI Connext DDS Python API](https://community.rti.com/static/documentation/developers/get-started/pip-install.html#python-installation) (`rti.connextdds`)
- The repository `Types` and `DdsUtils` modules (included in [modules/01-operating-room/src](./../../modules/01-operating-room/src/))

## Run the Example

### 1. Connect Controller

Ensure your joystick/gamepad is connected and recognized by the OS.

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

Start the controller app using the provided script:

```bash
cd ~/medtech_ra/modules/01-operating-room
./scripts/launch_arm_joystick.sh
```

>**Observe:** The controller will publish motor control commands based on joystick input. The app acts like any other managed device in the architecture: it sends heartbeats and status updates and listens for orchestrator commands so the Orchestrator can start, pause, or shutdown the Arm as part of a larger scenario.

## Button and Stick Mappings

The joystick inputs map to specific motor controls:

| Controller Input | Motor | Direction
| ---------------- | ----- | ---------
| X-Axis (left) | `BASE` | decrement
| X-Axis (right) | `BASE` | increment
| `PRIMARY_LEFT` (button 3) + Y-Axis (up) | `SHOULDER` | increment
| `PRIMARY_LEFT` (button 3) + Y-Axis (down) | `SHOULDER` | decrement
| `PRIMARY_RIGHT` (button 0) + Y-Axis (up) | `ELBOW` | increment
| `PRIMARY_RIGHT` (button 0) + Y-Axis (down) | `ELBOW` | decrement
| `SECONDARY_LEFT` (button 4) + Y-Axis (up) | `WRIST` | increment
| `SECONDARY_LEFT` (button 4) + Y-Axis (down) | `WRIST` | decrement
| `SECONDARY_RIGHT` (button 1) + X-Axis (left) | `HAND` | decrement
| `SECONDARY_RIGHT` (button 1) + X-Axis (right) | `HAND` | increment

*Note: Button indices are based on the joystick used when this example was written; indexes may differ between controllers.*

## Notes on Behavior

- The app publishes `MotorControl` messages based on axis polarity and the currently active target motor (determined by the pressed modifier button).
- If no joystick is detected, the app exits with `No joystick detected.` Ensure your joystick/gamepad is connected and recognized by the OS.
- Button indices may differ between controllers. Use `joystick.get_numbuttons()` and `joystick.get_axis()` in an interactive session to verify.
