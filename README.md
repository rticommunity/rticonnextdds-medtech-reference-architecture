# RTI MedTech Reference Architecture

The Medical Reference Architecture demonstrates RTI's best practices for building medical devices using RTI Connext®.

This repository contains documentation and module demo applications showcasing different capabilities of Connext in a Medical context. The goal is to provide a comprehensive guide to help developers leverage Connext for building robust, scalable, and interoperable medical systems.

## Contents

- [Introduction](#introduction)
- [Quick Start](#quick-start)
- [Hands-On: Modules](#hands-on-modules)
  - [Module 01: Digital Operating Room](#module-01--digital-operating-room)
  - [Module 02: RTI Recording Service & RTI Replay Service](#module-02--rti-recording-service--rti-replay-service)
  - [Module 03: Remote Teleoperation with RTI Real-Time WAN Transport](#module-03--remote-teleoperation-with-rti-real-time-wan-transport)
  - [Module 04: Security Threat Demonstration](#module-04--security-threat-demonstration)
- [Hands-On: Architecture](#hands-on-architecture)
- [Architecture Overview](#architecture-overview)
  - [Data Types](#data-types)
  - [Quality of Service (QoS)](#quality-of-service-qos)
  - [Domains & Topics](#domains--topics)
  - [DomainParticipants & DDS Entities](#domainparticipants--dds-entities)
  - [DDS Security](#dds-security)
- [Going Further](#going-further)
  - [Want to dig deeper?](#want-to-dig-deeper)
- [Additional references](#additional-references)

## Introduction

RTI Connext is a leading connectivity framework designed to facilitate real-time data distribution in distributed systems. In the medical field, it is crucial to have reliable and timely data exchange between various medical devices and systems. This project aims to illustrate how Connext can be used to build a robust Medical Reference Architecture that ensures data interoperability, scalability, and reliability.

By following the examples and best practices outlined in this documentation, architects and developers can find inspiration to create medical applications.

Here are some links that compliment this repository:

- [MedTech Reference Architecture Overview on Youtube](https://www.youtube.com/watch?v=RiFxmO6RAEw).
- [Capability Brief PDF](https://www.rti.com/hubfs/_Collateral/capability-briefs/rti-capability-brief-MedTech-Reference-Architecture.pdf)
- [Case+Code page on rti.com](https://www.rti.com/developers/case-code/medtech-reference-architecture)

## Quick Start

The steps below cover environment setup, dependencies, security artifacts, and building the project. To run anything, follow the module-specific README for the scenario you want to explore.

### 1. Prerequisites

You will need:

- **RTI Connext DDS 7.3** installed and `NDDSHOME` set, including the Python API `.whl`.
  See the [Installation Guide](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/installation_guide/installation_guide/Installing.htm) and [Python API setup](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/getting_started_guide/python/before_python.html#installing-connext-heading).

  > If `NDDSHOME` is not already in your environment, source the platform setup script from your Connext installation: `source <connext_dir>/resource/scripts/rtisetenv_<arch>.bash` (Linux/macOS) or `rtisetenv_<arch>.bat` (Windows). This script sets `NDDSHOME`, `CONNEXTDDS_ARCH`, and related library paths required by both `build.py` and `launch.py`.
- **CMake** ≥ 3.17 and a C++ compiler toolchain.
- **Python** ≥ 3.9.

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

### 2. Clone the Repository

```bash
git clone https://github.com/rticommunity/rticonnextdds-medtech-reference-architecture.git
cd rticonnextdds-medtech-reference-architecture
```

### 3. Set Up a Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Install the RTI Connext Python API from your local Connext installation:
pip install rti.connext.activated -f $NDDSHOME/resource/python_api
# Alternatively, if the above path is not available, install from PyPI:
# pip install rti.connext==7.3.0
```

### 4. Build the C++ Modules

Build all modules:

```bash
python3 build.py
```

To build only the modules you intend to run:

```bash
python3 build.py --target module-01   # all C++ targets in Module 01
python3 build.py --target ArmController  # only the ArmController target
```

The compiled binaries are placed under `build/<CONNEXTDDS_ARCH>/`.

### 5. Generate Security Artifacts *(optional — skip if not using `-s`)*

The security flag (`-s`) requires PKI certificates, signed governance/permissions XML, and a WAN PSK seed file. Generate them once:

```bash
python3 system_arch/security/setup_security.py
```

Re-run with `--force` to regenerate existing artifacts. See the [Security README](./system_arch/security/README.md) for full details.

When setup is complete, use the module-specific READMEs below to choose a workflow. They explain what each demo launches and how to run it from the repository root with the project-level `launch.py` script.

## Hands-On: Modules

The RTI MedTech Reference Architecture demonstrates use cases and capabilities of the provided system architecture.

Use the module-specific READMEs when you want to run a demo. They describe what each workflow launches, why it exists, and the exact `launch.py` commands to use from the repository root.

- ### [Module 01](./modules/01-operating-room/) : Digital Operating Room

- ### [Module 02](./modules/02-record-playback/) : RTI Recording Service & RTI Replay Service

- ### [Module 03](./modules/03-remote-teleoperation/) : Remote Teleoperation with RTI Real-Time WAN Transport

- ### [Module 04](./modules/04-security-threat/) : Security Threat Demonstration

## Hands-On: Architecture

RTI System Designer allows you to graphically design, configure, examine, and share Connext system architectures.

*RTI recommends using the provided RTI System Designer project file ([RefArch.rtisdproj](./system_arch/RefArch.rtisdproj)) to follow along with the next section, [Architecture Overview](#architecture-overview).*

1. Launch RTI System Designer.
    - From RTI Launcher:
        1. Open *RTI Launcher*.
        2. Navigate to the **Tools** tab.
        3. Click the *System Designer* button.
    - From a terminal:
        1. Launch the `rtisystemdesigner[.bat]` script found in the *$NDDSHOME/bin* folder. *Where *$NDDSHOME* is the folder where Connext is installed.*
2. Open the Project File.
    1. Select **Projects** in the toolbar.
    2. Click **Open** in the dropdown.
    3. In the file browser popup, navigate to *system_arch/RefArch.rtisdproj* and open.

*Please refer to [Project Management](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/tools/system_designer/project_mgmt.html) documentation for more detailed instructions on working with RTI System Designer projects.*

## Architecture Overview

The Medical Reference Architecture is designed to support various use cases within the medical domain. This reference architecture ensures that data flows seamlessly from devices to applications, enabling real-time monitoring, decision-making, and reporting.

The RTI MedTech Reference Architecture consists of the following key components:

- [Data Types](#data-types)
- [Quality of Service (QoS)](#quality-of-service-qos)
- [Domains & Topics](#domains--topics)
- [DomainParticipants & DDS Entities](#domainparticipants--dds-entities)
- [DDS Security](#dds-security)

Through *RTI XML-Based Application Creation*, aspects of all 4 components are expressed in XML statically, separate from application code and choice of language. This allows for the extraction of a common system definition from the application logic and behavior - a must-have for designing integrated systems with multiple development teams.

Please find a diagram of the Digital OR module module below:

![diagram](./resource/images/module-01-diagram-digital-OR.svg)

### Data Types

DDS is a **data-centric** communication standard that understands user-defined Data Types. You can define a Data Type, its members, and annotations in IDL, XML, or XSD. *Conversion between file formats and type-support code generation for (de)serialization can be done with [RTI Code Generator](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/code_generator/users_manual/code_generator/users_manual/UsersManual_Title.htm#).*

This reference architecture defines the following Data Types in [Types.xml](./system_arch/Types.xml):

| Data Type       | Intended Use
| ---------       | -----------
| DeviceStatus    | Describes a status (e.g. `ON`, `PAUSED`) for a unique device
| DeviceHeartbeat | Asserts that a unique device is alive
| MotorControl    | Commands the direction of motion for an arm motor (e.g. `SHOULDER`, `ELBOW`)
| DeviceCommand   | Commands initiating a status (e.g. `START`, `SHUTDOWN`) to a unique device
| Vitals          | Describes data representative of a unique patient's collected vital signs

### Quality of Service (QoS)

Quality of Service (QoS) in DDS characterizes a system's infrastructure and data flow. In a QoS Profile, you can define a set of QoS policy values for a DDS entity (e.g. DomainParticipant, DataWriter, DataReader).

The hierarchy of components configured in a QoS Profile are as follows:

```text
QoS Profile
├── DomainParticipant QoS
├── Topic QoS
├── Publisher QoS
├── Subscriber QoS
├── DataWriter QoS
└── DataReader QoS
```

This reference architecture defines the following QoS Profiles in [Qos.xml](./system_arch/qos/Qos.xml):

| Qos Library | Qos Profile         | Intended Use
| ----------- | ---------           | -----------
| System      | DefaultParticipant  | Common, or base, *system configuration* (e.g. transport, network interfaces, discovery, thread priorities, etc.)
| DataFlow    | Streaming           | Periodic data that is published at a high frequency (i.e. frequencies <1 second)
| DataFlow    | Status              | "Current status"-like data, sent once at the beginning of operation and again only upon change to the status
| DataFlow    | Command             | Data that represents commands or trigger some action in the system
| DataFlow    | Heartbeat           | Assert and detect the presence of system devices

### Domains & Topics

A Domain represents a data space where data can be shared by means of reading and writing the same Topics, where each Topic has a corresponding Data Type. In a Domain, you can define Topics and associate Data Types.

The hierarchy of the components configured in a Domain are as follows:

```text
Domain → Domain ID
├── Type Name → Data Type
└── Topic → Type Name
 
Legend:
 → references
```

This reference architecture defines the following Domains in [DomainLibrary.xml](./system_arch/xml_app_creation/DomainLibrary.xml):

| Domain                  | Intended Use
| ------                  | -----------
| OperationalDataDomain   | Real-time operational medical device data

*Note, this reference architecture defines just a single Domain. As a Connext system design scales over time, additional domains could be defined for monitoring, logging, etc. Those additional domains should not affect the performance of our operational data, and therefore should belong to a different domain.*

This reference architecture defines the following Topics in [DomainLibrary.xml](./system_arch/xml_app_creation/DomainLibrary.xml):

| Domain                | Topic               | Intended Use
| ------                | -----               | -----------
| OperationalDataDomain | `t/MotorControl`    | Command the direction of motion for a motor kind (e.g. `SHOULDER`, `ELBOW`)
| OperationalDataDomain | `t/DeviceStatus`    | Status (e.g. `ON`, `PAUSED`) for a unique system component
| OperationalDataDomain | `t/DeviceHeartbeat` | Assert that a unique system component is alive
| OperationalDataDomain | `t/DeviceCommand`   | Command initiating a status (e.g. `START`, `SHUTDOWN`) to a unique system component
| OperationalDataDomain | `t/Vitals`          | Data representative of a unique patient's collected vital signs

*Note, this reference architecture defines a unique Topic for each Data Type defined. While a Topic may only reference a single Data Type, a multi-purpose Data Type can be associated with multiple Topics. It is a **best practice** to limit the number of defined Topics, but in doing so, it may be feasible to re-use a Data Type for several Topics.*

### DomainParticipants & DDS Entities

A DomainParticipant is a discoverable Domain actor. DomainParticipants own DDS entities such as DataWriters and DataReaders.

This is where the entire system architecture is tied together:

- DomainParticipants are configured to operate on a defined *Domain*.
- DomainParticipants are configured to use a defined *QoS Profile*.
- DataWriters and DataReaders are contained within a defined *DomainParticipant*.
- DataWriters and DataReaders are configured to operate on a defined *Topic*, which has been associated with a defined *Data Type*.
- DataWriters and DataReaders are configured to use a defined *QoS Profile*.

The hierarchy of DDS entities and components configured in a DomainParticipant are as follows:

```text
DomainParticipant → Domain
├── DomainParticipant QoS → QoS Profile
├── Publisher
|   ├── Publisher QoS → QoS Profile
│   └── DataWriter → Topic
|       └── DataWriter QoS → QoS Profile
└── Subscriber
    ├── Subscriber QoS → QoS Profile
    └── DataReader → Topic
        └── DataReader QoS → QoS Profile
        └── Content Filter
            ├── Expression
            └── Expression Parameters

Legend:
 → references
```

This reference architecture defines the following DomainParticipants in [ParticipantLibrary.xml](./system_arch/xml_app_creation/ParticipantLibrary.xml):

| Domain                | DomainParticipant | Subscriptions                         | Publications                                       | Intended Use
| --------------------- | ----------------- | ------------------------------------- | -------------------------------------------------- | ------------
| OperationalDataDomain | Arm               | `t/DeviceCommand`, `t/MotorControl`   | `t/DeviceStatus`, `t/DeviceHeartbeat`              | Operate a robotic surgery arm with 5 motors: Base, Shoulder, Elbow, Wrist, and Hand.
| OperationalDataDomain | ArmController     | `t/DeviceCommand`                     | `t/MotorControl`, `t/DeviceHeartbeat`              | Administer commands to an Arm device to control its motors.
| OperationalDataDomain | Orchestrator      | `t/DeviceStatus`, `t/DeviceHeartbeat` | `t/DeviceCommand`                                  | Administer device-level commands and monitor presence and status of all devices.
| OperationalDataDomain | PatientSensor     | `t/DeviceCommand`                     | `t/Vitals`, `t/DeviceStatus`, `t/DeviceHeartbeat`  | Stream simulated patient vitals.
| OperationalDataDomain | PatientMonitor    | `t/DeviceCommand`, `t/Vitals`         | `t/DeviceStatus`, `t/DeviceHeartbeat`              | Process and display patient vitals.

*Note, this reference architecture utilizes one DomainParticipant for each device application. It is a **best practice** to define one DomainParticipant per application. However, in more complex systems, an application may be required to operate on multiple Domains. This requires defining multiple DomainParticipants for those applications that run in parallel.*

### DDS Security

DDS Security defines authentication, access control, and encryption capabilities essential for medical device communications. Security is critical in medical systems to protect patient data, ensure device integrity, and maintain regulatory compliance.

DDS Security is meant to be a pluggable component to the system architecture. This reference architecture demonstrates the flexibility of the RTI Security Plugins, and how a system can be secured purely through configuration. It should be noted that enabling security does have an effect on performance - both at initialization due to authentication and in steady-state operation due to encryption. It is because of this, that a system's architecture should be designed with security in mind, even if application code has no dependency on the use of security.

The reference architecture configures security in [SecureAppsQos.xml](./system_arch/qos/SecureAppsQos.xml) with:

| Component              | Security Features
| ---------------------- | -----------------
| **LAN Communications** | Domain 0 governance, participant-specific certificates and permissions
| **WAN Communications** | Domain 1 governance for WAN connections
| **RTI Services**       | Dedicated security profiles for Recording/Replay Services and Routing Services

Security Artifacts Structure in [security](./system_arch/security/):

- `ca/` - Certificate Authority hierarchy (root CA → intermediate identity CA + intermediate permissions CA)
- `domain_scope/` - Per-domain governance and permissions XML documents with signed versions
- `identity/` - Per-participant identity certificates, private keys, and cert chains organized by module

See the [Security README](./system_arch/security/README.md) for generation instructions and full details.

## Going Further

### Want to dig deeper?

Check out the the [system_arch](./system_arch/) folder, where the system architecture artifacts live and are covered in more depth!

## Additional References

- [RTI XML-Based Application Creation](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/XMLAppCreationGSG_title.htm#)
- [RTI System Designer](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/tools/system_designer/index.html)
- [RTI Core Libraries Users Manual](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/users_manual/users_manual/title.htm#)
- [RTI Security Plugins](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_secure/users_manual/index.html)
- [RTI Connext Modern C++ API](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/api/connext_dds/api_cpp2/index.html) *, used in Module 01: Digital Operating Room*
- [RTI Connext Python API](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/api/connext_dds/api_python/index.html) *, used in Module 01: Digital Operating Room*
- [RTI Recording Service & Replay Service](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/services/recording_service/introduction.html) *, used in Module 02: RTI Recording Service & RTI Replay Service*
- [Connext Real-Time WAN Transport](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/users_manual/users_manual/PartRealtimeWAN.htm) *, used in Module 03: Remote Teleoperation with RTI Real-Time WAN Transport*
- [RTI Routing Service](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/services/routing_service/index.html) *, used in Module 03: Remote Teleoperation with RTI Real-Time WAN Transport*
- [RTI Cloud Discovery Service](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/addon_products/cloud_discovery_service/index.html) *, used in Module 03: Remote Teleoperation with RTI Real-Time WAN Transport*
- [RTI Security Plugins Users Manual](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_secure/users_manual/index.html) *, used in Module 04: Security Threat Demonstration*
- [RTI Connext Third-Party Software](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/release_notes_3rdparty/index.html)
