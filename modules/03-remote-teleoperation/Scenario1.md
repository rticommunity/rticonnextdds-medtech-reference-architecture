# Scenario 1: Direct Peer-to-Peer Communication with Public IP Address

This scenario demonstrates WAN communication when one DomainParticipant is reachable at a public IP address. This is the simplest WAN deployment scenario.

The *Passive* RTI Routing Service listens for incoming communications. The *Active* RTI Routing Service uses the known public address and port of the *Passive* side to initiate discovery.

Security is optional. When enabled, both Routing Service participants are secured: Domain 0 uses `OperationalDomain` and Domain 1 uses `TeleopWanDomain`. Both profiles require authentication and protect RTPS traffic; their topic-level protection differs. See the [security documentation](../../system/security/README.md) for details.

For secure mode, append `-s` to each Module 01 and Routing Service launch below. Otherwise, run all participants without `-s`.

Make sure the shared setup in the root [Quick Start](../../README.md#quick-start) section is complete and that Module 01 is already working before you try this scenario.

![Scenario 1 diagram](../../docs/assets/module-03-diagram-scenario-01.gif)

## Setup and Installation

Complete the shared setup in the root [Quick Start](../../README.md#quick-start) section. This scenario then adds the WAN transport, security, and network configuration below.

Module-specific notes:

- If you plan to use secure mode, make sure the security artifacts from the root README have been generated.

### 1. Install RTI Real-Time WAN Transport

The RTI Real-Time WAN Transport is available as an add-on product. Follow the [RTI Real-Time WAN Transport Installation Guide](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/addon_products/realtime_wan_transport/installation_guide/index.htm) to install the transport plugin on both machines.

### 2. Security (optional)

Prepare the [local security bundle](../../system/security/README.md) before
running this scenario, or follow the [EPS WAN setup](../../docs/EPS.md#module-03-remote-teleoperation)
for agent-managed credentials.

**You should generate the security artifacts once and then distribute to whichever machines are used to run the demo applications. This ensures the certificates can be correctly verified across machines during DomainParticipant authentication.**

### 3. Network Configuration

On both *Passive* and *Active* sides, set the following environment variables before running the scenario. `NDDSHOME` must already be set from your Connext installation (see [Module 01 Setup](../01-operating-room/README.md#setup-and-installation)).

| Variable | Value | Default |
| --- | --- | --- |
| `PUBLIC_ADDRESS` | Publicly accessible IP address of the *Passive* side. | ***(required)*** |
| `PUBLIC_PORT` | Publicly accessible/forwarded port of the *Passive* side. | 10777 |
| `INTERNAL_PORT` | Internal/forwarded port of the *Passive* side. This may be the same as `PUBLIC_PORT`. | 10777 |

`PUBLIC_PORT` and `INTERNAL_PORT` default to `10777` in the XML configuration and only need to be set if you are forwarding a different port. `PUBLIC_ADDRESS` has no default and **must** be set, or the service will fail to start.

```bash
# Linux / macOS
export PUBLIC_ADDRESS=<public IP address of passive side>
export PUBLIC_PORT=10777       # only needed if not using the default
export INTERNAL_PORT=10777     # only needed if not using the default

# Windows Command Prompt
set PUBLIC_ADDRESS=<public IP address of passive side>
set PUBLIC_PORT=10777
set INTERNAL_PORT=10777
```

You must then configure UDP port forwarding on your *Passive* side router between `PUBLIC_PORT` and `INTERNAL_PORT` to expose your DDS applications on the WAN.
For example:

![Home office router configuration](../../docs/assets/module-03-home-router-config.png)

## Run the Scenario

> Important: Run the commands below from the repository root. `medtech.py run` lives at the project root and is the single runtime entrypoint for this project.

*Note: This scenario will not work if different certificate sets are used on each side when using Security.*

### 1. Launch Active Side Applications

From the machine *not* publicly exposed, start the teleop Arm Controller as the *Active* side:

```bash
# From the repository root
python medtech.py run 01-operating-room ArmController
```

### 2. Launch Passive Side Applications

From the machine *publicly* exposed, start the Operating Room applications as the *Passive* side:

```bash
# From the repository root
python medtech.py run 01-operating-room Orchestrator PatientSensor Arm PatientMonitor
```

>**Observe:** You should see **no communication** between applications since the Routing Service infrastructure has not been started yet.

### 3. Launch Passive Routing Service

In a new terminal on the *Passive* side:

```bash
# From the repository root
python medtech.py run 03-remote-teleoperation RsPassive
```

### 4. Launch Active Routing Service

In a new terminal on the *Active* side:

```bash
# From the repository root
python medtech.py run 03-remote-teleoperation RsActive
```

### 5. Observe Communication

[Observe the operating room applications](../01-operating-room/README.md#2-observe-the-application-behavior) to verify that all *Module 01: Digital Operating Room* functionality works across the WAN.

>**Observe:** Once discovery completes, you should see data flow between the Operating Room applications and the Arm Controller. RTI Routing Service provides scalability by bridging between the local networks over the WAN and avoids managing a separate WAN connection for each set of remote applications that communicate.

### 6. Kill the applications

Press `Ctrl-C` in each terminal to terminate the running applications.
