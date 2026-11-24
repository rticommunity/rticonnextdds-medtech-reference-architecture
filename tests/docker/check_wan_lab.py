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

"""Exercise the isolated containerlab topology with real Module 03 routes."""

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY = ROOT / "tests/docker/wan-lab.clab.yml"
NODES = ("edge-a", "nat-a", "internet", "nat-b", "edge-b", "cloud")
QOS = "/workspace/system/qos/Qos.xml;/workspace/system/qos/NonSecureAppsQos.xml"
CONFIG = "/workspace/modules/03-remote-teleoperation/xml_config"
SERVICE_BIN = "/opt/rti.com/rti_connext_dds-7.7.0/resource/app/bin/x64Linux4gcc8.5.0"


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, text=True, **kwargs)


def node(name, *args, **kwargs):
    return docker("exec", f"clab-medtechwan-{name}", *args, **kwargs)


def check_isolation():
    for name in NODES:
        info = json.loads(docker("inspect", f"clab-medtechwan-{name}", capture_output=True).stdout)[
            0
        ]
        if (
            info["Config"]["Labels"].get("clab-topo-file") != str(TOPOLOGY)
            or info["HostConfig"]["NetworkMode"] != "none"
            or info["HostConfig"]["IpcMode"] != "private"
            or info["HostConfig"]["RestartPolicy"]["Name"] != "no"
            or not info["State"]["Running"]
        ):
            raise RuntimeError(f"Unexpected ownership, network, restart policy, or state: {name}")
        policies = node(name, "ip6tables", "-S", capture_output=True).stdout.splitlines()
        if not {"-P INPUT DROP", "-P OUTPUT DROP", "-P FORWARD DROP"} <= set(policies):
            raise RuntimeError(f"IPv6 is not blocked on {name}")
    network = json.loads(
        docker("network", "inspect", "medtechwan-mgmt", capture_output=True).stdout
    )
    if network[0]["Containers"]:
        raise RuntimeError("The lab management network has connected containers")
    forward_rules = node("internet", "iptables", "-S", "FORWARD", capture_output=True).stdout
    if forward_rules.strip() != "-P FORWARD ACCEPT":
        raise RuntimeError("The simulated internet has unexpected forwarding rules")


