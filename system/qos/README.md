# Quality of Service (QoS)

QoS defines how the demo's DDS participants discover and communicate. The profiles are composed in [Qos.xml](Qos.xml); the [QoS profile reference](QOS_PROFILE_REFERENCE.md) explains the policies, inheritance, application security configuration, and external observer setup.

## Data-flow profiles

| QoS Profile | Reliability | History (kind+depth) | Durability | Deadline period | Intended Use
| ----------- | ----------- | ------- | ---------- | --------- | -----------
| [*Streaming*](QOS_PROFILE_REFERENCE.md#dataflowlibrarystreaming-profile) | *BEST_EFFORT* | *KEEP_LAST 1* | *VOLATILE* | -- | Periodic Topics published at a high rate.
| [*Control*](QOS_PROFILE_REFERENCE.md#dataflowlibrarycontrol-profile) | *BEST_EFFORT* | *KEEP_LAST 1* | *VOLATILE* | *50 ms* | Complete arm/jaw rates, with 250 ms writer lifespan.
| [*Telemetry*](QOS_PROFILE_REFERENCE.md#dataflowlibrarytelemetry-profile) | *BEST_EFFORT* | *KEEP_LAST 1* | *VOLATILE* | *200 ms* | Periodic observed arm feedback at approximately 20 Hz.
| [*Vitals*](QOS_PROFILE_REFERENCE.md#dataflowlibraryvitals-profile) | *BEST_EFFORT* | *KEEP_LAST 1* | *VOLATILE* | *2 s* | Patient vitals at approximately 1 Hz, with 2 s writer lifespan.
| [*Status*](QOS_PROFILE_REFERENCE.md#dataflowlibrarystatus-profile) | *RELIABLE* | *KEEP_LAST 1* | *TRANSIENT_LOCAL* | -- | "Current status"-like Topics, sent once at the beginning of operation and again only upon change to the status.
| [*Command*](QOS_PROFILE_REFERENCE.md#dataflowlibrarycommand-profile) | *RELIABLE* | *KEEP_LAST 1* | *VOLATILE* | -- | Topics that transmit commands or trigger some action in the system.
| [*Heartbeat*](QOS_PROFILE_REFERENCE.md#dataflowlibraryheartbeat-profile) | *BEST_EFFORT* | *KEEP_LAST 1* | *VOLATILE* | *200 ms* | To assert and detect the presence of system components.
| [*SecureLog*](QOS_PROFILE_REFERENCE.md#dataflowlibrarysecurelog-profile) | *RELIABLE* | *KEEP_LAST 64* | *TRANSIENT_LOCAL* | -- | Delivery of the DDS Security builtin secure-log Topic.

For system-wide profiles and the application-specific XML files, see the [profile reference](QOS_PROFILE_REFERENCE.md). For general DDS design and QoS concepts, see the [DDS design guide](../DDS_DESIGN_GUIDE.md#quality-of-service-qos).
