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
import os
import platform
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from functools import partial
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


def _interrupt_launch(_signum, _frame) -> None:
    raise KeyboardInterrupt


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


def _open_vscode_tab(url: str, title: str, *, close_token: str | None = None) -> None:
    """Open a localhost app in the MedTech VS Code web-tab extension."""
    parameters = {"url": url, "title": title}
    if close_token is not None:
        parameters["closeToken"] = close_token
    query = urllib.parse.urlencode(parameters)
    _open_vscode_uri(f"vscode://rti.medtech-web-tabs/open?{query}")


def _watch_tab_closures(children, close_tokens, stopped, state_dir=None, sensor_index=None) -> None:
    """Consume one-shot close requests for this launch's exact child processes."""
    if state_dir is None:
        state_dir = Path(tempfile.gettempdir()) / f"medtech-web-tabs-{os.getuid()}"
    pending = dict(close_tokens)
    sensor = children[sensor_index] if sensor_index is not None else None
    sensor_record = state_dir / "PatientSensor.process"

    def record_sensor(pid):
        if pid is None and json.loads(sensor_record.read_text()).get("pid") != children[sensor_index].pid:
            return
        temporary = sensor_record.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps({"pid": pid}))
        temporary.replace(sensor_record)

    if sensor is not None:
        state_dir.mkdir(parents=True, exist_ok=True)
        record_sensor(sensor.pid)
    while (pending or sensor is not None) and not stopped.wait(0.1):
        if sensor is not None and sensor.poll() is not None:
            record_sensor(None)
            sensor = None
        for index, token in list(pending.items()):
            request = state_dir / f"{token}.close"
            child = children[index]
            if request.exists():
                if child.poll() is None:
                    child.kill()
                request.unlink(missing_ok=True)
                del pending[index]
            elif child.poll() is not None:
                del pending[index]
    if sensor is not None and sensor.poll() is not None:
        record_sensor(None)


def _close_vscode_tabs(titles: list[str] | None = None) -> None:
    """Close the specified MedTech tabs, or all tabs for a full demo launch."""
    for title in titles or [None]:
        query = "?" + urllib.parse.urlencode({"title": title}) if title else ""
        _open_vscode_uri(f"vscode://rti.medtech-web-tabs/close{query}")


def _open_vscode_uri(vscode_uri: str) -> None:
    """Dispatch a URI to the MedTech VS Code extension."""
    if os.environ.get("MEDTECH_CLOUD") == "1":
        requests = Path(tempfile.gettempdir()) / f"medtech-web-tabs-{os.getuid()}" / "requests"
        requests.mkdir(parents=True, exist_ok=True)
        request = requests / f"{time.time_ns()}-{uuid.uuid4().hex}.json"
        pending = request.with_suffix(".tmp")
        pending.write_text(json.dumps({"uri": vscode_uri}))
        pending.replace(request)
    elif platform.system() == "Darwin":
        subprocess.run(["open", "-a", "Visual Studio Code", vscode_uri], check=False)
    else:
        webbrowser.open(vscode_uri)


def _open_when_ready(url: str, callback, title: str | None = None) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    if title is None:
                        callback(url)
                    else:
                        callback(url, title)
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    print(f"Web UI did not become ready: {url}", file=sys.stderr)


def _apply_web_flag(
    module_name: str, commands: list[list[str]], *, vscode: bool = False,
    close_tokens: dict[int, str] | None = None,
) -> None:
    """Switch supported GUI apps to their browser-based UI and open their UIs.

    Only 01-operating-room's Orchestrator, ArmController, Arm, and
    PatientMonitor apps currently support --web. Each gets its own fixed
    port so they can all run side by side.
    """
    if module_name != "01-operating-room":
        print(f"Note: --web has no effect for module '{module_name}'.")
        return

    # App name (by executable/script basename) -> web UI port.
    web_ports = {
        "Orchestrator": 8090,
        "ArmController": 8091,
        "Arm.py": 8092,
        "PatientMonitor.py": 8093,
    }

    opened_urls: list[tuple[str, str, str | None]] = []
    for index, cmd in enumerate(commands):
        if not cmd:
            continue
        for app_name, port in web_ports.items():
            if any(Path(part).name == app_name for part in cmd):
                cmd.extend(["--web", "--port", str(port)])
                token = None
                if vscode and close_tokens is not None:
                    token = uuid.uuid4().hex
                    close_tokens[index] = token
                opened_urls.append(
                    (app_name.removesuffix(".py"), f"http://localhost:{port}/", token)
                )
                break

    if not opened_urls:
        print("Note: --web has no effect since no web-capable app was launched.")
        return

    urls = [url for _, url, _ in opened_urls]
    destination = "VS Code tabs" if vscode else "browser tabs"
    print("Web UIs: " + ", ".join(urls) + f" (opening {destination} shortly...)")
    for title, url, token in opened_urls:
        callback = (
            partial(_open_vscode_tab, close_token=token) if vscode else webbrowser.open_new_tab
        )
        threading.Thread(
            target=_open_when_ready,
            args=(url, callback, title if vscode else None),
            daemon=True,
        ).start()


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
        "-s",
        "--security",
        action="store_true",
        help="Launch with Security enabled.",
    )
    ui_group = parser.add_mutually_exclusive_group()
    ui_group.add_argument(
        "--web",
        action="store_true",
        help="Launch 01-operating-room's Orchestrator, ArmController, Arm, and "
        "PatientMonitor with browser-based UIs instead of native GTK/Qt windows.",
    )
    ui_group.add_argument(
        "--vscode",
        action="store_true",
        help="Launch 01-operating-room's browser-based UIs in VS Code editor tabs. "
        "Requires the bundled rti.medtech-web-tabs extension.",
    )

    if argcomplete:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()
    if args.vscode:
        signal.signal(signal.SIGTERM, _interrupt_launch)

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
        close_tokens = {}
        stopped = threading.Event()
        watchers = []

        def watch_children(children):
            sensor_index = next((index for index, command in enumerate(cmds)
                                 if any(Path(part).name == "PatientSensor" for part in command)), None)
            watcher = threading.Thread(
                target=_watch_tab_closures,
                args=(children, close_tokens, stopped, None, sensor_index), daemon=True
            )
            watchers.append(watcher)
            watcher.start()

        if args.web or args.vscode:
            _apply_web_flag(args.module, cmds, vscode=args.vscode, close_tokens=close_tokens)
        try:
            if args.vscode:
                module_runner.launch(
                    cmds, mod_dir, env, on_started=watch_children,
                    keep_alive=args.module == "01-operating-room" and not args.apps,
                )
            else:
                module_runner.launch(cmds, mod_dir, env)
        finally:
            stopped.set()
            for watcher in watchers:
                watcher.join()
            if args.vscode:
                _close_vscode_tabs(args.apps or None)

    else:
        parser.error("Specify a module or --scenario")


if __name__ == "__main__":
    main()
