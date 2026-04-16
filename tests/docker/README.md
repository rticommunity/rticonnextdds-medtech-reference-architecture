# Docker Test Support

Docker assets for building and testing the MedTech Reference Architecture in a
consistent Linux environment, regardless of host OS (WSL2, macOS, native Linux).
These files are intended for headless test execution, not for running the demo
applications as end-user runtime containers.

## Images

| Image | Target | Purpose |
|-------|--------|--------|
| `medtech-build` | `build` | Ubuntu 22.04 + Connext 7.3.1 + CMake build of C++ modules + security artifacts |
| `medtech-test`  | `test`  | Extends build with Python deps, pytest, Xvfb for headless tests |

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
docker compose -f tests/docker/docker-compose.yml build
docker compose -f tests/docker/docker-compose.yml run test

# Run specific tests
docker compose -f tests/docker/docker-compose.yml run test \
    python -m pytest modules/01-operating-room/tests/test_types.py -v
```

### Using Docker directly

```bash
# From the repo root:

# 1. Build
docker build -f tests/docker/Dockerfile --target build -t medtech-build .
docker build -f tests/docker/Dockerfile --target test  -t medtech-test .

# 2. Run all tests (mount license at runtime)
docker run --rm \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.3.1/rti_license.dat:ro \
    medtech-test

# 3. Run specific tests
docker run --rm \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.3.1/rti_license.dat:ro \
    medtech-test \
    python -m pytest modules/01-operating-room/tests/test_types.py -v

# 4. Interactive shell for debugging
docker run --rm -it \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.3.1/rti_license.dat:ro \
    medtech-test bash
```

## Why two images?

- **`medtech-build`** contains the compiled C++ binaries and all system-level
  dependencies. It can be used standalone if you only need the build artifacts.
- **`medtech-test`** adds Python packages, pytest, and Xvfb on top. Keeping
  them separate means faster rebuilds when only Python deps change.

## Notes

- The images use **UDPv4 only** for DDS transport (no shared memory), which is
  the safe default for containers. This matches CI behavior.
- GUI tests run headlessly via `QT_QPA_PLATFORM=offscreen` and Xvfb.
- Security artifacts (certificates, signed governance) are generated during the
  build stage so secure tests can run.
