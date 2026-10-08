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

The *Patient Sensor* application's primary function is to publish simulated patient vitals data on Topic `t/Vitals`.

It has no user interface.

### Patient Monitor

The *Patient Monitor* application's primary function is to subscribe to simulated patient vitals data on Topic `t/Vitals`.

It displays synthetic ECG, plethysmograph, and capnography waveforms with numeric vital readouts.

### Arm

The *Arm* application simulates a surgical robot with Base, Shoulder, Elbow, Wrist, and Hand joints. It receives end-effector teleoperation commands on Topic `t/TeleopControl` and maps planar jogging, wrist rotation, and gripper open/close through its simplified kinematics.

It displays a side-view schematic of the articulated manipulator, its wrist, and a simulated gripper. The visualization uses a simplified planar model to demonstrate DDS-driven motion. Its header indicator shows whether an Arm Controller `TeleopControl` writer is matched over DDS; it reports application connectivity, not the physical Xbox connection.

### Arm Controller

The *Arm Controller* publishes teleoperation jog commands on Topic `t/TeleopControl`.

The default GTK/C++ implementation presents a teleoperation-style end-effector jog pad for planar X/Y motion, wrist roll, and gripper open/close, plus separate run/stop demonstration-motion controls. The demo runs a slow, repeatable planar sweep followed by coordinated wrist and gripper motion. It also shows an "Alerts" panel to display observed events. An optional Xbox/gamepad implementation provides the same jog controls using gamepad input.

### Orchestrator

The *Orchestrator* application primarily acts as a system application state observer and controller. It detects the presence and current status of other system applications on Topics `t/DeviceHeartbeat` and `t/DeviceStatus`, respectively. It can also command device-level actions, such as "Start" or "Shut Down" on Topic `t/DeviceCommand`.

It displays current device statuses, presents buttons to administer device commands, and shows a collapsible "Alerts" log to display observed events.

## Setup and Installation

