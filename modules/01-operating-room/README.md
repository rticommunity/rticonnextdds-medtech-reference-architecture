# Module 01: Digital Operating Room

Module 01 simulates a Digital Operating Room.

The applications have been tested to work in Debian-based environments with a GUI, including those in [WSL2 with GUI support](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps#install-support-for-linux-gui-apps) (Windows 10 and 11), as well as on macOS.

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

The *Orchestrator* application primarily acts as a system application state observer and controller. It detects the presence and current status of other system applications on Topics `t/DeviceHeartbeat` and `t/DeviceStatus`, respectively. It can also command device-level actions, such as "Start" or "Shut Down" on Topic `t/DeviceCommand`.

It displays current device statuses, presents buttons to administer device commands, and shows an "Alerts" panel to display observed events.

## Setup and Installation

### 1. Prerequisites

You will need:

- **RTI Connext DDS 7.3** installed and `NDDSHOME` set, including the Python API `.whl`.
  See the [Installation Guide](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/installation_guide/installation_guide/Installing.htm) and [Python API setup](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/getting_started_guide/python/before_python.html#installing-connext-heading).

  > If `NDDSHOME` is not already in your environment, source the platform setup script from your Connext installation: `source <connext_dir>/resource/scripts/rtisetenv_<arch>.bash` (Linux/macOS) or `rtisetenv_<arch>.bat` (Windows). This script sets `NDDSHOME`, `CONNEXTDDS_ARCH`, and related library paths required by both `build.py` and `launch.py`.
- **CMake** ≥ 3.17 and a C++ compiler toolchain.
- **Python** ≥ 3.9.

**Make sure you run [Hands-On 1: Your First DataWriter and DataReader](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/getting_started_guide/python/intro_pubsub_python.html#hands-on-1-your-first-datawriter-and-datareader) from the Getting Started Guide to confirm that the Python API works.**

Install the system build dependencies for your platform:

<details>
<summary><strong>Linux (Debian/Ubuntu)</strong></summary>

```bash
sudo apt install \
    build-essential \
    cmake \
    pkg-config \
    libgtkmm-3.0-dev \
    python3-venv
```

> `python3-venv` is required on Debian/Ubuntu to create virtual environments (`python3 -m venv`).
> It is a split package not included with the base `python3` install.

</details>

<details>
<summary><strong>macOS</strong></summary>

```bash
xcode-select --install          # compiler toolchain (if not already installed)
brew install cmake pkg-config gtkmm3 python3
```

> Homebrew's `python3` includes `pip` and `venv` — no separate installs needed.

</details>

### 2. Set Up a Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Install the RTI Connext Python API from your local Connext installation:
pip install rti.connext.activated -f $NDDSHOME/resource/python_api
# Alternatively, if the above path is not available, install from PyPI:
# pip install rti.connext==7.3.0
```

### 3. Build the Project

From the repository root:

```bash
python3 build.py
```

This script creates a `build/` directory, runs CMake configuration and compilation automatically.

To build only the modules you intend to run:

```bash
python3 build.py --target module-01   # all C++ targets in Module 01
python3 build.py --target ArmController  # only the ArmController target
```

The compiled binaries are placed under `build/<CONNEXTDDS_ARCH>/`.

### 4. Security (optional)

This module also demonstrates how [RTI Security Plugins](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_secure/users_manual/index.html) can easily be applied to an existing system.

To run the secure version of the module, you need the Security Plugins installed (see the [RTI Security Plugins Installation Guide](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_secure/installation_guide/security_plugins/installation_guide/SecurityPluginsInstallationTitle.htm)).

Generate the security artifacts (CA certificates, identity certificates, and signed governance/permissions XML). See the [Security README](../../system_arch/security/README.md) for full details.

```bash
python3 system_arch/security/setup_security.py
```

Re-run with `--force` to regenerate existing artifacts.

## Run the Demo

### 1. Launch the applications

Run operating room applications:

```bash
python3 launch.py 01-operating-room
```

To run with security enabled, use the `-s` option:

```bash
python3 launch.py 01-operating-room -s
```

*This script does the following:*

1. Set `NDDS_QOS_PROFILES` environment variable to load the appropriate XML configuration files (QoS Profiles, Domains, DomainParticipants).

2. Launch the application executables.

*Note, applications can be launched individually by name, e.g. `python3 launch.py 01-operating-room Arm PatientMonitor`. Refer to [module.json](./module.json) for the list of available app names and QoS configuration.*

### 2. Observe the application behavior

Observe and play around with the interactive operating room applications. The following are some ideas to get started:

- From the *Orchestrator* application, send a "PAUSE" command to the *Patient Sensor* Medical Device. Observe the effect in the *Patient Monitor* GUI application. Resume the *Patient Sensor* by sending a "START" command.
- From the *Arm Controller* application, send a command to stop all *Arm* motors. Observe the effect in the *Arm* GUI application. Resume just the *Elbow* motor by clicking the respective "PLAY" button in the *Arm Controller* application. While still stopped, increment or decrement the *Wrist* motor angle by clicking the respective "+" or "-" buttons in the *Arm Controller* application. Resume all *Arm* motors by pressing "PLAY ALL".
- Ungracefully terminate the *Arm* application by closing the application window. Observe the effect in the *Orchestrator* application "Alerts" panel.
- Initiate a gracefull remote shutdown of the *Arm Controller* by sending the appropriate command from the *Orchestrator*. Observe the effect of the *Arm Controller* application.

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

    >**Observe:** You should see both the *Arm Controller* and *Patient Monitor* applications shut down and exit. This is because the *Patient Monitor* is no longer to configured to recieve only device commands for Patient Monitor apps but any app.

5. Undo the Content Filter change to revert to the recommended configuration.

## Next Steps

Check out [Module 02: RTI Recording Service & RTI Replay Service](../02-record-playback/), which builds upon the applications from this module to show how data can be recorded from and replayed to the same applications.

Check out [Module 03: Remote Teleoperation with RTI Real-Time WAN Transport](../03-remote-teleoperation/), which builds upon the applications from this module to show how applications can be deployed remotely and integrate seamlessly over the Wide Area Network (WAN).

Head back to the [main README](../../README.md) and pick up with the [Hands-On: Architecture](../../README.md#hands-on-architecture) section to learn more about the system architecture.
