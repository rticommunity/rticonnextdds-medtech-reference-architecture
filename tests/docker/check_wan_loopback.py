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

"""Run the isolated, no-NAT Module 03 loopback routing check."""

import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "tests/support"))

import rti.connextdds as dds  # noqa: E402
from test_utils import UtilityApp  # noqa: E402


def main():
    from MedTech import Device

    if {name for _, name in socket.if_nameindex()} != {"lo"}:
        raise RuntimeError("Run this check inside a container with --network none")

    route_dir = root / "modules/03-remote-teleoperation/xml_config"
    qos = ET.parse(root / "system/qos/Qos.xml")
    mask = qos.find(
        ".//qos_library[@name='SystemLibrary']/qos_profile[@name='WanConfig']"
        "/domain_participant_qos/transport_builtin/mask"
    )
    if mask is None or mask.text != "UDPv4_WAN":
        raise RuntimeError("WAN profile must enable UDPv4_WAN only")
    app_qos = ET.parse(root / "system/qos/NonSecureAppsQos.xml")
    for side in ("Passive", "Active"):
        profile = app_qos.find(f".//qos_profile[@name='Rs{side}Wan']")
        if profile is None or profile.get("base_name") != "SystemLibrary::WanConfig":
            raise RuntimeError(f"Unexpected {side} WAN QoS inheritance")
    env = os.environ.copy()
    env.update(
        PUBLIC_ADDRESS="127.0.0.1",
        PUBLIC_PORT="10777",
        INTERNAL_PORT="10777",
        NDDS_QOS_PROFILES=f"{root}/system/qos/Qos.xml;{root}/system/qos/NonSecureAppsQos.xml",
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        processes = []
        logs = []
        apps = []
        capture = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
        capture.bind(("lo", 0))
        capture.setblocking(False)
        try:
            for side, domain in (("Passive", 20), ("Active", 21)):
                config_path = route_dir / f"RsConfig{side}.xml"
                route = ET.parse(config_path)
                wan_qos = route.find(".//participant[@name='WAN_domain']/domain_participant_qos")
                wan_domain = route.findtext(".//participant[@name='WAN_domain']/domain_id")
                if (
                    wan_domain != "1"
                    or wan_qos is None
                    or wan_qos.get("base_name") != f"RtiServicesLib::Rs{side}Wan"
                ):
                    raise RuntimeError(f"Unexpected WAN participant in {side} route")
                config = config_path.read_text()
                if config.count("<domain_id>0</domain_id>") != 1:
                    raise RuntimeError(f"Unexpected local domain configuration in {side} route")
                (temp / f"{side}.xml").write_text(
                    config.replace("<domain_id>0</domain_id>", f"<domain_id>{domain}</domain_id>")
                )

            prototype = UtilityApp.make_non_secure()
            provider = prototype.qos_provider
            prototype.close()
            for domain in (20, 21):
                participant = dds.DomainParticipant(
                    domain, provider.participant_qos_from_profile("DpQosLib::Test")
                )
                participant.enable()
                apps.append(UtilityApp(qos_provider=provider, participant=participant))

            writers = [app.device_heartbeat.writer for app in apps]
            readers = [app.device_heartbeat.reader for app in apps]
            devices = [Device.DeviceType.ARM, Device.DeviceType.PATIENT_SENSOR]

            def start(side):
                log = (temp / f"{side}.log").open("w+")
                logs.append(log)
                processes.append(
                    subprocess.Popen(
                        [
                            "rtiroutingservice",
                            "-cfgFile",
                            str(temp / f"{side}.xml"),
                            "-cfgName",
                            f"RsConfig{side}",
                        ],
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )
                )

            def exchange(seconds):
                seen = set()
                wan_packets = 0
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    for proc in processes:
                        if proc.poll() is not None:
                            raise RuntimeError(f"Routing Service exited: {proc.returncode}")
                    for writer, device in zip(writers, devices):
                        writer.write(Device.Heartbeat(device=device))
                    for index, reader in enumerate(readers):
                        if any(
                            sample.device == devices[1 - index] for sample in reader.take_data()
                        ):
                            seen.add(index)
                    while True:
                        try:
                            packet = capture.recv(65535)
                        except BlockingIOError:
                            break
                        if (
                            len(packet) < 42
                            or packet[12:14] != b"\x08\x00"
                            or packet[23] != 17
                            or packet[26:34] != b"\x7f\x00\x00\x01\x7f\x00\x00\x01"
                        ):
                            continue
                        ip_length = (packet[14] & 15) * 4
                        if len(packet) >= 14 + ip_length + 4:
                            ports = struct.unpack_from("!HH", packet, 14 + ip_length)
                            if 10777 in ports:
                                wan_packets += 1
                    if len(seen) == 2:
                        break
                    time.sleep(0.2)
                return seen, wan_packets

            start("Passive")
            observed, _ = exchange(5)
            if observed:
                raise RuntimeError(f"Inter-domain data without the active route: {observed}")
            print("Negative control: no inter-domain samples with active route absent", flush=True)

            start("Active")
            observed, packets = exchange(30)
            if observed != {0, 1}:
                raise RuntimeError(f"Expected both routed directions, saw {observed}")
            if packets == 0:
                raise RuntimeError("No loopback UDP packets observed on the passive WAN port")
            print(f"Observed {packets} loopback UDP packets on WAN port 10777", flush=True)
            print("Positive: heartbeat samples traversed both WAN routes", flush=True)
        except Exception:
            for log in logs:
                log.flush()
                log.seek(0)
                print(f"--- {log.name} ---")
                print(log.read())
            raise
        finally:
            for proc in processes:
                proc.terminate()
            for proc in processes:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            for log in logs:
                log.close()
            for app in apps:
                app.close()
            capture.close()


if __name__ == "__main__":
    main()
