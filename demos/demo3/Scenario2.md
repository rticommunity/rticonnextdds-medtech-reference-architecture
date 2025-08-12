# Non-security scenario 2: Peer-to-peer communication with DomainParticipants behind cone NATs using Cloud Discovery Service

## Requirements

Packages:

```plaintext
rti_connext_dds-7.3.0-pro-host-<architecture>.<run/exe>
rti_cloud_discovery_service-7.3.0-host-<architecture>.rtipkg (only on the Cloud)
rti_real_time_wan_transport-7.3.0-host-<architecture>.rtipkg
```

This scenario requires Home Office 1 and Home Office 2 NATs to be cone NATs.
You can use the NAT type checker script in [resources/nat_type_checker](../../resources/nat_type_checker)
to make sure you have cone NATs.

With regards to network configuration, you'll need to add a security rule on
your AWS instance to allow incoming / outgoing traffic on `PUBLIC_PORT` for the
UDP protocol. For instance:

![AWS Configuration](../../resources/images/configuration_aws.png)

## Diagram

![Non-security scenario 2 diagram](../../resources/images/non_security_scenario_2.png)

Cloud Discovery Service will put the Active Routing Services in contact when
they reach out to it. The Active Routing Services will point their their
initial peers at AWS. In the diagram above, AWS's address needs to be known by
the remote Active Routing Services.

## How to run this scenario

On AWS:

1. In a terminal, set up `NDDSHOME` pointing at the Connext installation and set these variables:

    ```bash
    export PUBLIC_ADDRESS=<public_IP_address>
    export PUBLIC_PORT=<PUBLIC_PORT>
    ```

2. Run Cloud Discovery Service:

    ```bash
    cd non_security_scenarios/scenario_2/
    $NDDSHOME/bin/rticlouddiscoveryservice -cfgFile CdsConfig_Cloud.xml -cfgName CdsConfig_Cloud
    ```

On Home Office 1:

1. Start a Shapes Demo publisher on **domain 1**. Publish some shapes.
2. In a terminal, set up `NDDSHOME` pointing at the Connext installation and set these variables:

    ```bash
    export PUBLIC_ADDRESS=<public_IP_address>
    export PUBLIC_PORT=<PUBLIC_PORT>
    ```

3. Run Routing Service:

    ```bash
    cd non_security_scenarios/scenario_2/
    $NDDSHOME/bin/rtiroutingservice -cfgFile "../../Qos.xml;RsConfig_Active.xml" -cfgName RsConfig_Active
    ```

On Home Office 2:

1. Start a Shapes Demo subscriber on **domain 1**. Subscribe to some shapes.
2. In a terminal, set up `NDDSHOME` pointing at the Connext installation and set these variables:

    ```bash
    export PUBLIC_ADDRESS=<public_IP_address>
    export PUBLIC_PORT=<PUBLIC_PORT>
    ```

3. Run Routing Service:

    ```bash
    cd non_security_scenarios/scenario_2/
    $NDDSHOME/bin/rtiroutingservice -cfgFile "../../Qos.xml;RsConfig_Active.xml" -cfgName RsConfig_Active
    ```

## Expected output

After a few seconds, once discovery is completed, Home Office 2 should start
receiving the shapes that Home Office 1 publishes. Actually, you could start
any number of Shapes Demo publishers on either side and the other one should
receive those as well. Routing Service helps with scalability because you do
not need to initiate new WAN connections per application, Routing Service will
simply take care of that for you.
