#
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

"""Small embedded HTTP server for headless (--web) modes of the Python GUI
apps in this module (Arm, Patient Monitor).

Uses only the Python standard library (no Flask/etc dependency) — serves
static files from a directory and a single JSON state endpoint that a
frontend polls, matching the same polling-over-HTTP approach used by the
C++ apps (Orchestrator, Arm Controller) via cpp-httplib.
"""

from __future__ import annotations

import json
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable


class _Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, web_dir: Path, get_state: Callable[[], dict], **kwargs):
        self._web_dir = web_dir
        self._get_state = get_state
        super().__init__(*args, **kwargs)

    def log_message(self, fmt, *args):
        pass  # keep the app's own console output clean

    def do_GET(self):
        if self.path == "/api/state":
            body = json.dumps(self._get_state()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        self._serve_static()

    def _serve_static(self):
        rel_path = self.path.split("?", 1)[0].lstrip("/")
        if rel_path == "":
            rel_path = "index.html"

        file_path = (self._web_dir / rel_path).resolve()
        try:
            file_path.relative_to(self._web_dir.resolve())
        except ValueError:
            self.send_error(403, "Forbidden")
            return

        if not file_path.is_file():
            self.send_error(404, "Not Found")
            return

        content_types = {
            ".html": "text/html",
            ".js": "application/javascript",
            ".css": "text/css",
        }
        content_type = content_types.get(file_path.suffix, "application/octet-stream")

        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_web_server(web_dir: Path, get_state: Callable[[], dict], port: int) -> ThreadingHTTPServer:
    """Start a background HTTP server serving `web_dir` and a GET /api/state
    endpoint backed by `get_state`. Returns the running server (call
    `.shutdown()` to stop it)."""
    handler = partial(_Handler, web_dir=web_dir, get_state=get_state)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)

    import threading

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd
