#!/usr/bin/env python3
"""Top-level launcher — run applications from any module(s) or scenario.

Usage:
    python3 launch.py <module> [apps ...] [-s] [--variant ROLE=CHOICE ...]
    python3 launch.py --scenario <name> [-s] [--variant ROLE=CHOICE ...]
    python3 launch.py --list-scenarios

Examples:
    python3 launch.py 01-operating-room Arm ArmController -s
    python3 launch.py 01-operating-room --variant ArmController=xbox
    python3 launch.py 02-record-playback RecordingService
    python3 launch.py --scenario record -s
    python3 launch.py --scenario or-all --variant ArmController=xbox
    python3 launch.py --scenario record --variant 01-operating-room:ArmController=xbox
    python3 launch.py --list-scenarios
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import argcomplete
except ImportError:
    argcomplete = None

sys.path.insert(0, str(Path(__file__).resolve().parent / "resource" / "python"))
from scripts import module_runner

PROJECT_ROOT = Path(__file__).resolve().parent
SCENARIOS_PATH = PROJECT_ROOT / "resource" / "config" / "scenarios.json"

with open(SCENARIOS_PATH, encoding="utf-8") as f:
    SCENARIOS: dict[str, dict] = json.load(f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_module(
    module_name: str,
    app_names: list[str] | None,
    security: bool,
    variants: dict[tuple[str | None, str], str] | None = None,
) -> tuple[list[list[str]], Path, dict[str, str]]:
    """Load a module's config and return (commands, module_dir, env)."""
    modules = module_runner.discover_modules()
    module_dir = modules[module_name]

    app_variant_names = module_runner.get_app_variant_names(module_dir)
    module_variants = {
        role: choice
        for (scope, role), choice in (variants or {}).items()
        if role in app_variant_names and (scope is None or scope == module_name)
    }
    env, all_apps = module_runner.load_module_config(
        module_dir,
        flags={"security": security},
        variants=module_variants,
    )

    if app_names:
        for name in app_names:
            if name not in all_apps:
                raise ValueError(
                    f"Unknown app '{name}' in module '{module_name}'. "
                    f"Available: {', '.join(all_apps)}"
                )
        commands = [all_apps[app] for app in app_names]
    else:
        commands = list(all_apps.values())

    return commands, module_dir, env


def _parse_variant_selection(value: str) -> tuple[str | None, str, str]:
    """Parse a ``ROLE=CHOICE`` or ``MODULE:ROLE=CHOICE`` selection."""
    selector, separator, choice = value.partition("=")
    if not separator or not selector or not choice:
        raise argparse.ArgumentTypeError(
            "app variants must use ROLE=CHOICE (for example, ArmController=xbox)"
        )
    if ":" not in selector:
        return None, selector, choice

    module_name, role = selector.split(":", 1)
    if not module_name or not role:
        raise argparse.ArgumentTypeError(
            "scoped app variants must use MODULE:ROLE=CHOICE "
            "(for example, 01-operating-room:ArmController=xbox)"
        )
    return module_name, role, choice


def _validate_variant_selections(
    variants: dict[tuple[str | None, str], str],
    module_specs: list[tuple[str, list[str] | None]],
    modules: dict[str, Path],
) -> None:
    """Ensure each requested role is included unambiguously in the launch."""
    if not variants:
        return

    configured_roles: dict[str, set[str]] = {}
    selected_role_modules: dict[str, set[str]] = {}
    selected_assignments: set[tuple[str, str]] = set()
    for module_name, app_names in module_specs:
        role_names = module_runner.get_app_variant_names(modules[module_name])
        configured_roles[module_name] = role_names
        for role in role_names:
            if app_names is None or role in app_names:
                selected_role_modules.setdefault(role, set()).add(module_name)

    target_modules = set(configured_roles)
    for scope, role in variants:
        if scope is not None:
            if scope not in modules:
                raise ValueError(f"Unknown module scope '{scope}' for app variant '{role}'")
            if scope not in target_modules:
                raise ValueError(f"Module '{scope}' is not part of the selected launch")
            if role not in configured_roles[scope]:
                raise ValueError(f"Unknown app variant role '{role}' in module '{scope}'")
            selected_modules = (
                {scope}
                if role in selected_role_modules and scope in selected_role_modules[role]
                else set()
            )
        else:
            configured_in_targets = {
                module_name for module_name, roles in configured_roles.items() if role in roles
            }
            if not configured_in_targets:
                raise ValueError(f"Unknown app variant role '{role}'")
            selected_modules = selected_role_modules.get(role, set())

        if not selected_modules:
            raise ValueError(f"App variant role '{role}' is not included in the selected apps")
        if scope is None and len(selected_modules) > 1:
            raise ValueError(
                f"App variant role '{role}' is defined in multiple selected modules; "
                f"use --variant MODULE:{role}=CHOICE to scope it"
            )
        for module_name in selected_modules:
            assignment = (module_name, role)
            if assignment in selected_assignments:
                raise ValueError(
                    f"App variant role '{role}' was selected more than once for "
                    f"module '{module_name}'"
                )
            selected_assignments.add(assignment)


