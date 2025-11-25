# Module 01: Digital Operating Room

Module 01 simulates a Digital Operating Room.

The applications have been tested to work in Debian-based environments with a GUI, including those in [WSL2 with GUI support](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps#install-support-for-linux-gui-apps) (Windows 10 and 11).

## Contents

- [Module Description](#module-description)
- [Setup and Installation](#setup-and-installation)
- [Run the Demo](#run-the-demo)
- [Hands-On: Going Further](#hands-on-going-further)
- [Next Steps](#next-steps)

## Module Description

This module implements 5 interactive Connext applications using the MedTech Reference Architecture to simulate a digital operating room. You can find a diagram below:

![image](../../resource/images/module-01-diagram-digital-OR.svg)

### Patient Sensor

The *Patient Sensor* application's primary function is to publish simulated patient vitals data on Topic `t/Vitals`.

It has no user interface.

### Patient Monitor

The *Patient Monitor* application's primary function is to subscribe to patient vitals data on Topic `t/Vitals`.

It displays the received patient vital data in a GUI as a live "Patient Monitor Graph" line plot.

### Arm

The *Arm* application's primary function is to simulate a surgical robot with 5 motors: Base, Shoulder, Elbow, Wrist, and Hand. It receives commands on Topic `t/MotorControl` to control the movement of the individual motors.

It displays the motor angles as an "Arm Motor Angles" line plot. This is a very basic representation of the movement of a robotic arm. We've intentionally made it simple to focus on the data transfer.

### Arm Controller

The *Arm Controller* application's primary function is to send motor-movement commands on Topic `t/MotorControl`.

It presents buttons to administer *Arm* motor commands, and shows an "Alerts" panel to display observed events.

### Orchestrator

The *Orchestrator* application primarily acts as a system application state observer and controller. It detects the presense and current status of other system applications on Topics `t/DeviceHeartbeat` and `t/DeviceStatus`, respectively. It can also command device-level actions, such as "Start" or "Shut Down" on Topic `t/DeviceCommand`.

It displays current device statuses, presents buttons to administer device commands, and shows an "Alerts" panel to display observed events.

## Setup and Installation

### 1. Install Dependencies

To install Connext, follow the [installation guide](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/installation_guide/installation_guide/Installing.htm#Chapter_1_Installing_RTI%C2%A0Connext) and other required tools. You will also need the [Python API](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/getting_started_guide/python/before_python.html#installing-connext-heading) to be installed. **Make sure you run [Hands-On 1: Your First DataWriter and DataReader](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/getting_started_guide/python/intro_pubsub_python.html#hands-on-1-your-first-datawriter-and-datareader) from the Getting Started Guide to confirm that the Python API works.**

Dependencies for building with C++:

- `build-essential`

Dependencies used for GUI applications:

- `PyGObject`
- `GTK`

Install (Debian) system-provided packages with *apt*:

```bash
sudo apt install \
    build-essential \
    python3-pip \
    python3-gi \
    python3-gi-cairo \
    python3-matplotlib \
    python3-numpy \
    python3-cairo \
    gir1.2-gtk-4.0 \
    libgtksourceviewmm-3.0-dev
```

Alternatively, install PyPI-provided packages with *pip* (for virtual environments):

```bash
sudo apt install \
    build-essential \
    python3-dev \
    libcairo2-dev \
    libgirepository-2.0-dev \
    gir1.2-gtk-4.0

pip install \
    pygobject \
    numpy \
    matplotlib
```

### 2. Build the Project using CMake

```bash
source <connext installation directory>/resource/scripts/rtisetenv_x64Linux4gcc7.3.0.bash
mkdir build
cd build
cmake ..
cmake --build .
```

### 3. Security (optional)

This module also demonstrates how [RTI Security Plugins](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_secure/users_manual/index.html) can easily be applied to an existing system.

To run the secure version of the module, you need the Security Plugins installed (see the [RTI Security Plugins Installation Guide](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_secure/installation_guide/security_plugins/installation_guide/SecurityPluginsInstallationTitle.htm)).

Generate the security artifacts using OpenSSL.
This includes identity certificates, private keys, and the signing of DDS Security XML permissions & governance files located in [system_arch/security](../../system_arch/security).

```bash
cd system_arch/security
./setup_security.sh
```

## Run the Demo

### 1. Launch the applications

Run operating room applications:

```bash
./scripts/launch_all.sh
```

To run with security enabled, use the `-s` option:

```bash
./scripts/launch_all.sh -s
```

*This script does the following:*

1. Set `NDDS_QOS_PROFILES` environment variable to load the appropriate XML configuration files (QoS Profiles, Domains, DomainParticipants).

2. Launch the application executables.

*Note, applications can be launched individually from a terminal instead of all at once via the **launch_all.sh** script. Please refer how `NDDS_QOS_PROFILES` is set in [launch_all.sh](./scripts/launch_all.sh), so your terminal environment can be configured similarly without errors.*

### 3. Observe the application behavior

Observe and play around with the interactive operating room applications. The following are some ideas to get started:

- From the *Orchestrator* application, send a "PAUSE" command to the *Patient Sensor* Medical Device. Observe the effect in the *Patient Monitor* GUI application. Resume the *Patient Sensor* by sending a "START" command.
- From the *Arm Controller* application, send a command to stop all *Arm* motors. Observe the effect in the *Arm* GUI application. Resume just the *Elbow* motor by clicking the respective "PLAY" button in the *Arm Controller* application. While still stopped, increment or decrement the *Wrist* motor angle by clicking the respective "+" or "-" buttons in the *Arm Controller* application. Resume all *Arm* motors by pressing "PLAY ALL".
- Ungracefully terminate the *Arm* application by closing the application window. Observe the effect in the *Orchestrator* application "Alerts" panel.
- Initiate a gracefull remote shutdown of the *Arm Controller* by sending the appropriate command from the *Orchestrator*. Observe the effect of the *Arm Controller* application.

### 3. Kill the applications

To ensure application processes are killed when finished, run:

```bash
./scripts/kill_all.sh
```

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

    >**Observe:** You should see both the *Arm Controller* and *Patient Monitor* applications shut down and exit. This is because the *Patient Monitor* is no longer to configured to recieve only device commands for Patient Monitor apps but any app.

5. Undo the Content Filter change to revert to the recommended configuration.

## Next Steps

Check out [Module 02: RTI Recording Service & RTI Replay Service](../02-record-playback/), which builds upon the applications from this module to show how data can be recorded from and replayed to the same applications.

Check out [Module 03: Remote Teleoperation with RTI Real-Time WAN Transport](../03-remote-teleoperation/), which builds upon the applications from this module to show how applications can be deployed remotely and integrate seamlessly over the Wide Area Network (WAN).

Head back to the [main README](../../README.md) and pick up with the [Hands-On: Architecture](../../README.md#hands-on-architecture) section to learn more about the system architecture.
