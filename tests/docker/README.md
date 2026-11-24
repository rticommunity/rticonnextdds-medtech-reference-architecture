# Docker Test Support

Docker assets for building and testing the MedTech Reference Architecture in a
consistent Linux environment, regardless of host OS (WSL2, macOS, native Linux).
These files are intended for headless test execution, not for running the demo
applications as end-user runtime containers.

## Images

| Image | Target | Purpose |
| --- | --- | --- |
| `medtech-build` | `build` | Ubuntu 24.04 + Connext SDK 7.7.0 + CMake build of C++ modules |
| `medtech-test` | `test` | Extends build with Playwright Chromium and its system dependencies for the full pytest suite |

## Prerequisites

- Docker (or Docker Desktop on macOS/Windows)
- `RTI_LICENSE_FILE` environment variable pointing to your `rti_license.dat`

```bash
# Set this in your shell profile or before running docker commands
export RTI_LICENSE_FILE=/path/to/rti_license.dat
# Common locations:
#   $NDDSHOME/rti_license.dat
#   ~/rti_license.dat
```

## Quick Start

### Using Docker Compose (recommended)

```bash
# Run all tests (default: the full suite over the repo)
docker compose -f tests/docker/docker-compose.yml run --rm --build test

# Run specific test file with custom pytest args
docker compose -f tests/docker/docker-compose.yml run --rm --build test \
    system/tests -v

# Run tests matching a pattern
docker compose -f tests/docker/docker-compose.yml run --rm --build test \
    -k "test_types"

# Run fast tests only (skip slow/GUI/secure)
docker compose -f tests/docker/docker-compose.yml run --rm --build test \
    -m "not slow and not gui and not secure"

# Optional: compose up style (then clean up service container)
docker compose -f tests/docker/docker-compose.yml up --build --abort-on-container-exit --exit-code-from test test
docker compose -f tests/docker/docker-compose.yml down --remove-orphans
```

### Using Docker directly

```bash
# From the repo root:

# 1. Build both images
docker build -f tests/docker/Dockerfile --target build -t medtech-build .
docker build -f tests/docker/Dockerfile --target test  -t medtech-test .

# 2. Run all tests (mounts license; runs the full suite)
docker run --rm \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_license.dat:ro \
    medtech-test

# 3. Run specific tests
docker run --rm \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_license.dat:ro \
    medtech-test \
    system/tests -v

# 4. Run tests matching a pattern
docker run --rm \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_license.dat:ro \
    medtech-test \
    -k "test_types"

# 5. Interactive shell for debugging
docker run --rm -it --entrypoint bash \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_license.dat:ro \
    medtech-test
```

## Understanding the Test Flow

The image build is the explicit configure/codegen/build stage. The
`medtech-test` stage inherits those prepared outputs. The Docker entrypoint
(`tests/docker/entrypoint.sh`):

1. Sources the RTI Connext environment
2. Runs the separate licensed Python participant smoke
3. Issues and stages test credentials inside the disposable container, not the image
4. Runs pytest with any provided arguments; it does not reconfigure or rebuild

Example: `docker run medtech-test` → entrypoint calls `pytest .` against the
outputs built into the image

Example: `docker run medtech-test -k "test_types"` → entrypoint calls `pytest -k "test_types"`

The dependency layer copies `pyproject.toml` and the committed `uv.lock`, then
uses an exact locked developer sync. The PyPI Connext API is part of that lock;
it is neither installed separately nor duplicated during synchronization.
The installed Connext packages are pinned to the Python API patch. Update these
together when changing Connext versions. Package availability for an
architecture does not by itself establish that all services are supported there.

## WAN loopback check

The optional Linux container check uses the `build` image and requires a valid
license. It runs only with `--network none`, and needs the container's default
raw-socket capability to count loopback packets (it does not print packet
contents):

```bash
docker build -f tests/docker/Dockerfile --target build -t medtech-build .
docker run --rm --network none --hostname localhost \
    -v "$RTI_LICENSE_FILE:/opt/rti.com/rti_license.dat:ro" \
    --entrypoint /bin/bash medtech-build -ec \
    'source "$NDDSHOME"/resource/scripts/rtisetenv_*.bash; python tests/docker/check_wan_loopback.py'
```

The check places the two local sides in separate DDS domains, verifies the
WAN-only transport profiles, checks that samples do not cross with the active
route absent, then checks bidirectional heartbeat delivery and UDP packets on
the WAN port with both routes running. It exercises no-NAT loopback routing;
it does not validate actual WAN paths, NAT traversal, firewalls or security.

## Containerlab WAN and NAT check

