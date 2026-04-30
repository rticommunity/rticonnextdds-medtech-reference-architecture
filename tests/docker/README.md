# Docker Test Support

Docker assets for building and testing the MedTech Reference Architecture in a
consistent Linux environment, regardless of host OS (WSL2, macOS, native Linux).
These files are intended for headless test execution, not for running the demo
applications as end-user runtime containers.

## Images

| Image | Target | Purpose |
| --- | --- | --- |
| `medtech-build` | `build` | Ubuntu 22.04 + Connext 7.7.0 + CMake build of C++ modules + security artifacts |
| `medtech-test` | `test` | Extends build with Python deps, pytest, rumdl, and Xvfb for headless tests |

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
# Run all tests (default: verbose output)
docker compose -f tests/docker/docker-compose.yml run --rm --build test

# Run specific test file with custom pytest args
docker compose -f tests/docker/docker-compose.yml run --rm --build test \
    modules/01-operating-room/tests/test_types.py -v

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

# 2. Run all tests (mounts license, default pytest with -v)
docker run --rm \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.7.0/rti_license.dat:ro \
    medtech-test

# 3. Run specific tests
docker run --rm \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.7.0/rti_license.dat:ro \
    medtech-test \
    modules/01-operating-room/tests/test_types.py -v

# 4. Run tests matching a pattern
docker run --rm \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.7.0/rti_license.dat:ro \
    medtech-test \
    -k "test_types"

# 5. Interactive shell for debugging
docker run --rm -it \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.7.0/rti_license.dat:ro \
    medtech-test bash
```

## Understanding the Test Flow

The Docker entrypoint (`tests/docker/entrypoint.sh`):

1. Starts Xvfb virtual display (`:99`) for headless GUI tests
2. Sources the RTI Connext environment
3. Runs `python -m pytest` with any provided arguments
4. Cleans up Xvfb on exit

Example: `docker run medtech-test` → entrypoint calls `python -m pytest -v`

Example: `docker run medtech-test -k "test_types"` → entrypoint calls `python -m pytest -k "test_types"`

## Why two images?

- **`medtech-build`** contains the compiled C++ binaries and all system-level
  dependencies. It can be used standalone if you only need the build artifacts.
- **`medtech-test`** adds Python packages, pytest, rumdl, and Xvfb on top. Keeping
  them separate means faster rebuilds when only Python deps change.

## Notes

- The images use **UDPv4 only** for DDS transport (no shared memory), which is
  the safe default for containers. This matches CI behavior.
- GUI tests run headlessly via `QT_QPA_PLATFORM=offscreen` and Xvfb.
- Security artifacts (certificates, signed governance) are generated during the
  build stage so secure tests can run.
- `docker compose run --rm ...` avoids leftover one-off containers after test
  completion.
- All 130 tests (repo-level + modules) are collected and run via the unified
  `python -m pytest` approach configured in the root `pyproject.toml`.
