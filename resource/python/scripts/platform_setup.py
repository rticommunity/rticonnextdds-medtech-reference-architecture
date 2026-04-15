"""Platform-specific utilities shared across all modules.

Handles NDDSHOME validation, native library discovery, dynamic library
path setup (DYLD_LIBRARY_PATH / LD_LIBRARY_PATH / PATH), compiled
executable location, and RTI service binary location.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


# -- Connext environment variables and paths ------------------------------------------------

def get_nddshome() -> Path:
    """Return the ``NDDSHOME`` path or exit with an error."""
    nddshome = os.environ.get("NDDSHOME")
    if not nddshome:
        raise EnvironmentError("NDDSHOME environment variable is not set.")
    return Path(nddshome)

def get_connextdds_arch() -> str:
    connextdds_arch = os.getenv("CONNEXTDDS_ARCH")
    if not connextdds_arch:
        raise EnvironmentError("CONNEXTDDS_ARCH environment variable is not set.")
    return connextdds_arch

def build_path() -> Path:
    return Path("build") / get_connextdds_arch()


# -- Library discovery -------------------------------------------------------

def connext_lib(nddshome: "Path | None" = None) -> Path:
    """Return the first Connext lib/ directory that contains the core C lib."""
    if nddshome is None:
        nddshome = get_nddshome()

    lib_dir = nddshome / "lib" / get_connextdds_arch()
    if not lib_dir.is_dir() or not any(lib_dir.glob("*nddscore*")):
        raise FileNotFoundError(f"Could not find Connext libraries in {lib_dir}")
    return lib_dir


def openssl_lib(nddshome: "Path | None" = None) -> Path:
    """Return the bundled OpenSSL release/lib directory, if present."""
    if nddshome is None:
        nddshome = get_nddshome()

    for crypto_lib in sorted(nddshome.glob(f"third_party/openssl-*/{get_connextdds_arch()}/release/lib/libcrypto*"), reverse=True):
        if crypto_lib.is_file():
            return crypto_lib.parent
    raise FileNotFoundError("Could not find OpenSSL libraries.")


# -- Executable / service binary location ------------------------------------

def find_executable(name: str, build_dir: "Path | None" = None) -> str:
    """Locate a compiled C++ executable, accounting for platform differences.

    Searches *build_dir* first, then falls back to the project-level build
    tree (``build/<arch>/modules/*/``), then the legacy per-module build dir.

    On single-config generators (Make/Ninja) the binary is at
    ``<dir>/<name>``.  On multi-config generators (Visual Studio) it is at
    ``<dir>/Release/<name>.exe`` (or ``Debug/``).
    """
    candidates: list[Path] = []

    if build_dir is not None:
        candidates.append(build_dir)

    # Project-level build: scan all module subdirectories
    try:
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        modules_build = project_root / "build" / get_connextdds_arch() / "modules"
        if modules_build.is_dir():
            candidates.extend(sorted(modules_build.iterdir()))
    except EnvironmentError:
        pass

    # Legacy per-module build dir (relative to cwd)
    try:
        candidates.append(build_path())
    except EnvironmentError:
        pass

    for search_dir in candidates:
        if platform.system() == "Windows":
            for config in ("Release", "Debug", "RelWithDebInfo", "MinSizeRel"):
                candidate = search_dir / config / f"{name}.exe"
                if candidate.exists():
                    return str(candidate)
        else:
            candidate = search_dir / name
            if candidate.exists():
                return str(candidate)

    searched = ", ".join(str(d) for d in candidates) if candidates else "(none)"
    raise FileNotFoundError(f"Could not find executable '{name}'. Searched: {searched}")


def find_service_binary(name: str) -> Path:
    """Locate an RTI service binary under ``NDDSHOME/bin/``.

    On Windows, RTI typically ships batch-wrapper launchers for services, so
    the lookup also checks ``.bat`` and ``.exe`` suffixes.
    """
    bin_dir = get_nddshome() / "bin"
    candidates = [bin_dir / name]

    if platform.system() == "Windows":
        candidates.extend([
            bin_dir / f"{name}.bat",
            bin_dir / f"{name}.exe",
        ])

    for candidate in candidates:
        if candidate.exists():
            return candidate

    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        f"Could not find RTI service binary '{name}'. Searched: {searched}"
    )


# -- Environment setup for launching applications ----------------------------

def lib_path_var() -> str:
    """Return the platform-specific dynamic library path variable name."""
    system = platform.system()
    if system == "Darwin":
        return "DYLD_LIBRARY_PATH"
    elif system == "Windows":
        return "PATH"
    return "LD_LIBRARY_PATH"

def prepend_path_var(env: os._Environ, var: str, path: Path) -> None:
    """Prepend *path* to the environment variable *var* in *env*."""
    env[var] = str(path) + os.pathsep + env.get(var, "")


def setup_library_env(env: os._Environ, nddshome: Path) -> None:
    """Add Connext and bundled-OpenSSL library directories to *env* in-place.

    On macOS: prepends to ``DYLD_LIBRARY_PATH``.
    On Linux: prepends to ``LD_LIBRARY_PATH``.
    On Windows: prepends to ``PATH``.
    """

    try:
        prepend_path_var(env, lib_path_var(), openssl_lib(nddshome))
    except FileNotFoundError:
        print("Warning: Could not find OpenSSL libraries. Security features may not work.", file=sys.stderr)

    prepend_path_var(env, lib_path_var(), connext_lib(nddshome))
