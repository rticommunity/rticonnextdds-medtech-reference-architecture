# Arm and controller

[← Module 01 walkthrough](README.md)

## Controller behavior

**RUN DEMO** captures the observed TCP position and jaw gap, then repeats a
small translation/jaw loop with a brief hold at its starting point. Each
waypoint uses achieved telemetry; the return targets are within 0.7 mm position
and 0.4 mm gap of the captured start, rather than accumulated command estimates.
The showcase leaves angular rates at zero; all six manual axes remain available.
It requires complete pose/jaw telemetry no more than 500 ms old and stops with a
warning if feedback becomes unavailable, the arm reports a fault, or a waypoint
cannot be reached within four seconds. This is demo motion, not a safety system.

A manual jog takes over from the showcase. A release-only event does not cancel
it. **STOP MOTION** clears both the showcase and held jogs. PAUSE/SHUTDOWN clear
motion and send zero before ending the command stream; START resumes idle zeros,
not the old showcase or cached browser inputs. A new RUN DEMO captures a new
starting point. Browser control schemas and presentation are in
[ArmControllerUi.hpp](src/ArmControllerUi.hpp); ordinary Connext entity lookup,
reads, and writes remain in [ArmController.cxx](src/ArmController.cxx).

## Optional controller and simulation reference

### Use the Xbox/gamepad Arm Controller

The simulated Arm Controller remains the default and requires no gamepad. Pygame CE is included in the standard project requirements. To select the Xbox/gamepad implementation, run:

```bash
python medtech.py run 01-operating-room --variant ArmController=xbox
```

The selection also applies to scenarios that launch the Arm Controller:

```bash
python medtech.py run --scenario or-all --variant ArmController=xbox
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

The supported deployment is one operating room, one instance of each app role,
and one intended arm command source: either controller variant **or** replay.
Do not run both controller variants or a live controller alongside replay
against the same arm. Keys identify data instances; they do not provide
multi-device discovery, command-source arbitration, or operator ownership.
The security threat demonstration deliberately adds a competing writer to show
the unsecured/secured contrast; that is not a supported multi-controller mode.

At startup, the simulator uses a raised shoulder and bent elbow, with the tool
pointing forward and 20 degrees downward. This keeps the initial posture away
from full extension and gives room for translation and rotation. It is
initialization only; no HOME action is implemented.

The Arm uses **MuJoCo + Mink**, installed by the root `arm` capability.
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
[articulated GLB](../../resources/ui/web/models/articulated-arm.glb) and
[reproducible generator](../../resources/ui/web/generate_arm_glb.py). Drag to
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
