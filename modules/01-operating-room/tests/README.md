# Module 01 — Test Suite

Automated tests for the **Digital Operating Room** module.  
Tests verify that applications build, launch, communicate via DDS, and
behave as described in the module README.

## Prerequisites

| Requirement | Notes |
|---|---|
| RTI Connext DDS 7.3.0+ | `NDDSHOME` must be set |
| Python 3.9+ | With the Connext Python API (`rti.connextdds`) |
| pytest | `pip install pytest` |
| C++ build complete | Run `python scripts/build.py` first |
| PySide6, pyqtgraph, numpy | For GUI app tests |
| Security artifacts (optional) | Run `system_arch/security/setup_security.py` for `@secure` tests |

## Running Tests

From the `modules/01-operating-room/` directory:

```bash
# All tests (requires display for GUI tests)
python -m pytest tests/ -v

# Skip GUI tests (headless / CI)
python -m pytest tests/ -v -m "not gui"

# Skip slow end-to-end tests
python -m pytest tests/ -v -m "not slow"

# Only fast, non-GUI tests (best for quick validation)
python -m pytest tests/ -v -m "not gui and not slow"

# Only DDS communication tests
python -m pytest tests/test_dds_communication.py -v

# Only security tests (requires setup_security.py)
python -m pytest tests/ -v -m "secure"

# Skip security tests
python -m pytest tests/ -v -m "not secure"
```

## Test Structure

| File | What it tests | Markers |
|---|---|---|
| `test_build.py` | CMake build, binary existence, Python type imports | — |
| `test_launch.py` | Each app starts without crashing | `gui` for GTK/Qt apps |
| `test_dds_communication.py` | DDS topics carry correct data (vitals, heartbeats, statuses, commands) | `gui` for Arm tests |
| `test_demo_flow.py` | End-to-end README scenarios (crash detection, pause/resume, shutdown) | `gui`, `slow`, `secure` |

## How It Works

Tests create their own DDS participant on domain 0 and use it to:

- **Subscribe** to topics (`t/Vitals`, `t/DeviceStatus`, `t/DeviceHeartbeat`) to
  verify apps are publishing the expected data.
- **Publish** commands (`t/DeviceCommand`, `t/MotorControl`) to verify apps
  respond correctly (pause, shutdown, motor control).

This tests the real DDS communication paths without interacting with GUIs.

## Markers

- `@pytest.mark.gui` — Requires a graphical display. Auto-skipped on headless systems.
  Python Qt apps use `QT_QPA_PLATFORM=offscreen`; C++ GTK apps need a real display.
- `@pytest.mark.slow` — Long-running tests (>10s). Safe to skip for quick validation.
- `@pytest.mark.secure` — Requires DDS Security artifacts. Auto-skipped if
  `setup_security.py` hasn't been run.
