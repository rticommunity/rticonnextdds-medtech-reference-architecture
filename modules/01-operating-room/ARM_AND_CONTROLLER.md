# Arm and controller

[← Module 01 walkthrough](README.md)

## Physical-device development

The experimental `kortex` and `falcon` variants implement
physical teleoperation. Automated tests exercise them with mocked vendor
devices; they do not establish physical-device behavior. Separate
hardware checks report device state without DDS, a UI, or robot motion RPCs.
The Falcon check exchanges device packets and performs kinematics; it is not
electrically passive. Do not deploy or connect to the target without explicit
authorization and an appropriate supervised plan.

The Kinova app and check require a compatible `kortex_api`. For live operation,
they also require `KORTEX_IP`, `KORTEX_USERNAME`, and `KORTEX_PASSWORD` in their
process environment. Supply credentials securely, not in source or shell history.
Without the watchdog assertion described below, the Kinova app opens an offline
preview: it does not connect to the arm, stays not ready, and cannot re-arm.
Restart with the verified assertion to use the live arm. An invalid assertion
is an error. The Falcon app and check
require the compatible `pynifalcon.FalconDeviceBridge` and its native dependencies;
the check also requires a connected Falcon. Neither vendor SDK nor bridge is
packaged by this project.
The bridge must provide device enumeration, input, `loadFirmware()`, and
`setHomingMode()`; initialization may load its embedded firmware.
With a compatible bridge but no detected Falcon, the controller stays open,
reports not ready, publishes neutral commands, and retries device detection.
Missing bridge dependencies and device initialization failures remain errors.

The [software motion gate](src/PhysicalMotionGate.py) disarms on loss of arm
connection, health, or valid required commands. Kortex requires only the arm
stream; the simulator's optional gate requires both arm and jaw streams.
An asynchronous DDS WaitSet also disarms the gate when a required control
reader misses its configured 50 ms deadline. On a miss, required cached streams
are discarded; recovery requires new valid neutral commands and a new operator
re-arm event.
Re-arm requests made before those conditions hold are rejected, not queued.
Lifecycle commands also disarm the gate immediately, including when PAUSE and
START arrive before the next control tick. Before the first sample, no deadline
is monitored for that instance, so every required stream must be present before re-arm.
The existing 250 ms writer Lifespan expires cached DDS commands; there is no
separate application sample-age threshold. Deadline monitors update intervals,
not the age of a command at actuation. Events, control and stop RPCs can be
delayed by scheduling or a blocked process; neither policy guarantees a stop.

The arm's "controller connected" indicator means at least one matched DDS
arm-command writer; it is diagnostic and is not a motion-gate condition.
"Neutral" means zero DDS linear/angular rates, plus zero jaw rate for the
simulator's optional gate. These are not verified
raw Falcon device state or physical control neutrality. The gate does not
arbitrate or identify command writers: competing writers or mixed arm and jaw
sources can pass it. The Falcon controller requires an alive ARM status
instance and exactly one matched telemetry writer. Instance lifecycle does
not prove that only one writer publishes ARM status.
A physical adapter must separately verify device connection, health, and
neutral controls and must not keep publishing nonzero commands after input is
lost. These tests cannot establish physical holding behavior, watchdog
behavior, or safety. A supervised test plan and approval are required before
physical motion.

### Staged rehearsal and physical checks

