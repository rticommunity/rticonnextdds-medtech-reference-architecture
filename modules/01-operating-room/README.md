# Module 01: Digital Operating Room

Module 01 simulates a Digital Operating Room.

The applications have been tested to work in Debian-based environments with a GUI, including those in [WSL2 with GUI support](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps#install-support-for-linux-gui-apps) (Windows 10 and 11), as well as on macOS.

All run commands in this README are launched from the repository root. The project-level `launch.py` script is the runtime entrypoint; there is no module-local launcher in this folder.

## Contents

- [Module Description](#module-description)
- [Setup and Installation](#setup-and-installation)
- [Run the Demo](#run-the-demo)
- [Hands-On: Going Further](#hands-on-going-further)
- [Next Steps](#next-steps)

## Module Description

This module implements five logical Connext applications using the MedTech Reference Architecture to simulate a digital operating room. The Arm Controller has an optional Xbox/gamepad implementation. You can find a diagram below:

![image](../../resource/images/module-01-diagram-digital-OR.svg)

### Patient Sensor

The *Patient Sensor* application's primary function is to publish simulated patient vitals data on Topic `t/patient/vitals`.

It has no user interface.

### Patient Monitor

The *Patient Monitor* application's primary function is to subscribe to simulated patient vitals data on Topic `t/patient/vitals`.

The RTI Demo UI browser frontend displays synthetic ECG, plethysmograph, and capnography waveforms with numeric vital readouts.

### Arm

The *Arm* application simulates a six-axis articulated arm with fixed-length
links, a spherical wrist, an oriented TCP, and parallel jaws. It integrates
base-frame velocity on `t/robot/arm/control` and signed jaw-opening rate on
`t/robot/tool/control`, using lightweight FK/IK with joint/reach limits.

The existing RTI Demo UI Scene3D renderer displays an original articulated GLB
with persistent orbit/zoom and observed pose/gap readouts. Its connection badge
indicates a matched arm-control DDS writer, not a physical Xbox connection.
Readiness is separate from connectivity and generic device lifecycle.

### Arm Controller

Both *Arm Controller* variants publish complete arm/tool rate streams at 50 Hz,
including zeros while idle, and display actual arm readiness and telemetry.

The C++ frontend provides six base-frame translation/rotation controls, signed
jaw controls, and run/stop demonstration motion. The Xbox adapter maps sticks,
triggers, bumpers, and buttons to the same hardware-independent data model.
Neither controller predicts actual arm execution from its own command state.

### Orchestrator

The *Orchestrator* application primarily acts as a system application state observer and controller. It detects the presence and current status of other system applications on Topics `t/device/heartbeat` and `t/device/status`, respectively. It can also command device-level actions, such as "Start" or "Shut Down" on Topic `t/device/command`.

The RTI Demo UI frontend displays current device statuses, presents buttons to administer device commands, and shows an activity stream of observed events.

All graphical apps serve the same local web frontend. Browser mode is the
default; `--ui-mode native` opens that frontend in the RTI Demo UI embedded
webview rather than changing its renderer to native widgets.

## Setup and Installation

Complete the shared setup in the root [Quick Start](../../README.md#quick-start) section. That covers prerequisites, environment setup, the project-level build, and security artifact generation.

Module-specific notes:

- If you plan to use secure mode, make sure the security artifacts from the root README have been generated.
- There is no module-local build or launch script; use the project-level `build.py` and `launch.py` scripts from the repository root.
- The Xbox/gamepad variant is optional at runtime. Its Pygame Community Edition dependency is installed with the standard root `requirements.txt`.
- Native webview mode is optional. Python requires `pip install -r requirements-native.txt`; on Linux with Python 3.13+, create the virtual environment with `--system-site-packages` so it can import the system `python3-gi` binding. C++ requires configuring with `-DRTI_DEMO_BUILD_NATIVE_WEBVIEW=ON`; the SDK root integration builds the core and optional native companion together. Native windows use the project RTI logo; Windows uses its ICO variant. Install the platform prerequisites described in the root README and the RTI Demo UI native-webview guide.
- In native mode, the C++ System Orchestrator opens at 1600x950 and the Arm Controller at 1400x900; both windows remain resizable.

## Run the Demo

> Important: Run the commands below from the repository root. `launch.py` lives at the project root and is the single runtime entrypoint for this project.

### 1. Launch the applications

Run operating room applications from the repository root:

```bash
# From the repository root
python3 launch.py 01-operating-room
```

Open the local URL printed by each graphical app. To use an embedded desktop
webview instead of an external browser, add `--ui-mode native`.

To run with security enabled, use the `-s` option:

```bash
# From the repository root
python3 launch.py 01-operating-room -s
```

*This script does the following:*

1. Set `NDDS_QOS_PROFILES` environment variable to load the appropriate XML configuration files (QoS Profiles, Domains, DomainParticipants).

2. Launch the application executables.

*Note, applications can be launched individually by logical app name, e.g. `python3 launch.py 01-operating-room Arm PatientMonitor`. Refer to [module.json](./module.json) for app roles, variant choices, and QoS configuration.*

### Use the Xbox/gamepad Arm Controller

The simulated Arm Controller remains the default and requires no gamepad. Pygame CE is included in the standard project requirements. To select the Xbox/gamepad implementation, run:

```bash
python3 launch.py 01-operating-room --variant ArmController=xbox
```

The selection also applies to scenarios that launch the Arm Controller:

```bash
python3 launch.py --scenario or-all --variant ArmController=xbox
```

The gamepad app uses Pygame CE only to read SDL controller input; its status page
is served by RTI Demo UI. Both controller variants publish complete
`Robot::Arm::TeleopControl` rates on `t/robot/arm/control` and signed
`Robot::Tool::ParallelJawControl` rates on `t/robot/tool/control`:

| Xbox control | Base-frame control | Effect |
| --- | --- | --- |
| Left stick right / left | Positive / negative linear X | Proportional sideways TCP motion |
| Left stick forward / back | Positive / negative linear Y | Move across the workspace |
| Right stick up / down | Positive / negative linear Z | Move up / down |
| Hold LB + right stick right / left | Positive / negative angular Y | Rotate about fixed base Y |
| Hold LB + right stick up / down | Negative / positive angular X | Rotate about fixed base X |
| Hold LB + right / left trigger | Positive / negative angular Z | Rotate about fixed base Z |
| D-pad right-left / up-down | Linear X/Y fallback | Workspace motion when the corresponding stick is neutral |
| A / B buttons | Positive / negative opening rate | Open / close parallel jaws while held |

Right-stick horizontal and the triggers have no effect unless LB is held.
While LB is held, right-stick Z translation is disabled; left-stick translation
and jaw control remain available. After releasing LB, return both right-stick
axes to their dead zone before Z translation resumes. This prevents a stick held
for rotation from immediately commanding translation. RB is unused.

This layout uses the fixed, right-handed arm base frame. Base X/Y span the
horizontal workspace and +Z is up. Neither wrist rotation nor camera orbit
changes the command axes; they are not screen-relative. Angular commands rotate
about base-oriented axes through the TCP. Rotation about base Z is not
necessarily roll around the tool shaft.

Analog magnitude is preserved after dead-zone handling; combined vectors are
bounded by the demo limits. Opposite digital inputs cancel. Both streams publish
at 50 Hz while ON, including zero rates when idle, released, or disconnected.
There is no `STOPPED` wire enum, target-width command, or special gripper-roll
axis. Browser controls provide matching press/release behavior; their input
refresh timeout stops a hold if the browser misses a release.

Orchestrator START, PAUSE, and SHUTDOWN retain their device lifecycle meanings.
Pause stops publication. Fresh rates resume after START/reconnection even when
controls remain held, subject to the rotation-to-translation neutral rule above.
With no supported
gamepad, the app stays running, reports the condition, and emits idle zeros.
Closing a browser tab does not stop its process; use `Ctrl-C` in the launcher.

### Arm model, command validity, and observed feedback

The demo has one keyed arm, `arm-1`. Linear velocity uses m/s and angular
velocity rad/s, with IDL unit annotations. Commands are relative to the
fixed **base frame**, with +Z up, for both linear and angular velocity.
The separate jaw command remains tool-local: positive jaw rate opens the total
gap symmetrically along tool X; tool +Z points along the shaft.
The demo limits are 0.05 m/s linear norm, 0.5 rad/s angular norm, 0.02 m/s
gap rate, and a 0-0.06 m gap. These are hypothetical demo values, not hardware
guarantees.

At startup, the simulator uses a raised shoulder and bent elbow, with the tool
pointing forward and 20 degrees downward. This keeps the initial posture away
from full extension and gives room for translation and rotation. It is
initialization only; no HOME action is implemented.

The Arm uses **MuJoCo + Mink**, installed by the root `requirements.txt`.
The original [MJCF model](./models/arm.xml) is authoritative for the six-axis
chain, jaw slides, link dimensions, joint ranges, velocity actuators, illustrative
inertias, gravity compensation, a coupled parallel-jaw mechanism, and demo rate
limits. No vendor meshes or robot descriptions are copied, and no URDF or ROS
installation is required.
The existing GLB generator reads its link dimensions from that model.

A 50 Hz application tick reads DDS rates independently of incoming message
handling. Each tick advances MuJoCo in substeps no longer than 2 ms. Mink solves
constrained differential IK from the **achieved** configuration at each substep.
IK joint-velocity commands are limited to 2 rad/s. Direction constraints keep
the solved TCP velocity on the requested base-frame twist: translation does not
request rotation, rotation does not request translation, and combined components
slow together rather than acquiring sideways motion. Command speed cannot be
amplified or reversed by the solver.
Regularization increases smoothly for commanded directions that approach a
singularity, avoiding an elbow crossing caused by actuator inertia. Joint-limit
approaches also slow before the mechanical range ends. An infeasible direction
holds rather than switching to another IK branch. There is no branch enumeration
or step-halving solver.

Selected base-to-forearm/wrist/tool and upper-arm-to-tool pairs use simplified
collision geometry. Mink slows commands as these parts approach one another;
MuJoCo also resolves contact for those pairs. The IK clearance target is 15 mm,
but actuator inertia and numerical integration can reduce that clearance.
Adjacent links, other self-collision pairs, and the environment are not covered.

MuJoCo's gravity-compensated velocity actuators produce the actual movement,
including short acceleration/braking transients and small integration/tracking
errors. One tendon actuator controls total jaw opening; a joint equality models
the gearing between the fingers. Mechanical travel is limited on the total gap,
not by redundant independent end stops on the coupled fingers.
Zero rates brake; they do not chase an accumulated Cartesian or joint
position target. Thus achieved speed/pose need not exactly equal the command,
and equal-duration outward/return holds need not return to the starting pose
when one direction was limited. Telemetry and scene transforms come from the
actual physics state, not the IK velocity solution.
A fixed overlay inside the scene reports reduced or held motion without moving
the header, scene, or telemetry. Moving in another direction can resume arm
motion; the jaws remain independently controllable.
Links never stretch and requested poses are not reported as achieved. This is a
demo simulation, not a physical hardware or safety guarantee. Numerical backend
failures stop the application with ERROR/FAULT and an explicit diagnostic.

Each step reads the current valid DDS rates, including previously READ samples.
Rates remain eligible until replaced or removed by the writer's 250 ms
lifespan. Reusing a valid rate advances another time interval; it does not
repeat a one-shot action. There is no application-owned active target or
duplicate command timeout. No eligible arm command brakes both arm and jaws;
no eligible tool command brakes the jaws independently. A valid zero arm
stream permits tool-only operation. Pause/START drain cached pre-transition
commands. Command loss never automatically opens the jaws.

Command QoS is best-effort, volatile, KEEP_LAST(1), with a diagnostic 50 ms
deadline. Finite lifespan is required on every command writer, including routing
and replay outputs, and is not enforced by DDS requested/offered matching.
Reader expiration uses reception time in Connext 7.7. Braking begins on the next
running tick after expiry (250 ms plus up to one 20 ms period and scheduling
jitter); delayed/republished data can start a new local validity window.
Deadlines and liveliness are diagnostics, not stopping mechanisms or safety
guarantees.

`t/robot/arm/status` reports initial/on-change readiness separately from device
lifecycle. `t/robot/arm/telemetry` carries actual base-relative TCP pose and optional
jaw gap at approximately 20 Hz. Both controllers display this DDS feedback and
telemetry freshness, not a local command prediction. Readiness is displayed as
the last known status: silence is normal for an on-change publisher and does not
expire the value. Stale telemetry indicates missing periodic feedback, not a
new readiness state or proof of the status writer's availability. The orientation quaternion
`(x,y,z,w)` maps tool vectors into base coordinates. There is no payload timestamp;
unavailable optional feedback is not replaced with zeros.

The Arm's own window labels its local pose/gap readouts **Reported telemetry**.
Its green light blinks while local telemetry publications continue; it dims
after 500 ms without a newly observed publication. This is publication activity,
not confirmation of delivery to a remote reader. These are the simulated values
the Arm publishes, not incoming controller data, so this window has no
FRESH/STALE badge. The Arm continues reporting its stationary state when the
controller disconnects. With reduced-motion preferences, the green light is
steady while publishing.

The browser and optional native webview use the pinned SDK's existing
Three.js-backed Scene3D renderer, with an original
[articulated GLB](../../resource/ui_web/models/articulated-arm.glb) and
[reproducible generator](../../resource/ui_web/generate_arm_glb.py). Drag to
orbit, right-drag or Shift-drag to pan, and scroll to zoom; two-finger touch
gestures pan and zoom. These controls and reset change only the camera, not
command frames. Telemetry sits beside the scene on wide windows and below it
on narrow windows. Model-load or WebGL
failure is explicitly reported as degraded visualization; native support depends
on the webview/platform. The same backend-derived joint transforms drive the
scene, without a second JavaScript kinematics solver.

**Reset camera** restores the initial camera angle, center, and distance. It
does not change the arm's pose and has no visual effect if the view is already
at its initial setting; an inline message confirms the camera action.
**Fit arm** centers/fits the model and its reference ring while retaining the
current viewing direction; it has no visible effect if already fitted.
The renderer's internal node-status list is hidden during normal visualization;
it remains available as diagnostic fallback if the model cannot be rendered.
**Side view** and **Top view** snap to base-relative views and fit the arm.
Camera presets remain browser-local and survive periodic pose updates; they
never change control axes or move the arm. Reset camera always returns to the
initial view, including after selecting a preset.
The SDK preserves the GLB's graphite/silver structure, blue accents, and orange
tool marker instead of repainting the model with node-status colors. Arm
readiness and faults remain visible in the status display.

The gripper palm connects both sliding fingers to the wrist. The TCP is centered
between the opposing contact pads; their inner-face separation matches the
observed total jaw gap, including zero gap when closed. The shaft ends at the
palm rather than extending into the gripping space.

This is a rigid-body/actuator simulation with illustrative parameters, not a
calibrated hardware digital twin. The selected self-collision pairs are not a
complete collision model. Environment/object contact, grasping, and
force-feedback control are not enabled.
There is no claim of collision-safe movement. No real arm adapter is implemented.
A future adapter must translate
units/frames and supply vendor-specific execution/safety behavior; this DDS
polling loop is not suitable inside a vendor hard-real-time callback.

### 2. Observe the application behavior

Observe and play around with the interactive operating room applications. The following are some ideas to get started:

- From the *Orchestrator* application, send a "PAUSE" command to the *Patient Sensor* Medical Device. Observe the effect in the *Patient Monitor* GUI application. Resume the *Patient Sensor* by sending a "START" command.
- From the *Arm Controller*, hold translation and rotation controls to move the TCP in all six base-frame components, and hold jaw controls to open/close the tool. Release to zero the rate. "RUN DEMO" and "STOP MOTION" start/stop a bounded motion/tool sequence. Rotate the tool, then command +Z translation: it still moves upward in the base frame, not along the shaft. Compare observed feedback in the controller and Arm views.
- Ungracefully terminate the *Arm* application process. Observe the effect in the *Orchestrator* activity stream.
- Initiate a graceful remote shutdown of the *Arm Controller* by sending the appropriate command from the *Orchestrator*. Observe the effect of the *Arm Controller* application.

### 3. Kill the applications

Press `Ctrl-C` in the terminal where `launch.py` is running to terminate all application processes. Closing a browser tab does not stop its app process.

## Hands-On: Going Further

Here are a few hands-on exercises to demonstrate use cases of Connext features in this module.

### 1. Application Presence Detection

The module uses a 200 ms ***Deadline QoS*** period for DataWriters and DataReaders on the *t/device/heartbeat* Topic to detect when applications are no longer active. Specifically, the DataWriters and DataReaders use a 200 ms Deadline period. This means if the *Orchestrator* application does not receive a *t/device/heartbeat* within 200 ms, it will log an entry, such as the following, to the "Alerts" panel:

```text
DeviceType::PATIENT_MONITOR  is no longer sending heartbeats. Updating Status to OFF.
```

Let's try testing how modifying QoS Profiles can adjust system behavior without modifying any application logic.

1. Kill all active operating room applications.

2. Increase the `<datareader_qos>` Deadline period in QoS Profile *DataFlow::Heartbeat* in [Qos.xml](../../system/qos/Qos.xml) to **5 seconds**.

   *Note, you should undo this configuration change after completing this demonstration.*

    ```xml
    <deadline>
      <period>
        <sec>5</sec>
        <nanosec>0</nanosec>
      </period>
    </deadline>
    ```

3. Relaunch the operating room applications.

4. While monitoring the *Orchestrator* "Alerts" panel, ungracefully terminate the *Patient Monitor* application by closing the respective application window.

   >**Observe:** You should see the alert mentioned above logged, 5 seconds after the *Patient Monitor* application has been closed.

5. Undo the QoS change to revert to the recommended configuration.

### 2. Content Filters

The module uses Content-Filtered Topics for DataReaders in all applications that subscribe to the *t/device/command* Topic. This allows the *Orchestrator* application to use a single Topic to publish device-specific commands. This allows the subscribing application logic to not have to check if the device command is relevant before processing it.

For example, the *Patient Monitor* application uses a `device = 'PATIENT_MONITOR'` filter expression for its DataReader subscribed to the *t/device/command* Topic.

Let's try testing how removing a content filter can adjust system behavior without modifying any application logic.

1. Kill all active operating room applications.

2. Comment out the `<content_filter>` tag and contained content within it, for *dr/DeviceCommand* under *dp/PatientMonitor* in [ParticipantLibrary.xml](../../system/xml_app_creation/ParticipantLibrary.xml).

   *Note, you should undo this configuration change after completing this demonstration.*

3. Relaunch the operating room applications.

4. While monitoring both the *Arm Controller* and *Patient Monitor* application windows, send a "Shut Down" command from the *Orchestrator* application **for the *Arm Controller* application only**.

   >**Observe:** You should see both the *Arm Controller* and *Patient Monitor* applications shut down and exit. This is because the *Patient Monitor* is no longer configured to receive only device commands for Patient Monitor apps but any app.

5. Undo the Content Filter change to revert to the recommended configuration.

## Next Steps

Check out [Module 02: RTI Recording Service & RTI Replay Service](../02-record-playback/), which builds upon the applications from this module to show how data can be recorded from and replayed to the same applications.

Check out [Module 03: Remote Teleoperation with RTI Real-Time WAN Transport](../03-remote-teleoperation/), which builds upon the applications from this module to show how applications can be deployed remotely and integrate seamlessly over the Wide Area Network (WAN).

Head back to the [main README](../../README.md) and pick up with the [Hands-On: Architecture](../../README.md#hands-on-architecture) section to learn more about the system architecture.
