# Release Plan

This document defines the versioning strategy, release process, and maintenance
guidelines for the **RTI MedTech Reference Architecture** project.

---

## Table of Contents

- [Versioning Scheme](#versioning-scheme)
- [What Warrants a Version Change](#what-warrants-a-version-change)
- [Version Increment Rules](#version-increment-rules)
- [What Does NOT Warrant a New Release](#what-does-not-warrant-a-new-release)
- [Relationship Between Version and Release](#relationship-between-version-and-release)
- [Release Process](#release-process)
- [Changelog Management](#changelog-management)
- [Branch Strategy](#branch-strategy)
- [Dependency Versioning](#dependency-versioning)
- [Pre-release and Release Candidate Policy](#pre-release-and-release-candidate-policy)
- [Deprecation Policy](#deprecation-policy)
- [Support and Maintenance Policy](#support-and-maintenance-policy)

---

## Versioning Scheme

This project follows [Semantic Versioning 2.0.0](https://semver.org/) (SemVer):

```text
MAJOR.MINOR.PATCH
```

| Component | Meaning |
| --------- | -------------------------------------------------------------- |
| **MAJOR** | Incompatible changes that break existing usage or integration |
| **MINOR** | New functionality added in a backward-compatible manner |
| **PATCH** | Backward-compatible bug fixes, corrections, and small updates |

The initial release of this project is **v1.0.0** (Modules 01–03). Prior to that,
development versions may use **v0.x.y** to signal that the API and architecture
are not yet stable.

---

## What Warrants a Version Change

A new version is warranted when changes are **functional, structural, or
behavioral** — meaning they affect how the software is built, run, integrated
with, or understood by users and downstream consumers.

### Examples that warrant a version change

| Change | Version Impact |
| --- | --- |
| New module added (e.g., `04-security-threat/`) | MINOR |
| Breaking change to DDS topic types in `Types.xml` | MAJOR |
| QoS profile restructured in a non-backward-compatible way | MAJOR |
| Bug fix in `PatientSensor.cxx` that corrects data publishing | PATCH |
| New QoS profile added (existing profiles unchanged) | MINOR |
| Security configuration updated to fix a vulnerability | PATCH |
| Upgrade from RTI Connext DDS 7.3.0 to 8.0.0 | MAJOR |
| New launch script for an existing module | MINOR |
| Fix to CMakeLists.txt that resolves a build failure | PATCH |
| Removal of a deprecated module or feature | MAJOR |

---

## Version Increment Rules

### MAJOR version (X.0.0) — Breaking Changes

Increment MAJOR when changes are **incompatible** with previous versions. Any
consumer or integrator of this reference architecture would need to modify their
setup, code, or configuration to accommodate the change.

**Increment MAJOR when:**

- DDS type definitions (`Types.xml`) change in a way that breaks existing
  subscribers or publishers (e.g., removing a field, renaming a topic, changing a
  field type)
- QoS profiles are renamed, removed, or restructured such that existing
  participant configurations would fail
- A module's public interface changes (e.g., topic names, domain IDs, command
  structure)
- A required dependency version changes with breaking API differences (e.g.,
  RTI Connext DDS major version upgrade)
- XML Application Creation files (`ParticipantLibrary.xml`,
  `DomainLibrary.xml`) are restructured in incompatible ways

**Examples:**

```text
v1.0.0 → v2.0.0
  - Renamed topic "PatientData" to "PatientVitals" in Types.xml
  - Removed deprecated Module 01 launch scripts
  - Upgraded minimum Connext DDS requirement from 7.x to 8.x
```

### MINOR version (x.Y.0) — New Features, Backward-Compatible

Increment MINOR when new functionality is added without breaking existing
behavior. Everything that worked before continues to work.

**Increment MINOR when:**

- A new module is added (e.g., `04-security-threat/`)
- New DDS types or topics are added (existing types unchanged)
- New QoS profiles are added (existing profiles unchanged)
- New scripts, tools, or UI components are added
- New configuration options are introduced with sensible defaults
- New documentation for a new feature or module is added

**Examples:**

```markdown
v1.0.0 → v1.1.0
  - Added Module 04: Security Threat Demonstration
  - Added new QoS profile "HighThroughputStream" to Qos.xml
```

### PATCH version (x.y.Z) — Bug Fixes, Corrections

Increment PATCH when fixing bugs or making small corrections that don't add new
features or break compatibility.

**Increment PATCH when:**

- A bug in application logic is fixed (e.g., incorrect sensor data calculation)
- A build issue is resolved (e.g., CMake configuration fix)
- A typo in configuration that caused runtime errors is corrected
- Security certificates or security configuration are updated to fix a
  vulnerability
- A script bug is fixed (e.g., incorrect path, missing environment variable)
- Test fixes or test additions for existing functionality

**Examples:**

```markdown
v1.3.0 → v1.3.1
  - Fixed PatientSensor publishing incorrect units for heart rate
  - Fixed CMakeLists.txt failing on Ubuntu 24.04
  - Updated expired security certificates
```

---

## What Does NOT Warrant a New Release

Not every commit or merge needs a release. Changes that are purely cosmetic,
organizational, or internal to the development process do not warrant a version
bump or release.

**Do NOT create a new release for:**

- README or documentation-only changes (typo fixes, rewording, formatting)
- Code comment updates
- `.gitignore` changes
- CI/CD pipeline changes (GitHub Actions workflows) that don't affect the
  deliverable
- Development tooling changes (linter config, editor settings, pre-commit hooks)
- Refactoring that does not change external behavior
- Adding or updating tests that don't fix a bug

These changes should still be committed and merged to `main` — they simply do
not trigger the release process. They will be included in the next release
naturally.

> **Guideline:** If a user of the reference architecture would not need to take
> any action or notice any difference, it probably does not need a release.

---

## Relationship Between Version and Release

**Version** and **release** are related but distinct concepts:

| Concept | Definition |
| --- | --- |
| **Version** | A label (e.g., `v1.3.1`) that identifies a specific state of the code |
| **Release** | The published artifact on GitHub that packages a version for consumers |

### Key Principles

1. **Every release has a version, but not every version requires a release.**
   During active development, the version in the repository may be ahead of the
   latest release (e.g., the code on `main` may reflect `v1.4.0-dev` while the
   latest release is `v1.3.1`).

2. **A release is a deliberate publication event.** It involves creating a Git
   tag, writing release notes, and publishing a GitHub Release. It signals to
   users that the code at that point is tested, stable, and ready for use.

3. **A Git tag marks the exact commit for a version.** Tags are immutable
   pointers to specific commits. Once a version is tagged and released, that
   tag must never be moved or deleted.

4. **Releases are cumulative.** A release includes all changes since the
   previous release — not just the change that triggered the version bump. For
   example, if five documentation fixes and two bug fixes were merged since the
   last release, the new PATCH release captures all of them.

### Version Lifecycle

```markdown
Development ─→ Version Bump ─→ Git Tag ─→ GitHub Release
    │                │              │             │
    │                │              │             └─ Published artifact with
    │                │              │                release notes, available
    │                │              │                to users
    │                │              └─ Immutable pointer to the release commit
    │                │                 (e.g., v1.3.1)
    │                └─ Version updated in tracked files
    │                   (CHANGELOG, VERSION, etc.)
    └─ Ongoing work on main or feature branches;
       no version label until release decision
```

---

## Release Process

When a release is warranted, the maintainer must complete the following steps:

### 1. Pre-Release Checklist

- [ ] All intended changes are merged to `main`
- [ ] All tests pass (unit tests, integration tests, manual validation)
- [ ] All modules build successfully against the documented dependencies
- [ ] No known critical bugs remain unresolved
- [ ] CHANGELOG.md is updated with all changes since the last release
- [ ] Any updated security artifacts (certificates, governance files) are valid

### 2. Update Version References

- [ ] Update the `CHANGELOG.md` with the new version number, date, and changes
- [ ] If a `VERSION` file exists, update it
- [ ] Update any version references in documentation if applicable
- [ ] Commit these changes to `main` with message: `chore: prepare release vX.Y.Z`

### 3. Create the Git Tag

```bash
# Create an annotated tag (preferred — includes metadata)
git tag -a vX.Y.Z -m "Release vX.Y.Z: <brief summary>"

# Push the tag to the remote
git push origin vX.Y.Z
```

> **Important:** Always use annotated tags (`-a`), not lightweight tags. Annotated
> tags store the tagger, date, and message — essential metadata for releases.

### 4. Create the GitHub Release

1. Navigate to the repository on GitHub → **Releases** → **Draft a new release**
2. Select the tag `vX.Y.Z` that was just pushed
3. Set the release title: `vX.Y.Z — <brief description>`
4. Write release notes (see [Release Notes Template](#release-notes-template))
5. Attach any relevant binary artifacts if applicable
6. Mark as **pre-release** if appropriate (see
   [Pre-release Policy](#pre-release-and-release-candidate-policy))
7. Click **Publish release**

### 5. Post-Release Actions

- [ ] Verify the GitHub Release page is correct and links work
- [ ] Announce the release to stakeholders if applicable
- [ ] If a hotfix branch was used, merge it back to `main`

### Release Notes Template

```markdown
## What's New

- <Feature or change summary>

## Bug Fixes

- <Bug fix summary>

## Breaking Changes

- <Breaking change summary and migration guidance>

## Dependencies

- <Dependency version changes>

## Contributors

- @username — <contribution summary>

## Full Changelog

https://github.com/<org>/<repo>/compare/vPREVIOUS...vX.Y.Z
```

---

## Changelog Management

Maintain a `CHANGELOG.md` alongside this document in `docs/release/` following
the [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- <new features not yet released>

## [1.0.1] - 2026-XX-XX

### Fixed
- Fixed PatientSensor publishing incorrect heart rate units

## [1.1.0] - 2026-XX-XX

### Added
- Module 04: Security Threat Demonstration
- Shared utility library (modules/00-common/)

## [1.0.0] - 2026-03-25

### Added
- Initial release with Modules 01-03
- Operating Room module with Orchestrator, PatientSensor, ArmController
- Record and Playback module
- Remote Teleoperation module
```

### Changelog Categories

Use these section headers within each version entry:

| Category | Use For |
| --- | --- |
| **Added** | New features, modules, scripts, configurations |
| **Changed** | Changes to existing functionality |
| **Deprecated** | Features that will be removed in a future release |
| **Removed** | Features removed in this release |
| **Fixed** | Bug fixes |
| **Security** | Vulnerability fixes or security-related changes |

---

## Branch Strategy

| Branch | Purpose |
| --- | --- |
| `main` | Stable, release-ready code. All releases are tagged here. |
| `develop` | Integration branch for ongoing work (optional). |
| `feature/*` | New features — branched from and merged back to `main` (or `develop`). |
| `bugfix/*` | Bug fixes — branched from and merged back to `main` (or `develop`). |
| `hotfix/*` | Urgent fixes for released versions — branched from a release tag, merged back to `main`. |
| `release/*` | Release preparation (optional) — branched from `develop`, merged to `main` and tagged. |

> For a project of this size, a simplified flow using `main` + `feature/*`
> branches is sufficient. Adopt `develop` and `release/*` branches only when
> multiple contributors are working in parallel and release coordination becomes
> necessary.

---

## Dependency Versioning

This project depends on external software. Document minimum supported versions
and update them as part of the release process.

| Dependency | Current Minimum Version | Tracked In |
| --- | --- | --- |
| RTI Connext DDS | 7.3.0 | CMakeLists.txt, README.md |
| RTI Code Generator | 4.3.0 | Generated source headers |
| CMake | 3.17 | CMakeLists.txt |

**When a dependency version changes:**

- If the new dependency has breaking API changes → bump **MAJOR**
- If the new dependency adds optional features you now use → bump **MINOR**
- If the dependency update is for a patch/security fix → bump **PATCH**

---

## Pre-release and Release Candidate Policy

For significant releases (especially MAJOR), use pre-release versions to gather
feedback before the final release:

```markdown
v2.0.0-alpha.1   → Early preview, may be incomplete
v2.0.0-beta.1    → Feature-complete, may have known issues
v2.0.0-rc.1      → Release candidate, believed ready for release
v2.0.0           → Final stable release
```

Pre-releases:

- Are tagged and published as GitHub Releases with the **pre-release** checkbox
  enabled
- Must NOT be marked as "Latest" on GitHub
- Follow the same tagging and changelog process as full releases
- Are not required for MINOR or PATCH releases

---

## Deprecation Policy

Before removing a feature or making a breaking change:

1. **Mark as deprecated** in the current MINOR release — add a `### Deprecated`
   entry to the CHANGELOG and update relevant documentation with a deprecation
   notice
2. **Maintain for at least one MINOR release** — the deprecated feature must
   continue to work for at least one additional MINOR release cycle
3. **Remove in a MAJOR release** — the actual removal constitutes a breaking
   change and triggers a MAJOR version bump

**Example timeline:**

```markdown
v1.3.0 — Module 01 legacy launch scripts deprecated (still functional)
v1.4.0 — Deprecation warning remains; scripts still work
v2.0.0 — Legacy launch scripts removed
```

---

## Support and Maintenance Policy

- **Only the latest release is actively supported.** Bug fixes and security
  patches are applied to `main` and included in the next release.
- **Older releases receive no backported fixes** unless a critical security
  vulnerability is discovered, in which case a PATCH release may be issued from
  a hotfix branch off the affected release tag.
- **End-of-life (EOL) versions** should be clearly noted in the CHANGELOG and
  release notes when applicable.

---

## Quick Decision Reference

```markdown
Is the change functional, structural, or behavioral?
├── NO  → Do not release (commit to main, include in next release)
└── YES → Does it break backward compatibility?
    ├── YES → MAJOR bump
    └── NO  → Does it add new functionality?
        ├── YES → MINOR bump
        └── NO  → PATCH bump
```

---

*This release plan was established on 2026-03-25 and applies to all releases
going forward.*