Run these commands from the repository root in order. Complete the shared
[Quick start](../../README.md#quick-start), including the sourced Connext
environment and license. `up` prepares the project environment and builds
before launching; after preparation, replace `up` with `run` to avoid repeating
setup and build. Open the printed app URLs and stop each scenario with Ctrl-C
before starting the next. Do not run another controller, arm, or replay
against the same domain.

The Kinova steps require a compatible Kortex API on the launcher Python import
path and `KORTEX_IP`, `KORTEX_USERNAME`, and `KORTEX_PASSWORD` in the
environment. Supply credentials securely. Falcon motion requires the compatible
`pynifalcon.FalconDeviceBridge` and native dependencies. Neither SDK nor bridge
is installed by the launcher. `up` uses
the project `.venv`; ensure the relevant imports work there before the hardware
steps (or in the active environment when using `run`):

```bash
.venv/bin/python -c 'import kortex_api'
.venv/bin/python -c 'from pynifalcon import FalconDeviceBridge'
```

1. **Simulated controller and simulated arm — baseline.**

   ```bash
   python3 medtech.py up --scenario or-all
   ```

   Check application discovery, vitals, arm readiness and telemetry. Use manual
   jog and **RUN DEMO**, comparing movement with the simulated arm's reported
   pose. Release a manual jog to stop it; use **STOP MOTION** to stop the
   showcase. This does not test either hardware adapter.

2. **Falcon and simulated arm — controller mapping.**

   For a hardware-only diagnostic before the scenario, run:

   ```bash
   .venv/bin/python modules/01-operating-room/tools/check_falcon.py
   ```

   If homing is not confirmed, rerun with `--home` and follow the prompt. The
   check closes the device afterward; homing may need to be repeated in the app.

   Then launch the scenario:

   ```bash
   FALCON_WORKSPACE_MAX=0.5,0.25,0.60 python3 medtech.py up --scenario or-all --variant ArmController=falcon
   ```

   If the app shows **WAITING FOR HOMING**, select **HOME FALCON** and move the
   handle fully out, then straight fully in. Wait for **READY**. During homing,
   the controller publishes neutral commands. If homing times out, retry.
   With the Falcon ready, release button 1, then hold it and
   move the handle. Check that the simulated TCP responds and release stops
   the command. Observe the mapping and telemetry; no physical arm is
   commanded. The override includes the simulated arm's initial X position;
   it is not a verified physical workspace.

3. **Check Kinova — device state without DDS or arm commands.**

   ```bash
   .venv/bin/python modules/01-operating-room/tools/check_kortex.py
   ```

   The one-shot check reports the TCP pose, arm state, servoing mode, fault
   banks and whether they meet the motion adapter's health criteria. It exits
   nonzero on a failed check or unmet health criteria. It does not check DDS,
   command motion, or establish watchdog and holding behavior.

4. **Virtual controller and Kinova — supervised manual motion.**

   ```bash
   python3 medtech.py up --scenario or-all --variant Arm=kortex
   ```

   Only after an approved supervised motion procedure and watchdog verification
   described below, start with neutral controls and use **RE-ARM MOTION** in
   the Kinova arm UI once available. Check `READY`, then use brief manual
   translation jogs and compare actual movement with reported TCP pose. Release
   the jog and check the response. Jaw controls have no effect: this arm has
   no jaw command subscription. The controller's jaw subscriber indicator
   should show **NO MATCH** unless another subscriber is present.
   **RUN DEMO** requires jaw telemetry and is unavailable for this arm.

5. **Falcon and Kinova — supervised combined control.**

   ```bash
   python3 medtech.py up --scenario or-all --variant Arm=kortex --variant ArmController=falcon
   ```

   Under the same approved motion procedure, configure the Falcon target bounds
   for the actual starting pose and test area before launch, if the defaults
   are unsuitable. Re-arm with neutral arm commands, release button 1, then
   hold it to capture the reference. Check small translations, actual TCP
   telemetry and the response to release. Target bounds are not physical safety
   limits. Rotation, jaw control and force feedback are not implemented.

Steps 4 and 5 currently require the operator assertion
`KORTEX_LIVE_WATCHDOG=VERIFIED_KORTEX_CONNECTION_TIMEOUT_STOP` in the
environment; set it **only after** the connection-timeout stop has been
verified under the approved procedure. Even verified connection-loss behavior
does not establish a stop when an SDK worker stalls with a live connection.
`Stop` and zero-twist RPCs are best effort; physical hold, fault and recovery
behavior remain unverified. These commands do not themselves establish
readiness for physical testing.

### Experimental Kinova motion arm

The separately selected `kortex` variant consumes the existing
base-frame DDS arm rates. It converts angular rates from radians to degrees
per second. The maximum linear and angular speeds are the smaller of the
shared demo limits and the device-reported kinematic hard limits. These are
not physical safety limits. Jaw
motion is not implemented. Its XML participant, `dp/ArmKortex`, has no jaw
command reader; missing or nonzero jaw commands do not affect arm admission.
The simulator retains its independent jaw support.
The arm must already be in single-level servoing mode.
The adapter validates the shared demo command limits independently of the
simulator. At motion-driver startup, it queries Kortex kinematic hard limits and
rejects invalid limits; RPC failure also prevents startup. This check does not
establish active soft limits, safe movement, or actual physical-device compatibility.
The current demo limits permit up to 0.05 m/s and 0.5 rad/s (about 28.6 degrees/s),
which are higher than the earlier provisional Kortex-specific caps of 0.01 m/s
and 5 degrees/s. Review the configured limits as part of the supervised plan
before physical motion.

The arm publishes lifecycle `ON` with `NOT_READY` while connecting; `ON` is
application lifecycle, not physical connection or motion permission.
It requires recent fault-free Kortex health, valid neutral arm commands
and an explicit UI re-arm. The arm window's **LOG** control shows re-arm and
disarm diagnostics, including stale health, unavailable commands and missed
deadlines. It attempts Kortex
`Stop` on loss of motion, a command deadline miss, health or permission, and
on lifecycle shutdown. These
are best-effort RPCs: if a request or process blocks, or the connection is
lost, the application cannot guarantee that a stop reaches the arm. Kortex
twist duration is not an implemented watchdog. The motion variant therefore
requires the operator assertion
`KORTEX_LIVE_WATCHDOG=VERIFIED_KORTEX_CONNECTION_TIMEOUT_STOP`; do not set it
until that behavior has actually been verified under an approved supervised
procedure. Connection-loss behavior alone also does not prove a stop when an
SDK worker stalls while its connection remains alive.

Queued twists carry a revocable re-arm token. Lifecycle commands, command
Deadline misses, unhealthy observations and cleanup revoke that token. The SDK
worker rejects a revoked token or expired health observation before invoking
the twist RPC, even if the operator has since re-armed. An already executing
RPC cannot be retracted, and stop RPCs still wait for the same worker.
After a fault, START/PAUSE or a subsequent healthy observation cannot clear
`ERROR`/`FAULTED`; restart only after separately verified recovery.

The motion path has mock SDK tests and shared-memory-only DDS integration tests
with the virtual controller and mocked Falcon input. No physical deployment,
movement, hold, failure recovery, axis direction or device-limit behavior has
been verified. The hardware check can inspect the device without the assertion
or any motion RPCs.
An RPC or background-task failure attempts a stop, then publishes arm
`ERROR`/`FAULTED` before teardown;
delivery is not guaranteed when the participant closes.
After the assertion has been verified and a motion session separately approved,
the variant can be selected with:

```bash
python medtech.py run 01-operating-room Arm --variant Arm=kortex
```

It uses the Kortex SDK and credential environment variables described above.

### Experimental Falcon motion controller

For manual control, the separately selected `falcon` variant publishes translation
and neutral jaw/rotation commands. It uses an identity-axis, relative-position
mapping: release button 1, then hold it to capture a
reference and translate. Release commands zero; stale input or arm feedback,
an arm that is not ready, a control-loop gap, PAUSE and START require a new
release before another reference can be captured. Feedback freshness measures
time since the application processed the latest telemetry, not its source or
DDS reception timestamp. It uses a 0.01 m/s speed limit, 0.02 m/s² acceleration
limit and 0.35 smoothing factor.
Force feedback, manual rotation and manual jaw control are not implemented.
The app checks for confirmed homing at startup; if needed, **HOME FALCON**
starts a 30-second manual homing window. It remains not ready and publishes
neutral commands until homing is confirmed. Loss of homing during tracking
stops the controller.

The default target workspace is `(-0.25, -0.25, 0.10)` to
`(0.25, 0.25, 0.60)` metres in the arm base frame. Override these using
`FALCON_WORKSPACE_MIN` and `FALCON_WORKSPACE_MAX` as comma-separated XYZ
metres. These are bounds on the **target**, not physical safety limits or a
guarantee that the robot cannot cross a boundary. Axis directions and workspace
remain unverified on the actual equipment. The simulated arm starts outside
the default X range, so for a simulation-only check use:

```bash
FALCON_WORKSPACE_MAX=0.5,0.25,0.60 python medtech.py run 01-operating-room ArmController --variant ArmController=falcon
```

Only one controller should publish at a time. This variant can produce nonzero
DDS commands and must not be used with a physical arm except under a separately
approved supervised test. It has only been tested with mock input and the
simulated arm, including shared-memory-only DDS; its command-loss behavior
does not prove a physical stop.

## Controller behavior

Controller headers show separate arm and jaw command subscriber matches.
These indicate DDS endpoint matching only: a match may be a monitor or other
subscriber, not an arm, and does not prove command delivery or execution.
These indicators do not change controller publication or arm gating.

**RUN DEMO** captures the observed TCP position and jaw gap, then repeats a
small translation/jaw loop with a brief hold at its starting point. Each
waypoint uses achieved telemetry; the return targets are within 0.7 mm position
and 0.4 mm gap of the captured start, rather than accumulated command estimates.
The showcase leaves angular rates at zero; the simulated and Xbox controllers
offer all six manual axes.
It requires complete pose/jaw telemetry no more than 500 ms old and stops with a
warning if feedback becomes unavailable, the arm reports a fault, or a waypoint
cannot be reached within four seconds. It is available on the simulated, Xbox,
and Falcon controllers, but not with the Kortex arm because that arm does not
provide jaw feedback. This is demo motion, not a safety system.

On Xbox and Falcon, starting the showcase also requires the controller to be ON,
connected and ready, with its controls neutral. Loss of input stops the showcase.
The Falcon showcase is autonomous: it does not require holding the manual
deadman button, and its motion does not use the Falcon manual workspace, speed,
or acceleration limits. It can command jaw motion even though Falcon manual
control cannot.

A manual jog takes over from the showcase. A release-only event does not cancel
it. **STOP MOTION** clears both the showcase and held jogs. PAUSE/SHUTDOWN clear
motion and send zero before ending the command stream; the showcase does not
resume after START. On hardware controllers, STOP MOTION inhibits held manual
input until it returns to neutral. A new RUN DEMO captures a new starting point.
Browser control schemas and presentation for the simulated controller are in
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
is served by RTI Demo UI. The simulated and Xbox variants publish complete
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
PAUSE and SHUTDOWN send neutral arm and jaw rates before stopping publication.
Fresh rates resume after START/reconnection even when
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
guarantees. Both arm variants clamp finite over-limit linear and angular vectors
to the demo limits without changing their direction and report a warning.
Non-finite arm velocities are rejected and disarm the motion gate when enabled.
The simulator rejects invalid or over-limit jaw rates separately.

The supported deployment is one operating room, one instance of each app role,
and one intended arm command source: either controller variant **or** replay.
Do not run multiple controller variants or a live controller alongside replay
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
failures stop the application with ERROR/FAULTED and an explicit diagnostic.

Each step reads the current valid DDS rates, including previously READ samples.
Rates remain eligible until replaced, expired by the writer's 250 ms lifespan,
or discarded by application handling. Reusing a valid rate advances another
time interval; it does not repeat a one-shot action. There is no application-owned active target or
duplicate command timeout. No eligible arm command brakes both arm and jaws;
no eligible tool command brakes the jaws independently. A valid zero arm
stream permits tool-only operation. PAUSE and SHUTDOWN drain cached arm and jaw
control samples; START does not. This does not exclude commands still in flight
at the transition. Command loss never automatically opens the jaws.

Command QoS is best-effort, volatile, KEEP_LAST(1), with a 50 ms
deadline. Finite lifespan is required on every command writer, including routing
and replay outputs, and is not enforced by DDS requested/offered matching.
Reader expiration uses reception time in Connext 7.7. A requested-deadline miss
discards the affected cached commands and wakes the control loop; a gated arm
discards both streams and disarms. Delayed or republished data can start a new
local validity window. Neither Deadline nor Lifespan guarantees a timely stop.

`t/device/status` reports the arm's initial/on-change lifecycle and readiness.
`t/robot/arm/telemetry` carries actual base-relative TCP pose and optional
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
There is no claim of collision-safe movement. The experimental physical arm
adapter and its unverified stop behavior are described above; this simulation's
DDS polling loop is not suitable inside a vendor hard-real-time callback.
