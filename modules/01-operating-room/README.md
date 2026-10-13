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

The RTI Demo UI browser frontend displays synthetic ECG, plethysmograph, and capnography waveforms with numeric vital readouts.

### Arm

The *Arm* application simulates a surgical robot with Base, Shoulder, Elbow, Wrist, and Hand joints. It receives end-effector teleoperation commands on Topic `t/TeleopControl` and maps planar jogging, wrist rotation, and gripper open/close through its simplified kinematics.

The RTI Demo UI frontend displays a live side-view schematic of the articulated manipulator, its wrist, and a simulated gripper. The visualization uses a simplified planar model to demonstrate DDS-driven motion. Its status shows whether an Arm Controller `TeleopControl` writer is matched over DDS; it reports application connectivity, not physical Xbox connection.

### Arm Controller

The *Arm Controller* publishes teleoperation jog commands on Topic `t/TeleopControl`.

The RTI Demo UI frontend presents a teleoperation-style end-effector jog pad for planar X/Y motion, wrist roll, and gripper open/close, plus separate run/stop demonstration-motion controls. The demo runs a slow, repeatable planar sweep followed by coordinated wrist and gripper motion. It also shows an activity stream of observed events. An optional Xbox/gamepad adapter publishes the same DDS jog commands.

### Orchestrator

The *Orchestrator* application primarily acts as a system application state observer and controller. It detects the presence and current status of other system applications on Topics `t/DeviceHeartbeat` and `t/DeviceStatus`, respectively. It can also command device-level actions, such as "Start" or "Shut Down" on Topic `t/DeviceCommand`.

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
- Native webview mode is optional. Python requires `pip install -r requirements-native.txt`; on Linux with Python 3.13+, create the virtual environment with `--system-site-packages` so it can import the system `python3-gi` binding. C++ requires configuring with `-DRTI_DEMO_BUILD_NATIVE_WEBVIEW=ON`; the SDK root integration builds the core and optional native companion together. Install the platform prerequisites described in the root README and the RTI Demo UI native-webview guide.

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

The gamepad app uses Pygame CE only to read SDL controller input; its status page is served by RTI Demo UI. The interface highlights active analog and button input and publishes the same `SurgicalRobot::TeleopControl` samples on `t/TeleopControl`:

| Xbox control | Jog control | Effect |
| --- | --- | --- |
| Left stick horizontal | X left/right | Jog the end effector in planar X |
| Left stick vertical | Y up/down | Jog the end effector in planar Y |
| Right stick horizontal | Roll left/right | Rotate the gripper |
| Left / right triggers | Gripper open/close | Open or close the gripper |
| D-pad | X/Y jog | Jog the end effector in planar X/Y |
| Left / right bumpers | Roll left/right | Rotate the gripper |
| A / B buttons | Gripper open/close | Open or close the gripper |

Stick movement uses a 35% dead zone and publishes jog commands at 50 Hz while held. Gripper triggers use the same threshold; squeeze the left trigger to open and the right trigger to close. Digital D-pad, bumper, and A/B input works when its corresponding analog input is centered. Releasing an input publishes `STOPPED` for that axis; a short input lease also stops motion if the browser misses a release. The Arm simulator's per-sample kinematic step is unchanged. The right stick's vertical axis and other buttons are unused. Orchestrator START, PAUSE, and SHUTDOWN commands continue to control the Arm Controller's device status. If no supported gamepad is connected, the app stays running and reports that it is waiting. Closing the browser tab does not stop the app; use `Ctrl-C` in the launcher terminal. The simulated operating-room apps remain the default, so a gamepad is not required for the normal demo.

### 2. Observe the application behavior

Observe and play around with the interactive operating room applications. The following are some ideas to get started:

- From the *Orchestrator* application, send a "PAUSE" command to the *Patient Sensor* Medical Device. Observe the effect in the *Patient Monitor* GUI application. Resume the *Patient Sensor* by sending a "START" command.
- From the *Arm Controller* application, hold the X/Y jog controls to move the simulated tool tip, use wrist roll, and open/close the gripper. Release a control to stop that jog. The "RUN DEMO" and "STOP MOTION" buttons start and stop a slow, repeatable planar sweep with coordinated wrist and gripper movement.
- Ungracefully terminate the *Arm* application process. Observe the effect in the *Orchestrator* activity stream.
- Initiate a graceful remote shutdown of the *Arm Controller* by sending the appropriate command from the *Orchestrator*. Observe the effect of the *Arm Controller* application.

### 3. Kill the applications

Press `Ctrl-C` in the terminal where `launch.py` is running to terminate all application processes. Closing a browser tab does not stop its app process.

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
