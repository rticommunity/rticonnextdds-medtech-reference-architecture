#
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software. RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

"""Browser state and lifecycle shared by the two security demonstration apps."""

from __future__ import annotations

import argparse
import copy
import signal
import threading
import time
from pathlib import Path

import rti.connextdds as dds
from web_server_utils import start_web_server


class ThreatWebApp:
    def __init__(self, kind: str, modes: dict[str, str], port: int):
        self.kind = kind
        self.modes = modes
        self.port = port
        self._participant = None
        self._prev_matched = None
        self._lock = threading.RLock()
        self._stopped = threading.Event()
        self.state = {
            "kind": kind,
            "mode": None,
            "status": "IDLE",
            "logs": [],
            "modes": list(modes),
        }

    def log(self, level: str, message: str):
        self.state["logs"].append(
            {
                "time": time.strftime("%H:%M:%S"),
                "level": level,
                "message": message,
            }
        )
        del self.state["logs"][:-200]
        print(f"[{level}] {message}", flush=True)

    def get_state(self) -> dict:
        with self._lock:
            return copy.deepcopy(self.state)

    def _reset(self):
        self._prev_matched = None

    def _stop(self):
        if self._participant is not None:
            self._participant.close()
            self._participant = None
        self._reset()
        self.state.update(mode=None, status="IDLE")

    def _select_mode(self, mode: str):
        if mode not in self.modes:
            raise ValueError(f"Unknown mode: {mode}")
        self._stop()
        try:
            self._participant = dds.QosProvider.default.create_participant_from_config(
                self.modes[mode]
            )
            self._setup_entities()
        except dds.Error as error:
            self._stop()
            self.state["status"] = "ATTACK FAILED"
            self.log("BLOCKED", f"Participant creation blocked: {error}")
            raise RuntimeError(f"Participant creation blocked: {error}") from error
        self.state.update(mode=mode, status="CONNECTING")
        self.log("INFO", f"Participant created: {mode}")

    def command(self, command: dict) -> dict:
        with self._lock:
            action = command.get("action")
            if action == "mode":
                mode = command.get("mode")
                if not isinstance(mode, str):
                    raise ValueError("mode must be a string")
                self._select_mode(mode)
            elif action == "stop":
                self._stop()
                self.log("INFO", "Attack stopped; returned to idle")
            else:
                self._command(command)
            return self.get_state()

    def _command(self, command: dict):
        raise ValueError(f"Unknown action: {command.get('action')}")

    def _setup_entities(self):
        raise NotImplementedError

    def _poll(self):
        raise NotImplementedError

    def run(self):
        parser = argparse.ArgumentParser(description=f"{self.kind} browser interface")
        parser.add_argument("--port", type=int, default=self.port)
        args = parser.parse_args()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: self._stopped.set())
        web_dir = Path(__file__).resolve().parent.parent / "web"
        httpd = start_web_server(web_dir, self.get_state, args.port, self.command)
        print(f"{self.kind} web UI: http://localhost:{args.port}/", flush=True)
        print(f"Started {self.kind}", flush=True)
        try:
            while not self._stopped.wait(0.05):
                with self._lock:
                    self._poll()
        finally:
            httpd.shutdown()
            httpd.server_close()
            with self._lock:
                self._stop()
