# Scenario 1: Peer-to-peer communication with a DomainParticipant that has a public IP address

## Requirements

Packages:

```plaintext
rti_connext_dds-7.3.0-pro-host-<architecture>.<run/exe>
rti_real_time_wan_transport-7.3.0-host-<architecture>.rtipkg
```

If using RTI Security Plugins, you'll also need these packages:

```plaintext
rti_security_plugins-7.3.0-host-openssl-3.0-<architecture>.rtipkg
openssl-3.0.12-7.3.0-host-<architecture>.rtipkg
```

With regards to network configuration, you'll need to set up a static mapping
of your OR's router (could be a home office) between a `PUBLIC_PORT` and an
`INTERNAL_PORT`, for the UDP protocol. For instance:

![Home office router configuration](../../resource//images/configuration_home_office_router.png)

## Diagram

![Scenario 1 diagram](../../resource//images/scenario1_diagram.gif)

The passive Routing Service will listen for incoming communications. The Active
Routing Service will use its initial peers to start the communication with the
Passive one. In the diagram above, the public address needs to be known by the
remote Active Routing Service.

As you can see, only domain 1 is secured. That means that for this demo, you
will run the different applications from demo 1 in their not-secured version. In
a real-world scenario, you may opt to secure the entire system, or just the WAN
part like in this demo.

## How to run this scenario

1. Start the Surgeon Console / Arm Controller on the _Active_ side:

    ```bash
    cd demo1
    ./scripts/launch_arm_controller.sh
    ```

2. Start the rest of the applications of the OR on the _Passive_ side:

    ```bash
    cd demo1
    ./scripts/launch_OR_apps.sh
    ```

3. You should see **no communication** between the Arm Controller and the rest
of the applications since the Routing Service infrastructure hasn't been started
yet.

4. In a terminal on the _Passive_ side, set up `NDDSHOME` pointing at the
Connext installation, set these variables and run Routing Service:

    ```bash
    cd demo3
    ./scripts/launch_rs_passive.sh
    ```

5. In a terminal on the _Active_ side, set up `NDDSHOME` pointing at the Connext
installation, set these variables and run Routing Service:

    ```bash
    cd demo3
    ./scripts/launch_rs_active.sh
    ```

## Expected output

After a few seconds, once discovery is completed, you should see communication
between the OR applications and the Arm Controller. Actually, you could start
the applications on either side and the communication should keep flowing.
Routing Service helps with scalability because you do not need to initiate new
WAN connections per application, Routing Service will simply take care of that
for you.
