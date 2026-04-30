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
ruff check .

# Python formatting
ruff format .

# Spelling
codespell --toml pyproject.toml

# Markdown lint/format
rumdl check .
rumdl fmt .

# Run all tests from project root (repo-level + modules)
python -m pytest -v

# Run project-level tests only
python -m pytest tests/ -v

# Run a specific module
python -m pytest modules/01-operating-room/tests/ -v
```

### On every `git commit` (automatic)

After `pre-commit install`, the following hooks run on your staged files before
the commit is recorded:

| Hook | What it checks / fixes |
| --- | --- |
| `ruff` | Python lint — auto-fixes where possible |
| `ruff-format` | Python formatting — auto-reformats files |
| `trailing-whitespace` | Removes trailing whitespace from all text files |
| `end-of-file-fixer` | Ensures files end with a single newline |
| `check-yaml` | Validates YAML syntax |
| `check-xml` | Validates XML syntax |
| `check-added-large-files` | Blocks files larger than 500 KB |
| `codespell` | Checks spelling for source and docs using `pyproject.toml` settings |
| `clang-format` | Reformats C/C++ source files |
| `rumdl` | Markdown lint + auto-fix |
| `rumdl-fmt` | Markdown formatting pass |

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

| Job | What it does |
| --- | --- |
| Lint & Format | `ruff check .`, `ruff format --check .`, codespell, clang-format dry-run, markdown lint via `rvben/rumdl` action |
| Build | CMake configure + build all C++ modules |
| Project-level Tests | `pytest tests/` |
| Unit Tests | Fast Python type/script/QoS tests |
| DDS Communication Tests | Non-GUI DDS pub/sub tests |
| Integration Tests | Slow end-to-end demo flow tests |
| GUI Tests | Headless Qt application tests |
| Security Tests | DDS Security plugin tests |
| Module 02 Tests | Record/Playback module tests |
| Module 04 Tests | Security Threat module tests |

CI uses a pinned Ruff version (see [Upgrading Ruff](#upgrading-ruff)). If
pre-commit and CI share the same pin, a clean local commit will not produce
lint failures in CI.

---

## Running Tests Locally

### Option 1 — direct pytest

```bash
# All tests from project root (repo-level + modules)
python -m pytest -v

# Project-level tests only
python -m pytest tests/ -v

# Single module
python -m pytest modules/01-operating-room/tests/ -v
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

> **Note:** The Docker default command runs `python -m pytest -v` via the
> test entrypoint. It executes functional/behavioral tests. It does **not** run Ruff lint,
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
- [ ] `python -m pytest tests/` passes locally
- [ ] `python -m pytest -v` passes locally
- [ ] `CHANGELOG.md` updated if the change is user-visible
- [ ] No `# noqa` suppressions added without a documented justification

---

## Upgrading Ruff

Ruff is pinned in two places so that local pre-commit hooks and CI produce
identical results. When upgrading, update **both together**:

| File | Setting to change |
| --- | --- |
| `.github/workflows/ci.yml` | `pip install ruff==<new-version>` |
| `.pre-commit-config.yaml` | `rev: v<new-version>` under `astral-sh/ruff-pre-commit` |

`pyproject.toml` carries a minimum version (`required-version = ">=0.15"`) and
`requirements-dev.txt` carries a matching lower bound (`ruff>=0.15`). These do
**not** need to change on every Ruff bump unless the new version introduces a
breaking change to the configuration format.

### Procedure

```bash
# 1. Update the two pinned locations (ci.yml and .pre-commit-config.yaml)

# 2. Update your local pre-commit environment
pre-commit autoupdate --freeze    # or manually set the rev

# 3. Run the full pre-commit suite to surface any new lint findings
pre-commit run --all-files

# 4. Fix any new violations introduced by the new Ruff version

# 5. Update the minimum version bounds if appropriate
#    pyproject.toml:      required-version = ">=<new-major.minor>"
#    requirements-dev.txt: ruff>=<new-major.minor>

# 6. Commit everything together
git add .pre-commit-config.yaml .github/workflows/ci.yml pyproject.toml requirements-dev.txt
git commit -m "chore: bump Ruff to <new-version>"
```