def _list_scenarios() -> None:
    """Print all available scenarios and exit."""
    print("Available scenarios:\n")
    max_name = max(len(name) for name in SCENARIOS)
    for name, spec in SCENARIOS.items():
        desc = spec.get("description", "")
        modules_str = ", ".join(
            f"{m} ({', '.join(apps) if apps else 'all'})" for m, apps in spec["modules"]
        )
        print(f"  {name:<{max_name}}  {desc}")
        print(f"  {'':<{max_name}}  -> {modules_str}")
        print()


def _complete_apps(prefix, parsed_args, **kwargs):
    """Return app names for the already-selected module (for argcomplete)."""
    module_name = getattr(parsed_args, "module", None)
    if not module_name:
        return []
    modules = module_runner.discover_modules()
    module_dir = modules.get(module_name)
    if not module_dir:
        return []
    try:
        config_path = module_dir / "module.json"
        with open(config_path, encoding="utf-8") as f:
            raw = json.load(f)
        app_variants = raw.get("app_variants", {})
        implementation_names = {
            app_name
            for spec in app_variants.values()
            for app_name in spec.get("choices", {}).values()
        }
        selectable_apps = (set(raw.get("apps", {})) - implementation_names) | set(app_variants)
        return sorted(app for app in selectable_apps if app.startswith(prefix))
    except (AttributeError, OSError, ValueError, json.JSONDecodeError):
        return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    modules = module_runner.discover_modules()

    parser = argparse.ArgumentParser(
        description="Launch applications from module(s) or a predefined scenario.",
        usage=(
            "launch.py (<module> [apps ...] | --scenario <name>) [-s] [--variant ROLE=CHOICE ...]"
        ),
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "module",
        nargs="?",
        choices=sorted(modules),
        default=None,
        help="Module to launch (e.g. 01-operating-room).",
    )
    group.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        metavar="NAME",
        help="Launch a predefined scenario.",
    )
    group.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List all available scenarios and exit.",
    )

    parser.add_argument(
        "apps",
        nargs="*",
        default=None,
        help="Applications to launch (default: all in the module).",
    ).completer = _complete_apps
    parser.add_argument(
        "-s",
        "--security",
        action="store_true",
        help="Launch with Security enabled.",
    )
    parser.add_argument(
        "--variant",
        action="append",
        type=_parse_variant_selection,
        default=[],
        metavar="ROLE=CHOICE",
        help=(
            "Select an app-role implementation; scope duplicate role names as "
            "MODULE:ROLE=CHOICE. May be repeated."
        ),
    )

    if argcomplete:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()
    variants: dict[tuple[str | None, str], str] = {}
    for scope, role, choice in args.variant:
        key = (scope, role)
        if key in variants:
            parser.error(f"App variant role '{role}' was selected more than once")
        variants[key] = choice

    if args.list_scenarios:
        _list_scenarios()
        return

    if args.scenario:
        spec = SCENARIOS[args.scenario]
        unknown_modules = [
            module_name for module_name, _ in spec["modules"] if module_name not in modules
        ]
        if unknown_modules:
            parser.error(f"Scenario references unknown module(s): {', '.join(unknown_modules)}")
        try:
            _validate_variant_selections(variants, spec["modules"], modules)
        except ValueError as exc:
            parser.error(str(exc))
        print(f"Scenario: {args.scenario} — {spec.get('description', '')}")
        if variants:
            print(
                "App variants: "
                + ", ".join(
                    f"{scope + ':' if scope else ''}{role}={choice}"
                    for (scope, role), choice in variants.items()
                )
            )
        specs = []
        for module_name, app_names in spec["modules"]:
            try:
                cmds, mod_dir, env = _resolve_module(
                    module_name,
                    app_names,
                    args.security,
                    variants,
                )
            except ValueError as exc:
                parser.error(str(exc))
            specs.append((cmds, mod_dir, env))
        module_runner.launch_multi(specs)

    elif args.module:
        try:
            _validate_variant_selections(
                variants,
                [(args.module, args.apps or None)],
                modules,
            )
            cmds, mod_dir, env = _resolve_module(
                args.module,
                args.apps or None,
                args.security,
                variants,
            )
        except ValueError as exc:
            parser.error(str(exc))
        app_label = ", ".join(args.apps) if args.apps else "all"
        print(f"Launching from {args.module}: {app_label}")
        if variants:
            print(
                "App variants: "
                + ", ".join(
                    f"{scope + ':' if scope else ''}{role}={choice}"
                    for (scope, role), choice in variants.items()
                )
            )
        module_runner.launch(cmds, mod_dir, env)

    else:
        parser.error("Specify a module or --scenario")


if __name__ == "__main__":
    main()
