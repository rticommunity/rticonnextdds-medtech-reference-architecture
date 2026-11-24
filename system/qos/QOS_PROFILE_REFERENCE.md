# QoS profile reference

[← QoS overview](README.md)

## QoS Profile Configuration

The hierarchy of components configured in a QoS profile are as follows:

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

| Qos Library | Intended Use
| ----------- | ------------
| [*SystemLibrary*](#systemlibrary) | Characterize the *system* (e.g. transport, network interfaces, discovery, thread priorities, and entity creation).
| [*DataFlowLibrary*](#dataflowlibrary) | Characterize data flows (e.g. reliability, history, durability, and deadline) for DataWriters and DataReaders.
| *DataFlowSnippetLibrary* | Reusable deadline and writer-lifespan policy snippets composed into dataflow profiles.

### ***SystemLibrary***

*SystemLibrary* contains the following QoS profile (`<qos_profile>`):

| QoS Profile | Intended Use
| ----------- | ------------
| [*DefaultParticipant*](#systemlibrarydefaultparticipant-profile) | Common DomainParticipant configuration.
| [*WanConfig*](#systemlibrarywanconfig-profile) | WAN transport configuration, used by Module 03: Remote Teleoperation.

[ApplicationFactoryQos.xml](./ApplicationFactoryQos.xml) selects manual
participant enablement for application processes, inheriting the selected
secure or non-secure factory settings. RTI Services do not load this file and
retain automatic participant enablement for their internally managed entities.

#### ***SystemLibrary::DefaultParticipant* profile**

This QoS profile acts as a common base configuration for all DomainParticipants in the system to provide a level of consistency. It inherits from a builtin profile called *BuiltinQosLib::Generic.Common* through the `base_name` XML attribute.

#### ***SystemLibrary::WanConfig* profile**

This QoS profile configures the DomainParticipant for communication over the Wide Area Network (WAN). It inherits from *BuiltinQosLib::Generic.Common* and additionally:

- Enables the **UDPv4_WAN** builtin transport (via the `transport_builtin` mask), which provides the RTI Real-Time WAN Transport's NAT-traversal capabilities.
- Shortens the participant liveliness assert period to speed up discovery over the WAN.

When security is enabled, WAN participants compose the *WanCommonSecurityConfig* snippet from [SecureAppsQos.xml](SecureAppsQos.xml), which uses the [TeleopWanDomain.xml](../security/domain_scope/TeleopWanDomain/governance/TeleopWanDomain/TeleopWanDomain.xml) governance (and the matching `TeleopWanDomain.psk` seed) instead of the LAN-side *OperationalDomain* governance. *TeleopWanDomain* applies the same domain-level protection but extends metadata encryption to **every** topic. See [SecureAppsQos.xml](#application-specific-qos-nonsecureappsqosxml-and-secureappsqosxml) for details.

It is used by Module 03: Remote Teleoperation. See the [Module 03 README](../../modules/03-remote-teleoperation/README.md) for the WAN scenarios that rely on it.

### ***DataFlowLibrary***

*DataFlowLibrary* contains the following QoS profiles (`<qos_profile>`):

Control, Telemetry, and Heartbeat compose narrowly scoped snippets from
*DataFlowSnippetLibrary*. Deadline snippets apply to writers and readers;
the lifespan snippet applies only to writers. Telemetry and Heartbeat share
the 200 ms deadline snippet, so changing it affects both profiles.

See the [data-flow profile comparison](README.md#data-flow-profiles) for the
reliability, history, durability, deadline, and purpose of each profile.

#### ***DataFlowLibrary::Streaming* profile**

This QoS profile is used for Topics published periodically at a high rate.

It inherits from the *BuiltinQosLib::Generic.Common* profile in addition to being composed with builtin QoS snippets. As a result, this QoS profile applies the following:

- *BEST_EFFORT* Reliability QoS. These streams favor fresh updates over
  repairing every lost sample; subsequent delivery is not guaranteed.
- *KEEP_LAST, depth=1* History QoS. There is no need to process or track more than 1 sample per instance at a time. You could increase the *depth* on the DataReader side if your application cannot access the data fast enough from the DataReader's queue.

#### ***DataFlowLibrary::Control* profile**

This profile applies to `t/robot/arm/control` and `t/robot/tool/control`.
Each sample is a complete rate state, not a one-shot event. Controllers publish
at 50 Hz, including idle zeros, independently of the simulator's stepping clock.

It derives from *Streaming*, not the depth-100 *Pattern.ReliableStreaming*:

- *BEST_EFFORT*, *KEEP_LAST(1)*, *VOLATILE* on both endpoints. History is per key,
  not a bound on every network/application queue.
- A 50 ms offered/requested *Deadline*. A reader miss reports an update gap;
  the arm application discards cached commands and disarms when gated.
- A 250 ms writer *Lifespan*. The Arm reads retained READ and NOT_READ samples
  for each step; rereading does not renew expiry. No eligible arm data holds
  pose and jaw gap; absent tool data holds gap independently.

Lifespan must be set on every controller, routing, replay, and test writer.
It is not a requested/offered matching requirement, so a reader cannot enforce
the bound merely by choosing this profile. Connext 7.7 reader expiration is
reception-based; republishing/delayed data can start another local validity
window. The next running step observes expiry, with polling/scheduling tolerance.
No application-owned rate target or duplicate expiry timer is used.

This is a non-hard-real-time demo, not a physical safety-stop design. See the
[system contract](../DDS_DESIGN_GUIDE.md#rate-command-validity) for limits and recovery.

#### ***DataFlowLibrary::Telemetry* profile**

Telemetry inherits from *Streaming* and adds the 200 ms offered/requested
deadline snippet for stale-feedback diagnostics. The Arm publishes observed
feedback at approximately 20 Hz.

#### ***DataFlowLibrary::Vitals* profile**

Vitals inherits from *Streaming* and sets a two-second offered and requested
Deadline and a two-second writer Lifespan for the approximately one-second
sensor cadence. Sensor, monitor, routing, recording, and replay endpoints use
this profile. Deadline detects misses only after an instance is observed;
Lifespan expires cached samples, not application copies. Writer Lifespan is
not a requested/offered matching requirement, so all vitals writers must use
the profile. Routing and replay republish samples, so each hop has its own
cadence and reception-based expiry window. Neither policy authenticates the
source or guarantees original measurement freshness.

#### ***DataFlowLibrary::Status* profile**

This QoS profile is used for status-related Topics. These are Topics that describe the current status of a system component (a device, an observed object, etc.). They're typically sent once at the beginning of operation and again only upon change to the status.

It inherits from the *BuiltinQosLib::Pattern.Status* profile. As a result, this QoS profile applies the following:

- *RELIABLE* Reliability QoS. Samples should be repaired if lost because the timing of the next status update is unknown.
- *KEEP_LAST, depth=1* History QoS. Typically, only the last status per system component needs to be processed or tracked by subscribing applications, or cached by DataWriters to repair as needed.
- *TRANSIENT_LOCAL* Durability QoS. Late-joining DataReaders should automatically receive the most recent status per system component when they join the communication.
- Some optimizations to make repairs faster.

Transient-local history is owned by a live writer; it is not persistent storage.

#### ***DataFlowLibrary::Command* profile**

This QoS profile is used for command and event-related Topics. These are Topics that transmit commands or trigger some action in the system. They are not sent periodically. They should not be delivered to late-joining applications that joined after being published.

It inherits from the *BuiltinQosLib::Generic.Common* profile in addition to builtin QoS snippets. As a result, this QoS profile applies the following:

- *RELIABLE* Reliability QoS. Samples should be repaired if lost because the frequency of commands is unknown and irregular.
- *KEEP_LAST, depth=1* History QoS. In this simplified demonstration, only the last command for a system component should be processed by subscribing applications, or cached by DataWriters to repair as needed.
- *VOLATILE* Durability QoS. Late-joining DataReaders should **not** receive historical commands that were published before they joined.
- Some optimizations to make repairs faster.

*Note, this QoS profile is nearly identical to the *Status* QoS profile, but uses *VOLATILE* durability, since late-joining DataReaders should not receive historical commands.*

#### ***DataFlowLibrary::Heartbeat* profile**

This QoS profile is used to implement a lightweight mechanism to assert and detect the presence of system components.

It inherits from the *Streaming* QoS profile and sets:

- *200 ms* offered/requested Deadline QoS period. Publishers derive their heartbeat interval as one third of the writer's offered deadline (about 67 ms with this profile), leaving margin for best-effort sample loss. A missed reader deadline prompts the Orchestrator to reconcile per-device reception timestamps.

*This QoS profile is designed to be used only for the `t/device/heartbeat` Topic in this reference architecture. This Topic is used to manually signal whether an application is still present in the system or not (e.g. cable disconnected, application crashed, otherwise unreachable, etc.).*

Since this QoS profile uses *BEST_EFFORT* Reliability QoS, a minimal amount of sample loss may occur without repairing. This is accounted for by using a larger Deadline period than the period applications should publish to the `t/device/heartbeat` Topic.

> [!TIP]
> **Best practice:** When using a finite Deadline, consider publishing at
> 2–4 times the deadline frequency to leave margin for an occasional dropped
> sample and scheduling jitter. Choose the margin for the system's requirements.

For this profile, one lost heartbeat followed by an on-time delivery leaves
about 133 ms between received samples, within the 200 ms deadline. Further
loss or jitter can still cause a reader deadline miss; the status indicates a
gap in received updates, not its cause.

#### ***DataFlowLibrary::SecureLog* profile**

This QoS profile is used by the *dr/SecureLog* DataReader (under the *dp/SecureLogReader* DomainParticipant) to consume the RTI Security Plugins builtin secure-logging Topic.

It inherits from *BuiltinQosLib::Generic.KeepLastReliable.TransientLocal* and applies:

- *RELIABLE* Reliability QoS and *TRANSIENT_LOCAL* Durability QoS, matching the QoS the Security Plugins use for their builtin secure-logging writers.
- *KEEP_LAST, depth=64* History QoS (with a matching `max_samples` resource limit), the default history depth used by the secure-logging writers.
- Dynamic memory allocation for the DataReader cache, since the secure-logging type is unbounded.

## Application-specific QoS: [NonSecureAppsQos.xml](NonSecureAppsQos.xml) and [SecureAppsQos.xml](SecureAppsQos.xml)

In addition to the [Qos.xml](#qosxml) file, this reference architecture describes *per-application* QoS in 2 additional XML files:

- [NonSecureAppsQos.xml](./NonSecureAppsQos.xml)
- [SecureAppsQos.xml](./SecureAppsQos.xml)

The contents of these files determine whether the Connext applications are secure or not. When launching the applications, the `NDDS_QOS_PROFILES` environment variable must reference one, but not both, of these files to dictate that decision and apply the resulting configuration.

Both files contain only 1 QoS library: ***DpQosLib***. This QoS library contains 1 QoS profile per DomainParticipant. The rationale behind this library is that DomainParticipants in each application may have different needs. For instance, in the provided modules, the security certificates of each application will be different from each other.

[NonSecureAppsQos.xml](./NonSecureAppsQos.xml) contains one profile for each DomainParticipant. For the simplified demonstration, each profile inherits from *SystemLibrary::DefaultParticipant* in [Qos.xml](./Qos.xml). No additional configuration is applied for any given DomainParticipant.

[SecureAppsQos.xml](./SecureAppsQos.xml) defines secure profiles for the demo DomainParticipants and services in a similar way to **NonSecureAppsQos.xml**, but with security configuration added.

[SecureAppsQos.xml](./SecureAppsQos.xml) defines *LanCommonSecurityConfig* for local domains. It references common permissions CA, identity CA, governance files, and the OperationalDomain PSK seed file. The governance uses `rtps_protection_kind=ENCRYPT_WITH_ORIGIN_AUTHENTICATION` with `rtps_psk_protection_kind=ENCRYPT` for domain-level protection. The [security guide](../security/README.md#key-concepts) describes the topic-level settings.

[SecureAppsQos.xml](./SecureAppsQos.xml) defines a QoS snippet - *WanCommonSecurityConfig* defines common configuration to enable security for remote domains (WAN connections). It references common permissions CA, identity CA, governance files, and the TeleopWanDomain PSK seed file. The same domain-level protection applies (`rtps_protection_kind=ENCRYPT_WITH_ORIGIN_AUTHENTICATION`, `rtps_psk_protection_kind=ENCRYPT`), but the WAN governance applies *stricter* topic-level protection: a catch-all `*` rule with `metadata_protection_kind=ENCRYPT` protects the submessage metadata of **every** topic. The secure log topic `DDS:Security:LogTopicV2` keeps its own `SIGN`/`ENCRYPT`.

## External security snippets: [SecureExternalAppsQos.xml](SecureExternalAppsQos.xml)

[SecureExternalAppsQos.xml](./SecureExternalAppsQos.xml) provides standalone QoS snippets for participants that are **not** part of the demo applications themselves. Unlike the profiles in [SecureAppsQos.xml](./SecureAppsQos.xml), these are independent, Security-specific configurations meant to plug external observers into the secured system.

The file currently defines one snippet:

- **`SecureExternalAppsQosLib::SecureSystemObserver`** — a reusable [QoS Snippet](https://community.rti.com/best-practices/qos-profile-inheritance-and-composition-guidance#h.wr6u1ebybeff) that encapsulates the complete DDS Security property set for a read-only System Observer:
  - Composes `BuiltinQosSnippetLib::Feature.Security.Enable` to activate the Security Plugins
  - Permissions CA and Identity CA trust anchors
  - Operational domain governance
  - SystemObserver identity certificate and private key
  - SystemObserver signed permissions document
  - Secure logging disabled (`mode_mask=BUILTIN`, `verbosity=SILENT`) because the observer has no publish permissions

### Usage

Compose the snippet into any DomainParticipant QoS using the `<base_name>` element:

```xml
<domain_participant_qos>
  <base_name>
    <element>SecureExternalAppsQosLib::SecureSystemObserver</element>
  </base_name>
</domain_participant_qos>
```

### Connext Studio (Spy source)

This configuration is ideal for use with **RTI Connext Studio**. To observe the secured domain with the Spy data source:

1. From the repository root, generate the DDS Security artifacts (identity/permissions CAs, certificates, PSK seeds, and signed governance/permissions). A regular `setup_security.py` run (no flags) creates these under the security tree:

   ```bash
   python3 system/security/setup_security.py
   python3 system/security/setup_security.py --stage
   ```

2. Generate resolved QoS files with absolute security-artifact paths. `--generate-resolved-qos` only emits the QoS files — it does **not** generate the artifacts themselves, so the previous step must be run first:

   ```bash
   python3 system/security/setup_security.py --generate-resolved-qos
   ```

3. In Connext Studio, add a Spy Source and configure the source with the configuration under
`SecureExternalAppsQosLib::SecureSystemObserver` snippet from the `system/security/resolved_qos/SecureExternalAppsQos.xml`.
4. Spy will join the secured Operational Domain as a read-only observer — able to subscribe to all Topics without publish permissions.

## XML QoS Best Practices

> [!TIP]
> **Best practice:** Compose your QoS profiles with [QoS Snippets](https://community.rti.com/best-practices/qos-profile-inheritance-and-composition-guidance#h.wr6u1ebybeff). Snippets provide easier readability and result in more maintainable QoS for increasingly complex systems by reducing repetitive configuration.

> [!TIP]
> **Best practice:** Inherit from [Built-in QoS Profiles](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Built_in_QoS_Profiles.htm). Builtin profiles provide starting points to frequently used and tuned QoS combinations.

Please take a look at the comments inside the profiles and snippets in [Qos.xml](./Qos.xml), [NonSecureAppsQos.xml](./NonSecureAppsQos.xml), [SecureAppsQos.xml](./SecureAppsQos.xml), and [SecureExternalAppsQos.xml](./SecureExternalAppsQos.xml) for further details on each QoS policy and more **best practices** related to QoS configuration.
