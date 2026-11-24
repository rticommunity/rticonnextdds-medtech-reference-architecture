#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software. RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

"""Exercise the actual arm and controller across the Containerlab WAN."""

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests" / "docker"))

from check_wan_lab import Service, check_isolation, node  # noqa: E402

UI_REQUEST = """
import json, sys, urllib.request
base, action = sys.argv[1:3]
if action == "state":
    with urllib.request.urlopen(base + "/api/state", timeout=2) as response:
        print(json.dumps(json.load(response)["data"]))
else:
    with urllib.request.urlopen(base + "/api/command-capability", timeout=2) as response:
        capability = json.load(response)["capability"]
    request = urllib.request.Request(
        base + "/api/commands/" + action, data=b"{}",
        headers={"Content-Type": "application/json", "Origin": base,
                 "X-RTI-Demo-Command-Capability": capability}, method="POST")
    with urllib.request.urlopen(request, timeout=2) as response:
        print(json.dumps(json.load(response)))
"""


class Application:
    def __init__(self, edge, app, directory):
        self.edge = edge
        self.pid_path = f"/tmp/medtech-wan-app-{app}.pid"
        node(edge, "test", "!", "-e", self.pid_path)
        self.log = (directory / f"{app}.log").open("w+")
        command = (
            'source "$NDDSHOME"/resource/scripts/rtisetenv_*.bash; '
            f"echo $$ > {self.pid_path}; "
            f"exec python medtech.py run 01-operating-room {app}"
        )
        self.process = subprocess.Popen(
            [
                "docker",
                "exec",
                "-w",
                "/workspace",
                f"clab-medtechwan-{edge}",
                "bash",
                "-ec",
                command,
            ],
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )

    def output(self):
        self.log.flush()
        return Path(self.log.name).read_text(errors="replace")

    def ensure_running(self):
        if self.process.poll() is not None:
            raise RuntimeError(f"{self.edge} application exited:\n{self.output()}")

    def stop(self):
        if self.process.poll() is None:
            pid = node(self.edge, "cat", self.pid_path, capture_output=True).stdout.strip()
            if not pid.isdecimal():
                raise RuntimeError(f"Invalid application process ID: {pid}")
            node(self.edge, "kill", "-INT", pid)
            self.process.wait(timeout=15)
        node(self.edge, "rm", "-f", self.pid_path)
        self.log.close()


def ui_request(url, action="state"):
    result = node("edge-a", "python", "-c", UI_REQUEST, url, action, capture_output=True)
    return json.loads(result.stdout)


def wait_until(predicate, processes, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            process.ensure_running()
        result = predicate()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError(f"Timed out waiting for {predicate.__name__}")


@unittest.skipUnless(os.environ.get("MEDTECH_WAN_LAB") == "1", "requires the opt-in WAN lab")
class TestWanTeleoperation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            check_isolation()
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                "Could not inspect the WAN lab; start it using the Docker test README. "
                f"Docker reported: {error.stderr or error}"
            ) from error

    def run_scenario(self, scenario):
        active = ("rtiroutingserviceapp", "RsConfigActive.xml", "RsConfigActive")
        routes = []
        applications = []
        with tempfile.TemporaryDirectory() as temp, ExitStack() as cleanup:
            directory = Path(temp)

            def block(src, dst):
                rule = ("FORWARD", "-s", src, "-d", dst, "-j", "DROP")
                node("internet", "iptables", "-I", rule[0], "1", *rule[1:])
                cleanup.callback(node, "internet", "iptables", "-D", *rule)

            def start_route(*args, **kwargs):
                route = Service(*args, **kwargs)
                routes.append(route)
                cleanup.callback(route.stop)

            try:
                applications.append(Application("edge-b", "Arm", directory))
                cleanup.callback(applications[-1].stop)
                applications.append(Application("edge-a", "ArmController", directory))
                cleanup.callback(applications[-1].stop)
                controller = applications[-1]

                def controller_url():
                    match = re.search(
                        r"Arm Controller listening on (http://127\.0\.0\.1:\d+)",
                        controller.output(),
                    )
                    return match.group(1) if match else None

                url = wait_until(controller_url, applications)
                state = ui_request(url)
                self.assertFalse(state.get("feedback", {}).get("freshness", {}).get("telemetry"))

                if scenario == "relay":
                    block("198.18.0.2", "198.18.0.6")
                    block("198.18.0.6", "198.18.0.2")

                if scenario == "public":
                    start_route(
                        "edge-b",
                        "rtiroutingserviceapp",
                        "RsConfigPassive.xml",
                        "RsConfigPassive",
                        directory,
                        public_address="198.18.0.6",
                    )
                    start_route("edge-a", *active, directory, public_address="198.18.0.6")
                else:
                    cloud = (
                        ("rticlouddiscoveryserviceapp", "CdsConfigCloud.xml", "CdsConfigCloud")
                        if scenario == "discovery"
                        else ("rtiroutingserviceapp", "RsConfigCloud.xml", "RsConfigCloud")
                    )
                    start_route("cloud", *cloud, directory)
                    for edge in ("edge-a", "edge-b"):
                        start_route(edge, *active, directory)

                def feedback_ready():
                    feedback = ui_request(url).get("feedback", {})
                    return (
                        feedback
                        if (
                            feedback.get("freshness", {}).get("telemetry")
                            and feedback.get("readiness") == "READY"
                            and feedback.get("position") is not None
                        )
                        else None
                    )

                initial = wait_until(feedback_ready, applications + routes)
                origin = initial["position"]
                self.assertTrue(ui_request(url, "start-demo")["ok"])

                def arm_moved():
                    data = ui_request(url)
                    feedback = data.get("feedback", {})
                    position = feedback.get("position")
                    if not feedback.get("freshness", {}).get("telemetry") or not position:
                        return None
                    distance = math.dist(
                        [origin[axis] for axis in "xyz"], [position[axis] for axis in "xyz"]
                    )
                    return distance if distance > 0.001 else None

                distance = wait_until(arm_moved, applications + routes)
                self.assertTrue(ui_request(url, "stop-demo")["ok"])

                # Break the payload path, including the relay leg where applicable.
                destination = "198.18.0.10" if scenario == "relay" else "198.18.0.6"
                block("198.18.0.2", destination)
                block(destination, "198.18.0.2")

                def feedback_stale():
                    return not (
                        ui_request(url).get("feedback", {}).get("freshness", {}).get("telemetry")
                    )

                wait_until(feedback_stale, applications + routes)
                print(
                    f"{scenario}: observed arm motion ({distance:.4f} m), "
                    "then lost feedback when blocked"
                )
            except Exception:
                for app in applications:
                    print(f"--- {app.edge} application ---\n{app.output()}", file=sys.stderr)
                raise

    def test_public_endpoint(self):
        self.run_scenario("public")

    def test_cloud_discovery(self):
        self.run_scenario("discovery")

    def test_cloud_relay(self):
        self.run_scenario("relay")


if __name__ == "__main__":
    unittest.main()
