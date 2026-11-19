# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Added launch-time application variant selection, including an optional Xbox
  gamepad implementation for ArmController while keeping the simulated
  controller as the default.
- Replaced graphical-app presentation with a shared RTI Demo UI frontend for
  browser mode and optional embedded native-webview mode.
- Added a launch-time `--ui-mode` selector and an opt-in CMake build switch for
  native C++ webview support.
- Added arm readiness, observed telemetry, and parallel-jaw rate control:
  three additional operational topics.
- Added an articulated six-axis kinematic demo and original GLB using the pinned
  SDK's existing Scene3D renderer, without replacing the UI backend.
- Added the `DataFlowLibrary::Control` QoS profile for best-effort, volatile,
  depth-one arm/tool rates with diagnostic deadlines and finite writer lifespan.

### Changed

- Made browser showcase motion return to observed starting position/jaw gap,
  with explicit stop/manual-takeover and feedback-loss cancellation behavior.
  Separated its presentation from the Connext application code.
- Made threat publication independent of optional preview failures, reporting
  preview unavailability without disabling DDS injection.
- Updated the pinned Python/C++ UI SDK, restored original arm-material colors,
  and added persistent base-relative side/top camera views without changing the
  control frame or arm position. The SDK pin includes consumer-provided native
  app icon support for both Python and C++ launchers.
- Added a publication-driven blinking light to the Arm's compact reported
  telemetry section, clarified camera-reset feedback, and consistently grouped
  opposing Xbox controls.
- Clarified the Arm window's locally reported telemetry, removed its incoming
  telemetry freshness badge, and simplified/styled the scene's camera controls
  and normal-rendering node list.
- Switched all linear/angular TCP commands to the fixed base frame (+Z up),
  preserving TCP position during rotation and keeping jaw travel tool-local.
  Updated both controllers and the fixed-frame contract; earlier tool-frame
  command recordings/publishers are semantically incompatible.
- Adapted the Xbox layout to base X/Y stick motion, trigger up/down, right-stick
  base X/Y rotation, and bumper base Z rotation.
- Connected the rendered parallel jaws to a gripper palm and aligned their
  contact faces with the TCP and observed jaw gap.
- Made shared GUI layouts adapt to narrower windows, including controller
  controls, header badges, feedback, and the exfiltrator's vitals panels.
- Display on-change arm readiness as last known, independently of periodic
  telemetry freshness, and preserve device `ERROR` in the Orchestrator display.
- Separated Connext adapters, simple application behavior, and presentation
  state; Python graphical apps now use asyncio, while C++ apps hand UI intents
  to a DDS-owning control thread.
- Standardized arm-controller and threat-injector commands on
  `t/robot/arm/control`, removing the legacy per-joint control path from DDS types,
  applications, security configuration, recording/replay, and routing.
- Breaking system-contract migration: renamed `system_arch/` to `system/`,
  replaced authored XML types with modular `MedTech.idl`, and centralized
  generated C++/Python/XML artifacts in the architecture-specific build tree.
- Replaced per-axis direction samples and per-message planar steps with complete
  base-frame TCP velocity and signed jaw-gap rates. A periodic simulation reads
  valid DDS-cached commands; lifespan expiry holds current pose/gap without a
  duplicate application timeout. Controllers display actual DDS feedback.
- Aligned all operational topic names with device/robot/patient namespaces,
  including service routes, recording/replay, and least-privilege permissions.
  Existing recordings must be recreated; no legacy wire/topic bridge is provided.
- Raised the project Python minimum to 3.11 for RTI Demo UI and pinned the
  Python/C++ SDK dependency to an immutable commit.
- Added RTI copyright and license notices to comment-capable source and
  configuration files, using per-file Git history to set the year or year
  range.

### Fixed

- Preserved Orchestrator device-selection and command buttons during live
  status updates so pointer clicks and keyboard activation are not lost.
- Preserved the log toggle's text hit target during live updates so clicks on
  its label work as reliably as clicks on its padding in native WebKit windows.
- Updated security controls and gamepad readouts in place during live updates.
  Frequency edits and keyboard focus survive refreshes; held arm jogs continue
  through unrelated demo-button changes and stop when their controls are disabled.
- Kept activity rows and scroll position stable while reading earlier events,
  following new events automatically only when already at the bottom.
- Preserved Scene3D fallback node-list text targets so native WebKit selection
  works on labels as well as row padding.

### Removed

- Removed the maintained System Designer project and its recommended-use workflow.
- Removed the GTK/gtkmm and Qt/PySide6 frontends, Glade layouts, and
  pyqtgraph dependency from the graphical applications.

## [1.3.1] - 2026-09-16

### Added

- Added a least-privilege `SecureSystemObserver` QoS configuration and security
  identity for observing secured domains through Connext Studio Spy.
- Added `--generate-resolved-qos` support for generating QoS files with absolute
  security-artifact paths.
- Added automatic GitHub Release publication after successful CI for pushed,
  SemVer tags, including pre-release handling and generated notes.

### Changed

- Improved security artifact generation output with generated and skipped
  counts and clearer warnings for existing artifacts.
