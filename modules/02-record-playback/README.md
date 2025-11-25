# Module 02: RTI Recording Service & RTI Replay Service

Module 02 demonstrates recording and playback of Digital Operating Room data from [Module 01: Digital Operating Room](../01-operating-room/).

RTI Recording Service is used to record realtime DDS data on the following Topics:

- *t/MotorControl*
- *t/Vitals*

RTI Replay Service is used to play back the recorded data to the Arm and Patient Monitor GUI applications, simulating live data.

This module reuses the operating room applications from [Module 01](../01-operating-room/). Those applications have been tested to work in Debian-based environments with a GUI, including those in [WSL2 with GUI support](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps#install-support-for-linux-gui-apps).

RTI Recording Service and RTI Replay Service can be run on any [officially supported platform](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/release_notes/pam_table.html#rti-infrastructure-services), provided the machine is directly discoverable by the machine the operating room applications are launched from.

## Contents

- [Module Description](#module-description)
- [Setup and Installation](#setup-and-installation)
- [Run the Demo](#run-the-demo)
- [Hands-On: Going Further](#hands-on-going-further)
- [Next Steps](#next-steps)

## Module Description

This module uses RTI Recording Service to record data from the operating room applications from Module 01. It then uses RTI Replay Service to replay the recorded data back to the same OR applications. Please find a diagram of how Recording / Replay Service connect to the RTI Connext Databus below:

![diagram](../../resource/images/module-02-diagram-record-playback.svg)

### RTI Recording Service

RTI Recording Service is used in this module to record the `t/MotorControl` and `t/Vitals` Topics from [Module 01: Digital Operating Room](../01-operating-room/).

### RTI Replay Service

RTI Recording Service is used in this module to replay recorded data from the `t/MotorControl` and `t/Vitals` Topics from [Module 01: Digital Operating Room](../01-operating-room/).

## Setup and Installation

### 1. See Module 01 Setup and Installation

[Installation and build steps from Module 01: Digital Operating Room](../01-operating-room/README.md#setup-and-installation) satisfy prerequisites for this module.

### 2. Security (optional)

Generate the security artifacts for RTI Recording Service and RTI Replay Service using OpenSSL.
This includes identity certificates, private keys, and the signing of DDS Security XML permissions & governance files located in [system_arch/security](../../system_arch/security).

```bash
cd system_arch/security
./setup_security.sh
```

## Run the Demo

### 1. Run Operating Room Applications

In its own terminal, launch the operating room applications from [Module 01](../01-operating-room/README.md#run-the-demo) (use `-s` option for security):

```bash
cd 01-operating-room
./scripts/launch_all.sh [-s]
```

### 2. Run RTI Recording Service

Configure the Connnext environment with [NonSecureAppsQos.xml](../../system_arch/NonSecureAppsQos.xml):

```bash
cd 02-record-playback
source <connext installation directory>/resource/scripts/rtisetenv_x64Linux4gcc7.3.0.bash
export NDDS_QOS_PROFILES="../../system_arch/qos/Qos.xml;../../system_arch/qos/NonSecureAppsQos.xml"
```

Alternatively, if using security, configure with [SecureAppsQos.xml](../../system_arch/SecureAppsQos.xml):

```bash
cd 02-record-playback
source <connext installation directory>/resource/scripts/rtisetenv_x64Linux4gcc7.3.0.bash
export NDDS_QOS_PROFILES="../../system_arch/qos/Qos.xml;../../system_arch/qos/SecureAppsQos.xml"
```

Run RTI Recording Service:

```bash
$NDDSHOME/bin/rtirecordingservice -cfgFile RecordingServiceConfiguration.xml -cfgName RecServCfg
```

Let RTI Recording Service run for some time (e.g. 10-20 seconds) before initiating shutdown with `Ctrl-C`.

>**Observe:** Once finished, a new folder should be created - [or_recording](./or_recording/) - containing the recording files.

#### Further Learning: Recording Service

Inspect [RecordingServiceConfiguration.xml](RecordingServiceConfiguration.xml) to understand how RTI Recording Service is configured to record DDS Topics.

### 3. Shutdown Operating Room Applications / Restart GUI Applications

Kill all running operating room application processes:

```bash
../01-operating-room/scripts/kill_all.sh
```

Relaunch the Digital Operating Room Arm and Patient Monitor GUI applications only (use `-s` option for security):

```bash
cd 01-operating-room
./scripts/launch_arm_and_patient_monitor.sh [-s]
```

>**Observe:** You should see the GUI applications are not receiving data.

### 4. Run RTI Replay Service

In the terminal RTI Recording Service was launched and shutdown from [Step 2](#2-run-rti-recording-service), launch RTI Replay Service (to reuse the previously configured environment):

```bash
$NDDSHOME/bin/rtireplayservice -cfgFile ReplayServiceConfiguration.xml -cfgName RepServCfg
```

>**Observe:** You should see the Arm and Patient Monitor applications are receiving data previously recorded.

The Replay Service configuration has `<enable_looping>` set to `true`, so the replay will start over when it reaches the end of the recording.

### 5. Kill the applications

Kill all active operating room applications:

```bash
../01-operating-room/scripts/kill_all.sh
```

#### Further Learning: Replay Service

Inspect [ReplayServiceConfiguration.xml](ReplayServiceConfiguration.xml) to understand how RTI Replay Service is configured to replay recorded DDS Topics.

## Hands-On: Going Further

Here are a few hands-on exercises to demonstrate use cases of Connext features in this module.

### 1. Recording All Topics

The module is configured to record and replay just `t/MotorControl` and `t/Vitals` Topics only on Domain 0. Both RTI Recording Service and RTI Replay Service can be configured to record and replay explicit Topics, or discovered Topics/Data Types that match a pattern.

Let's try replaying just `t/Vitals`, while still recording both Topics.

1. Kill all active operating room applications and RTI Recording/Replay Services.

2. Comment out the `<topic>` tag  and contained content within it, for `t/MotorControl` in [RecordingServiceConfiguration.xml](./RecordingServiceConfiguration.xml).

    *Note, you should undo this configuration change after completing this demonstration.*

3. Relaunch the operating room applications and RTI Recording Service for 10-20 seconds.

4. Kill RTI Recording Service and the operating room applications.

5. Relaunch the operating room *Arm* and *Patient Monitor* applications and RTI Replay Service.

6. While monitoring the *Arm* and *Patient Monitor* application GUIs, start RTI Replay Service.

    >**Observe:** You should see the *Patient Monitor* receiving data, but *Arm* should appear as if there is no motor movement. This is because while RTI Replay Service is configured to replay data on both `t/MotorControl` and `t/Vitals` Topics, only data for `t/Vitals` was recorded.

7. Undo the QoS change to revert to the recommended configuration.

### 2. RTI Admin Console

[RTI Admin Console](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/tools/admin_console/index.html) is a troubleshooting tool that includes handy integrations for RTI Recording Service and RTI Replay Service. This module configures both RTI Recording Service and RTI Replay Service to allow for "administration" capabilities on Domain 99.

Let's try using RTI Admin Console to administer RTI Recording Service.

1. Launch RTI Admin Console.

    - From RTI Launcher:
        1. Open *RTI Launcher*.
        2. Navigate to the **Tools** tab.
        3. Click the *Admin Console* button.
    - From a terminal:
        1. Launch the `rtiadminconsole[.bat]` script found in the *$NDDSHOME/bin* folder. *Where *$NDDSHOME* is the folder where Connext is installed.*

2. In RTI Admin Console, join Domains 0 (Operational Data) and 99 (RTI Recording Service Administration).

    1. In RTI Admin Console toolbar, go to "View" > "Preferences".
    2. In the preferences popup, ensure you have the "Administration" tab selected in the sidebar.
    3. In the popup's main panel, select the "Manually join and leave domains" radio button.
    4. In next field, "Please specify the domains to be joined", enter `0,99`.
    5. Click "Apply and Close" in the Preferences popup.

3. Launch the operating room applications and RTI Recording Service.

4. In RTI Admin Console, go to the "Physical View" and select the RTI Recording Service process.

    1. In RTI Admin Console toolbar, go to "View" and check if an option "Show Physical Tree View" exists - if so, click it. If instead, you see "Hide Physical Tree View", find the Physical Tree view panel already open.
    2. Expand the "System" tree two levels ("System", \<hostname>).
    3. Select `RecServCfg`.

5. In RTI Admin Console main panel, view RTI Recording Service statuses and available commands.

6. Remotely shut down RTI Recording Service.

    1. From RTI Admin Console, while viewing the RTI Recording Service process, click the "Shutdown" button to stop and kill the RTI Recording Service process.
    2. Confirm in the popup that you would like to shut down the service.

    >**Observe:** You should see the RTI Recording Service process has been stopped gracefully in the terminal which you launched it.

## Next Steps

Check out [Module 03: Remote Teleoperation with RTI Real-Time WAN Transport](../03-remote-teleoperation/), which builds upon the applications from this module to show how applications can be deployed remotely and integrate seamlessly over the Wide Area Network (WAN).

Head back to the [main README](../../README.md) and pick up with the [Hands-On: Architecture](../../README.md#hands-on-architecture) section to learn more about the system architecture.
