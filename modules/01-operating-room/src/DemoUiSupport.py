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
from typing import Any

from rti_demo_ui import DemoUiApp

AsyncWork = Callable[[DemoUiApp], Awaitable[None]]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEB_ROOT = PROJECT_ROOT / "resource" / "ui_web"


def native_icon_path() -> Path:
    filename = "rti_logo.ico" if sys.platform == "win32" else "rti_logo.png"
    return WEB_ROOT / filename


def arm_angles_for_view(angles, joints) -> dict[str, float]:
    return {joints[joint]: round(float(angle), 1) for joint, angle in angles.items()}


def create_demo_ui(title: str) -> DemoUiApp:
    return DemoUiApp(
        title,
        host="127.0.0.1",
        static_root=WEB_ROOT,
        listening_message_prefix=f"{title} listening on",
    )


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
                "install requirements-native.txt and the platform webview prerequisites"
            ) from exc
        run_native(app, async_main=work, icon=native_icon_path())
        return

    asyncio.run(_run_browser(app, work))


async def _run_browser(app: DemoUiApp, work: AsyncWork) -> None:
    server_task = asyncio.create_task(app.run())
    work_task: asyncio.Task[None] | None = None
    loop = asyncio.get_running_loop()
    if os.name != "nt":
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, lambda: asyncio.create_task(app.stop()))

    try:
        await app.wait_until_ready()
        sys.stdout.flush()
        work_task = asyncio.create_task(work(app))
        done, _ = await asyncio.wait(
            (server_task, work_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            task.result()
    finally:
        await app.stop()
        for task in (work_task, server_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (work_task, server_task) if task is not None),
            return_exceptions=True,
        )
