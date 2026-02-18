# Examples - RTI MedTech Reference Architecture

This folder contains runnable example applications demonstrating how devices and services participate as first-class citizens in the RTI MedTech Reference Architecture. Each example includes a README with implementation details, button/axis mappings (where applicable), and step-by-step run instructions.

See the project root [README.md](../README.md) for the overall architecture and examples of how these pieces interact.

## Contents

- [Example Applications](#example-applications)
- [Running Examples](#running-examples)
- [Tips](#tips)

## Example Applications

### [Joystick Controller](./joystick_controller/)

Joystick Arm controller implementation (uses `pygame`).
See the example's README for details and button/stick mappings.

### [Xbox Controller](./xbox_controller/)

Xbox gamepad Arm controller implementation (uses `pygame`).
See the example's README for details and button/stick mappings.

### [lss_robot](./lss_robot/)

LynxMotion LSS serial-servo Robot Arm controller that publishes real `MotorTelemetry` to `topic/MotorTelemetry` on domain 6.
See the example's README for hardware setup and safety notes.

### [telemetry_bridge](./telemetry_bridge/)

Digital Twin bridge that subscribes to `MotorControl` and publishes simulated `MotorTelemetry` to `topic/MotorTelemetry` on domain 6.
See the example's README for details.

### [WIS](./WIS/) (Web Integration Service)

RTI Web Integration Service example that hosts a web UI which publishes `MotorControl` commands via WebSockets.
See the example's README for configuration and UI behavior.

### [CANoe](./CANoe/)

Vector CANoe Integration example that leverages CANoe's native Python scripting capabilities to create a bidirectional bridge between multiple DDS domains, enabling both topic translation and domain bridging while providing real-time monitoring and control capabilities.
See the example's README for details.

## Running Examples

### 1. Prerequisites

***Unless otherwise noted in the example's README, these examples are best run from a Docker container running the image from [containers/examples/](./../containers/examples/Dockerfile). Currently, the examples (except Web Integration Service) are not designed to be run directly on a host machine and will likely fail to launch.***

To build the image:

```bash
docker build \
    -t connext:medtech_ra \
    -f containers/examples/Dockerfile \
    --build-arg RTI_LICENSE_AGREEMENT_ACCEPTED=accepted \
    --build-arg CONNEXT_VERSION=7.3.0 \
    .
```

To start the container:

```bash
# Ensure $RTI_LICENSE_FILE is set, or the applications may fail to start.
docker run --rm -it \
    --network host \
    -e DISPLAY \
    -e SDL_AUDIODRIVER=dummy \
    --device=/dev/ttyUSB0 \
    --privileged \
    --hostname rtimedtech \
    -v $HOME/.Xauthority:/root/.Xauthority \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v $RTI_LICENSE_FILE:/root/rti_license.dat connext:medtech_ra \
    bash
```

Read the README in the example you intend to run for per-example prerequisites and run instructions (e.g., Python packages, hardware drivers, or Web Integration Service setup).

### 2. Launch

Use the included `launch_*` scripts where present from inside the container to start example apps with the intended settings.

The docker image copies the necessary sources and launch scripts into the `01-operating-room` module folder for convenience.
Be sure to cd to the directory inside the container before launching example applications.

```none
medtech_ra/modules/01-operating-room/scripts/
|-- launch_OR_apps.sh
|-- launch_all.sh
|-- launch_arm_and_patient_monitor.sh
|-- launch_arm_controller.sh
|-- launch_arm_joystick.sh
|-- launch_arm_xbox.sh
|-- launch_robot_app.sh
`-- launch_telemetry_app.sh
```

## Tips

- Don't have physical hardware to simulate telemetry? Use [telemetry_bridge](./telemetry_bridge/) - this helps validate orchestration and telemetry-receiving applications without the robot.
- Pay attention to controller axis/hat indices and button mappings - these may differ between controllers.
- For hardware examples, verify serial port names and permissions before running (e.g., `/dev/ttyUSB0` on Linux).
