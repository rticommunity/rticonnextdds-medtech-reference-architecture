# Project-level Tests

Tests that validate the project-wide build pipeline and cross-module concerns.
Module-specific tests live under each module's own `tests/` directory.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| RTI Connext DDS 7.3.1+ | `NDDSHOME` and `CONNEXTDDS_ARCH` must be set (via rtisetenv script) |
| Python 3.9+ | With `rti.connextdds` and `pytest` installed (in `.venv39` or equivalent) |
| C++ build complete | Run `python build.py` first |

## Quick Start

From the repository root, after sourcing the RTI environment and activating the Python venv:

```bash
# Run all 130 tests (repo-level + all modules)
python -m pytest

# Run with verbose output
python -m pytest -v

# Run specific module or test
python -m pytest modules/01-operating-room/tests/test_types.py -v

# Run tests matching a pattern
python -m pytest -k "test_types" -v

# Run a specific test class or function
python -m pytest tests/test_config_parsing.py::TestModuleJsonContract -v
```

## Environment Setup

The root `pyproject.toml` configures pytest to automatically discover tests in:

- `tests/` — Project-level tests
- `modules/01-operating-room/tests/` — Module 01 tests
- `modules/02-record-playback/tests/` — Module 02 tests
- `modules/04-security-threat/tests/` — Module 04 tests

Before running pytest, ensure the RTI environment is sourced:

```bash
source /opt/rti.com/rti_connext_dds-7.3.1/resource/scripts/rtisetenv_x64Linux4gcc7.3.0.bash
source .venv39/bin/activate
```

## Test Running Approaches

### Direct pytest (Recommended for Day-to-Day)

Use root-level `pytest` directly for fast iteration and clear output:

```bash
# All tests
python -m pytest

# With markers to skip slow/gui/secure tests
python -m pytest -m "not slow and not gui and not secure"

# Fast feedback on a single file
python -m pytest tests/test_config_parsing.py -v
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
rumdl check .

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
python -m pytest -m "not slow and not gui and not secure"
```

Run only GUI tests:

```bash
python -m pytest -m "gui"
```

## Test Structure

| File | What it tests |
| --- | --- |
| `test_project_build_pipeline.py` | CMake configure & build; Module 01 C++ binaries & shared libraries exist |
| `test_config_parsing.py` | Module JSON schemas and configuration parsing for all modules |
| `test_security_status.py` | Security artifacts generation and availability for secure tests |
| `test_markdown_lint.py` | Project documentation (README, Scenario, etc.) passes rumdl checks |
