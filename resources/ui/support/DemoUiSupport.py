#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  The software is
# provided "as is", with no warranty of any type.

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rti_demo_ui import DemoUiApp

if TYPE_CHECKING:
    from rti.connextdds import DomainParticipant

AsyncWork = Callable[[DemoUiApp], Awaitable[None]]
WEB_ROOT = Path(__file__).resolve().parents[1] / "web"


def participant_security_enabled(participant: DomainParticipant) -> bool:
    return participant.qos.property.exists("com.rti.serv.load_plugin")


def native_icon_path() -> Path:
    filename = "rti_logo.ico" if sys.platform == "win32" else "rti_logo.png"
    return WEB_ROOT / filename


def create_demo_ui(title: str) -> DemoUiApp:
    return DemoUiApp(
        title,
        host="127.0.0.1",
        static_root=WEB_ROOT,
        listening_message_prefix=f"{title} listening on",
    )


def log_failure(context: str, error: Exception) -> None:
    print(f"{context} failed: {error}", file=sys.stderr, flush=True)


async def run_app_task(work: Callable[[], Awaitable[None]], name: str, on_failure) -> None:
    try:
        await work()
    except Exception as error:
        log_failure(name, error)
        try:
            await on_failure()
        except Exception as stop_error:
            log_failure(f"{name} shutdown", stop_error)


class DemoUiState:
    def __init__(self, app: DemoUiApp, *, kind: str, title: str, description: str):
        self.app = app
        self.value: dict[str, Any] = {
            "kind": kind,
            "title": title,
            "description": description,
            "status": "STARTING",
            "control_groups": [],
            "devices": [],
            "logs": [],
        }

    def update(self, **fields: Any) -> None:
        self.value.update(fields)
        self.app.set_data(self.value)

    def log(self, message: str, level: str = "info") -> None:
        logs = self.value["logs"]
        logs.append(
            {
                "time": datetime.now().astimezone().strftime("%H:%M:%S"),
                "level": level.lower(),
                "message": message,
            }
        )
        del logs[:-80]
        self.app.set_data(self.value)


def run_demo_ui(app: DemoUiApp, work: AsyncWork) -> None:
    mode = os.environ.get("RTI_DEMO_UI_MODE", "browser").strip().lower()
    if mode not in {"browser", "native"}:
        raise ValueError(f"Unknown RTI_DEMO_UI_MODE '{mode}'; choose browser or native")

    if mode == "native":
        try:
            from rti_demo_ui_native import run_native
        except ImportError as exc:
            raise RuntimeError(
                "Native UI mode requires the optional rti-demo-ui-native package; "
                "sync the native capability and install the platform webview prerequisites"
            ) from exc
        failed = False

        async def native_work(ui: DemoUiApp) -> None:
            nonlocal failed
            try:
                await work(ui)
            except Exception as error:
                failed = True
                log_failure("Application task", error)
                try:
                    await ui.stop()
                except Exception as stop_error:
                    log_failure("UI shutdown", stop_error)

        run_native(app, async_main=native_work, icon=native_icon_path())
        if failed:
            raise SystemExit(1)
        return

    if not asyncio.run(_run_browser(app, work)):
        raise SystemExit(1)


async def _run_browser(app: DemoUiApp, work: AsyncWork) -> bool:
    async def run_task(work, name: str) -> bool:
        try:
            await work()
            return True
        except Exception as error:
            log_failure(name, error)
            return False

    server_task = asyncio.create_task(run_task(app.run, "UI server"))
    ready_task = asyncio.create_task(run_task(app.wait_until_ready, "UI startup"))
    work_task: asyncio.Task[bool] | None = None
    success = True
    loop = asyncio.get_running_loop()
    if os.name != "nt":
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, lambda: asyncio.create_task(app.stop()))

    try:
        done, _ = await asyncio.wait(
            (server_task, ready_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if server_task in done or not ready_task.result():
            if server_task in done and server_task.result():
                print("UI server stopped before becoming ready", file=sys.stderr, flush=True)
            success = False
        else:
            sys.stdout.flush()
            work_task = asyncio.create_task(run_task(lambda: work(app), "Application task"))
            done, _ = await asyncio.wait(
                (server_task, work_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            success = all(task.result() for task in done)
    except Exception as error:
        log_failure("UI runtime", error)
        success = False
    finally:
        try:
            await app.stop()
        except Exception as error:
            log_failure("UI shutdown", error)
            success = False
        for task in (work_task, ready_task, server_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (work_task, ready_task, server_task) if task is not None),
            return_exceptions=True,
        )
        for task in (work_task, ready_task, server_task):
            if task is not None and not task.cancelled() and not task.result():
                success = False
    return success
