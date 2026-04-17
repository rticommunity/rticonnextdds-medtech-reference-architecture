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
```

## Test Structure

| File | What it tests |
| --- | --- |
| `test_build.py` | CMake configure & build succeed; Module 01 C++ binaries exist |
| `test_markdown_lint.py` | All non-ignored `.md` files pass `.markdownlint.json` rules |
