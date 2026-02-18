# LSS Robot — RTI MedTech Reference Architecture

This example implements a Robot Arm application that controls a LynxMotion LSS serial-servo arm and publishes real servo telemetry to the MedTech Reference Architecture. The application reads motor control commands from the `MotorControl` topic and publishes `MotorTelemetry` samples on the `topic/MotorTelemetry` topic on **Domain 6**. It participates as a first-class Arm device by publishing device status and heartbeats and responding to Orchestrator commands.

See the project root [README.md](../../README.md) for overall architecture and how this example fits in.

## Contents

- [Example Description](#example-description)
- [Setup and Installation](#setup-and-installation)
- [Run the Example](#run-the-example)
- [Telemetry Outputs and Topic](#telemetry-outputs-and-topic)
- [Notes on Behavior](#notes-on-behavior)
- [Hands-On: Going Further](#hands-on-going-further)

## Example Description

This example implements a physical robot arm controller using LynxMotion LSS serial servos. The system consists of:

### Main Application

The `lss_robot_app.py` application controls LynxMotion servos and publishes telemetry:

- Declares `SurgicalRobot::MotorTelemetry` via a Python `idl.struct` mapping and assigns it to `SurgicalRobot.MotorTelemetry`.
- Registers DDS types (DeviceStatus, DeviceHeartbeat, DeviceCommand, MotorControl, MotorTelemetry) with Connext using `DdsUtils`.
- Uses a QoS-configured DomainParticipant (via `DdsUtils.arm_dp_fqn`) for the Arm domain and creates a second `DomainParticipant(6)` for publishing telemetry to `topic/MotorTelemetry`.
- Hardware setup: opens the LynxMotion serial bus and initializes `LSS(i)` for each servo, resets axes and moves servos to a safe initial position.
- Subscribes to `MotorControl` and applies INCREMENT/DECREMENT commands to physical servos, respecting per-servo speed (`maxrpm`) and movement limits.
- Reads physical servo state (position, speed, current, voltage, temperature) and publishes `MotorTelemetry` samples on Domain 6 at a configurable frequency (default 0.5s).

### Launch Script

The `launch_robot_app.sh` helper script sets up environment variables and starts the application.

## Setup and Installation

### 1. Install Dependencies

***This example is best run from a Docker container running the image from [containers/examples/](./../containers/examples/Dockerfile). Currently, the example is not designed to be run directly on a host machine and will fail to launch using the script.***

*Refer to [1. Prerequisites](./../README.md#1-prerequisites) to build and start the examples container.*

This example uses:

- Python 3
- [LynxMotion LSS Python Library](https://github.com/Lynxmotion/LSS_PRO_Library_Python)
- [RTI Connext DDS Python API](https://community.rti.com/static/documentation/developers/get-started/pip-install.html#python-installation) (`rti.connextdds`)
- The repository `Types` and `DdsUtils` modules (included in [modules/01-operating-room/src](./../../modules/01-operating-room/src/))

### 2. Configure Hardware

Ensure the serial port configured in the app (default `/dev/ttyUSB0`) is correct for your hardware and that the user has permission to access it.

On Linux, add your user to the appropriate group or use `udev` rules. On Windows, set the correct COM port.

## Run the Example

### 1. Connect Hardware

Ensure your LynxMotion LSS servos are connected and powered.

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

### 3. Start the Application

Start the application using the provided script:

```bash
cd ~/medtech_ra/modules/01-operating-room
./scripts/launch_robot_app.sh
```

>**Observe:** The application will control the physical servos based on motor control commands and publish real telemetry to `topic/MotorTelemetry` on Domain 6. The app acts like any other managed device in the architecture: it sends heartbeats and status updates and listens for orchestrator commands so the Orchestrator can start, pause, or shutdown the Arm as part of a larger scenario.

## Telemetry Outputs and Topic

The application publishes telemetry on the following topic:

- **Topic**: `topic/MotorTelemetry` on **Domain 6**

Published fields (per sample):

| Field | Description
| ----- | -----------
| `id` | Motor identifier (BASE, SHOULDER, ELBOW, WRIST, HAND)
| `position_deg` | Current servo position in degrees
| `speed_rpm` | Current servo speed in RPM
| `current_mA` | Current draw in milliamps
| `voltage_V` | Voltage in volts
| `temp_c` | Temperature in degrees Celsius

Update frequency: 0.5 seconds by default (see `write_telemetry()` in the application).

## Notes on Behavior

- The app inverts ELBOW and WRIST directions when mapping control commands to physical movement to match the arm's mechanical conventions. Shoulder and elbow telemetry position may be inverted to align with the digital twin convention.
- Servo movement respects configured `limits` and `maxrpm` per axis to prevent unsafe motion.
- If you don't have the hardware available, run the `telemetry_bridge` Digital Twin example to simulate telemetry and validate orchestration and telemetry consumers before connecting the physical arm.
- Verify the serial port name and permissions before running (e.g., `/dev/ttyUSB0` on Linux).
- Use conservative `maxrpm` and `limits` when first testing physical hardware.

## Hands-On: Going Further

### 1. Telemetry Validation with RTI DDS Spy

Quickly validate with RTI DDS Spy that the telemetry app is publishing data on Domain 6.

```bash
$NDDSHOME/bin/rtiddsspy \
  -domainId 6 \
  -topicRegex "topic/MotorTelemetry" \
  -mode USER \
  -printSample
```

Or with public Docker image:

```bash
docker run -it --rm \
  --network host \
  --name=dds_spy \
  rticom/dds-spy:latest \
  -domainId 6 \
  -topicRegex "topic/MotorTelemetry" \
  -mode USER \
  -printSample
```
