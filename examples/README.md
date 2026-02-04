# Examples — RTI MedTech Reference Architecture

This folder contains runnable example applications demonstrating how devices
and services participate as first-class citizens in the RTI MedTech Reference
Architecture. Each example includes a README with implementation details,
button/axis mappings (where applicable), and step-by-step run instructions.

See the project root [README.md](/README.md) for the overall architecture and examples of how
these pieces interact.

Contents
- `joystick_controller/` — Joystick Arm controller (uses `pygame`). See
  `joystick_controller/README.md` for full details and button/stick mappings.
- `xbox_controller/` — XBox gamepad Arm controller. See
  `xbox_controller/README.md` for mappings and tips.
- `lss_robot/` — LynxMotion LSS serial-servo Robot Arm controller that publishes
  real `MotorTelemetry` to `topic/MotorTelemetry` on domain 6. See
  `lss_robot/README.md` for hardware setup and safety notes.
- `telemetry_bridge/` — Digital Twin bridge that subscribes to `MotorControl`
  and publishes simulated `MotorTelemetry` to `topic/MotorTelemetry` on domain 6.
  See `telemetry_bridge/README.md` for details.
- `WIS/` — Web Integration Service example that hosts a web UI which publishes
  `MotorControl` commands via WebSockets. See `WIS/readme.md` for WIS
  configuration and UI behavior.
- `CANoe/` — Vector CANoe Integration example that leverages CANoe's native Python
   scripting capabilities to create a bidirectional bridge between multiple DDS
   domains, enabling both topic translation and domain bridging while providing
   real-time monitoring and control capabilities.

Running
1. Read the README in the example you intend to run for per-example prerequisites
   and run instructions (e.g., Python packages, hardware drivers, or WIS setup).
2. Ensure `NDDS_QOS_PROFILES` points to the repository QoS XML files and any
   required environment variables are set (see each example's README).
3. Use the included `launch_*` scripts where present to start example apps with
   the intended settings.

Tips
- Use `telemetry_bridge` to simulate telemetry when physical hardware is not
  available — this helps validate orchestration and telemetry-receiving
  applications without the robot.
- Pay attention to controller axis/hat indices and button mappings — these may
  differ between controllers.
- For hardware examples, verify serial port names and permissions before
  running (e.g., `/dev/ttyUSB0` on Linux).

Files
- See each example directory for a complete `README.md`, example scripts, and
  implementation details.

