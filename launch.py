#!/usr/bin/env python3
"""Top-level launcher — run applications from any module(s) or scenario.

Usage:
    python3 launch.py <module> [apps ...] [-s]
    python3 launch.py --scenario <name> [-s]
    python3 launch.py --list-scenarios

Examples:
    python3 launch.py 01-operating-room Arm ArmController -s
    python3 launch.py 02-record-playback RecordingService
    python3 launch.py --scenario record -s
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

PROJECT_ROOT = Path(__file__).resolve().parent
SCENARIOS_PATH = PROJECT_ROOT / "resource" / "config" / "scenarios.json"

sys.path.insert(0, str(PROJECT_ROOT / "resource" / "python"))
from scripts import module_runner

with open(SCENARIOS_PATH) as f:
    SCENARIOS: dict[str, dict] = json.load(f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_module(
    module_name: str,
    app_names: list[str] | None,
    security: bool,
) -> tuple[list[list[str]], Path, dict[str, str]]:
    """Load a module's config and return (commands, module_dir, env)."""
    modules = module_runner.discover_modules()
    module_dir = modules[module_name]

    env, all_apps = module_runner.load_module_config(module_dir, flags={"security": security})

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


def _list_scenarios() -> None:
    """Print all available scenarios and exit."""
    print("Available scenarios:\n")
    max_name = max(len(name) for name in SCENARIOS)
    for name, spec in SCENARIOS.items():
        desc = spec.get("description", "")
        modules_str = ", ".join(
            f"{m} ({', '.join(apps) if apps else 'all'})"
            for m, apps in spec["modules"]
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
        with open(config_path) as f:
            raw = json.load(f)
        return [a for a in raw.get("apps", {}) if a.startswith(prefix)]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    modules = module_runner.discover_modules()

    parser = argparse.ArgumentParser(
        description="Launch applications from module(s) or a predefined scenario.",
        usage="launch.py (<module> [apps ...] | --scenario <name>) [-s]",
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
        "-s", "--security",
        action="store_true",
        help="Launch with Security enabled.",
    )

    if argcomplete:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()

    if args.list_scenarios:
        _list_scenarios()
        return

    if args.scenario:
        spec = SCENARIOS[args.scenario]
        print(f"Scenario: {args.scenario} — {spec.get('description', '')}")
        specs = []
        for module_name, app_names in spec["modules"]:
            if module_name not in modules:
                parser.error(f"Scenario references unknown module '{module_name}'")
            cmds, mod_dir, env = _resolve_module(module_name, app_names, args.security)
            specs.append((cmds, mod_dir, env))
        module_runner.launch_multi(specs)

    elif args.module:
        cmds, mod_dir, env = _resolve_module(args.module, args.apps or None, args.security)
        app_label = ", ".join(args.apps) if args.apps else "all"
        print(f"Launching from {args.module}: {app_label}")
        module_runner.launch(cmds, mod_dir, env)

    else:
        parser.error("Specify a module or --scenario")


if __name__ == "__main__":
    main()
