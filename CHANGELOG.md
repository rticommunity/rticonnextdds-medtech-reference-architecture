# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- macOS Dock icon support for C++ apps via Objective-C runtime (`MacOsDockIcon.h`)
- RTI logo window icon for all Python GUI apps (Arm, PatientMonitor, Threat apps)
- `system_arch/scripts/platform_setup.py` — shared utility for `NDDSHOME`
  resolution, architecture detection, OpenSSL discovery, and Connext library
  path setup
- `xml_setup.py` helpers in each module for resolving XML config paths and
  setting `NDDS_QOS_PROFILES` at runtime

### Changed

- Replaced all `.sh` and `.bat` scripts with cross-platform Python equivalents
  across all modules and `system_arch/security/`. Launch commands change from
  e.g. `./scripts/launch_all.sh` to `python3 scripts/launch_all.py`
- Security plugins are now optional in CMake: OpenSSL (including RTI-bundled)
  is auto-detected and `security_plugins` is only requested when available
- Simplified FQN constants in `Types.xml` — names are now pre-assembled
  (e.g. `MedicalDemoParticipantLibrary::dp/ArmController`) instead of
  requiring runtime string concatenation
- All C++ and Python apps updated to use the new FQN constants directly
- Replaced `rti_logo.ico` with `rti_logo.png` for cross-platform compatibility
- CMake links `-framework AppKit` on Apple targets for Dock icon support
- Ported `setup_security.sh` and `setup_threat_security.sh` to Python
- All C++ and Python applications now handle SIGINT/SIGTERM for graceful
  shutdown without warnings; launch scripts forward signals to child processes
- Security setup scripts suppress verbose OpenSSL output and print a summary
  of generated artifacts on completion

### Removed

- All `.sh` and `.bat` scripts (replaced by Python equivalents)
- `DdsUtils.hpp` (FQN logic moved into XML constants)
- Runtime FQN-mangling code from `DdsUtils.py` (both Module 01 and 04)

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
- CMake >= 3.11

---

### Pre-v1.0.0 History

The following milestones occurred during development prior to the adoption of
formal versioning:

| Date | Commit | Milestone |
|------|--------|-----------|
| 2024-09-24 | `b2ff6e4` | First commit — Modules 01 (Operating Room) and 02 (Record/Playback) with system architecture |
| 2024-10-15 | `d68d8a4` | Optimized C++ type registration |
| 2025-09-18 | `39aff1b` | Changed `patient_name` to `patient_id` for HIPAA compliance |
| 2025-10-27 | `81cb841` | Module 03 (Remote Teleoperation) added |
| 2025-11-25 | `bc15eee` | Fixed unsigned int types for measurement fields |
| 2025-11-25 | `964f40d` | Refactored naming conventions (demo → module), consolidated security under system_arch |
| 2025-11-26 | `b949a18` | Made launch scripts executable |
| 2025-11-26 | `d227e59` | Renovated GUIs merged (PR #2) |
