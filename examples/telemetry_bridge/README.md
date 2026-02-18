# Telemetry Bridge — RTI MedTech Reference Architecture

This example implements a telemetry bridge (Digital Twin) for the RTI MedTech Reference Architecture. The bridge listens to `MotorControl` commands on the Arm domain, updates an internal simulated model of motor angles, and publishes simulated `MotorTelemetry` data to the `topic/MotorTelemetry` topic on **Domain 6** using a separate DomainParticipant. It also participates as a first-class Arm device by publishing device status and heartbeats and responding to orchestrator commands.

See the project root [README.md](../../README.md) for overall architecture and how this example fits in.

## Contents

- [Example Description](#example-description)
- [Setup and Installation](#setup-and-installation)
- [Run the Example](#run-the-example)
- [Telemetry Outputs and Topic](#telemetry-outputs-and-topic)
- [Notes on Behavior](#notes-on-behavior)
- [Hands-On: Going Further](#hands-on-going-further)

## Example Description

This example implements a telemetry bridge (Digital Twin) that simulates motor telemetry for the surgical robot arm. The system consists of:

### Main Application

The `telemetry_app.py` application simulates motor telemetry and publishes DDS messages:

- Declares a Python `idl.struct` mapping for `SurgicalRobot::MotorTelemetry` and assigns it to `SurgicalRobot.MotorTelemetry`.
- Registers DDS types (DeviceStatus, DeviceHeartbeat, DeviceCommand, MotorControl, MotorTelemetry) with Connext using `DdsUtils`.
- Creates a DomainParticipant for the Arm domain (via QoS provider) to read `MotorControl` and publish `DeviceStatus`/heartbeats.
- Creates a second DomainParticipant on **Domain 6** and a `topic/MotorTelemetry` topic to publish simulated telemetry data from the Digital Twin.
- Subscribes to `MotorControl` and updates an internal `angles` map when INCREMENT/DECREMENT commands are received.
- Runs a background telemetry writer thread that periodically publishes `MotorTelemetry` samples with fields: `position_deg`, `speed_rpm`, `current_mA`, `voltage_V`, and `temp_c`.

### Launch Script

The `launch_telemetry_app.sh` helper script sets up environment variables and starts the application.

## Setup and Installation

### 1. Install Dependencies

***This example is best run from a Docker container running the image from [containers/examples/](./../containers/examples/Dockerfile). Currently, the example is not designed to be run directly on a host machine and will fail to launch using the script.***

*Refer to [1. Prerequisites](./../README.md#1-prerequisites) to build and start the examples container.*

This example uses:

- Python 3
- [RTI Connext DDS Python API](https://community.rti.com/static/documentation/developers/get-started/pip-install.html#python-installation) (`rti.connextdds`)
- The repository `Types` and `DdsUtils` modules (included in [modules/01-operating-room/src](./../../modules/01-operating-room/src/))

## Run the Example

### 1. Start the examples container

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

### 2. Start the Application

Start the application using the provided script:

```bash
cd ~/medtech_ra/modules/01-operating-room
./scripts/launch_telemetry_app.sh
```

>**Observe:** The bridge will publish simulated telemetry to `topic/MotorTelemetry` on Domain 6 based on motor control commands. The app acts like any other managed device in the architecture: it sends heartbeats and status updates and listens for orchestrator commands so the Orchestrator can start, pause, or shutdown the bridge as part of a larger scenario.

## Telemetry Outputs and Topic

The application publishes telemetry on the following topic:

- **Topic**: `topic/MotorTelemetry` on **Domain 6**

Published fields (per sample):

| Field | Description
| ----- | -----------
| `id` | Motor identifier (BASE, SHOULDER, ELBOW, WRIST, HAND)
| `position_deg` | Current simulated angular position in degrees
| `speed_rpm` | Reserved for future use (not actively computed in the default example)
| `current_mA` | Simulated current consumption in milliamps (randomized within a small range)
| `voltage_V` | Simulated supply voltage in volts (small randomized variation)
| `temp_c` | Simulated temperature in degrees Celsius

Update frequency: 0.5 seconds by default (see `write_telemetry()` in the application).

## Notes on Behavior

- The bridge maintains an internal model of motor positions and updates them in response to `MotorControl` INCREMENT/DECREMENT messages.
- Telemetry is published from a distinct DomainParticipant on Domain 6 to demonstrate cross-domain telemetry publishing and to keep telemetry traffic segregated from control traffic.
- The bridge also behaves as any other managed device in the architecture: it publishes DeviceStatus and DeviceHeartbeat and listens for Orchestrator `DeviceCommand`s (START, PAUSE, SHUTDOWN) to change device state.
- If you want higher or lower telemetry frequency, change the sleep delay in `write_telemetry()` (default 0.5s).
- This example uses randomized telemetry values for current/voltage/temperature to simulate realistic but synthetic sensor output.

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
