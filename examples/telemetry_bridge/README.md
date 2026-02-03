# Telemetry Bridge — RTI MedTech Reference Architecture

This example implements a telemetry bridge (Digital Twin) for the RTI MedTech
Reference Architecture. The bridge listens to `MotorControl` commands on the
Arm domain, updates an internal simulated model of motor angles, and publishes
simulated `MotorTelemetry` data to the `topic/MotorTelemetry` topic on **domain
6** using a separate DomainParticipant. It also participates as a first-class
Arm device by publishing device status and heartbeats and responding to
orchestrator commands.

See the project root [README](/README.md) for overall architecture and how this example fits
in.

Contents
- `telemetry_app.py`: main application that subscribes to motor control and
  publishes simulated telemetry data.

Dependencies
- Python 3
- RTI Connext DDS Python API (`rti.connextdds`)
- RTI IDL Python helpers (`rti.idl`) for the telemetry struct
- The repository `Types` and `DdsUtils` modules (included under `examples`)

How it works (code overview)
- Declares a Python `idl.struct` mapping for `SurgicalRobot::MotorTelemetry` and
  assigns it to `SurgicalRobot.MotorTelemetry`.
- Registers DDS types (DeviceStatus, DeviceHeartbeat, DeviceCommand,
  MotorControl, MotorTelemetry) with Connext using `DdsUtils`.
- Creates a DomainParticipant for the Arm domain (via QoS provider) to read
  `MotorControl` and publish `DeviceStatus`/heartbeats.
- Creates a second DomainParticipant on **domain 6** and a `topic/MotorTelemetry`
  topic to publish simulated telemetry data from the Digital Twin.
- Subscribes to `MotorControl` and updates an internal `angles` map when
  INCREMENT/DECREMENT commands are received.
- Runs a background telemetry writer thread that periodically publishes
  `MotorTelemetry` samples with fields: `position_deg`, `speed_rpm` (unused in
  the current implementation), `current_mA`, `voltage_V`, and `temp_c`.

Telemetry outputs and topic
- Topic: `topic/MotorTelemetry` on **domain 6**
- Published fields (per sample):
  - `id`: motor identifier (BASE, SHOULDER, ELBOW, WRIST, HAND)
  - `position_deg`: current simulated angular position in degrees
  - `speed_rpm`: reserved for future use (not actively computed in the default example)
  - `current_mA`: simulated current consumption (randomized within a small range)
  - `voltage_V`: simulated supply voltage (small randomized variation)
  - `temp_c`: simulated temperature in Celsius
- Update frequency: 0.5 seconds by default (see `write_telemetry()` loop)

Notes on behavior
- The bridge maintains an internal model of motor positions and updates them
  in response to `MotorControl` INCREMENT/DECREMENT messages.
- Telemetry is published from a distinct DomainParticipant on domain 6 to
  demonstrate cross-domain telemetry publishing and to keep telemetry traffic
  segregated from control traffic.
- The bridge also behaves as any other managed device in the architecture: it
  publishes DeviceStatus and DeviceHeartbeat and listens for Orchestrator
  `DeviceCommand`s (START, PAUSE, SHUTDOWN) to change device state.

Running
1. Ensure the NDDS_QOS_PROFILES environment variable (or other RTI configuration)
   points to the project's QoS XML files.
2. Install dependencies: ensure RTI Connext DDS Python bindings are present and
   `rti.idl` is available.
3. Start the bridge with the included script or directly with:

```bash
./scripts/launch_telemetry_app.sh
```

Tips
- If you want higher or lower telemetry frequency, change the sleep delay in
  `write_telemetry()` (default 0.5s).
- This example uses randomized telemetry values for current/voltage/temperature
  to simulate realistic but synthetic sensor output.

Files
- See [/examples/telemetry_bridge/telemetry_app.py](telemetry_app.py) for the
  implementation and details.
