# Web Integration Service — RTI MedTech Reference Architecture

This configuration demonstrates how the RTI Web Integration Service (WIS)
hosts a remote web page that sends MotorControl commands into the MedTech
Reference Architecture over WebSockets. The WIS configuration (`wis_service.xml`)
exposes a `MotorControlApp` which registers the `SurgicalRobot::MotorControl`
type and publishes `t/MotorControl` on the Arm domain. A remote web page
(`examples/WIS/html/robot_arm.html`) uses WIS REST + WebSocket endpoints to
connect and issue real-time motor control samples.

See the project root [README.md](/README.md) for overall architecture and how this example fits
in.

Contents
- `wis_service.xml`: WIS configuration that defines the web application,
  registers types, and exposes a `MotorControlWriter` for the `t/MotorControl` topic.
- `html/robot_arm.html`: web UI that connects to WIS and sends MotorControl
  commands via WebSocket.

Dependencies
- RTI Web Integration Service (WIS)
- RTI Connext DDS (to run in the same network or be reachable from WIS)
- Browser with WebSocket support

How it works (configuration overview)
- `wis_service.xml` declares the MotorControl type (`SurgicalRobot::MotorControl`)
  and a `web_integration_service` named `MotorControlWebApp`.
- A domain participant named `MotorControlParticipant` is configured on **domain
  0**, registers the MotorControl type, and creates the `t/MotorControl` topic.
- A publisher and a `MotorControlWriter` data writer are defined; the writer uses
  a `DataFlowLibrary::Command` QoS profile configured for reliable, keep-last-1
  command delivery.
- The WIS exposes REST endpoints to create WebSocket connections and a WebSocket
  endpoint that the web UI can connect to. The web UI issues publish requests
  over the WebSocket and WIS translates these into DDS `MotorControl` samples
  on `t/MotorControl`.

Web control mappings (UI → MotorControl)
- Web page buttons send short, repeated MotorControl commands when pressed.
- Each control button encodes a target motor and a direction (increment /
  decrement) which WIS publishes as `MotorControl` messages to `t/MotorControl`.
- Example mappings from the web UI:
  - Base: `ccw` / `cw` → `Motors.BASE` (decrement / increment)
  - Shoulder: `up` / `down` → `Motors.SHOULDER` (increment / decrement)
  - Elbow: `up` / `down` → `Motors.ELBOW`
  - Wrist: `up` / `down` → `Motors.WRIST`
  - Gripper: `open` / `close` → `Motors.HAND`

Routing Service integration
- When the remote web host cannot directly reach the Arm domain, the Routing
  Service (see `modules/03-remote-teleoperation`) can be configured to route
  the WIS-published `MotorControl` samples into local domains. Using the
  Routing Service configuration provided in `03-remote-teleoperation` permits
  control samples published by WIS (remote) to be published locally for use by
  local Arm controllers.

Running
1. Start WIS with the WIS configuration and enable WebSockets (example):

```bash
./scripts/launch_wis.sh
```

2. Ensure the WIS can reach the DDS domain where `t/MotorControl` is defined
   (or configure the Routing Service to bridge/route traffic as needed).
3. Open `robot_arm.html` in a browser, and use the UI to send
   MotorControl commands.

Files
- See `examples/WIS/xml_config/wis_service.xml` for the exact WIS deployment
  configuration and `examples/WIS/html/robot_arm.html` for the web UI that
  produces MotorControl messages via WIS.
