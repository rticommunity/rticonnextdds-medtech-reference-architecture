#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

"""Shared build and launch infrastructure for all modules.

Each module provides a ``module.toml`` at its root describing:

- ``env``: environment variables to set, with values that may contain
  ``${args:<name>}``, ``${MODULE_DIR}``, or ``${SYSTEM_DIR}``
  placeholders.  Semicolon-delimited path entries in env values starting
  with ``system/`` resolve relative to the project root; all others
  resolve relative to the module directory.
- ``args``: conditional variable definitions.  Each key is a variable
  name referenced as ``${args:<name>}`` in ``env`` or ``apps``.  The
  value is a map of ``{true: ..., false: ...}`` keyed by a CLI flag
  (defaults to the variable name, or set explicitly with ``"flag"``).
- ``setup_library_paths``: whether to prepend Connext/OpenSSL library
  directories to the dynamic-library search path (default ``true``).
- ``apps``: ``{name: [cmd_args...]}`` with placeholder tokens:
  ``${PYTHON:<name>}``, ``${CPP:<name>}``, ``${RTISERVICE:<name>}``,
  ``${args:<name>}``, ``${MODULE_DIR}``, ``${SYSTEM_DIR}``.
  ``${PYTHON:<name>}`` expands to two args (interpreter + ``src/<name>.py``).
  ``${CPP:<name>}`` locates a compiled executable in the build tree.
- ``app_variants``: logical app roles mapped to a default choice and concrete
  app names from ``apps``. Non-selected implementations are omitted from the
  resolved app list.

The runner loads this config, resolves all placeholders, builds the
process environment, and manages application lifecycles.
"""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from . import platform_setup

# ---------------------------------------------------------------------------
# Module discovery
# ---------------------------------------------------------------------------

PROJECT_ROOT = platform_setup.PROJECT_ROOT

MODULES_DIR = PROJECT_ROOT / "modules"

SYSTEM_DIR = PROJECT_ROOT / "system"


def discover_modules() -> dict[str, Path]:
    """Return ``{dirname: absolute_path}`` for every ``modules/*/`` directory."""
    return {p.name: p for p in sorted(MODULES_DIR.iterdir()) if (p / "module.toml").is_file()}


def read_manifest(module_dir: Path) -> dict:
    with (module_dir / "module.toml").open("rb") as stream:
        return tomllib.load(stream)


# ---------------------------------------------------------------------------
# Manifest loading and placeholder expansion
# ---------------------------------------------------------------------------

_INLINE_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)(?::([^}]+))?\}")


def _resolve_args(args_section: dict, flags: dict[str, bool]) -> dict[str, str]:
    """Resolve the ``args`` section into ``{name: resolved_value}``.

    Each entry in *args_section* maps a variable name to a dict with
    ``"true"`` and ``"false"`` keys.  An optional ``"flag"`` key names
    the CLI flag that drives the selection (defaults to the variable name).

    Raises ``ValueError`` if a required flag is not present in *flags*.
    """
    resolved: dict[str, str] = {}
    for name, spec in args_section.items():
        flag_name = spec.get("flag", name)
        if flag_name not in flags:
            raise ValueError(
                f"module.toml args variable '{name}' requires flag "
                f"'{flag_name}' but it was not provided. "
                f"Available flags: {', '.join(sorted(flags)) or '(none)'}"
            )
        flag_value = flags[flag_name]
        resolved[name] = spec["true"] if flag_value else spec["false"]
    return resolved


def _normalize_app_variants(
    app_variants: object,
    app_names: set[str],
) -> dict[str, tuple[str, dict[str, str]]]:
    """Validate app-variant metadata and return normalized role definitions."""
    if not isinstance(app_variants, dict):
        raise ValueError("module.toml app_variants must be a table")

    normalized: dict[str, tuple[str, dict[str, str]]] = {}
    implementation_roles: dict[str, str] = {}

    for role, spec in app_variants.items():
        if not isinstance(role, str) or not role:
            raise ValueError("module.toml app_variants keys must be non-empty strings")
        if not isinstance(spec, dict):
            raise ValueError(f"module.toml app_variants.{role} must be a table")

        default = spec.get("default")
        choices = spec.get("choices")
        if not isinstance(default, str) or not default:
            raise ValueError(f"module.toml app_variants.{role}.default must be a non-empty string")
        if not isinstance(choices, dict) or not choices:
            raise ValueError(f"module.toml app_variants.{role}.choices must be a non-empty table")
        if default not in choices:
            raise ValueError(
                f"module.toml app_variants.{role}.default '{default}' must name one of its choices"
            )

        normalized_choices: dict[str, str] = {}
        for choice, app_name in choices.items():
            if not isinstance(choice, str) or not choice:
                raise ValueError(
                    f"module.toml app_variants.{role}.choices keys must be non-empty strings"
                )
            if not isinstance(app_name, str) or not app_name:
                raise ValueError(
                    f"module.toml app_variants.{role}.choices.{choice} must name an app from 'apps'"
                )
            if app_name not in app_names:
                raise ValueError(
                    f"module.toml app_variants.{role}.choices.{choice} "
                    f"references unknown app '{app_name}'"
                )
            if app_name in implementation_roles:
                raise ValueError(
                    f"App '{app_name}' is assigned to multiple variant roles: "
                    f"'{implementation_roles[app_name]}' and '{role}'"
                )
            implementation_roles[app_name] = role
            normalized_choices[choice] = app_name

        if role in app_names and role not in normalized_choices.values():
            raise ValueError(
                f"App variant role '{role}' conflicts with an app that is not one of its choices"
            )

        normalized[role] = (default, normalized_choices)

    return normalized


