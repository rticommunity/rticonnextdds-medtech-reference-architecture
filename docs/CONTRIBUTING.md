# Contributing & Maintainer Workflow

This document covers the developer environment setup, day-to-day workflow,
quality gates, and maintenance procedures for the RTI MedTech Reference
Architecture. It is intended for any maintainer — RTI staff or external
contributors working from a fork.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [One-Time Environment Setup](#one-time-environment-setup)
- [Day-to-Day Workflow](#day-to-day-workflow)
- [What Runs Automatically](#what-runs-automatically)
- [Testing CI Locally with act (Optional)](#testing-ci-locally-with-act-optional)
- [Running Tests Locally](#running-tests-locally)
- [Branch and PR Conventions](#branch-and-pr-conventions)
- [Upgrading Ruff](#upgrading-ruff)

---

## Prerequisites

| Tool | Minimum Version | Notes |
| --- | --- | --- |
| Python | 3.10 | Use `python3.10` explicitly if multiple versions are installed |
| RTI Connext DDS | 7.7.x | See [README.md](../README.md) for install instructions |
| CMake | 3.17 | Required for C++ module builds |
| Docker | Any recent | Optional; required only for containerised test runs |

---

## One-Time Environment Setup

Run these once after cloning the repository.

```bash
# 1. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install all development dependencies
pip install -r requirements-dev.txt

# 3. Register git hooks so pre-commit runs automatically on every commit
pre-commit install
```

After step 3, quality checks run automatically on every `git commit` — you do
not need to invoke them manually.

---

## Day-to-Day Workflow

### Manual checks (run anytime)

```bash
# Python lint
ruff check

# Python formatting
ruff format

# Spelling
codespell

# Markdown lint/format
rumdl check
rumdl fmt

# Run all tests from project root (repo-level + modules)
pytest

# Run project-level tests only
pytest tests/

# Run a specific module
pytest modules/01-operating-room/tests/
```

### On every `git commit` (automatic)

After `pre-commit install`, the following hooks run on your staged files before
the commit is recorded:

| Hook | What it checks / fixes |
| --- | --- |
| `ruff-check` | Python lint — auto-fixes where possible |
| `ruff-format` | Python formatting — auto-reformats files |
| `trailing-whitespace` | Removes trailing whitespace from all text files |
| `end-of-file-fixer` | Ensures files end with a single newline |
| `check-yaml` | Validates YAML syntax (excludes `.clang-format`) |
| `check-json` | Validates JSON syntax |
| `check-toml` | Validates TOML syntax |
| `check-xml` | Validates XML syntax |
| `check-merge-conflict` | Blocks committed merge-conflict markers |
| `check-case-conflict` | Blocks names that collide on case-insensitive filesystems |
| `check-illegal-windows-names` | Blocks filenames invalid on Windows |
| `check-executables-have-shebangs` / `check-shebang-scripts-are-executable` | Keep executable bits and shebangs consistent |
| `detect-private-key` | Blocks accidentally committed private keys |
| `requirements-txt-fixer` | Normalizes `requirements*.txt` ordering |
| `mixed-line-ending` | Enforces LF (CRLF for batch files) |
| `name-tests-test` | Enforces `test_*` naming for pytest files |
| `check-added-large-files` | Blocks files larger than 500 KB |
| `codespell` | Checks spelling for source and docs using `pyproject.toml` settings |
| `clang-format` | Reformats C/C++ source files |
| `rumdl` / `rumdl-fmt` | Markdown lint + auto-fix and formatting pass |

See `.pre-commit-config.yaml` for the authoritative hook list and configuration.

If a hook **modifies files**, the commit is aborted. Re-stage the modified
files and commit again:

```bash
git add -A
git commit -m "your message"
```

If a hook **fails without auto-fixing**, resolve the issue manually before
committing. In exceptional circumstances you can bypass hooks with
`git commit --no-verify`, but this should not be used routinely.

---

## What Runs Automatically

| Event | Triggered by | What runs |
| --- | --- | --- |
| `git commit` | git hook (local) | All pre-commit hooks (lint, format, whitespace, clang-format, markdown via rumdl) |
| `git push` / open PR | GitHub Actions | Full CI pipeline (see below) |
| PR merge to `main` | Blocked until CI passes | — |

### CI pipeline (`.github/workflows/ci.yml`)

The pipeline has two jobs; `test` runs only after `lint` passes:

| Job | What it does |
| --- | --- |
| `lint` (Lint & Format) | Runs **all** pre-commit hooks across the repo (`pre-commit/action` with `--all-files`) — the same ruff, ruff-format, codespell, clang-format, rumdl, and hygiene hooks you run locally. |
| `test` (Build & Test) | Installs Connext (apt) and Python deps, builds all C++ modules with `python build.py`, generates the system and Module 04 security artifacts, starts Xvfb, then runs the full suite from the repo root with `python -m pytest -v -m "not build_pipeline"` and uploads `results.xml`. |

Because the `lint` job runs `pre-commit` itself, CI and your local hooks execute
the **exact same** hook versions (pinned in `.pre-commit-config.yaml`). A clean
local commit will therefore not produce lint failures in CI. See
[Upgrading Ruff](#upgrading-ruff) for how the Ruff pin is managed.

## Testing CI Locally with act (Optional)

If you want to debug the GitHub Actions workflow itself, you can run the CI
jobs locally with [`act`](https://github.com/nektos/act).

```bash
# Ensure RTI_LICENSE_FILE points to your local rti_license.dat
export RTI_LICENSE_FILE=/path/to/rti_license.dat

# Run the "test" job from .github/workflows/ci.yml
act push -j test \
    --secret RTI_LICENSE_FILE="$(base64 -w0 "$RTI_LICENSE_FILE")" \
    --platform ubuntu-24.04=catthehacker/ubuntu:act-24.04
```

> **Note:** `act` is great for fast iteration, but behavior can differ slightly
> from GitHub-hosted runners (container image, networking, and environment
> details). Always rely on GitHub Actions as the final source of truth.

---

## Running Tests Locally

### Option 1 — direct pytest

```bash
# All tests from project root (repo-level + modules)
pytest -v

# Project-level tests only
pytest tests/ -v

# Single module
pytest modules/01-operating-room/tests/ -v
```

### Option 2 — Docker (closest to CI)

Requires `RTI_LICENSE_FILE` to point to your `rti_license.dat`:

```bash
export RTI_LICENSE_FILE=/path/to/rti_license.dat

# Build image and run all tests
docker compose -f tests/docker/docker-compose.yml run --rm --build test

# Run a specific test file
docker compose -f tests/docker/docker-compose.yml run --rm --build test \
    modules/01-operating-room/tests/test_types.py -v
```

> **Note:** With no arguments, the Docker test entrypoint runs `pytest` over the
> whole repo (it passes any arguments you supply straight through to pytest).
> It executes functional/behavioral tests. It does **not** run Ruff lint,
> rumdl markdown lint, or clang-format; those are enforced by pre-commit
> (locally) and the CI lint job (on push/PR).

---

## Branch and PR Conventions

Follow the branch strategy defined in
[docs/release/RELEASE_PLAN.md](release/RELEASE_PLAN.md).

In summary:

| Branch prefix | Purpose |
| --- | --- |
| `main` | Stable, release-ready. All releases are tagged here. |
| `develop` | Optional integration branch for parallel work. |
| `feat/*` | New features — branch from and merge back to `main`. |
| `bugfix/*` | Bug fixes — branch from and merge back to `main`. |
| `hotfix/*` | Urgent fixes for a released version. |
| `chore/*` | Maintenance work (dependency bumps, tooling, docs). |

### PR checklist

Before opening a PR, verify:

- [ ] `pre-commit run --all-files` passes cleanly
- [ ] `pytest tests/` passes locally
- [ ] `pytest -v` passes locally
- [ ] `CHANGELOG.md` updated if the change is user-visible
- [ ] No `# noqa` suppressions added without a documented justification

---

## Upgrading Ruff

The CI `lint` job runs `pre-commit`, so there is a **single** Ruff pin that
governs both local hooks and CI: the `astral-sh/ruff-pre-commit` revision in
`.pre-commit-config.yaml`. Bump that one pin to upgrade Ruff everywhere.

| File | Setting to change | When |
| --- | --- | --- |
| `.pre-commit-config.yaml` | `rev: v<new-version>` under `astral-sh/ruff-pre-commit` | Every Ruff bump (this is the authoritative pin used by CI). |
| `pyproject.toml` | `required-version = ">=<major.minor>"` | Only when raising the minimum supported version. |
| `requirements-dev.txt` | `ruff>=<major.minor>` | Only when raising the minimum supported version. |

The `pyproject.toml` and `requirements-dev.txt` bounds are lower bounds for
developers who run Ruff outside pre-commit; they do **not** need to change on
every Ruff bump unless the new version introduces a breaking change to the
configuration format.

### Procedure

```bash
# 1. Update the pin in .pre-commit-config.yaml
pre-commit autoupdate --freeze    # or manually set the rev

# 2. Run the full pre-commit suite to surface any new lint findings
pre-commit run --all-files

# 3. Fix any new violations introduced by the new Ruff version

# 4. Update the minimum version bounds only if appropriate
#    pyproject.toml:      required-version = ">=<new-major.minor>"
#    requirements-dev.txt: ruff>=<new-major.minor>

# 5. Commit everything together
git add .pre-commit-config.yaml pyproject.toml requirements-dev.txt
git commit -m "chore: bump Ruff to <new-version>"
```
