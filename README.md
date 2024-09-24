# RTI MedTech Reference Architecture

The Medical Reference Architecture demonstrates RTI's best practices for building medical devices using RTI Connext.

This repository contains documentation and demo applications showcasing different capabilities of Connext in a Medical context. The goal is to provide a comprehensive guide to help developers leverage Connext for building robust, scalable, and interoperable medical systems.

## Contents

- [Introduction](#introduction)
- [Getting Started](#getting-started)
- [Cloning the Repository](#cloning-the-repository)
- [Hands-On: Demos](#hands-on-demos)
  - [Demo 1: Digital Operating Room](#demo-1--digital-operating-room)
  - [Demo 2: RTI Recording Service & RTI Replay Service](#demo-2--rti-recording-service--rti-replay-service)
- [Hands-On: Architecture](#hands-on-architecture)
- [Architecture Overview](#architecture-overview)
  - [Data Types](#data-types)
  - [Quality of Service (QoS)](#quality-of-service-qos)
  - [Domains & Topics](#domains--topics)
  - [DomainParticipants & DDS Entities](#domainparticipants--dds-entities)
- [Going Further](#going-further)
  - [Want to dig deeper?](#want-to-dig-deeper)
- [Additional references](#additional-references)

## Introduction

RTI Connext is a leading connectivity framework designed to facilitate real-time data distribution in distributed systems. In the medical field, it is crucial to have reliable and timely data exchange between various medical devices and systems. This project aims to illustrate how Connext can be used to build a robust Medical Reference Architecture that ensures data interoperability, scalability, and reliability.

By following the examples and best practices outlined in this documentation, architects and developers can find inspiration to create medical applications.

## Getting Started

*RTI strongly recommends proceeding in the following order:*

1. Setup: [Clone the repository.](#cloning-the-repository)
2. Run: [Run the demos.](#hands-on-demos)
3. Learn: [Understand the architecture.](#hands-on-architecture)

## Cloning the Repository

To clone the repository you will need to run git clone as follows to download both the repository and its submodule dependencies:

```sh
git clone --recurse-submodule https://github.com/rticommunity/rticonnextdds-usecases.git
```

If you forget to clone the repository with `--recurse-submodule`, simply run
the following command to pull all the dependencies:

```sh
git submodule update --init --recursive
```

For the specific demos and their prerequisites, refer to the README.md located in each demo folder.

## Hands-On: Demos

The RTI MedTech Reference Architecture demos showcase usage and capabilities of the provided system architecture.

*RTI recommends following along the demo-specific READMEs before returning here and learning more about the designed system architecture.*

- ### [Demo 1](./demos/demo1/) : Digital Operating Room

- ### [Demo 2](./demos/demo2/) : RTI Recording Service & RTI Replay Service

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

Through *RTI XML-Based Application Creation*, aspects of all 4 components are expressed in XML statically, separate from application code and choice of language. This allows for the extraction of a common system definition from the application logic and behavior - a must-have for designing integrated systems with multiple development teams.

Please find a diagram of the Digital OR demo below:

![diagram](./resource/images/digital_OR_diagram.svg)

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

The heirarchy of components configured in a QoS Profile are as follows:

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
| DataFlow    | Heartbeat           | Assert and detect the presense of system devices

### Domains & Topics

A Domain represents a data space where data can be shared by means of reading and writing the same Topics, where each Topic has a corresponding Data Type. In a Domain, you can define Topics and associate Data Types.

The heirarchy of the components configured in a Domain are as follows:

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

The heirarchy of DDS entities and components configured in a DomainParticipant are as follows:

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

| Domain                | DomainParticipant | Subscriptions                       | Publications                                    | Intended Use
| ------                | ----------------- | ----------                          | ---------                                       | ------------
| OperationalDataDomain | Arm               | `t/DeviceCommand`, `t/MotorControl`  | `t/DeviceStatus`, `t/DeviceHeartbeat`            | Operate a robotic surgery arm with 5 motors: Base, Shoulder, Elbow, Wrist, and Hand.
| OperationalDataDomain | ArmController     | `t/DeviceCommand`                   | `t/MotorControl`, `t/DeviceHeartbeat`            | Administer commands to an Arm device to control its motors.
| OperationalDataDomain | Orchestrator      | `t/DeviceStatus`, `t/DeviceHeartbeat`| `t/DeviceCommand`                               | Administer device-level commands and monitor presense and status of all devices.
| OperationalDataDomain | PatientSensor     | `t/DeviceCommand`                   | `t/Vitals`, `t/DeviceStatus`, `t/DeviceHeartbeat` | Stream simulated patient vitals.
| OperationalDataDomain | PatientMonitor    | `t/DeviceCommand`, `t/Vitals`        | `t/DeviceStatus`, `t/DeviceHeartbeat`            | Process and display patient vitals.

*Note, this reference architecture utilizes one DomainParticipant for each device application. It is a **best practice** to define one DomainParticipant per application. However, in more complex systems, an application may be required to operate on multiple Domains. This requires defining multiple DomainParticipants for those applications that run in parallel.*

## Going Further

### Want to dig deeper?

Check out the the [system_arch](./system_arch/) folder, where the system architecture artifacts live and are covered in more depth!

## Additional References

- [RTI XML-Based Application Creation](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/XMLAppCreationGSG_title.htm#)
- [RTI System Designer](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/tools/system_designer/index.html)
- [RTI Core Libraries Users Manual](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/users_manual/users_manual/title.htm#)
- [RTI Connext Modern C++ API](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/api/connext_dds/api_cpp2/index.html) *, used by demo applications*
- [RTI Connext Python API](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/api/connext_dds/api_python/index.html) *, used by demo applications*
- [RTI Recording Service & Replay Service](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/services/recording_service/introduction.html) *, used in demo*
