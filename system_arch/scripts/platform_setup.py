"""Platform-specific utilities shared across all modules.

Handles NDDSHOME validation, native library discovery, dynamic library
path setup (DYLD_LIBRARY_PATH / LD_LIBRARY_PATH / PATH), compiled
executable location, RTI service binary location, and CLI argument parsing.
"""

import os
import platform
import sys
from pathlib import Path


def parse_security_flag(argv: "list[str] | None" = None) -> bool:
    """Return *True* when ``-s`` is passed on the command line."""
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        return False
    if args[0] == "-s":
        return True
    print(
        f"Unknown argument: {args[0]}. "
        "Use -s to run with Security. "
        "Don't use any argument to run without security."
    )
    sys.exit(1)


def check_nddshome() -> Path:
    """Return the ``NDDSHOME`` path or exit with an error."""
    nddshome = os.environ.get("NDDSHOME")
    if not nddshome:
        print(
            "Error: NDDSHOME must be set.\n"
            "  export NDDSHOME=/path/to/rti_connext_dds-<version>",
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(nddshome)


# -- Library discovery -------------------------------------------------------

def _find_connext_lib(nddshome: Path) -> "Path | None":
    """Return the first Connext lib/ directory that contains the core C lib."""
    for lib_dir in sorted(nddshome.glob("lib/*")):
        if not lib_dir.is_dir():
            continue
        if any(lib_dir.glob("libnddsc.*")) or any(lib_dir.glob("nddsc.*")):
            return lib_dir
    return None


def _find_openssl_lib(nddshome: Path) -> "Path | None":
    """Return the bundled OpenSSL release/lib directory, if present."""
    for arch_dir in sorted(nddshome.glob("third_party/openssl-*/*")):
        release_lib = arch_dir / "release" / "lib"
        if release_lib.is_dir():
            return release_lib
    return None


def _prepend_path(env: dict, var: str, path: Path) -> None:
    """Prepend *path* to the environment variable *var* in *env*."""
    existing = env.get(var, "")
    env[var] = str(path) + (":" + existing if existing else "")


def setup_library_env(env: dict, nddshome: Path) -> None:
    """Add Connext and bundled-OpenSSL library directories to *env* in-place.

    On macOS: prepends to ``DYLD_LIBRARY_PATH``.
    On Linux: prepends to ``LD_LIBRARY_PATH``.
    On Windows: prepends to ``PATH``.
    """
    connext_lib = _find_connext_lib(nddshome)
    openssl_lib = _find_openssl_lib(nddshome)
    lib_var = _lib_path_var()

    if openssl_lib:
        _prepend_path(env, lib_var, openssl_lib)
    if connext_lib:
        _prepend_path(env, lib_var, connext_lib)


# -- Executable / service binary location ------------------------------------

def find_executable(name: str, build_dir: Path = Path("build")) -> str:
    """Locate a compiled C++ executable, accounting for platform differences.

    On single-config generators (Make/Ninja) the binary is at
    ``build/<name>``.  On multi-config generators (Visual Studio) it is at
    ``build/Release/<name>.exe`` (or ``Debug/``).
    """
    if platform.system() == "Windows":
        for config in ("Release", "Debug", "RelWithDebInfo", "MinSizeRel"):
            candidate = build_dir / config / f"{name}.exe"
            if candidate.exists():
                return str(candidate)
        # Fallback
        return str(build_dir / "Release" / f"{name}.exe")

    candidate = build_dir / name
    return str(candidate)


def find_service_binary(name: str) -> str:
    """Locate an RTI service binary under ``NDDSHOME/bin/``."""
    nddshome = check_nddshome()
    bin_name = name
    if platform.system() == "Windows":
        bin_name += ".bat"
    return str(nddshome / "bin" / bin_name)


# -- OpenSSL discovery -------------------------------------------------------

def find_openssl() -> "tuple[str, dict]":
    """Locate the OpenSSL binary bundled with RTI Connext.

    Returns ``(openssl_path, env)`` where *env* is a copy of the current
    environment with library paths adjusted so the bundled OpenSSL can find
    its own ``libssl``/``libcrypto``.
    """
    nddshome = check_nddshome()
    openssl_bin: "Path | None" = None
    openssl_lib: "Path | None" = None

    for arch_dir in sorted(nddshome.glob("third_party/openssl-*/*")):
        candidate = arch_dir / "release" / "bin" / "openssl"
        if platform.system() == "Windows":
            candidate = candidate.with_suffix(".exe")
        if candidate.is_file():
            openssl_bin = candidate
            openssl_lib = arch_dir / "release" / "lib"
            break

    if openssl_bin is None:
        print(
            f"Error: Could not find OpenSSL under {nddshome}/third_party/",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Using OpenSSL: {openssl_bin}")

    env = os.environ.copy()
    if openssl_lib and openssl_lib.is_dir():
        _prepend_path(env, _lib_path_var(), openssl_lib)

    return str(openssl_bin), env


def _lib_path_var() -> str:
    """Return the platform-specific dynamic library path variable name."""
    system = platform.system()
    if system == "Darwin":
        return "DYLD_LIBRARY_PATH"
    elif system == "Windows":
        return "PATH"
    return "LD_LIBRARY_PATH"
