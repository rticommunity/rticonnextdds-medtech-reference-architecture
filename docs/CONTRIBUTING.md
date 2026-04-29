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
- [Markdown Tooling Roadmap](#markdown-tooling-roadmap)

---

## Prerequisites

| Tool | Minimum Version | Notes |
| --- | --- | --- |
| Python | 3.9 | Use `python3.9` explicitly if multiple versions are installed |
| Node.js | 18 | Required for `markdownlint-cli` in CI |
| RTI Connext DDS | 7.3.1 | See [README.md](../README.md) for install instructions |
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

# Run all project test suites
tests/run_tests.sh -v

# Run project or module-level tests
python -m pytest tests/
python -m pytest modules/01-operating-room/tests/
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
| `markdownlint-cli2` | Lint all `.md` files against `.markdownlint.json` |

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
| `git commit` | git hook (local) | All pre-commit hooks (lint, format, whitespace, clang-format, markdown) |
| `git push` / open PR | GitHub Actions | Full CI pipeline (see below) |
| PR merge to `main` | Blocked until CI passes | — |

### CI pipeline (`.github/workflows/ci.yml`)

| Job | What it does |
| --- | --- |
| Lint & Format | `ruff check .`, `ruff format --check .`, clang-format dry-run, markdownlint |
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
# Project-level tests only
python -m pytest tests/ -v

# Single module
cd modules/01-operating-room
python -m pytest tests/ -v

# All modules via helper script
tests/run_tests.sh -v
```

### Option 2 — Docker (closest to CI)

Requires `RTI_LICENSE_FILE` to point to your `rti_license.dat`:

```bash
export RTI_LICENSE_FILE=/path/to/rti_license.dat

# Build image and run all tests
docker compose -f tests/docker/docker-compose.yml run --rm --build test

# Run a specific test file
docker compose -f tests/docker/docker-compose.yml run --rm --build test \
    python -m pytest modules/01-operating-room/tests/test_types.py -v
```

> **Note:** The Docker default command runs `tests/run_tests.sh`, which
> executes functional/behavioral tests. It does **not** run Ruff lint or
> clang-format; those are enforced by pre-commit (locally) and the CI lint
> job (on push/PR).

---

## Branch and PR Conventions

Follow the branch strategy defined in
[docs/release/RELEASE_PLAN.md](release/RELEASE_PLAN.md#branch-strategy).

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
- [ ] Relevant module tests pass (`tests/run_tests.sh -v`)
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

---

## Markdown Tooling Roadmap

The active, blocking markdown gate remains `markdownlint-cli2` for now.

If maintainers decide to migrate to `rumdl` later, use this low-risk path:

1. Add `rumdl` to development dependencies and pin its version in CI.
2. Run `rumdl` in CI as advisory-only (non-blocking) for at least 1-2 weeks.
3. Compare findings between `markdownlint-cli2` and `rumdl` and resolve major rule gaps.
4. Add stable `rumdl` config under `pyproject.toml`.
5. Switch pre-commit and CI blocking gates from `markdownlint-cli2` to `rumdl` in one commit.
6. Update `tests/test_markdown_lint.py` to call the selected markdown tool and remove the old one.

Acceptance criteria for migration:

- No increase in markdown false positives in active docs.
- Equivalent or better rule coverage for heading/list/link hygiene.
- Consistent behavior in local runs, Docker, and CI.
