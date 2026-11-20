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
docker run --rm -it \
    -v $RTI_LICENSE_FILE:/opt/rti.com/rti_license.dat:ro \
    medtech-test bash
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

## Why two images?

- **`medtech-build`** contains the compiled C++ binaries and all system-level
  dependencies. It can be used standalone if you only need the build artifacts.
- **`medtech-test`** adds Chromium and its system libraries. Keeping
  browser installation in this final stage avoids adding Chromium to the build
  image. Browser prerequisites are required; missing dependencies fail the suite.

## Notes

- The images use **UDPv4 only** for DDS transport (no shared memory), which is
  the safe default for containers. This matches CI behavior.
- Browser-mode graphical apps and their local SDK endpoints run headlessly without Xvfb.
- Security artifacts (certificates, signed governance) are generated during the
  build stage so secure tests can run.
- `docker compose run --rm ...` avoids leftover one-off containers after test
  completion.
- The runtime smoke needs a valid license mounted at runtime. The image contains
  neither the license file nor its contents; provide the file through the
  compose volume or another secret/file mount.
- All 110+ tests (repo-level + modules) are collected and run via the unified
  `pytest` approach configured in the root `pyproject.toml`.
