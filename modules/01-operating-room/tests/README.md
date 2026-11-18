# Module 01 — Test Suite

Automated tests for the **Digital Operating Room** module.
Tests verify that applications build, launch, communicate via DDS, and
behave as described in the module README.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| RTI Connext DDS 7.7.x | `NDDSHOME` must be set |
| Python 3.11+ | With the Connext Python API (`rti.connextdds`) |
| pytest | `pip install pytest` |
| Central build complete | Run `python build.py` from the repository root, including generated C++/Python/XML |
| `rti-demo-ui` | For browser UI process and API tests |
| Pygame CE | Installed through the root `user` extra; used by the gamepad app |
| MuJoCo, Mink, DAQP | Installed through the root `user` extra; headless arm simulation needs no ROS/GPU |
| Security artifacts (optional) | Run `system/security/setup_security.py` for `@secure` tests |

## Running Tests

From the `modules/01-operating-room/` directory:

```bash
# All tests (browser UI tests need no display server)
pytest tests/ -v

# Skip browser UI process tests (optional)
pytest tests/ -v -m "not gui"

# Skip slow end-to-end tests
pytest tests/ -v -m "not slow"

# Only fast, non-GUI tests (best for quick validation)
pytest tests/ -v -m "not gui and not slow"

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
| `test_launch.py` | Each app starts without crashing | browser mode, no display server |
| `test_arm_kinematics.py` | Engine-derived FK, constrained base-frame motion, collision approaches/recovery, singularity recovery, actuator braking, numerical faults, signed jaw travel | — |
| `test_dds_communication.py` | Actual data paths, including arm/jaw motion, hold after stream loss, and fresh-command recovery | `gui` for Arm tests |
| `test_demo_flow.py` | End-to-end README scenarios (crash detection, pause/resume, shutdown) | `gui`, `slow`, `secure` |
| `test_xml_qos.py` | Loads system QoS XML and creates the five operational named participants; secure Orchestrator startup creates SecureLogReader | `gui`, `secure` for SecureLogReader |

## How It Works

Tests create their own DDS participant on domain 0 and use it to:

- **Subscribe** to topics (`t/patient/vitals`, `t/device/status`, `t/device/heartbeat`) to
  verify apps are publishing the expected data.
- **Publish** commands (`t/device/command`, `t/robot/arm/control`) to verify apps
  respond correctly (pause, shutdown, and teleoperation).

This tests the real DDS communication paths independently of the browser frontend.
The bootstrap imports the central generated model, not module-local bindings.
Command-loss tests observe pose/width/readiness with explicit timing tolerance;
they do not independently test Connext internals or compare design alternatives.

## Markers

- `@pytest.mark.gui` — Browser UI process tests; no graphical display is required.
- `@pytest.mark.slow` — Long-running tests (>10s). Safe to skip for quick validation.
- `@pytest.mark.secure` — Requires DDS Security artifacts. Auto-skipped if
  `setup_security.py` hasn't been run.
