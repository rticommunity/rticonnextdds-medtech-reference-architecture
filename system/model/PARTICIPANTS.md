# Participant library

[← DDS model](README.md)

## DomainParticipant Library

### DomainParticipant Configuration

The hierarchy of DDS entities and components configured in a DomainParticipant are as follows:

```text
DomainParticipant → Domain
├── DomainParticipant QoS → QoS Profile
├── Publisher
| ├── Publisher QoS → QoS Profile
│   └── DataWriter → Topic
| └── DataWriter QoS → QoS Profile
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

#### DomainParticipant

```text
Tag: <domain_participant>

Attributes:
  name:         Must be unique within the DomainParticipant Library.
                Applications use the 'create_participant_from_config()' API with this name
                to create the DomainParticipant and all underlying entities in code.
  domain_ref:   A reference to the Domain defined in a Domain Library.
                This DomainParticipant will use the Domain ID, Topics and Data Types defined
                in that Domain.

Subelements:
  <domain_participant_qos>: Explicit QoS for the DomainParticipant to use.
  <publisher>:              See section 'Publisher'.
  <subscriber>:             See section 'Subscriber'.
```

#### Publisher

```text
Tag: <publisher>

Attributes:
  name:             Must be unique within the DomainParticipant.

Subelements:
  <publisher_qos>:  Explicit QoS for the Publisher to use.
  <data_writer>:    See section 'DataWriter'.
```

#### DataWriter

```text
Tag: <data_writer>

Attributes:
  name:             Must be unique within the Publisher.
                    Applications use a 'find_datawriter_by_name()' API with this name to
                    retrieve DataWriters in code.
  topic_ref:        A reference to the Topic defined in the Domain the DomainParticipant is
                    configured to operate on.
                    This DataWriter must use the Data Type the Topic is configured to use in
                    that Domain.

Subelements:
  <datawriter_qos>: Explicit QoS for the DataWriter to use.
```

#### Subscriber

```text
Tag: <subscriber>

Attributes:
  name:             Must be unique within the DomainParticipant.

Subelements:
  <subscriber_qos>: Explicit QoS for the Subscriber to use.
  <data_reader>:    See section 'DataReader'.
```

#### DataReader

```text
Tag: <data_reader>

Attributes:
  name:             Must be unique within the Subscriber.
                    Applications use a 'find_datareader_by_name()' API with this name to
                    retrieve DataReaders in code.
  topic_ref:        A reference to the Topic defined in the Domain the DomainParticipant is
                    configured to operate on.
                    This DataReader must use the Data Type the Topic is configured to use in
                    that Domain.

Subelements:
  <datareader_qos>: Explicit QoS for the DataReader to use.
  <content_filter>: See section 'Content Filter'.
```

#### Content Filter

```text
Tag: <content_filter>

Subelements:
  <expression>:             Uses the name of the fields defined in the Data Type and the
                            contents of the field data.
  <expression_parameters>:  Defines initial values for expression parameter references.
