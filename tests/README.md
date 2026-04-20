# Project-level Tests

Tests that validate the project-wide build pipeline and cross-module
concerns.  Module-specific tests live under each module's own `tests/`
directory.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| RTI Connext DDS 7.3.0+ | `NDDSHOME` and `CONNEXTDDS_ARCH` must be set |
| Python 3.9+ | With `rti.connextdds` and `pytest` installed |
| C++ build complete | Run `python build.py` first |

## Running Tests

From the repository root:

```bash
# All project-level tests (includes cmake re-configure)
python -m pytest tests/ -v

# Skip cmake configure/build (just verify binaries exist)
python -m pytest tests/ -v -k "not cmake"

# Markdown lint only (requires markdownlint-cli on PATH)
python -m pytest tests/test_markdown_lint.py -v

# Full project test sweep (repo-level + module-level tests)
tests/run_tests.sh -v

# Full project test sweep without rebuilding
tests/run_tests.sh -v --skip-build

# Full project test sweep in containerized environment
docker run --rm \
  -v "$RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.3.1/rti_license.dat:ro" \
  medtech-test
```

## Choosing a Test Path

Use this quick guide to pick the right command:

| Goal | Preferred approach | Why |
| --- | --- | --- |
| Fast local iteration on one test/file | `pytest` directly | Fastest feedback loop and easiest targeted debugging |
| Validate only project-level tests under `tests/` | `pytest tests/ -v` | Runs just the root test suite defined in this folder |
| Validate end-to-end test coverage before merge (repo + modules) | `tests/run_tests.sh` | Runs root tests and each module's `tests/` suite in one command |
| Reproduce CI/container-specific behavior or dependency issues | Docker test image | Ensures clean, repeatable environment close to pipeline execution |

### When to Prefer `tests/run_tests.sh`

Prefer `tests/run_tests.sh` when you need confidence across the whole repository, not just root tests. In particular:

1. Before pushing or opening a PR, to catch module-level failures that `pytest tests/` does not execute.
2. After changing shared code used by multiple modules.
3. After build or environment changes where a full sweep is safer than targeted checks.

Use `--skip-build` if binaries are already up to date and you only want to rerun tests quickly.

### When to Prefer Explicit `pytest`

Prefer direct `pytest` commands during day-to-day development when you are focused on one area and want fast feedback:

1. Running a single test file/class/function while debugging.
2. Working only on repo-level tests under `tests/`.
3. Tight edit-test cycles where full project sweeps would be too slow.

### When to Prefer Docker Testing

Prefer the Docker path when environment parity matters more than speed:

1. Reproducing failures that do not occur on your host machine.
2. Verifying behavior with containerized dependencies/tooling.
3. Final validation for environments where local host differences may hide issues.

## Test Structure

| File | What it tests |
| --- | --- |
| `test_build.py` | CMake configure & build succeed; Module 01 C++ binaries exist |
| `test_markdown_lint.py` | All non-ignored `.md` files pass `.markdownlint.json` rules |
