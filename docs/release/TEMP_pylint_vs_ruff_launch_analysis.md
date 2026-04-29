# Temporary Analysis: `pylint launch.py` vs current CI Ruff checks

Date: 2026-04-22

## Scope
This document explains, line-by-line, why each concern raised by `pylint launch.py` is not flagged (or not considered a concern) by the current Ruff configuration used in CI.

Relevant config:
- CI runs `ruff check .` and `ruff format --check .`.
- Ruff config is in `pyproject.toml`.
- Enabled Ruff lint families are: `E`, `F`, `W`, `I`, `UP`.
- `line-length = 120`.
- `launch.py` has per-file ignore: `E402`.

## Pylint findings and Ruff comparison

### 1) `C0301 line-too-long`
- Pylint lines: `launch.py:57` and `launch.py:71`
- Pylint details: 117/100 and 109/100.
- Why Ruff does not flag:
  - Ruff line-length (`E501`) is set to 120, so these lines are under threshold.
- Conclusion: Same check category, different configured threshold.

### 2) `E0401 import-error`
- Pylint line: `launch.py:32`
- Message: Unable to import `scripts`.
- Why Ruff does not flag:
  - Current Ruff selection (`E/F/W/I/UP`) does not include a pylint-style import-resolution error equivalent to `E0401` in this setup.
  - Ruff focuses on enabled rule families and does not surface this as configured.
- Conclusion: Pylint catches environment/import-path resolution here; current Ruff config does not.

### 3) `C0413 wrong-import-position`
- Pylint line: `launch.py:32`
- Why Ruff does not flag:
  - Ruff equivalent is `E402` (module import not at top).
  - `launch.py` explicitly ignores `E402` in `pyproject.toml`.
  - Running Ruff in isolated mode (`--isolated --select E402`) does flag this line.
- Conclusion: Ruff can detect it, but repo config intentionally suppresses it for `launch.py`.

### 4) `W1514 unspecified-encoding`
- Pylint lines: `launch.py:34` and `launch.py:88`
- Why Ruff does not flag in CI:
  - Ruff equivalent is `PLW1514` (Pylint-derived rule family).
  - `PL*` rules are not enabled by current `select` list.
  - In this Ruff version, `PLW1514` is preview-gated and requires `--preview`.
- Conclusion: Detectable by Ruff with additional rule selection (and preview), but not active in CI.

### 5) `W0621 redefined-outer-name`
- Pylint line: `launch.py:88`
- Why Ruff does not flag:
  - The direct code `PLW0621` is not recognized in the installed Ruff version used locally for this analysis.
- Conclusion: No direct recognized Ruff rule code available for this exact pylint message in current tool version.

### 6) `W0718 broad-exception-caught`
- Pylint line: `launch.py:91`
- Why Ruff does not flag in CI:
  - Ruff equivalent is `BLE001`.
  - `BLE` rules are not enabled in current `select`.
- Conclusion: Ruff can report this when `BLE` is selected; CI does not currently enable it.

### 7) `W0613 unused-argument`
- Pylint line: `launch.py:77`
- Why Ruff does not flag in CI:
  - Ruff equivalent is `ARG001`.
  - `ARG` rules are not enabled in current `select`.
- Conclusion: Ruff can report this when `ARG` is selected; CI does not currently enable it.

### 8) `C0116 missing-function-docstring`
- Pylint line: `launch.py:100`
- Why Ruff does not flag in CI:
  - Ruff equivalent is `D103` (pydocstyle family).
  - `D` rules are not enabled in current `select`.
- Conclusion: Ruff can report this when `D` rules are selected; CI does not currently enable docstring enforcement.

## Summary
Current CI is intentionally narrow and performance-focused (`E/F/W/I/UP` + formatting). Most differences with `pylint launch.py` come from one of:
1. Different thresholds (line length 120 vs pylint default 100).
2. Explicit ignore (`E402` for `launch.py`).
3. Rule families not enabled in Ruff (`PL`, `BLE`, `ARG`, `D`).
4. Pylint-specific import-resolution behavior (`E0401`).
