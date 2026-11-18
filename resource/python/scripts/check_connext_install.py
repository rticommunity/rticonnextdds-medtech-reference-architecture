#!/usr/bin/env python3
#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software solely in combination with RTI Connext DDS. The Software
# is provided "as is", with no warranty of any type.

"""Check that the locked Python API and selected Connext SDK are compatible."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RTIDDSGEN_VERSIONS = {"7.7.0": "4.7.0"}


class PreflightError(RuntimeError):
    """An actionable Connext installation compatibility error."""


def project_python_api_version(pyproject_path: Path = PROJECT_ROOT / "pyproject.toml") -> str:
    """Return the exact rti.connext version declared by project metadata."""
    project = tomllib.loads(pyproject_path.read_text(encoding="utf-8")).get("project", {})
    dependencies = project.get("dependencies", [])
    requirements = [
        requirement
        for requirement in dependencies
        if re.match(r"\s*rti\.connext(?:\s|[<>=!~])", requirement, re.IGNORECASE)
    ]
    if len(requirements) != 1:
        raise PreflightError(
            "pyproject.toml must declare exactly one direct rti.connext dependency."
        )

    match = re.fullmatch(
        r"\s*rti\.connext==(\d+\.\d+\.\d+(?:\.\d+)?)\s*", requirements[0], re.IGNORECASE
    )
    if match is None:
        raise PreflightError(
            "The direct rti.connext dependency must be an exact release pin in pyproject.toml."
        )
    return match.group(1)


def _canonicalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def python_api_errors(
    expected_version: str,
    installed_distributions: list[tuple[str, str]],
    api_namespace_available: bool,
) -> list[str]:
    """Return Python package/source/version errors without importing the DDS API."""
    versions: dict[str, list[str]] = {}
    for name, version in installed_distributions:
        canonical_name = _canonicalize_name(name)
        if canonical_name in {"rti-connext", "rti-connext-activated"}:
            versions.setdefault(canonical_name, []).append(version)

    errors = []
    activated = versions.get("rti-connext-activated", [])
    if activated:
        errors.append(
            "Found the unsupported commercial rti.connext.activated distribution; "
            "remove it and use the locked PyPI rti.connext package."
        )

    connext = versions.get("rti-connext", [])
    if not connext:
        errors.append(
            "The rti.connext Python distribution is missing; install project dependencies "
            "with `uv sync --locked`."
        )
    elif len(connext) != 1:
        errors.append(
            f"Found {len(connext)} rti.connext distributions; remove duplicate installations "
            "and sync the project environment."
        )
    elif _patch_version(connext[0]) != _patch_version(expected_version):
        errors.append(
            f"rti.connext=={connext[0]} is installed, but pyproject.toml requires "
            f"rti.connext=={expected_version}; run `uv sync --locked`."
        )

    if not api_namespace_available:
        errors.append(
            "The rti.connextdds import namespace is missing; sync the project environment "
            "with the selected Python interpreter."
        )
    return errors


def sdk_version_from_home(nddshome: Path) -> str:
    """Read the SDK release from RTI's version-qualified NDDSHOME directory."""
    match = re.fullmatch(r"rti_connext_dds-(\d+\.\d+\.\d+)", nddshome.resolve().name)
    if match is None:
        raise PreflightError(
            f"Cannot determine the SDK release from NDDSHOME={nddshome}; "
            "expected an installation directory named rti_connext_dds-X.Y.Z."
        )
    return match.group(1)


def rtiddsgen_version(output: str) -> str:
    """Extract the generator version from the documented `rtiddsgen -version` output."""
    match = re.search(r"\brtiddsgen version\s+(\d+\.\d+\.\d+)\b", output, re.IGNORECASE)
    if match is None:
        raise PreflightError(
            "Could not read the RTI Code Generator version from `rtiddsgen -version` output:\n"
            f"{output.strip()}"
        )
    return match.group(1)


def sdk_compatibility_errors(
    expected_version: str,
    sdk_version: str,
    generator_output: str,
    declared_versions: dict[str, str],
) -> list[str]:
    """Return SDK/code-generator mismatches against the locked API release."""
    errors = []
    release_version = ".".join(expected_version.split(".")[:3])
    if sdk_version != release_version:
        errors.append(
            f"Connext SDK {sdk_version} (from NDDSHOME) does not match the locked "
            f"Python API release {expected_version}."
        )

    for name, version in declared_versions.items():
        if version and version != release_version:
            errors.append(
                f"{name}={version} does not match the locked Python API release {expected_version}."
            )

    expected_generator = RTIDDSGEN_VERSIONS.get(release_version)
    if expected_generator is None:
        errors.append(
            f"No rtiddsgen compatibility mapping is defined for Connext {expected_version}."
        )
    else:
        actual_generator = rtiddsgen_version(generator_output)
        if actual_generator != expected_generator:
            errors.append(
                f"rtiddsgen {actual_generator} does not match Connext {expected_version}; "
                f"expected rtiddsgen {expected_generator}."
            )
    return errors


def _patch_version(version: str) -> tuple[int, int, int, int]:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", version):
        raise PreflightError(f"Unrecognized Connext version: {version!r}")
    parts = tuple(int(part) for part in version.split("."))
    return (parts[0], parts[1], parts[2], parts[3] if len(parts) == 4 else 0)


