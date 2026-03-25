# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
