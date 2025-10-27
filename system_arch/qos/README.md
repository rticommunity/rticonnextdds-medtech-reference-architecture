# Quality of Service (QoS)

This README describes how we've approached QoS in this reference architecture. For a quick introduction to QoS, please go through the QoS section in this other [README](../README.md#quality-of-service-qos), which describes all the XML QoS elements and best practices.

## Contents

- [QoS Profile Configuration](#qos-profile-configuration)
  - [QoS Profile](#qos-profile-elements)
  - [Entity QoS](#entity-qos-elements)
- [Qos.xml](#qosxml)
  - [SystemLibrary](#systemlibrary)
    - [SystemLibrary::DefaultParticipant profile](#systemlibrarydefaultparticipant-profile)
  - [DataFlowLibrary](#dataflowlibrary)
    - [DataFlowLibrary::Streaming profile](#dataflowlibrarystreaming-profile)
    - [DataFlowLibrary::Status profile](#dataflowlibrarystatus-profile)
    - [DataFlowLibrary::Command profile](#dataflowlibrarycommand-profile)
    - [DataFlowLibrary::Heartbeat profile](#dataflowlibraryheartbeat-profile)
- [Application-specific QoS: NonSecureAppsQos.xml and SecureAppsQos.xml](#application-specific-qos-nonsecureappsqosxml-and-secureappsqosxml)
- [XML QoS Best Practices](#xml-qos-best-practices)

## QoS Profile Configuration

The heirarchy of components configured in a QoS profile are as follows:

```text
QoS Profile
├── DomainParticipant QoS
├── Topic QoS
├── Publisher QoS
├── Subscriber QoS
├── DataWriter QoS
└── DataReader QoS
```

### QoS Profile elements

```text
Tag: <qos_profile>

Main attributes:  
  name:             Must be unique within the QoS library. 
  base_name:        The QoS profile to inherit from, and use as a base.

Subelements:
  <base_name>:      Reference QoS Snippets to compose from.
  ...               See section 'Entity QoS elements' below.
```

### Entity QoS elements

```text
Tag: <domain_participant_qos> <publisher_qos> <subscriber_qos> <datawriter_qos> <datareader_qos>

Main attributes:  
  name:           Must be unique within the QoS profile for the entity kind.
  base_name:      The QoS profile to inherit from, and use as a base.
  topic_filter:   A Topic name expression, such that this QoS is used for matching Topics.
                  Only available for DataWriter and DataReader QoS.

Subelements:
  <base_name>:    Reference QoS Snippets to compose from.
  ...             See documentation for entity-specific QoS policies.
```

## [Qos.xml](Qos.xml)

This reference architecture defines the following QoS Libraries in [Qos.xml](./Qos.xml):

| Qos Library       | Intended Use
| -----------       | ------------
| [*SystemLibrary*](#systemlibrary)   | Characterize the *system* (e.g. transport, network interfaces, discovery, thread priorities, etc.). Profiles in this library configure the DomainParticipant QoS. **It is typical to define 1-2 profiles of this kind for any system.**
| [*DataFlowLibrary*](#dataflowlibrary) | Characterize the *dataflows* or *data patterns* (e.g. reliability history, durability, deadline, etc.). Profiles in this library configure DataWriter and DataReader (endpoint) QoS. **It is typical to define 3-5 profiles of this kind for any system.**

### ***SystemLibrary***

*SystemLibrary* contains the following QoS profile (`<qos_profile>`):

| QoS Profile | Intended Use
| ----------- | ------------
| [*DefaultParticipant*](#systemlibrarydefaultparticipant-profile) | Configuration common to all DomainParticipants.

#### ***SystemLibrary::DefaultParticipant* profile**

This QoS profile acts as a common base configuration for all DomainParticipants in the system to provide a level of consistency. It inherits from a builtin profile called *BuiltinQosLib::Generic.Common* through the `base_name` XML attribute.

### ***DataFlowLibrary***

*DataFlowLibrary* contains the following QoS profiles (`<qos_profile>`):

| QoS Profile | Reliability | History (kind+depth) | Durability | Deadline period | Intended Use
| ----------- | ----------- | ------- | ---------- | --------- | -----------
| [*Streaming*](#dataflowlibrarystreaming-profile) | *BEST_EFFORT* | *KEEP_LAST 1* | *VOLATILE* | -- | Periodic Topics that are published at a high frequency (i.e. frequencies <1 second).
| [*Status*](#dataflowlibrarystatus-profile) | *RELIABLE* | *KEEP_LAST 1* | *TRANSIENT_LOCAL* | -- | "Current status"-like Topics, sent once at the beginning of operation and again only upon change to the status.
| [*Command*](#dataflowlibrarycommand-profile) | *RELIABLE* | *KEEP_LAST 1* | *VOLATILE* | -- | Topics that transmit commands or trigger some action in the system.
| [*Heartbeat*](#dataflowlibraryheartbeat-profile) | *BEST_EFFORT* | *KEEP_LAST 1* | *VOLATILE* | *200 ms* | To assert and detect the presense of system components.

#### ***DataFlowLibrary::Streaming* profile**

This QoS profile is used for Topics that are published at a periodic high rate (i.e. frequencies of <1 second).

It inherits from the *BuiltinQosLib::Generic.Common* profile in addition to being composed with builtin QoS snippets. As a result, this QoS profile applies the following:

- *BEST_EFFORT* Reliability QoS. It is not necessary to repair lost samples, which adds overhead and latency, because the next update will arrive quickly.
- *KEEP_LAST, depth=1* History QoS. There is no need to process or track more than 1 sample per instance at a time. You could increase the *depth* on the DataReader side if your application cannot access the data fast enough from the DataReader's queue.

#### ***DataFlowLibrary::Status* profile**

This QoS profile is used for status-related Topics. These are Topics that describe the current status of a system component (a device, an observed object, etc.). They're typically sent once at the beginning of operation and again only upon change to the status.

It inherits from the *BuiltinQosLib::Pattern.Status* profile. As a result, this QoS profile applies the following:

- *RELIABLE* Reliability QoS. Samples should be repaired if lost because the timing of the next status update is unknown.
- *KEEP_LAST, depth=1* History QoS. Typically, only the last status per system component needs to be processed or tracked by subscribing applications, or cached by DataWriters to repair as needed.
- *TRANSIENT_LOCAL* Durability QoS. Late-joining DataReaders should automatically receive the most recent status per system component when they join the communication.
- Some optimizations to make repairs faster.

#### ***DataFlowLibrary::Command* profile**
  
This QoS profile is used for command and event-related Topics. These are Topics that transmit commands or trigger some action in the system. They are not sent periodically. They should not be delivered to late-joining applications that joined after being published.

It inherits from the *BuiltinQosLib::Generic.Common* profile in addition to builtin QoS snippets. As a result, this QoS profile applies the following:

- *RELIABLE* Reliability QoS. Samples should be repaired if lost because the frequency of commands is unkown and irregular.
- *KEEP_LAST, depth=1* History QoS. In this simplified use case, only the last command for a system component should be processed by subscribing applications, or cached by DataWriters to repair as needed.
- *VOLATILE* Durability QoS. Late-joining DataReaders should **not** receive historical commands that were published before they joined.  
- Some optimizations to make repairs faster.

*Note, this QoS profile is nearly identical to the *Status* QoS profile, but uses *VOLATILE* durability, since late-joining DataReaders should not receive historical commands.*

#### ***DataFlowLibrary::Heartbeat* profile**

This QoS profile is used to implement a lightweight mechanism to assert and detect the presense of system components.

It inherits from the *Streaming* QoS profile and sets:

- *200 ms* Deadline QoS period. It is assumed that each system component must assert themselves as present in the system at least once every 200 ms seconds. They do so by publishing a message on a common Topic. If a gap in received messages on this Topic were to reach 200 ms, applications subscribing to this Topic will be notified via the corresponding DataReader's [`REQUESTED_DEADLINE_MISSED`](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Statuses_for_DataReaders.htm#receiving_2076951295_607264) status.

*This QoS profile is designed to be used only for the `t/DeviceHeartbeat` Topic in this reference architecture. This Topic is used to manually signal whether an application is still present in the system or not (e.g. cable disconnected, application crashed, otherwise unreachable, etc.).*

Since this QoS profile uses *BEST_EFFORT* Reliability QoS, a minimal amount of sample loss may occur without repairing. This is accounted for by using a larger Deadline period than the period applications should publish to the `t/DeviceHeartbeat` Topic.

>**Best Practice:** Publish samples on Topics for which the DataWriter QoS defines a finite Deadline QoS period, at a rate that is 2x-4x that of the configured Deadline period. This ensures an infrequent drop in sample does not falsely trigger the `REQUESTED_DEADLINE_MISSED` status for DataReaders.

## Application-specific QoS: [NonSecureAppsQos.xml](NonSecureAppsQos.xml) and [SecureAppsQos.xml](SecureAppsQos.xml)

In addition to the [Qos.xml](#qosxml) file, this reference architecture describes *per-application* QoS in 2 additional XML files:

- [NonSecureAppsQos.xml](./NonSecureAppsQos.xml)
- [SecureAppsQos.xml](./SecureAppsQos.xml)

The contents of these files determine whether the Connext applications are secure or not. When launching the applications, the `NDDS_QOS_PROFILES` environment variable must reference one, but not both, of these files to dictate that decision and apply the resulting configuration.

Both files contain only 1 QoS library: ***DpQosLib***. This QoS library contains 1 QoS profile per DomainParticipant. The rationale behind this library is that DomainParticipants in each application may have different needs. For instance, in the demos, the security certificates of each application will be different from each other.

[NonSecureAppsQos.xml](./NonSecureAppsQos.xml) contains one profile for each DomainParticipant. For the simplified use case, each profile inherits from *SystemLibrary::DefaultParticipant* in [Qos.xml](./Qos.xml). No additional configuration is applied for any given DomainParticipant.

[SecureAppsQos.xml](./SecureAppsQos.xml) also defines one profile for each DomainParticipant in a similar way to that of **NonSecureAppsQos.xml**, but with security configuration added.

[SecureAppsQos.xml](./SecureAppsQos.xml) defines a QoS snippet - *Demo1and2CommonSecuritySettings* defines common configuration to enable security and point to the common permissions CA, identity CA, and governance files.

## XML QoS Best Practices

>**Best Practice:** Compose your QoS profiles with [QoS Snippets](https://community.rti.com/best-practices/qos-profile-inheritance-and-composition-guidance#h.wr6u1ebybeff). Snippets provide easier readability and result in more maintainable QoS for increasingly complex systems by reducing repetitive configuration.
>
>**Best Practice:** Inherit from [Built-in QoS Profiles](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Built_in_QoS_Profiles.htm). Builtin profiles provide starting points to frequently used and tuned QoS combinations.

Please take a look at the comments inside the profiles in [Qos.xml](./Qos.xml), [NonSecureAppsQos.xml](./NonSecureAppsQos.xml), and [SecureAppsQos.xml](./SecureAppsQos.xml) for further details on each QoS policy and more **best practices** related to QoS configuration.