def get_app_variant_names(module_dir: Path) -> set[str]:
    """Return the logical app roles declared by a module."""
    config_path = module_dir / "module.toml"
    raw = read_manifest(module_dir)

    apps = raw.get("apps", {})
    if not isinstance(apps, dict):
        raise ValueError(f"module.toml apps must be a table: {config_path}")

    variants = _normalize_app_variants(raw.get("app_variants", {}), set(apps))
    return set(variants)


def _select_app_definitions(
    app_definitions: object,
    app_variants: object,
    selected_variants: dict[str, str],
) -> dict[str, list[str]]:
    """Select raw app command templates without expanding unused variants."""
    if not isinstance(app_definitions, dict):
        raise ValueError("module.toml apps must be a table")

    normalized = _normalize_app_variants(app_variants, set(app_definitions))
    unknown_roles = sorted(set(selected_variants) - set(normalized))
    if unknown_roles:
        raise ValueError(
            f"Unknown app variant role(s): {', '.join(unknown_roles)}. "
            f"Available: {', '.join(sorted(normalized)) or '(none)'}"
        )

    implementation_roles = {
        app_name: role for role, (_, choices) in normalized.items() for app_name in choices.values()
    }
    selected: dict[str, list[str]] = {}

    for app_name, command in app_definitions.items():
        role = implementation_roles.get(app_name)
        if role is None:
            selected[app_name] = command
            continue
        if role in selected:
            continue

        default, choices = normalized[role]
        choice = selected_variants.get(role, default)
        if choice not in choices:
            raise ValueError(
                f"Invalid variant '{choice}' for app role '{role}'. Available: {', '.join(choices)}"
            )
        selected[role] = app_definitions[choices[choice]]

    return selected


def _expand_string(
    value: str,
    *,
    resolved_args: dict[str, str],
    module_dir: Path,
) -> str:
    """Expand all ``${...}`` placeholders in a string value."""

    def _replace(m: re.Match) -> str:
        kind = m.group(1)
        arg = m.group(2) or ""

        if kind == "args":
            if arg not in resolved_args:
                raise ValueError(f"Unknown args variable: {arg}")
            return resolved_args[arg]
        if kind == "MODULE_DIR":
            return str(module_dir)
        if kind == "SYSTEM_DIR":
            return str(SYSTEM_DIR)
        if kind == "PYTHON":
            return sys.executable
        if kind == "CPP":
            return platform_setup.find_executable(arg)
        if kind == "RTISERVICE":
            return str(platform_setup.find_service_binary(arg))
        raise ValueError(f"Unknown placeholder: ${{{kind}}}")

    return _INLINE_PLACEHOLDER_RE.sub(_replace, value)


def _expand_app_token(
    token: str,
    *,
    resolved_args: dict[str, str],
    module_dir: Path,
) -> list[str]:
    """Expand a single app command token, possibly producing multiple args.

    ``${PYTHON:Name}`` expands to ``[sys.executable, "src/Name.py"]``.
    All other tokens expand via ``_expand_string`` (single value).
    """
    m = _INLINE_PLACEHOLDER_RE.fullmatch(token)
    if m and m.group(1) == "PYTHON" and m.group(2):
        name = m.group(2)
        return [sys.executable, str(module_dir / "src" / f"{name}.py")]
    return [_expand_string(token, resolved_args=resolved_args, module_dir=module_dir)]


def _resolve_env_path(raw: str, module_dir: Path) -> str:
    """Resolve a single path segment from an env value.

    Paths starting with ``system/`` resolve from the project root.
    All other paths resolve from the module directory.
    """
    if raw.startswith("system/") or raw.startswith("system\\"):
        return str(PROJECT_ROOT / raw)
    return str(module_dir / raw)


def _resolve_env_value(value: str, module_dir: Path) -> str:
    """Resolve all semicolon-delimited path segments in an env value."""
    parts = value.split(";")
    return ";".join(_resolve_env_path(p, module_dir) for p in parts)


def select_apps(
    raw: dict,
    variants: dict[str, str],
    app_names: list[str] | None,
    module_name: str,
) -> dict[str, list[str]]:
    selected = _select_app_definitions(
        raw.get("apps", {}),
        raw.get("app_variants", {}),
        variants,
    )
    if app_names is None:
        return selected
    if len(set(app_names)) != len(app_names):
        raise ValueError(f"Duplicate app selection in '{module_name}'")
    for name in app_names:
        if name not in selected:
            raise ValueError(
                f"Unknown app '{name}' in module '{module_name}'. Available: {', '.join(selected)}"
            )
    return {name: selected[name] for name in app_names}


