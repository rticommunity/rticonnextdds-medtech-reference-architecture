# XML Application Creation files

## Contents

- [RTI XML-Based Application Creation](#rti-xml-based-application-creation)
  - [Usage in Connext Applications](#usage-in-connext-applications)
  - [XML-Based Application Creation References](#xml-based-application-creation-references)
- [Domain Library](#domain-library)
  - [Domain Configuration](#domain-configuration)
  - [DomainLibrary.xml](#domainlibraryxml)
  - [Domain Library Best Practices](#domain-library-best-practices)
- [DomainParticipant Library](#domainparticipant-library)
  - [DomainParticipant Configuration](#domainparticipant-configuration)
  - [ParticipantLibrary.xml](#participantlibraryxml)
  - [DomainParticipant Library Best Practices](#domainparticipant-library-best-practices)

## RTI XML-Based Application Creation

This reference architecture uses [RTI XML-Based Application Creation](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/Introduction/XMLAppCreation_Intro.htm#Chapter_1_Introduction) to define all DDS entities that the modules will use. This mechanism simplifies and streamlines the development of Connext applications. An alternative approach is to define the entities programatically, which is more cumbersome, error-prone, and more difficult to coordinate across distributed developer groups.

RTI XML-Based Application Creation allows for the extraction of a Connext system definition from the implemented application logic and behavior.

RTI XML-Based Application Creation is leveraged by defining:

- Domains & Topics: [DomainLibrary.xml](#domainlibraryxml)
- DomainParticipants & DDS Entities: [ParticipantLibrary.xml](#participantlibraryxml)

### Usage in Connext Applications

To leverage RTI XML-Based Application Creation, your application code simply indicates the name of the DomainParticipant that it needs to create. The XML-Based Application Creation infrastructure takes care of the rest: creating the DomainParticipant, registering the types and topics, and populating all the configured entities.

Applications can be implemented via any supported Connext Professional API language, while ensuring adherence to the common system design expressed in XML.

1. Register Types  
    To use generated Type-Support code (via [RTI Code Generator](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/code_generator/users_manual/code_generator/users_manual/UsersManual_Title.htm)), named *types* in the XML configuration must be registered with the DomainParticipant. This is necessary for the DomainParticipant to serialize and deserialize the data using the generated code.

    Documentation:
    - [Using User-Generated Types](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/UsingGeneratingTypes.htm#4.7.5_Using_User-Generated_Types)

2. Load XML Configuration  
    One or multiple XML files should be loaded by an application to understand the complete configuration for a single DomainParticipant.

    In this reference architecture, it is recommended to use `NDDS_QOS_PROFILES` environment variable to point to the defined XML files.

    For example, this bash statement will allow Connext to load the following files:
    - [Qos.xml](./Qos.xml)
    - [NonSecureAppsQos.xml](./NonSecureAppsQos.xml)
    - [DomainLibrary.xml](./DomainLibrary.xml)
    - [ParticipantLibrary.xml](./ParticipantLibrary.xml)

    ```bash
    export NDDS_QOS_PROFILES="./Qos.xml;./NonSecureAppsQos.xml;./DomainLibrary.xml;./ParticipantLibrary.xml"
    ```

    Documentation:
    - [Loading XML Configuration Files](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/LoadingXMLFiles.htm#4.2_Loading_XML_Configuration_Files)

3. Create Defined DDS Entities  
    DomainParticipants, and all underlying entities configured (Topics, Publishers, DataWriters, Subscribers, DataReaders), can be created with an API-specific implementation of the `create_participant_from_config()`.

    DomainParticipants are referred to by their fully-qualified name in configuration. Please see the referred documentation for more details.

    All DDS entities will be created with the names and QoS as described in the XML.

    For example, to create the ArmController DomainParticipant defined in [ParticipantLibrary.xml](ParticipantLibrary.xml#L48), the following C++ code can be used:

    ```c++
    auto default_provider = dds::core::QosProvider::Default();
    dds::domain::DomainParticipant participant =
        default_provider.extensions().create_participant_from_config(
            "MedicalDemoParticipantLibrary::dp/ArmController");
    ```

    Documentation:
    - [Creating and Retrieving Entities Configured in an XML File](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/CreatingEntities.htm)
    - [Referring to Entities and Other Elements within XML Files](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/ReferringToEntitiesElements.htm#4.6.1_Referring_to_Entities_and_Other_Elements_within_XML_Files)

4. Retrieve Created Entities by Name  
    Commonly, configured named DDS entities must be retreived for use (e.g. publishing to or subscribing to data) or preconfiguration before enabling (e.g. runtime QoS configuration).

    DDS entities can be retrieved by name via API-specific "find" or "lookup" functions. Entities are referred to by their fully-qualified name in configuration. Please see the referred documentation for entity-specifics.

    For example, to find the DeviceCommand DataReader defined in [ParticipantLibrary.xml](ParticipantLibrary.xml#L68), the following C++ code can be used:

    ```c++
    dds::sub::DataReader<Orchestrator::DeviceCommand> cmd_reader =
            rti::sub::find_datareader_by_name<dds::sub::DataReader<Orchestrator::DeviceCommand>>(
                participant, "s/subscriber::dr/DeviceCommand");
    ```

    Documentation:
    - [Accessing Entities Defined in XML Configuration from an Application](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/Accessing_Entit.htm#4.4_Accessing_Entities_Defined_in_XML_Configuration_from_an_Application)
    - [Referring to Entities and Other Elements within XML Files](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/ReferringToEntitiesElements.htm#4.6.1_Referring_to_Entities_and_Other_Elements_within_XML_Files)

### XML-Based Application Creation References

- [Getting Started Guide](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/XMLAppCreationGSG_title.htm)

## Domain Library

### Domain Configuration

The heirarchy of the components configured in a Domain are as follows:

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
              It is common to reuse the 'type_ref' attribute value.
  type_ref:   Reference to the actual Data Type defined in XML. (see Types.xml)
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

| Domain Library  | Intended Use
| --------------  | ------------
| [*ConnextDomainLib*](#connextdomainlib) | Contain all defined MedTech Domains

#### ***ConnextDomainLib***

This Domain Library will hold all Domains defined as part of this reference architecture for simplicity. *ConnextDomainLib* contains the following Domain (`<domain>`):

| Domain  | Domain ID | Intended Use
| ------  | --------- | ------------
| [*OperationalDataDomain*](#connextdomainliboperationaldatadomain) | 0 |  Real-time operational medical device data

##### ***ConnextDomainLib::OperationalDataDomain***

In this reference architecture, you will find a single Domain defined, called *OperationalDataDomain* for Domain 0.

*OperationalDataDomain* is named as such because as the system design scales over time, additional domains could be defined for monitoring, logging, etc. Those additional domains should not affect the performance of our operational data, and therefore should belong to a different domain.

*OperationalDataDomain* contains the following Topics (`<topic>`):

| Topic | Data Type | Intended Use
| ----- | --------- | ------------
| *t/MotorControl* | *SurgicalRobot::MotorControl* | Command the direction of motion for a motor kind (e.g. `SHOULDER`, `ELBOW`)
| *t/DeviceStatus* | *Common::DeviceStatus* | Status (e.g. `ON`, `PAUSED`) for a unique system component
| *t/DeviceHeartbeat* | *Common::DeviceHeartbeat* | Assert that a unique system component is alive
| *t/DeviceCommand* | *Orchestrator::DeviceCommand* | Command initiating a status (e.g. `START`, `SHUTDOWN`) to a unique system component
| *t/Vitals* | *PatientMonitor::Vitals* | Data representative of a unique patient's collected vital signs

*Please refer to the data types referenced in the table above in [Types.xml](../Types.xml)*

### Domain Library Best Practices

>**Best Practice:** Use prefixes to establish naming conventions and clearly indicate what is being named (e.g. "t/" prefix for Topics). This results in easier identification and readability.

## DomainParticipant Library

### DomainParticipant Configuration

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
| --------------            | ------------
| [*MedicalDemoParticipantLibrary*](#medicaldemoparticipantlibrary) | Contains all defined module DomainParticipants

#### ***MedicalDemoParticipantLibrary***

This reference architecture defines the following DomainParticipants in [ParticipantLibrary.xml](ParticipantLibrary.xml):

| DomainParticipant | Domain
| ----------------- | ------
| [*dp/Arm*](#medicaldemoparticipantlibrarydparm) | [*ConnextDomainLib::OperationalDataDomain*](#connextdomainliboperationaldatadomain)
| [*dp/ArmController*](#medicaldemoparticipantlibrarydparmcontroller) | [*ConnextDomainLib::OperationalDataDomain*](#connextdomainliboperationaldatadomain)
| [*dp/Orchestrator*](#medicaldemoparticipantlibrarydporchestrator) | [*ConnextDomainLib::OperationalDataDomain*](#connextdomainliboperationaldatadomain)
| [*dp/PatientSensor*](#medicaldemoparticipantlibrarydppatientsensor) | [*ConnextDomainLib::OperationalDataDomain*](#connextdomainliboperationaldatadomain)
| [*dp/PatientMonitor*](#medicaldemoparticipantlibrarydppatientmonitor) | [*ConnextDomainLib::OperationalDataDomain*](#connextdomainliboperationaldatadomain)

##### ***MedicalDemoParticipantLibrary::dp/Arm***

The *Arm* DomainParticipant is intended to demonstrate a Robotic Surgery Arm with 5 motors: Base, Shoulder, Elbow, Wrist, and Hand.

*dp/Arm* contains the following DataWriters (`<data_writer>`):

| DataWriter | Topic | QoS Profile | Intended Use
| ---------- | ----- | ----------- | ------------
| *dw/DeviceStatus* | *t/DeviceStatus* | [*DataFlowLibrary::Status*](../qos/README.md#dataflowlibrarystatus) | Publish Arm device status
| *dw/DeviceHeartbeat* | *t/DeviceHeartbeat* | [*DataFlowLibrary::Heartbeat*](../qos/README.md#dataflowlibraryheartbeat) | Assert Arm device is alive

*dp/Arm* contains the following DataReaders (`<data_reader>`):

| DataReader | Topic | QoS Profile | Content Filter | Intended Use
| ---------- | ----- | ----------- | -------------- | ------------
| *dr/MotorControl* | *t/MotorControl* | [*DataFlowLibrary::Command*](../qos/README.md#dataflowlibrarycommand) | -- | Receive and process motor control commands
| *dr/DeviceCommand* | *t/DeviceCommand* | [*DataFlowLibrary::Command*](../qos/README.md#dataflowlibrarycommand) | `device = 'ARM'` | Receive and process device commands targetting this Arm

##### ***MedicalDemoParticipantLibrary::dp/ArmController***

The *ArmController* DomainParticipant is intended to administer commands to the [*Arm*](#medicaldemoparticipantlibrarydparm) DomainParticipant, to control its motors.

*dp/ArmController* contains the following DataWriters (`<data_writer>`):

| DataWriter | Topic | QoS Profile | Intended Use
| ---------- | ----- | ----------- | ------------
| *dw/MotorControl* | *t/MotorControl* | [*DataFlowLibrary::Command*](../qos/README.md#dataflowlibrarycommand) | Publish Motor commands to Arm devices
| *dw/DeviceStatus* | *t/DeviceStatus* | [*DataFlowLibrary::Status*](../qos/README.md#dataflowlibrarystatus) | Publish ArmController device status
| *dw/DeviceHeartbeat* | *t/DeviceHeartbeat* | [*DataFlowLibrary::Heartbeat*](../qos/README.md#dataflowlibraryheartbeat) | Assert ArmController device is alive

*dp/ArmController* contains the following DataReaders (`<data_reader>`):

| DataReader | Topic | QoS Profile | Content Filter | Intended Use
| ---------- | ----- | ----------- | -------------- | ------------
| *dr/DeviceCommand* | *t/DeviceCommand* | [*DataFlowLibrary::Command*](../qos/README.md#dataflowlibrarycommand) | `device = 'ARM_CONTROLLER'` | Receive and process device commands targetting this Arm Controller

##### ***MedicalDemoParticipantLibrary::dp/Orchestrator***

The *Orchestrator* DomainParticipant is intended to administer device-level commands to all other DomainParticipants in the system. It also monitors status and presense of all system devices.

*dp/Orchestrator* contains the following DataWriters (`<data_writer>`):

| DataWriter | Topic | QoS Profile | Intended Use
| ---------- | ----- | ----------- | ------------
| *dw/DeviceCommand* | *t/DeviceCommand* | [*DataFlowLibrary::Command*](../qos/README.md#dataflowlibrarycommand) | Publish Device commands to all devices

*dp/Orchestrator* contains the following DataReaders (`<data_reader>`):

| DataReader | Topic | QoS Profile | Content Filter | Intended Use
| ---------- | ----- | ----------- | -------------- | ------------
| *dr/DeviceStatus* | *t/DeviceStatus* | [*DataFlowLibrary::Status*](../qos/README.md#dataflowlibrarystatus) | -- | Receive and process device statuses from all devices
| *dr/DeviceHeartbeat* | *t/DeviceHeartbeat* | [*DataFlowLibrary::Heartbeat*](../qos/README.md#dataflowlibraryheartbeat) | -- | Detect (loss of) presence of all devices

##### ***MedicalDemoParticipantLibrary::dp/PatientSensor***

The *PatientSensor* DomainParticipant is intended to simulate a streaming source for patient vitals data.

*dp/PatientSensor* contains the following DataWriters (`<data_writer>`):

| DataWriter | Topic | QoS Profile | Intended Use
| ---------- | ----- | ----------- | ------------
| *dw/Vitals* | *t/Vitals* | [*DataFlowLibrary::Streaming*](../qos/README.md#dataflowlibrarystreaming) | Publish simulated patient vitals data stream
| *dw/DeviceStatus* | *t/DeviceStatus* | [*DataFlowLibrary::Status*](../qos/README.md#dataflowlibrarystatus) | Publish PatientSensor device status
| *dw/DeviceHeartbeat* | *t/DeviceHeartbeat* | [*DataFlowLibrary::Heartbeat*](../qos/README.md#dataflowlibraryheartbeat) | Assert PatientSensor device is alive

*dp/PatientSensor* contains the following DataReaders (`<data_reader>`):

| DataReader | Topic | QoS Profile | Content Filter | Intended Use
| ---------- | ----- | ----------- | -------------- | ------------
| *dr/DeviceCommand* | *t/DeviceCommand* | [*DataFlowLibrary::Command*](../qos/README.md#dataflowlibrarycommand) | `device = 'PATIENT_SENSOR'` | Receive and process device commands targetting this PatientSensor

##### ***MedicalDemoParticipantLibrary::dp/PatientMonitor***

The *PatientMonitor* DomainParticipant is intended to process (display) patient vitals data in a graphical plot over time.

*dp/PatientMonitor* contains the following DataWriters (`<data_writer>`):

| DataWriter | Topic | QoS Profile | Intended Use
| ---------- | ----- | ----------- | ------------
| *dw/DeviceStatus* | *t/DeviceStatus* | [*DataFlowLibrary::Status*](../qos/README.md#dataflowlibrarystatus) | Publish PatientMonitor device status
| *dw/DeviceHeartbeat* | *t/DeviceHeartbeat* | [*DataFlowLibrary::Heartbeat*](../qos/README.md#dataflowlibraryheartbeat) | Assert PatientMonitor device is alive

*dp/PatientMonitor* contains the following DataReaders (`<data_reader>`):

| DataReader | Topic | QoS Profile | Content Filter | Intended Use
| ---------- | ----- | ----------- | -------------- | ------------
| *dr/DeviceCommand* | *t/DeviceCommand* | [*DataFlowLibrary::Command*](../qos/README.md#dataflowlibrarycommand) | `device = 'PATIENT_MONITOR'` | Receive and process device commands targetting this PatientMonitor
| *dr/Vitals* | *t/Vitals* | [*DataFlowLibrary::Streaming*](../qos/README.md#dataflowlibrarystreaming) | -- | Receive and process patient vitals data stream

### DomainParticipant Library Best Practices

>**Best Practice:** Group your DataWriters into a single Publisher, and your DataReaders into a single Subscriber for a given DomainParticipant, unless your requirements dictate otherwise.
>
>**Best Practice:** Use prefixes to establish naming conventions and clearly indicate what is being named (e.g. "dp/" prefix for DomainParticipants). This results in easier identification and readability.
>
>**Best Practice:** Reference explicit QoS Profiles for each entity. This ensures each entity uses the intended QoS Profile as designed.
>
>**Best Practice:** Do not define QoS policies in the `<domain_participant_library>`. This would add confusion as QoS Profiles should be maintained in QoS libraries for consistency.
