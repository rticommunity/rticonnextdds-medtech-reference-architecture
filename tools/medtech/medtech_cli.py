# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
# Licensed under the terms in LICENSE.

"""Compose the existing launcher, build and compatibility checks."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import logging
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import build, check_connext_install, launch, module_runner, platform_setup
from .providers import eps

ROOT = module_runner.PROJECT_ROOT
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
SETTINGS = ROOT / ".medtech" / "settings.toml"
DEFAULT_PROVIDER = "local"
CAPABILITIES = ("arm", "gamepad", "native")
ROLE_PACKAGES = {
    "Arm": ("arm", ("mink", "mujoco", "qpsolvers", "daqp")),
    "ArmKortex": ("arm", ("mink", "mujoco", "qpsolvers", "daqp")),
    "ArmControllerGamepad": ("gamepad", ("pygame-ce",)),
}
LOG = logging.getLogger(__name__)


def run_command(command: list[str], *, env: dict[str, str] | None = None) -> None:
    module_runner.print_command(command, ROOT, env)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def setup(extras: set[str]) -> None:
    if not VENV_PYTHON.is_file():
        run_command([sys.executable, "-m", "venv", str(VENV)])
    if not (VENV / "pyvenv.cfg").is_file():
        raise ValueError(f"{VENV} is not a virtual environment.")
    uv = shutil.which("uv")
    if uv:
        command = [uv]
    else:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        requirement = next(
            item
            for item in pyproject["project"]["optional-dependencies"]["maint"]
            if item.startswith("uv==")
        )
        uv_path = VENV_PYTHON.with_name("uv.exe" if os.name == "nt" else "uv")
        if not uv_path.is_file():
            run_command([str(VENV_PYTHON), "-m", "pip", "install", requirement])
        command = [str(uv_path)]
    # Keep capability additions on rerun; the lock still governs the requested extras.
    command += [
        "sync",
        "--locked",
        "--inexact",
        "--no-dev",
        "--no-install-project",
        "--python",
        str(VENV_PYTHON),
    ]
    for extra in sorted(extras):
        command += ["--extra", extra]
    run_command(command, env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(VENV)})


def project_python() -> str:
    if sys.prefix != sys.base_prefix:
        return sys.executable
    if VENV_PYTHON.is_file():
        return str(VENV_PYTHON)
    raise ValueError("No project environment. Run `python medtech.py setup` first.")


def enter_run(python: str, argv: list[str]) -> None:
    command = [python, str(ROOT / "medtech.py"), *argv]
    if os.name == "posix":
        module_runner.print_command(command, ROOT)
        os.chdir(ROOT)
        os.execv(python, command)
    run_command(command)


def selected_templates(args: argparse.Namespace) -> list[list[str]]:
    selection, variants = launch.select_roles(args)
    templates: list[list[str]] = []
    for module, roles in selection:
        manifest = module_runner.read_manifest(module_runner.MODULES_DIR / module)
        choices = {
            role: choice
            for (scope, role), choice in variants.items()
            if (scope is None or scope == module) and role in manifest.get("app_variants", {})
        }
        selected = module_runner.select_apps(manifest, choices, roles, module)
        templates.extend(selected.values())
    return templates


def capabilities(templates: list[list[str]], ui_mode: str) -> set[str]:
    result = set()
    python_apps = [
        cmd[0][len("${PYTHON:") : -1] for cmd in templates if cmd[0].startswith("${PYTHON:")
    ]
    for app in python_apps:
        if app in ROLE_PACKAGES:
            result.add(ROLE_PACKAGES[app][0])
    if ui_mode == "native" and python_apps:
        result.add("native")
    return result


def preflight_apps(specs: list[module_runner.LaunchSpec], extras: set[str]) -> None:
    packages = [
        package
        for extra, required in ROLE_PACKAGES.values()
        if extra in extras
        for package in required
    ]
    if "native" in extras:
        packages.append("rti-demo-ui-native")
    if any(cmd[0] == sys.executable for commands, _, _ in specs for cmd in commands):
        packages.extend(("rti.connext", "rti-demo-ui"))
        generated = platform_setup.generated_system_path() / "python" / "MedTech.py"
        if not generated.is_file():
            raise ValueError(
                f"Missing generated bindings: {generated}. Run `python medtech.py build`."
            )
        expected = check_connext_install.project_python_api_version()
        distributions = [
            (dist.metadata.get("Name", ""), dist.version)
            for dist in importlib.metadata.distributions()
        ]
        namespace_available = importlib.util.find_spec("rti") is not None and (
            importlib.util.find_spec("rti.connextdds") is not None
        )
        errors = check_connext_install.python_api_errors(
            expected,
            distributions,
            namespace_available,
        )
        if errors:
            raise ValueError("\n".join(errors))
    for package in packages:
        try:
            importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            flags = " ".join(f"--extra {extra}" for extra in sorted(extras))
            raise ValueError(
                f"Missing {package}. Run `python medtech.py setup {flags}`.".rstrip()
            ) from exc


@dataclass(frozen=True)
class SecurityProvider:
    preparation: tuple[str, ...]
    resolve_bundle: Callable[[], tuple[Path, str]] | None = None
    prepare_launch: Callable[[list[tuple[str, list[str] | None]]], dict[str, str]] | None = None


def local_bundle() -> tuple[Path, str]:
    return (
        Path(os.environ.get("RTI_SECURITY_ARTIFACTS_DIR", ROOT / "system/security/artifacts")),
        os.environ.get("RTI_SECURITY_DEPLOYMENT_NAME", "local"),
    )


SECURITY_PROVIDERS = {
    DEFAULT_PROVIDER: SecurityProvider(
        preparation=(
            "Issue:  python system/security/setup_security.py",
            "Stage:  python system/security/setup_security.py --stage",
        ),
        resolve_bundle=local_bundle,
    ),
    "eps": SecurityProvider(eps.PREPARATION, prepare_launch=eps.launch_environment),
}


def provider_choice(override: str | None = None) -> str:
    provider = override
    if provider is None and SETTINGS.is_file():
        with SETTINGS.open("rb") as stream:
            settings = tomllib.load(stream)
        provider = settings.get("provider", DEFAULT_PROVIDER)
    if provider is None:
        return DEFAULT_PROVIDER
    if not isinstance(provider, str) or provider not in SECURITY_PROVIDERS:
        raise ValueError(
            f"Unsupported security provider {provider!r}; choose "
            f"{', '.join(SECURITY_PROVIDERS)}. Update {SETTINGS} or pass --provider explicitly."
        )
    return provider


def security_plan(provider: str) -> None:
    print(f"Security provider: {provider} (planning only; no credentials changed)")
    for step in SECURITY_PROVIDERS[provider].preparation:
        print(step)


def check_security(specs: list[module_runner.LaunchSpec], provider: str) -> None:
    # Use the paths already referenced by the runtime QoS, not a second layout.
    resolve_bundle = SECURITY_PROVIDERS[provider].resolve_bundle
    if resolve_bundle is None:
        raise ValueError(f"Provider {provider} has no local bundle resolver.")
    root, deployment = resolve_bundle()
    root = root.resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", deployment) or deployment.endswith("."):
        raise ValueError(f"Invalid RTI_SECURITY_DEPLOYMENT_NAME: {deployment!r}")
    profiles = (ROOT / "system" / "qos" / "SecureAppsQos.xml").read_text(encoding="utf-8")
    roles = set()
    cds = False
    for commands, directory, _ in specs:
        for cmd in commands:
            name = Path(cmd[1] if cmd[0] == sys.executable else cmd[0]).stem
            if directory.name == "01-operating-room":
                roles.add(name)
            elif name == "rtirecordingservice":
                roles.add("RecordingService")
            elif name == "rtireplayservice":
                roles.add("ReplayService")
            elif name == "rtiroutingservice":
                config = cmd[cmd.index("-cfgName") + 1].replace("RsConfig", "Rs", 1)
                roles.add(f"{config}Wan")
                if config in ("RsActive", "RsPassive"):
                    roles.add(f"{config}Lan")
            elif name == "rticlouddiscoveryservice":
                cds = True
    if "ArmControllerGamepad" in roles:
        roles.add("ArmController")
    if "Orchestrator" in roles:
        roles.add("SecureLogReader")
    paths = re.findall(r"file:\$\(RTI_SECURITY_ARTIFACTS_DIR\)/([^<\s]+)", profiles)
    participant_paths = {
        Path(path)
        for path in paths
        if "$(RTI_SECURITY_DEPLOYMENT_NAME)" in path and Path(path).parts[-2] in roles
    }
    domains = {path.parts[0] for path in participant_paths}
    required = {
        path.as_posix()
        .replace("$(RTI_SECURITY_DEPLOYMENT_NAME)", deployment)
        .replace("$(RTI_SECURITY_LAN_DOMAIN_DIR)", "0")
        .replace("$(RTI_SECURITY_WAN_DOMAIN_DIR)", "1")
        for path in participant_paths
    }
    required.update(
        path.replace("$(RTI_SECURITY_LAN_DOMAIN_DIR)", "0").replace(
            "$(RTI_SECURITY_WAN_DOMAIN_DIR)", "1"
        )
        for path in paths
        if len(Path(path).parts) == 2
        and Path(path).parts[0] in domains
        and not path.endswith(("/psk_secret_extra.key", "/crl.pem"))
    )
    if cds:
        required.add("1/psk_secret.key")
    if not required:
        return
    missing = [
        path
        for path in sorted(required)
        if not (root / path).is_file() or not (root / path).stat().st_size
    ]
    if missing:
        security_plan(provider)
        raise ValueError(f"Incomplete security bundle at {root}: {', '.join(missing)}")
    for _, _, env in specs:
        env["RTI_SECURITY_ARTIFACTS_DIR"] = str(root)
        env["RTI_SECURITY_DEPLOYMENT_NAME"] = deployment
        env["RTI_SECURITY_LAN_BASE"] = "CommonSecurityConfig"
        env["RTI_SECURITY_LAN_DOMAIN_DIR"] = "0"
        env["RTI_SECURITY_WAN_BASE"] = "CommonSecurityConfig"
        env["RTI_SECURITY_WAN_DOMAIN_DIR"] = "1"


def parser_for_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare, build and run the MedTech DDS demo.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show additional diagnostics.")
    commands = parser.add_subparsers(dest="action", required=True)
    setup_parser = commands.add_parser("setup", help="Set up the locked workspace environment.")
    setup_parser.add_argument("--extra", action="append", choices=CAPABILITIES, default=[])
    commands.add_parser("build", help="Configure and build with CMake.")
    for name in ("run", "up"):
        sub = commands.add_parser(
            name,
            help="Launch prepared outputs."
            if name == "run"
            else "Set up, build and launch in order.",
        )
        launch.add_launch_arguments(sub)
        sub.add_argument(
            "--provider", choices=SECURITY_PROVIDERS, help="Override the saved provider."
        )
        sub.add_argument(
            "--explain",
            "--preflight",
            action="store_true",
            help="Check prepared outputs and print launch commands without spawning.",
        )
    security = commands.add_parser("security", help="Plan the security prerequisites.")
    plan = security.add_subparsers(dest="operation", required=True).add_parser("plan")
    plan.add_argument("--provider", choices=SECURITY_PROVIDERS)
    plan.add_argument("--save", action="store_true", help="Save only the provider name.")
    return parser


def main() -> int:
    parser = parser_for_cli()
    if launch.argcomplete:
        launch.argcomplete.autocomplete(parser)
    argv = sys.argv[1:]
    split = argv.index("--") if "--" in argv else len(argv)
    args = parser.parse_args(argv[:split])
    if split < len(argv) and args.action != "build":
        parser.error("Trailing CMake arguments are supported only by build.")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    try:
        if args.action == "security":
            provider = provider_choice(args.provider)
            security_plan(provider)
            if args.save:
                SETTINGS.parent.mkdir(exist_ok=True)
                SETTINGS.write_text(f'provider = "{provider}"\n', encoding="utf-8")
            return 0
        if args.action == "setup":
            setup(set(args.extra))
            return 0
        if args.action == "build":
            run_command([project_python(), str(check_connext_install.__file__)])
            build.run_build(argv[split + 1 :])
            return 0
        if args.list_scenarios:
            launch._list_scenarios()
            return 0
        if args.provider is not None and not args.security:
            parser.error("--provider requires --security for run and up.")
        provider = provider_choice(args.provider) if args.security else None
        templates = selected_templates(args)
        prepared_env = None
        prepare_launch = SECURITY_PROVIDERS[provider].prepare_launch if provider else None
        if prepare_launch is not None:
            selection, _ = launch.select_roles(args)
            try:
                prepared_env = prepare_launch(selection)
            except ValueError:
                security_plan(provider)
                raise
        extras = capabilities(templates, args.ui_mode)
        if args.action == "up" and not args.explain:
            setup(extras)
            run_command([str(VENV_PYTHON), str(check_connext_install.__file__)])
            build.run_build(
                ["-DRTI_DEMO_BUILD_NATIVE_WEBVIEW=ON"] if args.ui_mode == "native" else []
            )
            enter_run(
                str(VENV_PYTHON),
                [
                    *(["--verbose"] if args.verbose else []),
                    "run",
                    *argv[argv.index("up") + 1 :],
                ],
            )
            return 0
        needs_python = any(cmd[0].startswith("${PYTHON:") for cmd in templates)
        python = project_python() if needs_python else sys.executable
        if python != sys.executable:
            enter_run(python, argv)
            return 0
        try:
            specs = launch.launch_selection(args)
        except FileNotFoundError as exc:
            raise ValueError(
                f"{exc}. Check the selected Connext environment and build outputs."
            ) from exc
        preflight_apps(specs, extras)
        if prepared_env is not None:
            for commands, _, env in specs:
                env.update(prepared_env)
                for cmd in commands:
                    if Path(cmd[0]).stem == "rticlouddiscoveryservice":
                        cmd[cmd.index("-cfgName") + 1] = "CdsConfigCloudManaged"
        elif provider is not None:
            check_security(specs, provider)
        LOG.debug("Resolved %d module(s); Python: %s", len(specs), sys.executable)
        return module_runner.launch_multi(specs, explain=args.explain)
    except subprocess.CalledProcessError as exc:
        LOG.error("Command exited with status %s.", exc.returncode)
        return exc.returncode if exc.returncode > 0 else 128 - exc.returncode
    except (OSError, ValueError, check_connext_install.PreflightError) as exc:
        LOG.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        return 130
