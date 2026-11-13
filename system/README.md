# MedTech Reference Architecture - Documentation

The RTI Medical Reference Architecture demonstrates RTI's best practices for building medical devices using RTI Connext. This directory owns the central system definition: independently evolving applications integrate through its shared types, topics, QoS, entities, and security rules.

This README contains comprehensive details, explanations, best practices, and further documentation references relevant to the provided system architecture.

## Contents

- [Connext Architecture Concepts](#connext-architecture-concepts)
  - [Data Model](#data-model)
    - [Data Types](#data-types)
    - [How have we approached the Data Model in this reference architecture?](#how-have-we-approached-the-data-model-in-this-reference-architecture)
    - [Data Model References](#data-model-references)
  - [Quality of Service (QoS)](#quality-of-service-qos)
    - [QoS elements](#qos-elements)
      - [QoS Libraries](#qos-libraries)
      - [QoS Profiles](#qos-profiles)
      - [QoS Snippets](#qos-snippets)
      - [Builtin QoS](#builtin-qos)
    - [How have we approached QoS in this reference architecture?](#how-have-we-approached-qos-in-this-reference-architecture)
    - [QoS References](#qos-references)
- [RTI XML-Based Application Creation](#rti-xml-based-application-creation)
  - [Domains & Topics](#domains--topics)
    - [Domains & Topics elements](#domains--topics-elements)
      - [Domain Libraries](#domain-libraries)
      - [Domains](#domains)
      - [Topics](#topics)
    - [How have we approached Domains & Topics in this reference architecture?](#how-have-we-approached-domains--topics-in-this-reference-architecture)
    - [Domains & Topics References](#domains--topics-references)
  - [DomainParticipants & DDS Entities](#domainparticipants--dds-entities)
    - [DomainParticipants & DDS Entities elements](#domainparticipants--dds-entities-elements)
      - [DomainParticipant Libraries](#domainparticipant-libraries)
      - [DomainParticipants](#domainparticipants)
      - [Publishers and Subscribers](#publishers-and-subscribers)
      - [DataWriters and DataReaders](#datawriters-and-datareaders)
      - [Content Filters](#content-filters)
    - [How have we approached DDS entities in this reference architecture](#how-have-we-approached-dds-entities-in-this-reference-architecture)
    - [DDS Entities References](#dds-entities-references)
- [Security](#security)
  - [Security References](#security-references)

## Connext Architecture Concepts

### Data Model

A well-designed Connext Data Model is critical to a system's ability to share data amongst applications in real time, at scale. A Data Model in Connext is defined by:

- [Data Types](#data-types)
- [Quality of Service (QoS)](#quality-of-service-qos)

#### Data Types

DDS is a **data-centric** communication standard that understands user-defined Data Types. You can define a Data Type, its members, and annotations in [IDL](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Creating_User_Data_Types_with_IDL.htm), [XML](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Creating_User_Data_Types_with_Extensible.htm#17.4_Creating_User_Data_Types_with_Extensible_Markup_Language_(XML)), or [XSD](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/CreatingUserDataTypesWithXMLSchemas.htm).

*Conversion between file formats and type-support code generation for (de)serialization can be done with [RTI Code Generator](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/code_generator/users_manual/code_generator/users_manual/UsersManual_Title.htm).*

Data Types allow for capabilities in Connext such as:

- Evolvability
- Efficient Filtering
- Dynamic Bridging or Storing

#### How have we approached the Data Model in this reference architecture?

The authoritative types are IDL, collected by [MedTech.idl](./idl/MedTech.idl).
XML remains authoritative for entities, QoS, services, and security, not for a
second copy of the type definitions.

| IDL | Module | Responsibility |
| --- | --- | --- |
| [Geometry.idl](./idl/common/Geometry.idl) | `Geometry` | Vectors, quaternion `(x,y,z,w)`, and TCP pose |
| [Device.idl](./idl/device/Device.idl) | `Device` | Lifecycle commands, status, heartbeat, device roles |
| [Arm.idl](./idl/robot/Arm.idl) | `Robot::Arm` | TCP velocity, readiness, observed telemetry |
| [Tool.idl](./idl/robot/Tool.idl) | `Robot::Tool` | Parallel-jaw opening rate and observed gap |
| [Vitals.idl](./idl/patient/Vitals.idl) | `Patient` | Patient vital signs |
| [DdsEntities.idl](./idl/common/DdsEntities.idl) | `DdsEntities::Constants` | Application Creation entity lookup names, not topic semantics |

| Topic | Data type | Intended use |
| --- | --- | --- |
| `t/device/command` | `Device::Command` | Discrete START/PAUSE/SHUTDOWN |
| `t/device/status` | `Device::Status` | Initial and changed device lifecycle state |
| `t/device/heartbeat` | `Device::Heartbeat` | Periodic application presence |
| `t/robot/arm/control` | `Robot::Arm::TeleopControl` | Complete base-frame linear/angular TCP velocity |
| `t/robot/arm/status` | `Robot::Arm::Status` | Initial and changed NOT_READY/READY/FAULT |
| `t/robot/arm/telemetry` | `Robot::Arm::Telemetry` | Periodic actual base-relative TCP pose and optional jaw gap |
| `t/robot/tool/control` | `Robot::Tool::ParallelJawControl` | Signed total jaw-gap opening rate |
| `t/patient/vitals` | `Patient::Vitals` | Periodic vital signs for a keyed patient |

Domain-owned `TOPIC_*` string constants live beside their corresponding payloads.
Topic paths are naming conventions, not DDS subscription hierarchies. XML does
not substitute IDL constants; configuration and data-flow tests keep the
independently authored bindings consistent.

Arm/tool data uses the bounded `arm_id` key (`arm-1` in the demo), allowing future
variants without a topic per physical arm. Commands use m/s and rad/s with
`@unit` annotations; annotations document units but do not convert or enforce
them. Linear and angular TCP commands use the fixed, right-handed arm base frame:
X/Y span the horizontal workspace and +Z is up. Angular velocity rotates about
base-oriented axes through the TCP, not around the base origin. The TCP frame is
right-handed, with +Z along the shaft and symmetric jaw
travel along X. Positive opening rate increases the total gap; each finger
moves at half that speed. Rotation is angular velocity, not Euler-angle rates.
Observed pose is base-relative; its quaternion maps tool vectors into base
coordinates. Optional feedback is absent when unavailable, not fabricated as
zero/identity. Readiness is separate from periodic telemetry and device lifecycle.
There is no payload timestamp; DDS source time normally means publication time,
not sensor acquisition time.

The command frame is a fixed contract, not a per-sample option, and `@unit`
annotations do not encode or convert it. This base-frame revision keeps the type
shape and topic names but is semantically incompatible with earlier tool-frame
commands. Update all publishers/readers together and recreate command recordings
from that revision; do not mix the conventions. A physical Arm adapter must
translate base-frame TCP rates into the hardware SDK's required representation.

##### Generated artifacts

The central [CMake target](./CMakeLists.txt) generates these build-owned outputs:

```text
build/<CONNEXTDDS_ARCH>/system/generated/
  cpp/                 # C++ headers and support sources, preserving IDL folders
  python/MedTech.py     # Joined namespaces, without an application Arm.py collision
  xml/MedTech.xml       # Umbrella, with converted definitions in matching folders
```

Run `python build.py` before launching or testing. C++ consumers link
`refArchTypes`; Python applications launched through `launch.py` receive the
generated import path, preserving inherited `PYTHONPATH`. For direct invocation,
add the absolute generated `python/` directory to `PYTHONPATH` using the
platform's path separator and supply the module's normal DDS environment.
Tests use the same generated tree. Shared generated bindings are never owned
by an application source directory or committed.

`connextdds_rtiddsgen_convert` produces XML as a normal build artifact for
DynamicData/runtime tools. Load the generated umbrella together with its
converted include files; it is not a flattened standalone schema. Typed
applications register their generated types before XML Application Creation and
do not need to load generated XML. Included-IDL changes regenerate the artifacts.

##### Rate command validity

Controllers publish complete arm and jaw rates at 50 Hz, including idle zeros.
The simulator advances on its own 50 Hz clock. It reads the current valid DDS
sample each step, including already-READ samples: reusing a velocity integrates
the next time interval rather than repeating a one-shot action. Discrete
lifecycle commands retain their separate command semantics.

Both command streams use best-effort, volatile, KEEP_LAST(1), diagnostic 50 ms
deadlines, and a **writer lifespan of 250 ms**. Expired cache entries no longer
drive motion; no eligible arm sample means hold pose and jaw gap, while missing
tool data holds the gap independently. A valid zero arm stream allows tool-only
motion. Fresh valid rates resume immediately, even when controls remain held.
Lifecycle transitions drain command caches so pre-transition rates are not reused.

All command writers, including routing/replay outputs, must use the finite
lifespan: lifespan is not a requested/offered compatibility check. Connext 7.7
reader expiration is reception-based; delayed or republished data may start a
new local validity window. Stopping is observed at the next running tick,
approximately lifespan plus one 20 ms period and scheduling jitter, not an
end-to-end age bound. There is no retained application target or duplicate
command watchdog. Deadline/liveliness diagnostics do not implement stopping.

This is a non-hard-real-time kinematic demo, not hardware safety control. A
future physical-arm adapter needs its own vendor-specific execution and safety
design; DDS polling must not be inserted into vendor hard-real-time callbacks.
No vendor arm SDK integration is implemented.

#### Data Model References

- [Data Types](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/DataTypes.htm)
- [Extensible Types Guide](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/extensible_types_guide/extensible_types/XTypes_Title.htm)
- [RTI Code Generator](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/code_generator/users_manual/code_generator/users_manual/UsersManual_Title.htm)
- Creating User Data Types with [IDL](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Creating_User_Data_Types_with_IDL.htm) / [XML](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Creating_User_Data_Types_with_Extensible.htm#17.4_Creating_User_Data_Types_with_Extensible_Markup_Language_(XML)) / [XSD](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/CreatingUserDataTypesWithXMLSchemas.htm)

### Quality of Service (QoS)

Quality of Service (QoS) in DDS characterizes a system's infrastructure and data flow. QoS alleviates the need for applications to implement *how* data is delivered. This reduces unnecessary application logic and ELOC, in exchange for XML configuration that does not require recompiling upon modification.

QoS is applied to DDS Entities, as a way to configure how they should behave.

#### QoS elements

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

QoS is configured in XML via QoS Libraries, QoS Profiles, and QoS Snippets.

*Note, QoS can be configured across one or multiple XML files and reference configuration content by name across files. Given that Connext applications load all relevant files, Connext interprets all files as one cohesive configuration.*

##### QoS Libraries

QoS Libraries group QoS Profiles and Snippets. QoS Libraries can contain one or multiple Profiles, Snippets, or both. The decision to group Profiles and Libraries into one or multiple QoS Libraries is purely semantic and organizational, and has no effect on runtime performance.

##### QoS Profiles

A QoS Profile defines a set of QoS policy values for DDS entities - DomainParticipant, Publisher, Subscriber, DataWriter, and DataReader.

Examples of QoS policies include:

- *Reliability*: The ability to send transparent repairs for lost data.
- *Durability*: The ability to provide historically published data to late joining subscribers.
- *History*: Local endpoint data caching behavior.
- *Transport*: Which transports and interfaces to use, among other related configurations.

>**Best Practice:** Separate QoS Profiles by what you are configuring. For example, "System" profiles to define *system-level* policies (e.g. transport, network interfaces, discovery, thread priorities, etc.), and "DataFlow" profiles to characterize communication patterns (e.g. reliability, history, durability, deadline, etc.).

##### QoS Snippets

A QoS Snippet is a combination of correlated QoS policy values, whose intent is to apply a reusable coordinated configuration "snippet". It is commonly used to standardly configure an "enable X" policy across multiple profiles (e.g. "Enable and Configure Security").

>**Best Practice:** Use QoS Snippets to modularize, reduce maintenance of, and increase readability of XML QoS configuration.

##### Builtin QoS

Connext provides a set of usable Builtin QoS Libraries, Profiles, and QoS.

>**Best Practice:** Use Builtin QoS Profiles as base profiles, to leverage recommended optimizations, and increase readability of XML QoS configuration.

#### How have we approached QoS in this reference architecture?

| Folder | File | Description
| ------ | ---- | -----------
| [system/qos](./qos/) | [Qos.xml](./qos/Qos.xml) | Contains all base QoS Profiles.
| [system/qos](./qos/) | [NonSecureAppsQos.xml](./qos/NonSecureAppsQos.xml) | Contains all QoS Profiles for non-secure DomainParticipants.
| [system/qos](./qos/) | [SecureAppsQos.xml](./qos/SecureAppsQos.xml) | Contains all QoS Profiles for secure DomainParticipants.

#### QoS References

- [Configuring Connext Using QoS](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/PartConfiguringQos.htm)
- [Configuring QoS with XML](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/XMLConfiguration.htm)
- [RTI Connext QoS Reference Guide](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/qos_reference/qos_reference/qos_guide_all_in_one.htm)

## RTI XML-Based Application Creation

A Data Model alone does not fully capture a Connext Architecture. While adhering to an architected Data Model, applications would have to implement integrated applications separately. Those separately-implemented applications would have to adhere to a common design that states what Domains and Topics should be allowed, and with what QoS.

RTI XML-Based Application Creation allows for the definition of the remaining Connext Architecture, ensuring implemented applications adhere to the architecture as it is defined. It allows for the extraction of a common system definition from the application logic and behavior - a must-have for designing integrated systems with multiple development teams.

RTI XML-Based Application Creation is leveraged by defining:

- [Domains & Topics](#domains--topics)
- [DomainParticipants & DDS Entities](#domainparticipants--dds-entities)

### Domains & Topics

A Domain represents a data space where data can be shared by means of reading and writing the same Topics, where each Topic has a corresponding Data Type. In a Domain, you can define Topics and associate Data Types.

#### Domains & Topics elements

The hierarchy of the components configured in a Domain are as follows:

```text
Domain → Domain ID
├── Type Name → Data Type
└── Topic → Type Name

Legend:
 → references
```

Domains and Topics are configured in XML via Domain Libraries and Domains.

*Note, Domains can be configured across one or multiple XML files and reference configuration content by name across files. Given that Connext applications load all relevant files, Connext interprets all files as one cohesive configuration.*

##### Domain Libraries

Domain Libraries group Domains. Domain Libraries can contain one or multiple Domains. The decision to group Domains into one or multiple Domain Libraries is purely semantic and organizational, and has no effect on runtime performance.

##### Domains

Domains offer the highest level of separation of data and visibility in Connext. When considering what should be a Domain during design, consider:

- A DomainParticipant can operate only on a single Domain, which cannot be changed after creation.
- Applications may participate in multiple Domains, but require multiple DomainParticipants to do so.

>**Best Practice:** Use separate domains to isolate discovery and data of different criticalities (e.g. operational vs logging vs system health monitoring data).
>
>**Best Practice:** When possible, use a single DomainParticipant for every Domain an application operates on.

*Looking for a more dynamic means of data separation and visibility? Check out [DomainParticipant partitions](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/whats_new/whats_new/WhatsNew730.htm#AbilityPartition)!*

##### Topics

Topics describe a channel for which Connext applications can selectively publish and subscribe to. A Topic is associated with a well-known Data Type.

Endpoints (DataWriters and DataReaders) operating on a Topic require compatible QoS.

*Note, that while configured Topics can have explicit Topic QoS associated, it is extremely rare to have a valid use case for doing so. In almost all cases, not referencing explicit Topic QoS and therefore using the default Topic QoS, is sufficient.*

>**Best Practice:** Avoid Topic proliferation by [using Keys & Instances](https://community.rti.com/best-practices/use-keyed-topics) to subdivide streams of data within a single Topic. This reduces resource usage and supports better system scalability.

#### How have we approached Domains & Topics in this reference architecture?

| Folder | File | Description
| ------ | ---- | -----------
| [system/xml_app_creation](./xml_app_creation/) | [DomainLibrary.xml](./xml_app_creation/DomainLibrary.xml) | Contains all Domains and Topics.

#### Domains & Topics References

- [DDS Domains and DomainParticipants](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/DDS_Domains_and_DomainParticipants.htm)
- [Isolating DomainParticipants and Endpoints from Each Other](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Creating_ParticipantPartitions.htm)
- [Understanding XML-Based Application Creation](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/UnderstandingXMLCreate.htm)
- [Domain Library](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/DomainLibrary.htm#4.5.1_Domain_Library)

### DomainParticipants & DDS Entities

A DomainParticipant is a discoverable Domain actor. DomainParticipants own DDS entities such as Publishers, Subscribers, DataWriters, and DataReaders.

This is where the entire system architecture is tied together:

- DomainParticipants are configured to operate on a defined *Domain*.
- DomainParticipants are configured to use a defined *QoS Profile*.
- Publishers, Subscribers, DataWriters, and DataReaders are contained within a defined *DomainParticipant*.
- DataWriters and DataReaders are configured to operate on a defined *Topic*, which has been associated with a defined *Data Type*.
- Publishers, Subscribers, DataWriters, and DataReaders are configured to use a defined *QoS Profile*.

#### DomainParticipants & DDS Entities elements

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

##### DomainParticipant Libraries

DomainParticipant Libraries group DomainParticipants. DomainParticipant Libraries can contain one or multiple DomainParticipants. The decision to group DomainParticipants into one or multiple DomainParticipant Libraries is purely semantic and organizational, and has no effect on runtime performance.

##### DomainParticipants

A DomainParticipant is an application's mechanism for participating in a DDS Domain. It ultimately contains the necessary structure to publish and/or receive DDS data.

DomainParticipants are configured with a name, a Domain, and QoS profile.

When deciding what should be a DomainParticipant during design, consider:

- A DomainParticipant can operate only on a single Domain, which cannot be changed after creation.
- Applications may participate in multiple Domains, but require multiple DomainParticipants to do so.

>**Best Practice:** When possible, use a single DomainParticipant for every Domain an application operates on.

##### Publishers and Subscribers

Publishers and Subscribers are mechanisms to group DataWriters and DataReaders, respectively. Publishers and Subscribers are configured with a name and QoS profile.

When deciding what should be a Publisher or Subscriber during design, consider:

- A DomainParticipant may have one or multiple Publishers and/or Subscribers.
- A Publisher or Subscriber may have one or multiple DataWriters or DataReaders, respectively.
- [Partitions](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/PARTITION_QosPolicy.htm) are controlled at the Publisher and Subscriber level.

>**Best Practice:** Unless requirements dictate otherwise, use a single Publisher for all DataWriters and a single Subscriber for all Subscribers for each DomainParticipant.

##### DataWriters and DataReaders

DataWriters and DataReaders are considered the Endpoints of DDS. DataWriters and DataReaders are configured with a name, a Topic and QoS profile.

When deciding what should be a DataWriter or DataReader during design, consider:

- DataWriters and DataReaders are associated with a single Topic.
- [Using Keys & Instances](https://community.rti.com/best-practices/use-keyed-topics) to subdivide channels of data means less Topics are defined. Less Topics means less DataWriters and DataReaders are required. Less DataWriters and DataReaders used by an application reduces resources used (e.g. CPU, memory, network).
- DataWriters and DataReaders under a common DomainParticipant share common resources (e.g. Connext receive threads, UDP ports, etc.).

>**Best Practice:** Use explicit QoS Profiles for all DataWriters and DataReaders. For DataWriters and DataReaders designed to operate on the same Topic and match, use the same QoS Profiles, or ensure profiles are compatible.
>
>**Best Practice:** Avoid Topic proliferation by [using Keys & Instances](https://community.rti.com/best-practices/use-keyed-topics) to subdivide streams of data within a single Topic. This reduces resource usage and supports better system scalability.

##### Content Filters

DataReaders can use Content Filters to efficiently limit the data they receive on a Topic. Data samples published and received are evaluated against a defined Filter Expression before being presented to the subscribing application.

Content Filters are configured with a name, an expression, and expression parameters.

When deciding how a Content Filter should be designed, consider:

- Filter expressions and expression parameters can be changed at runtime.
- Filter expressions and expression parameters are propagated to matching DataWriters upon discovery and modification of the Content Filter at runtime.
- Filtering is optimized for filter expressions that evaluate only and all of the *keyed* Data Type field values.

*Why filter data with Connext as opposed to in application logic?*

- Connext can perform Writer-side filtering to significantly reduce resource usage, under [certain circumstances](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Where_Filtering_is_Applied.htm).
- If filtering on *keyed* Data Type field values, Connext optimizes filtering logic by caching filter results. This means DataReaders can skip the step of deserializing incoming data for instances known to fail filter evaluation.
- DataReaders maintain a configurable cache of samples it receives. Data filtered by Connext will not be stored in the cache. This not only has resource usage implications but implications of data delivery when a full DataReader cache contains potentially unwanted data affects the DataReaders ability to receive relevant data.

>**Best Practice:** If components of a Content Filter expression or expression parameters are determined dynamically, and cannot be fully described statically in XML, disable autoenabling of entities upon creation. After Content Filters are configured appropriately, entities should be explicitly enabled by calling [`enable()`](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Enabling_DDS_Entities.htm). Note, this concept is extended to other entities as well if certain QoS configuration must be applied dynamically before enabling.

#### How have we approached DDS entities in this reference architecture?

| Folder | File | Description
| ------ | ---- | -----------
| [system/xml_app_creation](./xml_app_creation/) | [ParticipantLibrary.xml](./xml_app_creation/ParticipantLibrary.xml) | Contains all DomainParticipants, Publishers, Subscribers, DataWriters, DataReaders, and Content Filters.

#### DDS Entities References

- [DDS Domains and DomainParticipants](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/DDS_Domains_and_DomainParticipants.htm)
- [Understanding XML-Based Application Creation](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/UnderstandingXMLCreate.htm)
- [Participant Library](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/ParticipantLibrary.htm#4.5.2_Participant_Library)

## Security

```text
Connext Security
├── Certificate Authority Hierarchy (Root → Intermediate CAs)
├── Governance (per-domain access rules)
├── Permissions (per-participant topic grants)
└── Identity Certificates (per-participant, with cert chains)
```

Data in a Connext Architecture can be protected against DDS system threats with the use of the RTI Security Plugins.

RTI Security Plugins provide configurable capability to prevent unauthorized actions in the system through authentication and encryption.

See the [Security README](./security/README.md) for artifact generation instructions and directory layout details.

>**Best Practice:** Use separate Domains for secure and unsecure DomainParticipants. [[more info](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_secure/users_manual/p3_advanced/best_practices.html)]
>
>**Best Practice:** Use a unique Governance file per Domain.
>
>**Best Practice:** Use a unique Permissions file for each DomainParticipant. [[more info](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_secure/users_manual/p3_advanced/best_practices.html#choosing-the-granularity-of-your-permissions-documents-for-domainparticipants)]
>
>**Best Practice:** Avoid encrypting the contents of each message twice. [[more info](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_secure/users_manual/p3_advanced/best_practices.html#using-serialized-data-protection-along-with-submessage-rtps-protection)]
>
>**Best Practice:** Explicitly configure the Topics to allow in the Permissions file. The default rule should be `DENY`.

### Security References

- [RTI Security Plugins Getting Started](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_secure/getting_started_guide/index.html)
- [RTI Security Plugins User's Manual](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_secure/users_manual/p1_welcome/overview.html)
