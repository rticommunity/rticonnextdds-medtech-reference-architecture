# Module 01 — Test Suite

Automated tests for the **Digital Operating Room** module.
Tests verify that applications build, launch, communicate via DDS, and
behave as described in the module README.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| RTI Connext DDS 7.7.x | `NDDSHOME` must be set |
| Python 3.10+ | With the Connext Python API (`rti.connextdds`) |
| pytest | `pip install pytest` |
| C++ build complete | Run `python build.py` from the repository root first |
| Security artifacts (optional) | Run `system_arch/security/setup_security.py` for `@secure` tests |

## Running Tests

From the `modules/01-operating-room/` directory:

```bash
# All tests
pytest tests/ -v

# Skip slow end-to-end tests
pytest tests/ -v -m "not slow"

# Only DDS communication tests
pytest tests/test_dds_communication.py -v

# Only security tests (requires setup_security.py)
pytest tests/ -v -m "secure"

# Skip security tests
pytest tests/ -v -m "not secure"
```

## Test Structure

| File | What it tests | Markers |
| --- | --- | --- |
| `test_types.py` | Python type imports, field/enum validation | — |
| `test_launch.py` | Each app starts without crashing | — |
| `test_dds_communication.py` | DDS topics carry correct data (vitals, heartbeats, statuses, commands) | — |
| `test_demo_flow.py` | End-to-end README scenarios (crash detection, pause/resume, shutdown) | `slow`, `secure` |

## How It Works

Tests create their own DDS participant on domain 0 and use it to:

- **Subscribe** to topics (`t/Vitals`, `t/DeviceStatus`, `t/DeviceHeartbeat`) to
  verify apps are publishing the expected data.
- **Publish** commands (`t/DeviceCommand`, `t/MotorControl`) to verify apps
  respond correctly (pause, shutdown, motor control).

This tests the real DDS communication paths without interacting with browser interfaces.

Run `node --test tests/web-controls.test.cjs` separately to test browser request
scheduling and command feedback with delayed HTTP responses. This suite needs
Node.js but does not need DDS or a running workspace.

## Markers

- `@pytest.mark.slow` — Long-running tests (>10s). Safe to skip for quick validation.
- `@pytest.mark.secure` — Requires DDS Security artifacts. Auto-skipped if
  `setup_security.py` hasn't been run.
