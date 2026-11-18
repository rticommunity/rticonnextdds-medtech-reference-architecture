# Project-level Tests

Tests that validate the project-wide build pipeline and cross-module concerns.
Module-specific tests live under each module's own `tests/` directory.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| RTI Connext DDS SDK 7.7.0 | `NDDSHOME` and `CONNEXTDDS_ARCH` must be set (via rtisetenv script) |
| Python 3.11+ | With locked `rti.connext==7.7.0`, `rti-demo-ui`, and `pytest` installed (in `.venv` or equivalent) |
| C++ build complete | Run `python build.py` first |

The responsive-window cases in `test_ui_mode.py` additionally use the optional
Playwright Python package and a system `google-chrome` or `chromium` executable.
They skip when these are unavailable; they run headlessly without a display.

## Quick Start

From the repository root, after sourcing the RTI environment and activating the Python venv:

```bash
# Install locked developer dependencies in the active virtual environment
python -m pip install uv==0.13.8
uv sync --active --locked --no-dev --extra dev --no-install-project
python resource/python/scripts/check_connext_install.py

# Configure, generate and build once before test execution
python build.py

# If you want to run the security tests
python3 system/security/setup_security.py
python modules/04-security-threat/security/setup_threat_security.py

# Run all tests against the prepared outputs
python -m pytest

# Run with verbose output
python -m pytest -v

# Run specific module or test
pytest system/tests -v

# Run tests matching a pattern
pytest -k "test_types" -v

# Run a specific test class or function
pytest tests/test_config_parsing.py::TestModuleJsonContract -v
```

## Environment Setup

The root `pyproject.toml` configures pytest to automatically discover tests in:

- `tests/` — Project-level tests
- `modules/01-operating-room/tests/` — Module 01 tests
- `modules/02-record-playback/tests/` — Module 02 tests
- `modules/04-security-threat/tests/` — Module 04 tests

Before running pytest, ensure the RTI environment is sourced:

```bash
source /opt/rti.com/rti_connext_dds-7.7.0/resource/scripts/rtisetenv_x64Linux4gcc8.5.0.bash
source .venv/bin/activate
```

## Test Running Approaches

### Direct pytest (Recommended for Day-to-Day)

Use root-level pytest for fast iteration and clear output. The project build is
an explicit prerequisite and is not started by test collection or execution:

```bash
# Pure collection/configuration checks (no generated bindings or DDS runtime)
python -m pytest --collect-only -q tests/test_config_parsing.py

# All tests, after `python build.py`
python -m pytest

# Fast feedback on a single file
python -m pytest tests/test_config_parsing.py -v
```

**When to use:**

- Daily development on single tests or modules
- Tight edit-test cycles where speed matters
- Focused debugging of one area

The separate licensed Python participant smoke is run only when a valid RTI
license is configured. The license-free CI lane does not run it and does not
claim that runtime licensing passed.

### Docker Container Testing

Use Docker for reproducible, isolated test environments. Building the test
image configures/codegens/builds once; the container entrypoint only runs pytest
against those prepared outputs:

```bash
# Set up license file
export RTI_LICENSE_FILE=/path/to/rti_license.dat

# Run all tests in container
docker compose -f tests/docker/docker-compose.yml run --rm --build test

# Run specific tests
docker compose -f tests/docker/docker-compose.yml run --rm --build test \
    -v system/tests

# Run tests matching a pattern
docker compose -f tests/docker/docker-compose.yml run --rm --build test \
    -k "test_types"
```

**When to use:**

- Reproducing CI failures in a clean environment
- Verifying behavior when host dependencies vary
- Final pre-merge validation
- Testing browser UI processes and their local SDK endpoints (no display server required)

### Markdown and Other Checks

```bash
# Markdown linting (rumdl)
rumdl check

# Code formatting and linting (pre-commit)
pre-commit run --all-files
```

## Test Markers

Tests can be filtered using pytest markers. Common markers:

- `@pytest.mark.slow` — Long-running tests (e.g., full application demos)
- `@pytest.mark.gui` — graphical-app process/UI tests; browser mode needs no display server
- `@pytest.mark.secure` — Security tests requiring artifacts and plugins

Run fast tests only (skip slow/GUI/secure):

```bash
pytest -m "not slow and not gui and not secure"
```

Run only graphical-app tests:

```bash
pytest -m "gui"
```

## Test Structure

| File | What it tests |
| --- | --- |
| `test_project_build_pipeline.py` | Prepared CMake/codegen outputs and Module 01 executables exist |
| `test_config_parsing.py` | Module JSON schemas and configuration parsing for all modules |
| `test_security_status.py` | Security artifacts generation and availability for secure tests |