def native_version_errors(nddshome: Path, architecture: str, expected_version: str) -> list[str]:
    """Compare installed inventory and binary build IDs, not runtime loader selection."""
    inventory = nddshome / "rti_versions.xml"
    try:
        root = ET.parse(inventory).getroot()
    except (OSError, ET.ParseError) as exc:
        raise PreflightError(f"Cannot read Connext inventory {inventory}: {exc}") from exc

    expected = _patch_version(expected_version)
    library_dir = nddshome / "lib" / architecture
    components = (
        ("Core", "api-core-lib", "nddsc", b"NDDSC_BUILD_"),
        ("Security", "addons-security-lib", "nddssecurity", b"SECURITYPLUGINS_BUILD_"),
    )
    errors = []
    for label, tag, library, marker in components:
        entries = [
            entry
            for entry in root.findall(f"./{tag}/installation")
            if entry.findtext("architecture") == architecture
        ]
        versions = {entry.findtext("version") for entry in entries}
        if not entries or None in versions or "" in versions:
            errors.append(f"{label} inventory version missing for {architecture} in {inventory}.")
            continue
        normalized = {_patch_version(version) for version in versions if version}
        if len(normalized) != 1 or normalized != {expected}:
            errors.append(
                f"{label} inventory versions {sorted(versions)} do not match "
                f"the required patch {expected_version} for {architecture}."
            )
            continue

        candidates = [
            library_dir / filename
            for filename in (f"lib{library}.so", f"lib{library}.dylib", f"{library}.dll")
            if (library_dir / filename).is_file()
        ]
        if len(candidates) != 1:
            errors.append(
                f"Cannot identify one {label} release library under {library_dir}; "
                f"found {len(candidates)}."
            )
            continue
        try:
            data = candidates[0].read_bytes()
        except OSError as exc:
            raise PreflightError(f"Cannot read {label} library {candidates[0]}: {exc}") from exc
        found = {
            _patch_version(match.decode("ascii"))
            for match in re.findall(re.escape(marker) + rb"(\d+\.\d+\.\d+\.\d+)_", data)
        }
        if found != {expected}:
            errors.append(
                f"{label} build ID in {candidates[0]} does not uniquely match required "
                f"patch {expected_version}: {sorted(found) or 'not found'}."
            )
    return errors


def _rtiddsgen_command(nddshome: Path) -> list[str]:
    bin_dir = nddshome / "bin"
    executable = next(
        (
            candidate
            for candidate in (bin_dir / "rtiddsgen", bin_dir / "rtiddsgen.bat")
            if candidate.is_file()
        ),
        None,
    )
    if executable is None and (bin_dir / "rtiddsgen.exe").is_file():
        executable = bin_dir / "rtiddsgen.exe"
    if executable is None:
        raise PreflightError(f"Could not find rtiddsgen under {bin_dir}.")
    if executable.suffix.lower() == ".bat":
        return ["cmd", "/c", str(executable), "-version"]
    return [str(executable), "-version"]


def main() -> None:
    try:
        expected_version = project_python_api_version()
        distributions = [
            (dist.metadata.get("Name", ""), dist.version)
            for dist in importlib.metadata.distributions()
        ]
        namespace_available = importlib.util.find_spec("rti") is not None and (
            importlib.util.find_spec("rti.connextdds") is not None
        )
        errors = python_api_errors(expected_version, distributions, namespace_available)
        if errors:
            raise PreflightError("\n".join(errors))

        nddshome_value = os.environ.get("NDDSHOME")
        if not nddshome_value:
            raise PreflightError(
                "NDDSHOME is not set; source the selected Connext SDK environment."
            )
        nddshome = Path(nddshome_value)
        if not nddshome.is_dir():
            raise PreflightError(f"NDDSHOME does not exist or is not a directory: {nddshome}")
        sdk_version = sdk_version_from_home(nddshome)
        architecture = os.environ.get("CONNEXTDDS_ARCH")
        if not architecture:
            raise PreflightError("CONNEXTDDS_ARCH is not set; source the Connext environment.")

        declared_versions = {
            name: os.environ.get(name, "") for name in ("CONNEXT_VERSION", "RTICONNEXTDDS_VERSION")
        }
        try:
            result = subprocess.run(
                _rtiddsgen_command(nddshome),
                cwd=nddshome,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise PreflightError(f"Could not run rtiddsgen from {nddshome}: {exc}") from exc

        output = f"{result.stdout}\n{result.stderr}".strip()
        if result.returncode:
            raise PreflightError(
                f"`rtiddsgen -version` failed with exit code {result.returncode}:\n{output}"
            )
        errors = sdk_compatibility_errors(expected_version, sdk_version, output, declared_versions)
        errors.extend(native_version_errors(nddshome, architecture, expected_version))
        if errors:
            raise PreflightError("\n".join(errors))
    except PreflightError as exc:
        print(f"Connext compatibility preflight failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Python API: rti.connext=={expected_version} (rti.connextdds available)")
    print(f"Connext SDK: {sdk_version}; rtiddsgen {RTIDDSGEN_VERSIONS[sdk_version]}")
    print(f"Core and Security inventory and build IDs match patch {expected_version}.")
    print("Runtime library selection is not checked; verify library paths if installations differ.")


if __name__ == "__main__":
    main()