- Updated SecureLogReader permissions to support all partitions for Connext
  Studio integration.
- Updated release and contributor guidance for the automated, tag-driven
  release process.

### Fixed

- Updated `QosProvider` construction for the Connext DDS 7.7 Python API.
- Eliminated pytest fixture warnings under Python 3.14.

### Security

- Strengthened LAN, WAN, and threat-example governance with RTPS origin
  authentication and pre-authentication PSK encryption.
- Added topic-level metadata encryption for `t/patient/vitals` and `t/MotorControl`,
  with encryption applied to all topics over WAN connections.
- Restricted the external System Observer to read-only access across topics
  and partitions.

### Removed

- Removed remaining Connext DDS 7.3 compatibility workarounds and the
  `test-connext-73` Docker Compose service.

## [1.3.0] - 2026-06-02

### Added

- Added `docs/CONTRIBUTING.md` guidance for maintainers.
- Root-level pytest marker `build_pipeline` in `pyproject.toml` for
  build/configure pipeline tests, enabling marker-based CI selection.
- Shared pytest support modules for module test suites:
  `module01_test_support.py`, `module02_test_support.py`, and
  `module04_test_support.py` to separate importable helpers from
  pytest-only fixture wiring.

### Changed

- Migrated the project baseline from RTI Connext DDS 7.3.1 to 7.7.0.
  - Updated C++ type-generation and source integration for IDL4 CPP.
  - Bumped required Python version to 3.10+.
  - Explicitly disabled Monitoring2.0 when using security.
- CI runner targeting and setup refined around `ubuntu-24.04`.
- Test execution model unified around root-level `python -m pytest`
  across local runs, Docker test entrypoint, and contributor docs.
- Module test imports refactored to remove direct imports from
  `conftest.py`; helper imports now resolve from dedicated support modules.
- Project test naming clarified and aligned:
  `tests/test_build.py` -> `tests/test_project_build_pipeline.py`,
  `modules/01-operating-room/tests/test_build.py` ->
  `test_build_and_types.py`, and module XML test filenames normalized.
- Lint and quality tooling policy tightened through migration to
  rumdl-based Markdown lint/format flows.
- CI workflow (`.github/workflows/ci.yml`) simplified to lint + unified
  root-level test execution, with marker-based exclusion of build-pipeline
  tests and concurrency cancellation.
- Ignore file hygiene and consistency improved across `.gitignore`,
  `.dockerignore`, and nested security `.gitignore` files.

### Fixed

- Improved DDS test-process lifecycle handling to reduce orphaned
  processes and cross-suite interference.
- Module 02 orphaned Recording/Replay Service processes are now
  explicitly reaped during teardown when tied to module test configs,
  preventing cross-suite DDS endpoint leakage.
- Module 04 secure exfiltrator tests now validate launch configuration
  assumptions for secure OR and unsecured threat probe setup before
  asserting expected security behavior.

### Removed

- Legacy `tests/run_tests.sh` wrapper script in favor of direct,
  root-level pytest invocation.
- Obsolete `.markdownlint.json` after migration to rumdl-based Markdown
  checks.

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
- `tests/test_security_status.py` — validates `system/security/` certificate
  chain via `setup_security.py --status`; fails on any EXPIRED artifact
- `modules/04-security-threat/tests/test_threat_security_status.py` — same
  status check for the Module 04 threat security tree via `setup_threat_security.py --status`
- Node.js 18 LTS (via NodeSource) to the Docker test image for `markdownlint-cli`
  compatibility; replaces the outdated system `nodejs` package
- `tests/README.md` guidance on when to use root-level `pytest` and the
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
  directories under both `system/security/` and
  `modules/04-security-threat/security/`
- Three-tier CA hierarchy: TrustedRootCa, TrustedIdentityCa,
  TrustedPermissionsCa
- Domain-scoped governance and permissions for OperationalDomain and
  TeleopWanDomain (system) and ThreatDomain (module 04)
- Per-participant identity configs organized by module
  (operating-room, record-playback, remote-teleop, security-threat)
- `.markdownlint.json` for consistent Markdown linting across contributors
- macOS Dock icon support for C++ apps via Objective-C runtime (`MacOsDockIcon.h`)
- RTI logo window icon for all Python GUI apps (Arm, PatientMonitor, Threat apps)

### Changed

- Replaced all per-module `scripts/` directories with the unified
  top-level `build.py` + `launch.py` orchestration
- Restructured `system/security/` from flat `identities/` + `xml/`
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
- `system/scripts/platform_setup.py` — moved to
  `resource/python/scripts/platform_setup.py`
- `resource/cmake/rticonnextdds-cmake-utils` submodule — replaced by
  CMake FetchContent
- Flat security layouts: `system/security/identities/`,
  `system/security/xml/`, and module 04 equivalents
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
- `system/qos/Qos.xml`: removed volatile durability override from
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
- CMake >= 3.18

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
| 2025-11-25 | `964f40d` | Refactored naming conventions (demo → module), consolidated security under system |
| 2025-11-26 | `b949a18` | Made launch scripts executable |
| 2025-11-26 | `d227e59` | Renovated GUIs merged (PR #2) |