```

### [ParticipantLibrary.xml](ParticipantLibrary.xml)

This reference architecture defines the following DomainParticipant library in [ParticipantLibrary.xml](ParticipantLibrary.xml):

| DomainParticipant Library | Intended Use
| ------------------------- | ------------
| [*MedicalDemoParticipantLibrary*](#medicaldemoparticipantlibrary) | Contains all defined module DomainParticipants

#### ***MedicalDemoParticipantLibrary***

This reference architecture defines the following DomainParticipants in [ParticipantLibrary.xml](ParticipantLibrary.xml):

| DomainParticipant | Domain
| ----------------- | ------
| [*dp/Arm*](#medicaldemoparticipantlibrarydparm) | [*ConnextDomainLib::OperationalDataDomain*](DOMAINS.md#connextdomainliboperationaldatadomain)
| [*dp/ArmKortex*](#medicaldemoparticipantlibrarydparmkortex) | [*ConnextDomainLib::OperationalDataDomain*](DOMAINS.md#connextdomainliboperationaldatadomain)
| [*dp/ArmController*](#medicaldemoparticipantlibrarydparmcontroller) | [*ConnextDomainLib::OperationalDataDomain*](DOMAINS.md#connextdomainliboperationaldatadomain)
| [*dp/Orchestrator*](#medicaldemoparticipantlibrarydporchestrator) | [*ConnextDomainLib::OperationalDataDomain*](DOMAINS.md#connextdomainliboperationaldatadomain)
| [*dp/PatientSensor*](#medicaldemoparticipantlibrarydppatientsensor) | [*ConnextDomainLib::OperationalDataDomain*](DOMAINS.md#connextdomainliboperationaldatadomain)
| [*dp/PatientMonitor*](#medicaldemoparticipantlibrarydppatientmonitor) | [*ConnextDomainLib::OperationalDataDomain*](DOMAINS.md#connextdomainliboperationaldatadomain)
| [*dp/SecureLogReader*](#medicaldemoparticipantlibrarydpsecurelogreader) | [*ConnextDomainLib::SecureLogDomain*](DOMAINS.md#connextdomainlibsecurelogdomain)

##### ***MedicalDemoParticipantLibrary::dp/Arm***

The *Arm* participant demonstrates six-axis kinematic TCP motion and parallel
jaws. It publishes observed feedback separately from command intent.

*dp/Arm* contains the following DataWriters (`<data_writer>`):

| DataWriter | Topic | QoS Profile | Intended Use
| ---------- | ----- | ----------- | ------------
| *dw/DeviceStatus* | *t/device/status* | [*DataFlowLibrary::Status*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarystatus-profile) | Publish Arm device status
| *dw/DeviceHeartbeat* | *t/device/heartbeat* | [*DataFlowLibrary::Heartbeat*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibraryheartbeat-profile) | Assert Arm device is alive
| *dw/ArmTelemetry* | *t/robot/arm/telemetry* | `DataFlowLibrary::Telemetry` | Periodic observed pose and optional jaw gap

*dp/Arm* contains the following DataReaders (`<data_reader>`):

| DataReader | Topic | QoS Profile | Content Filter | Intended Use
| ---------- | ----- | ----------- | -------------- | ------------
| *dr/TeleopControl* | *t/robot/arm/control* | [*DataFlowLibrary::Control*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarycontrol-profile) | -- | Read current base-frame linear/angular TCP rates each step
| *dr/ToolControl* | *t/robot/tool/control* | `DataFlowLibrary::Control` | -- | Read current signed total jaw-opening rate each step
| *dr/DeviceCommand* | *t/device/command* | [*DataFlowLibrary::Command*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarycommand-profile) | `device = 'ARM'` | Receive and process device commands targeting this Arm

##### ***MedicalDemoParticipantLibrary::dp/ArmKortex***

The experimental Kortex participant uses the same Arm participant QoS,
writers, arm-control reader and ARM-filtered lifecycle-command reader as
[*dp/Arm*](#medicaldemoparticipantlibrarydparm), but has no `dr/ToolControl`.
It therefore does not match jaw command writers or require jaw updates for
motion admission. It reports observed TCP telemetry without a jaw gap.
This changes no wire types, routed/recorded topics or security identity: it
uses the existing Arm role. See the [physical-device limitations and re-arm
requirements](../../modules/01-operating-room/ARM_AND_CONTROLLER.md#experimental-kinova-motion-arm).

##### ***MedicalDemoParticipantLibrary::dp/ArmController***

The *ArmController* DomainParticipant is intended to administer commands to the [*Arm*](#medicaldemoparticipantlibrarydparm) DomainParticipant, to control its motors.

*dp/ArmController* contains the following DataWriters (`<data_writer>`):

| DataWriter | Topic | QoS Profile | Intended Use
| ---------- | ----- | ----------- | ------------
| *dw/TeleopControl* | *t/robot/arm/control* | [*DataFlowLibrary::Control*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarycontrol-profile) | Publish teleoperation control state to Arm devices
| *dw/ToolControl* | *t/robot/tool/control* | `DataFlowLibrary::Control` | Publish complete signed jaw-opening rate
| *dw/DeviceStatus* | *t/device/status* | [*DataFlowLibrary::Status*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarystatus-profile) | Publish ArmController device status
| *dw/DeviceHeartbeat* | *t/device/heartbeat* | [*DataFlowLibrary::Heartbeat*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibraryheartbeat-profile) | Assert ArmController device is alive

*dp/ArmController* contains the following DataReaders (`<data_reader>`):

| DataReader | Topic | QoS Profile | Content Filter | Intended Use
| ---------- | ----- | ----------- | -------------- | ------------
| *dr/DeviceCommand* | *t/device/command* | [*DataFlowLibrary::Command*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarycommand-profile) | `device = 'ARM_CONTROLLER'` | Receive and process device commands targeting this Arm Controller
| *dr/DeviceStatus* | *t/device/status* | `DataFlowLibrary::Status` | `device = 'ARM'` | Observe arm readiness
| *dr/ArmTelemetry* | *t/robot/arm/telemetry* | `DataFlowLibrary::Telemetry` | -- | Display actual pose/gap with independent freshness

##### ***MedicalDemoParticipantLibrary::dp/Orchestrator***

The *Orchestrator* DomainParticipant is intended to administer device-level commands to all other DomainParticipants in the system. It also monitors status and presence of all system devices.

*dp/Orchestrator* contains the following DataWriters (`<data_writer>`):

| DataWriter | Topic | QoS Profile | Intended Use
| ---------- | ----- | ----------- | ------------
| *dw/DeviceCommand* | *t/device/command* | [*DataFlowLibrary::Command*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarycommand-profile) | Publish Device commands to all devices

*dp/Orchestrator* contains the following DataReaders (`<data_reader>`):

| DataReader | Topic | QoS Profile | Content Filter | Intended Use
| ---------- | ----- | ----------- | -------------- | ------------
| *dr/DeviceStatus* | *t/device/status* | [*DataFlowLibrary::Status*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarystatus-profile) | -- | Receive and process device statuses from all devices
| *dr/DeviceHeartbeat* | *t/device/heartbeat* | [*DataFlowLibrary::Heartbeat*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibraryheartbeat-profile) | -- | Detect (loss of) presence of all devices

##### ***MedicalDemoParticipantLibrary::dp/PatientSensor***

The *PatientSensor* DomainParticipant is intended to simulate a streaming source for patient vitals data.

*dp/PatientSensor* contains the following DataWriters (`<data_writer>`):

| DataWriter | Topic | QoS Profile | Intended Use
| ---------- | ----- | ----------- | ------------
| *dw/Vitals* | *t/patient/vitals* | [*DataFlowLibrary::Vitals*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibraryvitals-profile) | Publish simulated patient vitals data stream
| *dw/DeviceStatus* | *t/device/status* | [*DataFlowLibrary::Status*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarystatus-profile) | Publish PatientSensor device status
| *dw/DeviceHeartbeat* | *t/device/heartbeat* | [*DataFlowLibrary::Heartbeat*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibraryheartbeat-profile) | Assert PatientSensor device is alive

*dp/PatientSensor* contains the following DataReaders (`<data_reader>`):

| DataReader | Topic | QoS Profile | Content Filter | Intended Use
| ---------- | ----- | ----------- | -------------- | ------------
| *dr/DeviceCommand* | *t/device/command* | [*DataFlowLibrary::Command*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarycommand-profile) | `device = 'PATIENT_SENSOR'` | Receive and process device commands targeting this PatientSensor

##### ***MedicalDemoParticipantLibrary::dp/PatientMonitor***

The *PatientMonitor* DomainParticipant is intended to process (display) patient vitals data in a graphical plot over time.

*dp/PatientMonitor* contains the following DataWriters (`<data_writer>`):

| DataWriter | Topic | QoS Profile | Intended Use
| ---------- | ----- | ----------- | ------------
| *dw/DeviceStatus* | *t/device/status* | [*DataFlowLibrary::Status*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarystatus-profile) | Publish PatientMonitor device status
| *dw/DeviceHeartbeat* | *t/device/heartbeat* | [*DataFlowLibrary::Heartbeat*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibraryheartbeat-profile) | Assert PatientMonitor device is alive

*dp/PatientMonitor* contains the following DataReaders (`<data_reader>`):

| DataReader | Topic | QoS Profile | Content Filter | Intended Use
| ---------- | ----- | ----------- | -------------- | ------------
| *dr/DeviceCommand* | *t/device/command* | [*DataFlowLibrary::Command*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarycommand-profile) | `device = 'PATIENT_MONITOR'` | Receive and process device commands targeting this PatientMonitor
| *dr/Vitals* | *t/patient/vitals* | [*DataFlowLibrary::Vitals*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibraryvitals-profile) | `patient_id = %0` | Receive the configured patient ID (default `ab1234`)

##### ***MedicalDemoParticipantLibrary::dp/SecureLogReader***

The *SecureLogReader* DomainParticipant subscribes to the RTI Security Plugins builtin secure-logging Topic, demonstrating how secure-log events can be consumed by an application. It operates on [*SecureLogDomain*](DOMAINS.md#connextdomainlibsecurelogdomain).

*dp/SecureLogReader* contains the following DataReaders (`<data_reader>`):

| DataReader | Topic | QoS Profile | Content Filter | Intended Use
| ---------- | ----- | ----------- | -------------- | ------------
| *dr/SecureLog* | *DDS:Security:LogTopicV2* | [*DataFlowLibrary::SecureLog*](../qos/QOS_PROFILE_REFERENCE.md#dataflowlibrarysecurelog-profile) | -- | Receive DDS Security builtin secure-log samples

### DomainParticipant Library Best Practices

> [!TIP]
> **Best practice:** Group your DataWriters into a single Publisher, and your DataReaders into a single Subscriber for a given DomainParticipant, unless your requirements dictate otherwise.

> [!TIP]
> **Best practice:** Use consistent naming conventions to make entities easy
> to identify. This project uses the `dp/` prefix for DomainParticipants; DDS
> does not require it.

> [!TIP]
> **Best practice:** Reference explicit QoS Profiles for each entity. This ensures each entity uses the intended QoS Profile as designed.

> [!TIP]
> **Best practice:** Keep shared QoS in named QoS profiles to make it easier
> to review and reuse. Inline QoS is valid when appropriate to the application.
