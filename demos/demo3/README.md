# Demo 3 - Teleoperation with RTI Real-Time WAN Transport

Demo 3 demonstrates Teleoperation across the Wide Area Network (WAN) with the
RTI Real-Time WAN Transport. This is a transport plugin that enables
communication across WAN using UDP as the underlying IP transport-layer
protocol.

This examples demonstrates that the Surgeon Console of the Digital Operating
Room from [Demo 1 - Digital Operating Room](../demo1/) can be anywhere in the
world and continue to communicate with the rest of the system. Make sure you
are able to run Demo 1 before trying out this demo.

WAN communication can be deployed in 3 different scenarios:

1. Scenario 1: Peer-to-peer communication with a DomainParticipant that has a public IP address.
2. Scenario 2: Peer-to-peer communication with DomainParticipants behind cone-NATs using.
3. Scenario 3: Relayed communication with DomainParticipants behind any NAT using.

You can use this decision tree to decide what scenario suits your needs:

![Scenario decision tree](../../resource/images/scenario_decision_tree.png)

You can use the NAT type checker script in [resource/nat_type_checker](../../resource/nat_type_checker)
if you need to use scenario 2, which requires cone NATs.
