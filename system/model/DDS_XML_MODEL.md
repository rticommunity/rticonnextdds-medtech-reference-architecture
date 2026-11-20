# XML application creation workflow

[← DDS model](README.md)

## RTI XML-Based Application Creation

This reference architecture uses [RTI XML-Based Application Creation](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/Introduction/XMLAppCreation_Intro.htm#Chapter_1_Introduction) to define the DDS entities used by the modules. XML keeps shared configuration reviewable separately from application behavior; applications can also create entities programmatically where that better fits their requirements.

RTI XML-Based Application Creation allows for the extraction of a Connext system definition from the implemented application logic and behavior.

RTI XML-Based Application Creation is leveraged by defining:

- Domains & Topics: [Domain library](DOMAINS.md#domainlibraryxml)
- DomainParticipants & DDS Entities: [Participant library](PARTICIPANTS.md#participantlibraryxml)

### Usage in Connext Applications

Applications load the XML configuration, register generated type support, and
create a participant by its configured name. Connext creates the participant,
topics, and configured endpoints; the application then finds the entities it
needs and completes any required setup.

Applications can be implemented via any supported Connext Professional API language, while ensuring adherence to the common system design expressed in XML.

#### Register types

Register generated type support before creating the participant. For example,
[PatientSensor.cxx](../../modules/01-operating-room/src/PatientSensor.cxx)
registers each type it uses:

```cpp
rti::domain::register_type<Device::Command>();
rti::domain::register_type<Device::Status>();
rti::domain::register_type<Device::Heartbeat>();
rti::domain::register_type<Patient::Vitals>();
```

The XML type names must correspond to the registered types so the participant
can serialize and deserialize samples using the generated code.

[Using User-Generated Types](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/UsingGeneratingTypes.htm#4.7.5_Using_User-Generated_Types)

#### Load XML configuration

   One or multiple XML files should be loaded by an application to understand the complete configuration for a single DomainParticipant.

   In this reference architecture, it is recommended to use `NDDS_QOS_PROFILES` environment variable to point to the defined XML files.

From the repository root, load the shared QoS, non-secure app QoS, factory
policy, and the domain and participant libraries:

```bash
export NDDS_QOS_PROFILES="system/qos/Qos.xml;system/qos/NonSecureAppsQos.xml;\
system/qos/ApplicationFactoryQos.xml;system/model/DomainLibrary.xml;\
system/model/ParticipantLibrary.xml"
```

See [Loading XML Configuration Files](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/LoadingXMLFiles.htm#4.2_Loading_XML_Configuration_Files).

#### Create defined DDS entities

   DomainParticipants, and all underlying entities configured (Topics, Publishers, DataWriters, Subscribers, DataReaders), can be created with an API-specific implementation of the `create_participant_from_config()`.

   DomainParticipants are referred to by their fully-qualified name in configuration. Please see the referred documentation for more details.

   All DDS entities will be created with the names and QoS as described in the XML.

   For example, to create the ArmController DomainParticipant defined in [ParticipantLibrary.xml](ParticipantLibrary.xml#L48), the following C++ code can be used:

```cpp
auto default_provider = dds::core::QosProvider::Default();
dds::domain::DomainParticipant participant =
    default_provider.extensions().create_participant_from_config(
        "MedicalDemoParticipantLibrary::dp/ArmController");
```

Documentation:

- [Creating and Retrieving Entities Configured in an XML File](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/CreatingEntities.htm)
- [Referring to Entities and Other Elements within XML Files](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/ReferringToEntitiesElements.htm#4.6.1_Referring_to_Entities_and_Other_Elements_within_XML_Files)

#### Retrieve created entities by name

   Commonly, configured named DDS entities must be retrieved for use (e.g. publishing to or subscribing to data) or preconfiguration before enabling (e.g. runtime QoS configuration).

   DDS entities can be retrieved by name via API-specific "find" or "lookup" functions. Entities are referred to by their fully-qualified name in configuration. Please see the referred documentation for entity-specifics.

   For example, to find the DeviceCommand DataReader defined in [ParticipantLibrary.xml](ParticipantLibrary.xml#L68), the following C++ code can be used:

```cpp
dds::sub::DataReader<Device::Command> cmd_reader =
    rti::sub::find_datareader_by_name<dds::sub::DataReader<Device::Command>>(
        participant, "s/subscriber::dr/DeviceCommand");
```

Documentation:

- [Accessing Entities Defined in XML Configuration from an Application](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/Accessing_Entit.htm#4.4_Accessing_Entities_Defined_in_XML_Configuration_from_an_Application)
- [Referring to Entities and Other Elements within XML Files](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/UnderstandingXMLBased/ReferringToEntitiesElements.htm#4.6.1_Referring_to_Entities_and_Other_Elements_within_XML_Files)

#### Configure and enable

The demo's [factory QoS](../qos/ApplicationFactoryQos.xml) defers participant
enablement. Applications find their entities, finish required setup, then call
`participant.enable()`. This is useful when runtime-derived configuration must
be in place before entities match or receive data; changes to filter parameters
later do not by themselves require deferred enablement.

### XML-Based Application Creation References

- [Getting Started Guide](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/xml_application_creation/xml_based_app_creation_guide/XMLAppCreationGSG_title.htm)
