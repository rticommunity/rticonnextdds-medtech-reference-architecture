# Domain library

[← DDS model](README.md)

## Domain Library

### Domain Configuration

The hierarchy of the components configured in a Domain are as follows:

```text
Domain → Domain ID
├── Type Name → Data Type
└── Topic → Type Name

Legend:
 → references
```

#### Domain

```text
Tag: <domain>

Attributes:
  name:             Must be unique within the Domain Library.
  domain_id:        The Domain ID to use.

Subelements:
  <register_type>:  See section 'Data Type'.
  <topic>:          See section 'Topic'.
```

#### Data Type

```text
Tag: <register_type>

Attributes:
  name:       The Data Type's *registered* name, which Topics must reference.
              (see <topic> tag's 'register_type_ref' attribute in section 'Topic')
              Applications register their generated IDL types under this name.
  type_ref:   Optional reference to an XML-defined type. The operational domain
              omits this because typed applications register generated support.
```

#### Topic

```text
Tag: <topic>

Attributes:
  name:               The Topic name, which DataWriters and DataReaders must reference.
  register_type_ref:  Must be the name of the *registered* Data Type name.
                      (see <register_type> tag's 'name' attribute in section 'Data Type')

Subelements:
  <register_type>:    See section 'Data Type'.
  <topic>:            See section 'Topic'.
```

### [DomainLibrary.xml](DomainLibrary.xml)

This reference architecture defines the following Domain Library in [DomainLibrary.xml](DomainLibrary.xml):

| Domain Library | Intended Use
| -------------- | ------------
| [*ConnextDomainLib*](#connextdomainlib) | Contain all defined MedTech Domains

#### ***ConnextDomainLib***

This Domain Library will hold all Domains defined as part of this reference architecture for simplicity. *ConnextDomainLib* contains the following Domain (`<domain>`):

| Domain | Domain ID | Intended Use
| ------ | --------- | ------------
| [*OperationalDataDomain*](#connextdomainliboperationaldatadomain) | 0 | Real-time operational medical device data
| [*SecureLogDomain*](#connextdomainlibsecurelogdomain) | 0 | DDS Security builtin secure logging

##### ***ConnextDomainLib::OperationalDataDomain***

In this reference architecture, you will find two Domain definitions — *OperationalDataDomain* and *SecureLogDomain* — both configured for Domain ID `0`. Because they share the same Domain ID, they currently resolve to the **same** DDS domain.

*OperationalDataDomain* contains the following Topics (`<topic>`):

| Topic | Data Type | Intended Use
| ----- | --------- | ------------
| *t/robot/arm/control* | *Robot::Arm::TeleopControl* | Complete base-frame linear/angular TCP velocity
| *t/robot/tool/control* | *Robot::Tool::ParallelJawControl* | Signed total jaw-gap opening rate
| *t/robot/arm/telemetry* | *Robot::Arm::Telemetry* | Periodic actual base-relative TCP pose and optional jaw gap
| *t/device/status* | *Device::Status* | Last reported lifecycle and primary-role readiness, keyed by device type
| *t/device/heartbeat* | *Device::Heartbeat* | Assert that a unique system component is alive
| *t/device/command* | *Device::Command* | Command initiating a status (e.g. `START`, `SHUTDOWN`) to a unique system component
| *t/patient/vitals* | *Patient::Vitals* | Data representative of a unique patient's collected vital signs

*See the authoritative [MedTech.idl](../idl/MedTech.idl) and its domain includes.
Generated XML is available under the build tree for DynamicData tools.*

##### ***ConnextDomainLib::SecureLogDomain***

*SecureLogDomain* holds the RTI Security Plugins builtin secure-logging Topic. It is consumed by the *dp/SecureLogReader* DomainParticipant. It is configured for Domain ID `0` (the same Domain as *OperationalDataDomain*) but defined separately.

*SecureLogDomain* contains the following Topic (`<topic>`):

| Topic | Data Type | Intended Use
| ----- | --------- | ------------
| *DDS:Security:LogTopicV2* | *DDSSecurity::BuiltinLoggingTypeV2* | DDS Security builtin secure-logging stream

### Domain Library Best Practices

> [!TIP]
> **Best practice:** Use consistent naming conventions to make entities easy
> to identify. This project uses the `t/` prefix for Topics; DDS does not
> require it.