This optional Linux-only lab runs locally; it does not need external machines or
an Internet WAN. It uses containerlab virtual links to connect two private
edges through simulated NATs and an Internet router to a cloud node. The
`wan-lab` image contains the existing build and node network tools. A separate
Compose file runs Containerlab to create and destroy the topology:

```bash
# From the physical repository root; RTI_LICENSE_FILE must be an absolute
# path to a valid license. Rebuild after changing project sources.
docker compose -f tests/docker/docker-compose.wan.yml up -d --build --wait
python3 tests/docker/check_wan_lab.py
MEDTECH_WAN_LAB=1 python3 modules/03-remote-teleoperation/tests/test_wan_teleoperation.py -v
docker compose -f tests/docker/docker-compose.wan.yml down
```

If Docker build containers cannot resolve hosts but the Linux host can, add
`--network host` to a manual build, then start Compose without rebuilding.
This gives build steps host network access:

```bash
docker build --network host -f tests/docker/Dockerfile --target wan-lab -t medtech-wan-lab:local .
docker compose -f tests/docker/docker-compose.wan.yml up -d --no-build --wait
```

The runner uses a privileged container with the host network and PID namespaces,
Docker socket and network-namespace mounts to manage the lab. Its nodes have
their own network and IPC namespaces, no Docker management interface, IPv6
firewall drops and no automatic restart. Containerlab creates a dedicated
management network, but no lab nodes are attached to it. The script refuses
to deploy over existing lab resources and tears down only this topology.
The license is mounted read-only and is not included in the image. Keep the
same license path and repository working directory for `down` as well as `up`.

The containerized runner is not a host security boundary. Its privilege scope
is a follow-up hardening item: assess whether privileged mode, host network/PID
namespaces and host mounts can be narrowed while preserving deployment,
isolation checks, all three application scenarios, normal teardown and
interrupted-run recovery. The current runner still requires the declared
permissions; use a disposable VM if stronger host isolation is needed.

Normal `down` requests Containerlab teardown. A forced stop or host failure may
leave lab resources behind. After confirming the runner is stopped and the
remaining resources belong to this lab, recover them with:

```bash
docker compose -f tests/docker/docker-compose.wan.yml run --rm --no-deps lab recover
docker compose -f tests/docker/docker-compose.wan.yml down
```

Recovery refuses ambiguous or conflicting ownership; inspect any remaining
resources manually if it cannot establish ownership.

The check characterizes the lab's static 1:1 UDP translation: it compares
source mappings to two destinations and tests unsolicited inbound traffic on
each edge. It then uses the actual Module 03 configurations to test:

1. Bidirectional heartbeats over a CDS-assisted direct path, with packets seen
   between the translated edge addresses.
2. No remote heartbeats when that direct path is blocked after discovery,
   with firewall drop counters increasing.
3. Bidirectional heartbeats through the cloud Routing Service while the direct
   path remains blocked, with packets observed on both relay legs.

The lab checks its network and IPC isolation before testing. These are
unsecured tests of one simulated translation and filtering behavior, not proof
of real-world NAT, firewall, security, or Internet performance. CDS assists
discovery; it does not relay the application payload.

The Module 03 functional test runs the real Arm Controller and simulated Arm
on opposite lab edges. It checks that controller-initiated demo motion changes
the arm's reported position in each of the three scenarios, then blocks the
relevant WAN path and checks that feedback becomes stale. The relay scenario
blocks direct edge traffic before starting the relay. The test is skipped by
ordinary pytest runs unless `MEDTECH_WAN_LAB=1` is set; setting it requires an
already running lab and fails if the lab is not available.

## Why two images?

- **`medtech-build`** contains the compiled C++ binaries and all system-level
  dependencies. It can be used standalone if you only need the build artifacts.
- **`medtech-test`** adds Chromium and its system libraries. Keeping
  browser installation in this final stage avoids adding Chromium to the build
  image. Browser prerequisites are required; missing dependencies fail the suite.

## Notes

- DDS transport selection follows the project's QoS profiles. The WAN check
  requires UDPv4_WAN on its WAN participants; local participants may use
  other enabled transports.
- Browser-mode graphical apps and their local SDK endpoints run headlessly without Xvfb.
- Disposable security artifacts (certificates, signed governance) are generated
  by the test entrypoint at container runtime, not during the image build.
- `docker compose run --rm ...` avoids leftover one-off containers after test
  completion.
- The runtime smoke needs a valid license mounted at runtime. The image contains
  neither the license file nor its contents; provide the file through the
  compose volume or another secret/file mount.
- Tests (repo-level + modules) are collected and run via the unified
  `pytest` approach configured in the root `pyproject.toml`.
