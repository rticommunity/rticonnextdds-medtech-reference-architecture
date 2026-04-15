"""Shared build and launch infrastructure for all modules.

Each module provides a ``module.json`` at its root describing:

- ``env``: environment variables to set, with values that may contain
  ``${args:<name>}``, ``${MODULE_DIR}``, or ``${SYSTEM_ARCH}``
  placeholders.  Semicolon-delimited path entries in env values starting
  with ``system_arch/`` resolve relative to the project root; all others
  resolve relative to the module directory.
- ``args``: conditional variable definitions.  Each key is a variable
  name referenced as ``${args:<name>}`` in ``env`` or ``apps``.  The
  value is a map of ``{true: ..., false: ...}`` keyed by a CLI flag
  (defaults to the variable name, or set explicitly with ``"flag"``).
- ``setup_library_paths``: whether to prepend Connext/OpenSSL library
  directories to the dynamic-library search path (default ``true``).
- ``apps``: ``{name: [cmd_args...]}`` with placeholder tokens:
  ``${PYTHON:<name>}``, ``${CPP:<name>}``, ``${RTISERVICE:<name>}``,
  ``${args:<name>}``, ``${MODULE_DIR}``, ``${SYSTEM_ARCH}``.
  ``${PYTHON:<name>}`` expands to two args (interpreter + ``src/<name>.py``).
  ``${CPP:<name>}`` locates a compiled executable in the build tree.

The runner loads this config, resolves all placeholders, builds the
process environment, and manages application lifecycles.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import platform_setup


# ---------------------------------------------------------------------------
# Module discovery
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

MODULES_DIR = PROJECT_ROOT / "modules"

SYSTEM_ARCH = PROJECT_ROOT / "system_arch"


def discover_modules() -> dict[str, Path]:
    """Return ``{dirname: absolute_path}`` for every ``modules/*/`` directory."""
    return {
        p.name: p
        for p in sorted(MODULES_DIR.iterdir())
        if p.is_dir()
    }


# ---------------------------------------------------------------------------
# module.json loading and placeholder expansion
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
                f"module.json args variable '{name}' requires flag "
                f"'{flag_name}' but it was not provided. "
                f"Available flags: {', '.join(sorted(flags)) or '(none)'}"
            )
        flag_value = flags[flag_name]
        resolved[name] = spec["true"] if flag_value else spec["false"]
    return resolved


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
        elif kind == "MODULE_DIR":
            return str(module_dir)
        elif kind == "SYSTEM_ARCH":
            return str(SYSTEM_ARCH)
        elif kind == "PYTHON":
            return sys.executable
        elif kind == "CPP":
            return platform_setup.find_executable(arg)
        elif kind == "RTISERVICE":
            return str(platform_setup.find_service_binary(arg))
        else:
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

    Paths starting with ``system_arch/`` resolve from the project root.
    All other paths resolve from the module directory.
    """
    if raw.startswith("system_arch/") or raw.startswith("system_arch\\"):
        return str(PROJECT_ROOT / raw)
    return str(module_dir / raw)


def _resolve_env_value(value: str, module_dir: Path) -> str:
    """Resolve all semicolon-delimited path segments in an env value."""
    parts = value.split(";")
    return ";".join(_resolve_env_path(p, module_dir) for p in parts)


def load_module_config(
    module_dir: Path,
    flags: dict[str, bool] | None = None,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Load ``module.json`` and return ``(env, apps)``.

    *flags* is a dict of boolean CLI flags (e.g. ``{"security": True}``).
    Any flag referenced by the module's ``args`` section must be present;
    a ``ValueError`` is raised otherwise.

    *env* is a ready-to-use environment dict.
    *apps* is ``{name: [resolved_cmd_args]}``.
    """
    config_path = module_dir / "module.json"
    with open(config_path) as f:
        raw = json.load(f)

    if flags is None:
        flags = {}

    # --- Resolve args ---
    args_section = raw.get("args", {})
    resolved_args = _resolve_args(args_section, flags)

    # Warn about flags that are set but not consumed by this module
    consumed_flags = {
        spec.get("flag", name) for name, spec in args_section.items()
    }
    for flag_name, flag_value in flags.items():
        if flag_value and flag_name not in consumed_flags:
            print(
                f"Info: --{flag_name} has no effect on "
                f"{raw.get('description', module_dir.name)}"
            )

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

    desc = raw.get("description", module_dir.name)
    active_flags = [k for k, v in flags.items() if v]
    if active_flags:
        print(f"Launching {desc} with {', '.join(active_flags)}...")
    else:
        print(f"Launching {desc}...")

    # --- Apps ---
    apps: dict[str, list[str]] = {}
    for name, cmd_template in raw.get("apps", {}).items():
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
    for child in children:
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            child.kill()


def launch(commands: list[list[str]], module_dir: Path, env: dict[str, str]) -> None:
    """Spawn *commands* as child processes under *module_dir* and wait.

    All processes are launched concurrently.  ``KeyboardInterrupt``
    triggers a graceful shutdown (SIGTERM, then SIGKILL after 1 s).
    """
    children: list[subprocess.Popen] = []
    for cmd in commands:
        children.append(subprocess.Popen(cmd, env=env, cwd=module_dir))

    try:
        for child in children:
            child.wait()
    except KeyboardInterrupt:
        _shutdown(children)


def launch_multi(
    specs: list[tuple[list[list[str]], Path, dict[str, str]]],
) -> None:
    """Launch processes from multiple modules and manage them as one group.

    *specs* is a list of ``(commands, module_dir, env)`` tuples — one per
    module.  All processes across all modules are spawned concurrently and
    ``Ctrl-C`` tears down everything.
    """
    children: list[subprocess.Popen] = []
    for commands, module_dir, env in specs:
        for cmd in commands:
            children.append(subprocess.Popen(cmd, env=env, cwd=module_dir))

    try:
        for child in children:
            child.wait()
    except KeyboardInterrupt:
        _shutdown(children)
