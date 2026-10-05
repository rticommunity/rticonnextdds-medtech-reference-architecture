# Project-level Tests

Tests that validate the Module 01 build pipeline, launcher, and retained configuration.
Application-specific tests live under Module 01's `tests/` directory.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| RTI Connext DDS 7.7.x | `NDDSHOME` and `CONNEXTDDS_ARCH` must be set (via rtisetenv script) |
| Python 3.10+ | With `rti.connextdds` and `pytest` installed (in `.venv` or equivalent) |
| C++ build complete | Run `python build.py` first |

## Quick Start

From the repository root, after sourcing the RTI environment and activating the Python venv:

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# If you want to run the security tests
python3 system_arch/security/setup_security.py

# Run project-level and Module 01 tests
pytest

# Run with verbose output
pytest -v

# Run specific module or test
pytest modules/01-operating-room/tests/test_types.py -v

# Run tests matching a pattern
pytest -k "test_types" -v

# Run a specific test class or function
pytest tests/test_config_parsing.py::TestModuleJsonContract -v
```

## Environment Setup

The root `pyproject.toml` configures pytest to automatically discover tests in:

- `tests/` — Project-level tests
- `modules/01-operating-room/tests/` — Module 01 tests

Before running pytest, ensure the RTI environment is sourced:

```bash
source /opt/rti.com/rti_connext_dds-7.7.0/resource/scripts/rtisetenv_x64Linux4gcc8.5.0.bash
source .venv/bin/activate
```

## Test Running Approaches

### Direct pytest (Recommended for Day-to-Day)

Use root-level `pytest` directly for fast iteration and clear output:

```bash
# All tests
pytest

# With markers to skip slow/gui/secure tests
pytest -m "not slow and not gui and not secure"

# Fast feedback on a single file
pytest tests/test_config_parsing.py -v
```

**When to use:**

- Daily development on single tests or modules
- Tight edit-test cycles where speed matters
- Focused debugging of one area

### Docker Container Testing

Use Docker for reproducible, isolated test environments:

```bash
# Set up license file
export RTI_LICENSE_FILE=/path/to/rti_license.dat

# Run all tests in container
docker compose -f tests/docker/docker-compose.yml run --rm --build test

# Run specific tests
docker compose -f tests/docker/docker-compose.yml run --rm --build test \
    -v modules/01-operating-room/tests/test_types.py

# Run tests matching a pattern
docker compose -f tests/docker/docker-compose.yml run --rm --build test \
    -k "test_types"
```

**When to use:**

- Reproducing CI failures in a clean environment
- Verifying behavior when host dependencies vary
- Final pre-merge validation
- Testing GUI components on headless systems (Xvfb included)

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
- `@pytest.mark.gui` — GUI tests requiring a display
- `@pytest.mark.secure` — Security tests requiring artifacts and plugins

Run fast tests only (skip slow/GUI/secure):

```bash
pytest -m "not slow and not gui and not secure"
```

Run only GUI tests:

```bash
pytest -m "gui"
```

## Test Structure

| File | What it tests |
| --- | --- |
| `test_project_build_pipeline.py` | CMake configure & build; Module 01 C++ binaries & shared libraries exist |
| `test_config_parsing.py` | Module 01-only discovery, scenarios, System Designer includes, QoS references, and JSON parsing |
| `test_security_status.py` | Security artifacts generation and availability for secure tests |
| `test_markdown_lint.py` | Project documentation (README, Scenario, etc.) passes rumdl checks |