def check_nat():
    server = (
        "import socket,sys; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); "
        "s.settimeout(8); s.bind(('0.0.0.0',int(sys.argv[1]))); "
        "data,addr=s.recvfrom(1024); s.sendto(f'{addr[0]}:{addr[1]}'.encode(),addr)"
    )
    client = (
        "import socket,sys; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); "
        "s.settimeout(8); s.bind((sys.argv[1],int(sys.argv[2]))); "
        "[(s.sendto(b'probe',(host,port)), print(s.recv(1024).decode(),flush=True)) "
        "for host,port in [('198.18.0.10',31001),('198.18.0.5',31002)]]"
    )
    listener = (
        "import socket,sys; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); "
        "s.settimeout(8); s.bind((sys.argv[1],int(sys.argv[2]))); "
        "data,addr=s.recvfrom(1024); print(addr[0],data.decode(),flush=True)"
    )
    sender = (
        "import socket,sys; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); "
        "s.sendto(b'unsolicited',(sys.argv[1],int(sys.argv[2])))"
    )
    for side, local, public, port in (
        ("a", "10.77.1.2", "198.18.0.2", 31101),
        ("b", "10.77.2.2", "198.18.0.6", 31102),
    ):
        servers = [
            subprocess.Popen(
                ["docker", "exec", f"clab-medtechwan-{name}", "python", "-c", server, str(p)]
            )
            for name, p in (("cloud", 31001), ("internet", 31002))
        ]
        try:
            time.sleep(1)
            result = node(
                f"edge-{side}", "python", "-c", client, local, str(port), capture_output=True
            )
            if result.stdout.splitlines() != [f"{public}:{port}"] * 2:
                raise RuntimeError(f"Unexpected NAT mapping for edge {side}: {result.stdout}")
            for proc in servers:
                if proc.wait(timeout=10) != 0:
                    raise RuntimeError("NAT mapping reflector failed")
        finally:
            for proc in servers:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait()

        receive_port = port + 100
        receiver = subprocess.Popen(
            [
                "docker",
                "exec",
                f"clab-medtechwan-edge-{side}",
                "python",
                "-c",
                listener,
                local,
                str(receive_port),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            time.sleep(1)
            node("cloud", "python", "-c", sender, public, str(receive_port))
            output, error = receiver.communicate(timeout=10)
            if receiver.returncode != 0 or output.strip() != "198.18.0.10 unsolicited":
                raise RuntimeError(
                    f"Unsolicited NAT probe failed for edge {side}: {output} {error}"
                )
        finally:
            if receiver.poll() is None:
                receiver.terminate()
                receiver.wait()
    print("NAT: same mapping to two destinations and unsolicited UDP accepted on both edges")


class Service:
    def __init__(
        self, name, executable, config, config_name, log_dir, public_address="198.18.0.10"
    ):
        self.name = name
        self.pid_path = f"/tmp/medtech-wan-{name}.pid"
        node(name, "test", "!", "-e", self.pid_path)
        self.log = (log_dir / f"{name}.log").open("w+")
        shell = (
            f'source "$NDDSHOME"/resource/scripts/rtisetenv_*.bash; '
            f"echo $$ > {self.pid_path}; "
            f'exec "{SERVICE_BIN}/{executable}" -cfgFile "{CONFIG}/{config}" -cfgName {config_name}'
        )
        self.process = subprocess.Popen(
            [
                "docker",
                "exec",
                "-e",
                f"PUBLIC_ADDRESS={public_address}",
                "-e",
                "PUBLIC_PORT=10777",
                "-e",
                "INTERNAL_PORT=10777",
                "-e",
                f"NDDS_QOS_PROFILES={QOS}",
                f"clab-medtechwan-{name}",
                "bash",
                "-ec",
                shell,
            ],
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )

    def ensure_running(self):
        if self.process.poll() is not None:
            self.log.flush()
            self.log.seek(0)
            raise RuntimeError(f"{self.name} service exited:\n{self.log.read()}")

    def stop(self):
        if self.process.poll() is None:
            pid = node(self.name, "cat", self.pid_path, capture_output=True).stdout.strip()
            if not pid.isdecimal():
                raise RuntimeError(f"Invalid process ID for {self.name}")
            node(self.name, "kill", pid)
            self.process.wait(timeout=15)
        elif self.process.returncode != 0:
            self.log.flush()
            self.log.seek(0)
            print(f"{self.name} service exited:\n{self.log.read()}", file=sys.stderr)
        node(self.name, "rm", "-f", self.pid_path)
        self.log.close()


def probes(expected, captures, services):
    capture_procs = [
        subprocess.Popen(
            [
                "docker",
                "exec",
                f"clab-medtechwan-{node_name}",
                "timeout",
                "25",
                "tcpdump",
                "-nn",
                "-l",
                "-c",
                "1",
                "-i",
                interface,
                expression,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for node_name, interface, expression in captures
    ]
    app_procs = []
    try:
        time.sleep(1)
        for side in ("a", "b"):
            app_procs.append(
                subprocess.Popen(
                    [
                        "docker",
                        "exec",
                        f"clab-medtechwan-edge-{side}",
                        "bash",
                        "-ec",
                        'source "$NDDSHOME"/resource/scripts/rtisetenv_*.bash; '
                        f"exec python /workspace/tests/docker/wan_probe.py {side} --seconds 15",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            )
        for proc in app_procs:
            output, _ = proc.communicate(timeout=25)
            match = re.search(r"remote_heartbeats=(\d+)", output)
            if proc.returncode != 0 or match is None:
                raise RuntimeError(f"Heartbeat probe failed:\n{output}")
            count = int(match.group(1))
            if (expected and count < 3) or (not expected and count != 0):
                raise RuntimeError(f"Unexpected heartbeat count: {output}")
            print(output.strip().splitlines()[-1])
        for proc in capture_procs:
            output, error = proc.communicate(timeout=25)
            if proc.returncode != 0 or not output.strip():
                raise RuntimeError(f"Expected WAN packet not observed: {output} {error}")
        for service in services:
            service.ensure_running()
    finally:
        for proc in app_procs + capture_procs:
            if proc.poll() is None:
                proc.terminate()
                proc.wait()


def main():
    check_isolation()
    check_nat()
    active = ("rtiroutingserviceapp", "RsConfigActive.xml", "RsConfigActive")
    drops = [
        ("198.18.0.2", "198.18.0.6"),
        ("198.18.0.6", "198.18.0.2"),
    ]
    with tempfile.TemporaryDirectory() as temp:
        services = []
        try:
            services.append(
                Service(
                    "cloud",
                    "rticlouddiscoveryserviceapp",
                    "CdsConfigCloud.xml",
                    "CdsConfigCloud",
                    Path(temp),
                )
            )
            for side in ("edge-a", "edge-b"):
                services.append(Service(side, *active, Path(temp)))
            time.sleep(5)
            direct = [
                ("internet", "eth1", f"udp and src host {src} and dst host {dst}")
                for src, dst in drops
            ]
            print("Direct positive:")
            probes(True, direct, services)
            for src, dst in drops:
                node(
                    "internet", "iptables", "-I", "FORWARD", "1", "-s", src, "-d", dst, "-j", "DROP"
                )
            print("Direct blocked:")
            probes(False, [], services)
            counters = node(
                "internet", "iptables", "-L", "FORWARD", "-n", "-v", "-x", capture_output=True
            ).stdout
            for src, dst in drops:
                if not any(
                    len(parts := line.split()) >= 9
                    and int(parts[0]) > 0
                    and parts[-2:] == [src, dst]
                    for line in counters.splitlines()[2:]
                ):
                    raise RuntimeError(f"No blocked packets from {src} to {dst}")
            while services:
                services.pop().stop()
            services.append(
                Service(
                    "cloud",
                    "rtiroutingserviceapp",
                    "RsConfigCloud.xml",
                    "RsConfigCloud",
                    Path(temp),
                )
            )
            for side in ("edge-a", "edge-b"):
                services.append(Service(side, *active, Path(temp)))
            time.sleep(5)
            relay = [
                ("cloud", "eth1", f"udp and src host {src} and dst host {dst}")
                for edge in ("198.18.0.2", "198.18.0.6")
                for src, dst in ((edge, "198.18.0.10"), ("198.18.0.10", edge))
            ]
            print("Relay positive with direct path blocked:")
            probes(True, relay, services)
        finally:
            while services:
                services.pop().stop()
            for src, dst in drops:
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        "clab-medtechwan-internet",
                        "iptables",
                        "-C",
                        "FORWARD",
                        "-s",
                        src,
                        "-d",
                        dst,
                        "-j",
                        "DROP",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if result.returncode == 0:
                    node(
                        "internet", "iptables", "-D", "FORWARD", "-s", src, "-d", dst, "-j", "DROP"
                    )
                elif result.returncode != 1:
                    raise RuntimeError(f"Unable to inspect direct-path block: {result.returncode}")


if __name__ == "__main__":
    main()
