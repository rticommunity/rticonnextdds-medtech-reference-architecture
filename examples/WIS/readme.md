# Web Integration Service — RTI MedTech Reference Architecture

This example demonstrates how the RTI Web Integration Service hosts a remote web page that sends MotorControl commands into the MedTech Reference Architecture over WebSockets. A remote web page (`examples/WIS/html/robot_arm.html`) uses Web Integration Service REST + WebSocket endpoints to connect and issue real-time motor control samples over the same Topics the Arm already operates on.

See the project root [README.md](../../README.md) for overall architecture and how this example fits in.

## Contents

- [Example Description](#example-description)
- [Setup and Installation](#setup-and-installation)
- [Run the Example](#run-the-example)
- [Web Control Mappings](#web-control-mappings)
- [Hands-On: Going Further](#hands-on-going-further)

## Example Description

This example implements a web-based controller for the surgical robot arm using RTI Web Integration Service. The system consists of:

### Web Integration Service Configuration

The Web Integration Service configuration ([wis_service.xml](./xml_config/wis_service.xml)) reuses the already established system definitions for Data Types, Topics, Qos, and Domains.

The single system architecture ensures tight component integration via a concrete data model. The absence of an application implementation in the system definition supports scaling the system by reusing the common data model for new or extended system applications.

- A domain participant named `MotorControlParticipant` is configured on **Domain 0**, using the `RtiServicesLib::WebIntegrationService` QoS profile.
- A publisher and a `MotorControlWriter` data writer are defined; the writer uses the `DataFlowLibrary::Command` QoS profile.
- The Web Integration Service exposes REST endpoints to create WebSocket connections and a WebSocket endpoint that the web UI can connect to.

### Web UI

The web UI (`html/robot_arm.html`) connects to Web Integration Service and sends MotorControl commands via WebSocket. The web UI issues publish requests over the WebSocket and Web Integration Service translates these into DDS `MotorControl` samples on `t/MotorControl`.

## Setup and Installation

### 1. Install Dependencies

This example requires:

- [RTI Web Integration Service](https://community.rti.com/static/documentation/connext-dds/7.3.0/doc/manuals/connext_dds_professional/services/web_integration_service/index.html)
- Browser with WebSocket support

## Run the Example

### 1. Start Web Integration Service

***Unlike other examples, this example does not need to be started from a prepared "examples" Docker container. The following commands can be ran directly from a host to launch Web Integration Service.***

Start Web Integration Service and enable WebSockets:

```bash
./scripts/launch_wis.sh
```

Alternatively, run using RTI's public Docker image:

```bash
docker run -it --rm \
    --network host \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.3.0/rti_license.dat \
    -v $PWD/../..:/medtech_ra:ro \
    -e NDDS_QOS_PROFILES="/medtech_ra/system_arch/Types.xml;/medtech_ra/system_arch/qos/Qos.xml;/medtech_ra/system_arch/qos/NonSecureAppsQos.xml;/medtech_ra/system_arch/xml_app_creation/DomainLibrary.xml;/medtech_ra/system_arch/xml_app_creation/ParticipantLibrary.xml" \
    --name=web_integration_service \
    rticom/web-integration-service:7.3.0 \
    -cfgFile /medtech_ra/examples/WIS/xml_config/wis_service.xml \
    -cfgName MotorControlWebApp \
    -listeningPorts 8080 \
    -documentRoot /medtech_ra/examples/WIS \
    -enableKeepAlive yes \
    -enableWebSockets
```

### 2. Open Web UI

Open `http://<host>:<port>/html/robot_arm.html` in a browser, and use the UI to send MotorControl commands.

If running locally, this will be: [http://localhost:8080/html/robot_arm.html](http://localhost:8080/html/robot_arm.html).

>**Observe:** The web page buttons send short, repeated MotorControl commands when pressed. Each control button encodes a target motor and a direction (increment/decrement) which Web Integration Service publishes as `MotorControl` messages to `t/MotorControl`.

## Web Control Mappings

The web UI provides buttons that map to specific motor controls:

| Web UI Control | Motor         | Direction
| -------------- | -----         | ---------
| Base: `ccw`    | `Motors.BASE` | decrement
| Base: `cw`     | `Motors.BASE` | increment
| Shoulder: `up` | `Motors.SHOULDER` | increment
| Shoulder: `down` | `Motors.SHOULDER` | decrement
| Elbow: `up`    | `Motors.ELBOW` | increment
| Elbow: `down`  | `Motors.ELBOW` | decrement
| Wrist: `up`    | `Motors.WRIST` | increment
| Wrist: `down`  | `Motors.WRIST` | decrement
| Gripper: `open` | `Motors.HAND` | increment
| Gripper: `close` | `Motors.HAND` | decrement

## Hands-On: Going Further

### 1. RTI Routing Service Integration

When the remote web host cannot directly reach the Arm domain, RTI Routing Service (see [Module 03: Remote Teleoperation](../../modules/03-remote-teleoperation/)) can be configured to route the Web Integration Service-published `MotorControl` samples into local domains. Using the Routing Service configuration provided in Module 03 permits control samples published by Web Integration Service in a remote network to be routed locally for use by local Arms.
