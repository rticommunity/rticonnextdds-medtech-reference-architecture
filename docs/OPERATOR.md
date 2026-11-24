# Operating-room demo run card

This demo uses simulated devices and patient data. Run one operating room at a
time, on an isolated demo network.

## Prepare before the event

1. Follow the [Quick Start](../README.md#quick-start) to install and source
   Connext and prepare your RTI license. Use the same user account and worktree
   you will use at the event.
2. From the repository root, run `python medtech.py setup --extra arm`, then
   `python medtech.py build`. If using an Xbox controller, also install
   `--extra gamepad` and rehearse with `--variant ArmController=xbox`.
3. Run `python medtech.py run --scenario or-all --explain`, then rehearse the
   real launch with networking configured as it will be on site. For an offline
   showing, rehearse without Internet access; use `run`, not `up`, on site.
   Secure runs also need a [staged local bundle](../system/security/README.md)
   or an [EPS-managed bundle](EPS.md) selected with `--security --provider eps`.

## Launch and tell the story

For native windows, prepare the [desktop prerequisites](SETUP.md#native-windows),
run `python medtech.py setup --extra arm --extra native`, and build with
`python medtech.py build -- -DRTI_DEMO_BUILD_NATIVE_WEBVIEW=ON`. Use
`--ui-mode native` for both preflight and rehearsal.

```bash
python medtech.py run --scenario or-all --ui-mode native
```

Native mode opens the app windows automatically. For a browser fallback:

```bash
python medtech.py run --scenario or-all
```

In the terminal, look for the local URL labeled for each app. Open Orchestrator,
Patient Monitor, Arm Controller and Arm in the browser. For a first walkthrough:

1. **Orchestrator and Patient Monitor:** show device presence and streaming
   synthetic vitals. Select Patient Sensor and send **PAUSE**, then **START**
   to show the difference between device presence and data flow.
2. **Arm Controller and Arm:** start **RUN DEMO** and compare the command in
   the controller with the observed pose in the Arm view. Use **STOP MOTION**,
   then demonstrate manual jog and release. No gamepad is needed by default.
3. Point to the [DDS contract](../system/README.md#dds-contract) for the topics,
   QoS and ownership behind what the audience sees.

For recording/replay or WAN, use the
[module guides](../README.md#modules) to prepare the required services
and data before changing scenarios.

For experimental physical devices, use the separately supervised
[staged rehearsal and physical checks](../modules/01-operating-room/ARM_AND_CONTROLLER.md#staged-rehearsal-and-physical-checks);
this simulated run card does not qualify hardware motion.

## Reset, stop and recover

- Stop motion before restarting. For a clean reset, press **Ctrl-C** in the
  launcher terminal, wait for the children to exit, then run the same command
  again. In browser mode, open the newly printed URLs instead of reusing old tabs. Launch/reset
  does not delete recordings or security state.
- If an app fails to start, rerun with `--explain`. Check the sourced SDK,
  active license, required extras and build outputs. If the preflight succeeds
  but DDS data is missing, check runtime diagnostics, ensure no second demo is
  still running, and confirm every participant uses the intended security mode.
- For a repeatable rehearsal, record cold dependency preparation, build and
  first run in the prepared environment, and warm launch separately. For warm
  launch measure from `run` to live data in the UI, not just the first URL.
  Record hands-on effort separately from time spent waiting. An already-built
  smoke test is not a measurement of first-time setup.
