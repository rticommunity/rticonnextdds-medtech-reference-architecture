# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.2.1] - 2026-04-20

### Added

- Docker-based test infrastructure under `tests/docker/`: multi-stage
  `Dockerfile`, `docker-compose.yml`, and `medtech-build`/`medtech-test`
  images for reproducible build+test runs with runtime license mounting
- `tests/test_markdown_lint.py` + `.markdownlint.json` enforcement for
  repository markdown quality checks in local and CI workflows
- `tests/test_config_parsing.py` — module.json contract validation (required
  field shapes, type checks, `${args:X}` cross-reference) and negative
  `load_module_config` parsing tests (missing flags, unknown placeholders,
  undefined args references)
- `tests/test_security_status.py` — validates `system_arch/security/` certificate
  chain via `setup_security.py --status`; fails on any EXPIRED artifact
- `modules/04-security-threat/tests/test_threat_security_status.py` — same
  status check for the Module 04 threat security tree via `setup_threat_security.py --status`
- Node.js 18 LTS (via NodeSource) to the Docker test image for `markdownlint-cli`
  compatibility; replaces the outdated system `nodejs` package
- `tests/README.md` guidance on when to use `pytest`, `run_tests.sh`, or the
  Docker test image
- **Module 01 pytest test suite** (`modules/01-operating-room/tests/`) with
  build, launch, DDS communication, and end-to-end demo-flow tests; includes
  shared fixtures, custom markers (`gui`, `secure`, `slow`), and pytest
  configuration
- **Module 02 pytest test suite** (`modules/02-record-playback/tests/`) with
  Recording Service and
  Replay Service integration tests, plus XML configuration validation
- **Module 04 pytest test suite** (`modules/04-security-threat/tests/`) with threat injector and
  exfiltrator tests across all four attack modes (Unsecure, Rogue CA,
  Forged Permissions, Expired Certificate), plus XML configuration validation
- **GitHub Actions CI pipeline** (`.github/workflows/ci.yml`) with 10 jobs:
  lint, C++ build, Module 01 unit/integration/secure/GUI tests, Module 02
  tests, Module 04 tests, and artifact upload — runs on every push and PRs
  to main/develop
- `pyproject.toml` (root) with ruff linter/formatter configuration
- `requirements-dev.txt` with development/testing dependencies
- `.pre-commit-config.yaml` for ruff and clang-format hooks
- Per-module `pyproject.toml` files with pytest configuration
- DDS Security and QoS infrastructure for the test participant (`Test` QoS
  profile, identity, and permissions)
- 2026 copyright headers on all new test files

## [1.2.0] - 2026-04-14

### Added

- Centralized top-level `build.py` and `launch.py` replacing per-module
  build/launch scripts — usage: `python3 launch.py <module> [apps] [-s]`
- `resource/config/scenarios.json` for declarative scenario definitions across
  all modules
- `requirements.txt` for Python dependencies
- Top-level `CMakeLists.txt` for unified CMake build orchestration
- `resource/python/scripts/` package with `module_runner.py` and
  `platform_setup.py` (NDDSHOME resolution, architecture detection,
  OpenSSL discovery, Connext library path setup)
- `module.json` descriptors for all four modules
- Jinja2-based security artifact generation via `dds_security.py` and
  `security_tree.py` with templates (`ca.cnf.j2`, `governance.xml.j2`,
  `identity.cnf.j2`, `permissions.xml.j2`)
- Hierarchical security tree: `ca/`, `domain_scope/`, and `identity/`
  directories under both `system_arch/security/` and
  `modules/04-security-threat/security/`
- Three-tier CA hierarchy: TrustedRootCa, TrustedIdentityCa,
  TrustedPermissionsCa
- Domain-scoped governance and permissions for OperationalDomain and
  TeleopWanDomain (system_arch) and ThreatDomain (module 04)
- Per-participant identity configs organized by module
  (operating-room, record-playback, remote-teleop, security-threat)
- `.markdownlint.json` for consistent Markdown linting across contributors
- macOS Dock icon support for C++ apps via Objective-C runtime (`MacOsDockIcon.h`)
- RTI logo window icon for all Python GUI apps (Arm, PatientMonitor, Threat apps)

### Changed

- Replaced all per-module `scripts/` directories with the unified
  top-level `build.py` + `launch.py` orchestration
- Restructured `system_arch/security/` from flat `identities/` + `xml/`
  layout to hierarchical `ca/` + `domain_scope/` + `identity/` tree
- Restructured `modules/04-security-threat/security/` from flat layout
  (`expired/`, `forged_perms/`, `identities/`, `rogue_ca/`, `xml/`) to
  hierarchical `ca/` + `domain_scope/` + `identity/` tree
- Security setup scripts (`setup_security.py`, `setup_threat_security.py`)
  rewritten to use Jinja2 templates and the new tree structure
- QoS profiles updated with new security artifact paths
  (`SecureAppsQos.xml`, `NonSecureAppsQos.xml`, `ThreatQos.xml`)
- Remote teleoperation routing service configs updated for new security
  paths (`CdsConfigCloud.xml`, `RsConfigActive.xml`, `RsConfigCloud.xml`,
  `RsConfigPassive.xml`)
