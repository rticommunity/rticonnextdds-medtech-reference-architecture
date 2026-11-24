# Module 03 Tests

The opt-in WAN test runs the real Arm Controller and simulated Arm on separate
Containerlab edges. It verifies motion and returned feedback through each
Module 03 scenario, then blocks the WAN path and checks feedback becomes stale.

The lab requires Linux, Docker, an RTI license and privileged Containerlab
access. For setup, execution and cleanup, see the
[Containerlab WAN and NAT check](../../../tests/docker/README.md#containerlab-wan-and-nat-check).
This simulated topology does not establish real Internet or NAT behavior.