Complete the shared setup in the root [Quick Start](../../README.md#quick-start) section. That covers prerequisites, environment setup, the project-level build, and security artifact generation.

Module-specific notes:

- If you plan to use secure mode, make sure the security artifacts from the root README have been generated.
- There is no module-local build or launch script; use the project-level `build.py` and `launch.py` scripts from the repository root.
- The Xbox/gamepad variant is optional at runtime. Its Pygame Community Edition dependency is installed with the standard root `requirements.txt`; no additional package-install step is required.

## Run the Demo

> Important: Run the commands below from the repository root. `launch.py` lives at the project root and is the single runtime entrypoint for this project.

### 1. Launch the applications

Run operating room applications from the repository root:

```bash
# From the repository root
python3 launch.py 01-operating-room
```

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

The existing GTK Arm Controller remains the default and requires no gamepad. Pygame CE is included in the standard project requirements. To select the Xbox/gamepad implementation, run:

```bash
python3 launch.py 01-operating-room --variant ArmController=xbox
```

The selection also applies to scenarios that launch the Arm Controller:

```bash
python3 launch.py --scenario or-all --variant ArmController=xbox
```

The gamepad window is built with PySide6, matching the other Python GUIs; Pygame CE is used only to read SDL controller input. Its control row highlights while a stick or trigger is active. The controls follow the GTK jog pad and publish the same `SurgicalRobot::TeleopControl` samples on `t/TeleopControl`:

| Xbox control | GTK jog control | Effect |
| --- | --- | --- |
| Left stick horizontal | X left/right | Jog the end effector in planar X |
| Left stick vertical | Y up/down | Jog the end effector in planar Y |
| Right stick horizontal | Roll left/right | Rotate the gripper |
| Left / right triggers | Gripper open/close | Open or close the gripper |

Stick movement uses a 35% dead zone and the gamepad publishes jog commands at 50 Hz while held. GTK jog buttons also repeat at 50 Hz. Gripper triggers use the same threshold; squeeze the left trigger to open and the right trigger to close. Releasing a control publishes `STOPPED` for that axis. The Arm simulator's per-sample kinematic step is unchanged. The right stick's vertical axis and other buttons are unused. Orchestrator START, PAUSE, and SHUTDOWN commands continue to control the Arm Controller's device status. If no supported gamepad is connected, the selected app stays running and reports that it is waiting; it does not switch to the GTK controller. Closing its window stops the app. The simulated operating-room apps remain the default, so a gamepad is not required for the normal demo.

### Startup warning under Snap

If startup prints `Glycin running without additional sandbox inside snap confinement`, run the GTK applications individually to identify which one emits it:

```bash
python3 launch.py 01-operating-room Orchestrator
python3 launch.py 01-operating-room ArmController
```

Both GTK applications load the RTI logo through GdkPixbuf, so this warning may be emitted by the image-loading path rather than the Pygame app or DDS. The warning specifically mentions Snap confinement; do not change the app's stderr handling or security behavior just to hide it. If it appears for one application, share which command produced it and whether the app otherwise works.

### 2. Observe the application behavior

Observe and play around with the interactive operating room applications. The following are some ideas to get started:

- From the *Orchestrator* application, send a "PAUSE" command to the *Patient Sensor* Medical Device. Observe the effect in the *Patient Monitor* GUI application. Resume the *Patient Sensor* by sending a "START" command.
- From the *Arm Controller* application, hold the X/Y jog controls to move the simulated tool tip, use wrist roll, and open/close the gripper. Release a control to stop that jog. The "RUN DEMO" and "STOP MOTION" buttons start and stop a slow, repeatable planar sweep with coordinated wrist and gripper movement.
- Ungracefully terminate the *Arm* application by closing the application window. Observe the effect in the *Orchestrator* application "Alerts" panel.
- Initiate a graceful remote shutdown of the *Arm Controller* by sending the appropriate command from the *Orchestrator*. Observe the effect of the *Arm Controller* application.

### 3. Kill the applications

Press `Ctrl-C` in the terminal where `launch.py` is running to terminate all application processes.

## Hands-On: Going Further

Here are a few hands-on exercises to demonstrate use cases of Connext features in this module.

### 1. Application Presence Detection

The module uses a 200 ms ***Deadline QoS*** period for DataWriters and DataReaders on the *t/DeviceHeartbeat* Topic to detect when applications are no longer active. Specifically, the DataWriters and DataReaders use a 200 ms Deadline period. This means if the *Orchestrator* application does not receive a *t/DeviceHeartbeat* within 200 ms, it will log an entry, such as the following, to the "Alerts" panel:

```text
DeviceType::PATIENT_MONITOR  is no longer sending heartbeats. Updating Status to OFF.
```

Let's try testing how modifying QoS Profiles can adjust system behavior without modifying any application logic.

1. Kill all active operating room applications.

2. Increase the `<datareader_qos>` Deadline period in QoS Profile *DataFlow::Heartbeat* in [Qos.xml](../../system_arch/qos/Qos.xml) to **5 seconds**.

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

The module uses Content-Filtered Topics for DataReaders in all applications that subscribe to the *t/DeviceCommand* Topic. This allows the *Orchestrator* application to use a single Topic to publish device-specific commands. This allows the subscribing application logic to not have to check if the device command is relevant before processing it.

For example, the *Patient Monitor* application uses a `device = 'PATIENT_MONITOR'` filter expression for its DataReader subscribed to the *t/DeviceCommand* Topic.

Let's try testing how removing a content filter can adjust system behavior without modifying any application logic.

1. Kill all active operating room applications.

2. Comment out the `<content_filter>` tag and contained content within it, for *dr/DeviceCommand* under *dp/PatientMonitor* in [ParticipantLibrary.xml](../../system_arch/xml_app_creation/ParticipantLibrary.xml).

   *Note, you should undo this configuration change after completing this demonstration.*

3. Relaunch the operating room applications.

4. While monitoring both the *Arm Controller* and *Patient Monitor* application windows, send a "Shut Down" command from the *Orchestrator* application **for the *Arm Controller* application only**.

   >**Observe:** You should see both the *Arm Controller* and *Patient Monitor* applications shut down and exit. This is because the *Patient Monitor* is no longer configured to receive only device commands for Patient Monitor apps but any app.

5. Undo the Content Filter change to revert to the recommended configuration.

## Next Steps

Check out [Module 02: RTI Recording Service & RTI Replay Service](../02-record-playback/), which builds upon the applications from this module to show how data can be recorded from and replayed to the same applications.

Check out [Module 03: Remote Teleoperation with RTI Real-Time WAN Transport](../03-remote-teleoperation/), which builds upon the applications from this module to show how applications can be deployed remotely and integrate seamlessly over the Wide Area Network (WAN).

Head back to the [main README](../../README.md) and pick up with the [Hands-On: Architecture](../../README.md#hands-on-architecture) section to learn more about the system architecture.