- Converted `rticonnextdds-cmake-utils` from git submodule to CMake
  `FetchContent` dependency
- Comprehensive documentation refresh across all module READMEs,
  scenario guides, and system architecture docs
- Python 3.9 compatibility across `build.py`, `launch.py`,
  `module_runner.py`, `platform_setup.py`, `dds_security.py`,
  `security_tree.py`, `setup_security.py`, and
  `setup_threat_security.py` — required for macOS default Python

### Removed

- Per-module `scripts/` directories (modules 01, 03, 04) — replaced by
  centralized `build.py` + `launch.py`
- `system_arch/scripts/platform_setup.py` — moved to
  `resource/python/scripts/platform_setup.py`
- `resource/cmake/rticonnextdds-cmake-utils` submodule — replaced by
  CMake FetchContent
- Flat security layouts: `system_arch/security/identities/`,
  `system_arch/security/xml/`, and module 04 equivalents
  (`expired/`, `forged_perms/`, `identities/`, `rogue_ca/`, `xml/`)

## [1.1.0] - 2026-03-27

### Added

- **Module 04 — Security Threat Demonstration**: Two Python/PySide6 GUI
  applications (Threat Injector and Threat Exfiltrator) that simulate
  real-world DDS security attack scenarios (Rogue CA, Forged Permissions,
  Expired Certificate) against the operating room bus
- Module 04 security infrastructure: `setup_threat_security.py` script,
  OpenSSL configs, XML governance and permissions templates for rogue CA,
  forged permissions, and expired certificate attack modes
- Module 04 DDS configuration: `ThreatParticipantLibrary.xml` and
  `ThreatQos.xml` with partition-scoped threat participants
- Module 04 launch and kill scripts (`launch_injector.py`,
  `launch_exfiltrator.py`, `kill_all.py`)
- Module 04 local `DdsUtils.py` utility for participant and security
  configuration
- `.gitignore` for Module 04 security directory to exclude generated
  certificates, keys, and OpenSSL CA database files

### Changed

- **Module 01 — PyQt5 → PySide6 migration**: Arm.py and PatientMonitor.py
  ported from PyQt5 to PySide6 (updated imports, enum-style Qt constants,
  `Signal` instead of `pyqtSignal`, `app.exec()` instead of `app.exec_()`)
- Module 01 `CMakeLists.txt`: replaced manual `execute_process` codegen call
  with proper `connextdds_rtiddsgen_run` targets for Python type generation
  (both `Types.xml` and `builtin_logging_type.idl`); added `refArchTypesPy`
  custom target
- Module 01 `README.md`: updated Python dependency references from PyQt5 to
  PySide6
- `system_arch/qos/Qos.xml`: removed volatile durability override from
  secure-log DataReader QoS profile
- Root `.gitignore`: added patterns for `builtin_logging_type.py` and
  `*_timestamp.cmake` generated files
- Updated `rticonnextdds-cmake-utils` submodule to latest commit

## [1.0.0] - 2026-03-25

Initial stable release of the RTI MedTech Reference Architecture.

### Added

- **Module 01 — Operating Room**: Orchestrator (C++), PatientSensor (C++),
  ArmController (C++), PatientMonitor (Python/PySide6), and Arm (Python/PySide6)
  applications demonstrating a connected surgical environment
- **Module 02 — Record and Playback**: Recording Service and Replay Service
  configurations for capturing and replaying DDS data from the operating room
- **Module 03 — Remote Teleoperation**: Routing Service and Cloud Discovery
  Service configurations supporting three WAN communication scenarios
  (direct, cloud-relayed, and cloud-brokered)
- **System Architecture**: Shared Types.xml, QoS profiles (secure and
  non-secure), XML Application Creation (DomainLibrary, ParticipantLibrary),
  and DDS security infrastructure (certificates, governance, permissions)
- Renovated GUI for PatientMonitor and ArmController with real-time waveform
  rendering, arc gauges, and security-threat status indicators
- Orchestrator GUI with device status panels and unsecure/security-threat
  indicators
- NAT type checker utility for WAN scenario planning
- Cross-platform launch scripts (bash and batch) for all modules
- Security setup scripts for generating certificates and signing governance
  and permissions files

### Dependencies

- RTI Connext DDS 7.3.0
- RTI Code Generator (rtiddsgen) 4.3.0
- CMake >= 3.17

---

### Pre-v1.0.0 History

The following milestones occurred during development prior to the adoption of
formal versioning:

| Date | Commit | Milestone |
| --- | --- | --- |
| 2024-09-24 | `b2ff6e4` | First commit — Modules 01 (Operating Room) and 02 (Record/Playback) with system architecture |
| 2024-10-15 | `d68d8a4` | Optimized C++ type registration |
| 2025-09-18 | `39aff1b` | Changed `patient_name` to `patient_id` for HIPAA compliance |
| 2025-10-27 | `81cb841` | Module 03 (Remote Teleoperation) added |
| 2025-11-25 | `bc15eee` | Fixed unsigned int types for measurement fields |
| 2025-11-25 | `964f40d` | Refactored naming conventions (demo → module), consolidated security under system_arch |
| 2025-11-26 | `b949a18` | Made launch scripts executable |
| 2025-11-26 | `d227e59` | Renovated GUIs merged (PR #2) |