def load_module_config(
    module_dir: Path,
    flags: dict[str, bool] | None = None,
    variants: dict[str, str] | None = None,
    app_names: list[str] | None = None,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Load ``module.toml`` and return ``(env, apps)``.

    *flags* is a dict of boolean CLI flags (e.g. ``{"security": True}``).
    Any flag referenced by the module's ``args`` section must be present;
    a ``ValueError`` is raised otherwise.

    *env* is a ready-to-use environment dict.
    *apps* is ``{logical_app_name: [resolved_cmd_args]}``; each declared
    variant group resolves to its selected or default implementation.
    """
    raw = read_manifest(module_dir)
    selected_app_definitions = select_apps(raw, variants or {}, app_names, module_dir.name)

    if flags is None:
        flags = {}

    # --- Resolve args ---
    args_section = raw.get("args", {})
    resolved_args = _resolve_args(args_section, flags)

    # Warn about flags that are set but not consumed by this module
    consumed_flags = {spec.get("flag", name) for name, spec in args_section.items()}
    for flag_name, flag_value in flags.items():
        if flag_value and flag_name not in consumed_flags:
            print(f"Info: --{flag_name} has no effect on {raw.get('description', module_dir.name)}")

    # --- Environment ---
    nddshome = platform_setup.get_nddshome()
    env = os.environ.copy()

    for key, value in raw.get("env", {}).items():
        # First expand ${args:...} and other inline placeholders
        expanded = _expand_string(
            value,
            resolved_args=resolved_args,
            module_dir=module_dir,
        )
        # Then resolve semicolon-delimited path segments
        resolved = _resolve_env_value(expanded, module_dir)
        env[key] = resolved

    if raw.get("setup_library_paths", True):
        platform_setup.setup_library_env(env, nddshome)

    generated_python = platform_setup.generated_system_path() / "python"
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(generated_python),
            str(SYSTEM_DIR / "src"),
            str(PROJECT_ROOT / "resources" / "ui" / "support"),
            *filter(None, [env.get("PYTHONPATH", "")]),
        ]
    )

    desc = raw.get("description", module_dir.name)
    active_flags = [k for k, v in flags.items() if v]
    if active_flags:
        print(f"Launching {desc} with {', '.join(active_flags)}...")
    else:
        print(f"Launching {desc}...")

    # --- Apps ---
    apps: dict[str, list[str]] = {}
    for name, cmd_template in selected_app_definitions.items():
        cmd: list[str] = []
        for tok in cmd_template:
            cmd.extend(
                _expand_app_token(
                    tok,
                    resolved_args=resolved_args,
                    module_dir=module_dir,
                )
            )
        apps[name] = cmd

    return env, apps


# ---------------------------------------------------------------------------
# Launch helpers
# ---------------------------------------------------------------------------


def _shutdown(children: list[subprocess.Popen]) -> None:
    """Gracefully terminate then kill all children."""
    for child in children:
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + 2
    for child in children:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def launch(commands: list[list[str]], module_dir: Path, env: dict[str, str]) -> int:
    return launch_multi([(commands, module_dir, env)])


LaunchSpec = tuple[list[list[str]], Path, dict[str, str]]


def print_command(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    delta = ", ".join(sorted(k for k, v in (env or {}).items() if os.environ.get(k) != v))
    safe_args = []
    redact_next = False
    for arg in cmd:
        key, equals, _ = arg.partition("=")
        sensitive = key.startswith("-") and re.search(
            r"password|passwd|passphrase|token|secret|credential|api[_-]?key",
            key,
            re.IGNORECASE,
        )
        safe_args.append(
            "<redacted>" if redact_next else f"{key}=<redacted>" if sensitive and equals else arg
        )
        redact_next = bool(sensitive and not equals and not redact_next)
    line = subprocess.list2cmdline(safe_args) if os.name == "nt" else shlex.join(safe_args)
    print(f"[cwd: {cwd}] {line}", flush=True)
    if delta:
        print(f"  environment overrides (names only): {delta}", flush=True)


def launch_multi(
    specs: list[LaunchSpec],
    *,
    explain: bool = False,
) -> int:
    """Launch processes from multiple modules and manage them as one group.

    *specs* is a list of ``(commands, module_dir, env)`` tuples — one per
    module.  All processes across all modules are spawned concurrently and
    ``Ctrl-C`` tears down everything.
    """
    children: dict[subprocess.Popen, str] = {}
    try:
        for commands, module_dir, env in specs:
            for cmd in commands:
                print_command(cmd, module_dir, env)
                if not explain:
                    child = subprocess.Popen(cmd, env=env, cwd=module_dir)
                    children[child] = " ".join(cmd[:2])
        while children:
            for child, label in list(children.items()):
                code = child.poll()
                if code is None:
                    continue
                del children[child]
                if code:
                    print(f"{label} exited with status {code}", file=sys.stderr)
                    return code if code > 0 else 128 - code
                print(f"{label} exited normally", flush=True)
            if children:
                time.sleep(0.05)
        return 0
    except KeyboardInterrupt:
        return 128 + signal.SIGINT
    finally:
        _shutdown(list(children))
