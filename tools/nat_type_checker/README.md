# NAT Type Checker

This optional diagnostic helps select a [Module 03 WAN scenario](../../modules/03-remote-teleoperation/).
It uses `pystun3` to probe third-party STUN servers and reports the library's
classification as a **hint**, not a guarantee of NAT type or peer reachability.
The servers observe your public network address.

Run on each edge machine from the repository root:

```sh
python3 tools/nat_type_checker/nat_type_checker.py
```

The shared [Quick Start](../../README.md#quick-start) installs `pystun3`. For
standalone use, install it with `python3 -m pip install pystun3`.

The library uses an older STUN classification test. Servers may be unavailable
or lack the required changed-address and change-request behavior; firewalls,
multiple NATs and timeouts can also affect the result. In particular, a failed
change request is not proof of restrictive filtering. The tool does not
distinguish a directly reachable host from a full-cone NAT. An inconclusive
result is not proof that UDP is blocked.

Compare both edges' results with the scenario requirements, confirm public
endpoint and firewall configuration, and test actual end-to-end data flow.
Scenario 3 is a useful fallback when the NAT behavior is unknown or direct
communication fails, provided both edges can reach its public relay.
