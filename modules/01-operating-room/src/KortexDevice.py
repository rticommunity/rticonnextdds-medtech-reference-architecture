#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Kortex connection and read-only health and pose operations."""

import ipaddress
import math
import os
import time
from contextlib import ExitStack
from dataclasses import dataclass
from types import SimpleNamespace

RPC_TIMEOUT_MS = 1000


@dataclass(frozen=True)
class KortexHealth:
    arm_state: int
    servoing_mode: int
    fault_bank_a: int
    fault_bank_b: int
    ready: bool
    faulted: bool
    feedback_state: int | None = None
    state_connection_id: int | None = None
    command_connection_id: int | None = None
    feedback_observed_at: float | None = None


def pose_from_feedback(base) -> tuple[tuple[float, ...], tuple[float, ...]]:
    position = tuple(float(getattr(base, f"tool_pose_{axis}")) for axis in "xyz")
    angles = tuple(float(getattr(base, f"tool_pose_theta_{axis}")) for axis in "xyz")
    if not all(math.isfinite(value) for value in (*position, *angles)):
        raise ValueError("Kinova returned non-finite TCP pose")
    x, y, z = (math.radians(angle) / 2 for angle in angles)
    sx, sy, sz = math.sin(x), math.sin(y), math.sin(z)
    cx, cy, cz = math.cos(x), math.cos(y), math.cos(z)
    return position, (
        sx * cy * cz - cx * sy * sz,
        cx * sy * cz + sx * cy * sz,
        cx * cy * sz - sx * sy * cz,
        cx * cy * cz + sx * sy * sz,
    )


def _load_kortex_api():
    try:
        from kortex_api.autogen.client_stubs.BaseClientRpc import BaseClient
        from kortex_api.autogen.client_stubs.BaseCyclicClientRpc import BaseCyclicClient
        from kortex_api.autogen.messages import Base_pb2, Common_pb2, Session_pb2
        from kortex_api.RouterClient import RouterClient, RouterClientSendOptions
        from kortex_api.SessionManager import SessionManager
        from kortex_api.TCPTransport import TCPTransport
        from kortex_api.UDPTransport import UDPTransport
    except ImportError as exc:
        raise RuntimeError("Kinova requires a compatible Kortex Python SDK") from exc
    return SimpleNamespace(
        RouterClient=RouterClient,
        RouterClientSendOptions=RouterClientSendOptions,
        SessionManager=SessionManager,
        TCPTransport=TCPTransport,
        UDPTransport=UDPTransport,
        BaseClient=BaseClient,
        BaseCyclicClient=BaseCyclicClient,
        Base=Base_pb2,
        Common=Common_pb2,
        Session=Session_pb2,
    )


class KortexDevice:
    def __init__(self) -> None:
        self._api = None
        self._resources: ExitStack | None = None
        self._base = None
        self._cyclic = None
        self._tcp_router = None
        self.connected = False

    def open(self) -> None:
        if self._resources is not None:
            raise RuntimeError("Kinova device is already open")
        ip = os.environ.get("KORTEX_IP")
        username = os.environ.get("KORTEX_USERNAME")
        password = os.environ.get("KORTEX_PASSWORD")
        if not ip or not username or not password:
            raise RuntimeError("Set KORTEX_IP, KORTEX_USERNAME and KORTEX_PASSWORD")
        ipaddress.ip_address(ip)

        api = _load_kortex_api()
        info = api.Session.CreateSessionInfo()
        info.username = username
        info.password = password
        info.session_inactivity_timeout = 60000
        info.connection_inactivity_timeout = RPC_TIMEOUT_MS

        with ExitStack() as resources:
            tcp = api.TCPTransport()
            tcp.connect(ip, 10000)
            resources.callback(tcp.disconnect)
            tcp_router = api.RouterClient(tcp)
            tcp_session = api.SessionManager(tcp_router)
            tcp_session.CreateSession(info)
            resources.callback(tcp_session.CloseSession)

            udp = api.UDPTransport()
            udp.connect(ip, 10001)
            resources.callback(udp.disconnect)
            udp_router = api.RouterClient(udp)
            udp_session = api.SessionManager(udp_router)
            udp_session.CreateSession(info)
            resources.callback(udp_session.CloseSession)

            self._base = api.BaseClient(tcp_router)
            self._cyclic = api.BaseCyclicClient(udp_router)
            self._tcp_router = tcp_router
            self._api = api
            self._resources = resources.pop_all()
            self.connected = True

    def _options(self):
        if self._api is None:
            raise RuntimeError("Kinova device is not connected")
        options = self._api.RouterClientSendOptions()
        options.timeout_ms = RPC_TIMEOUT_MS
        return options

    def read_health(self) -> KortexHealth:
        if self._base is None or self._cyclic is None or self._api is None:
            raise RuntimeError("Kinova device is not connected")
        arm_state = self._base.GetArmState(options=self._options()).active_state
        servoing_mode = self._base.GetServoingMode(options=self._options()).servoing_mode
        feedback = self._cyclic.RefreshFeedback(options=self._options())
        feedback_observed_at = time.monotonic()
        feedback_state = getattr(feedback.base, "active_state", None)
        state_connection_id = getattr(feedback.base, "active_state_connection_identifier", None)
        connection_id = getattr(self._tcp_router, "getConnectionId", None)
        if connection_id is None:
            connection_id = getattr(self._tcp_router, "GetConnectionId", None)
        command_connection_id = connection_id() if callable(connection_id) else None
        fault_bank_a = int(feedback.base.fault_bank_a)
        fault_bank_b = int(feedback.base.fault_bank_b)
        faulted = (
            arm_state == self._api.Common.ARMSTATE_IN_FAULT
            or fault_bank_a != 0
            or fault_bank_b != 0
        )
        ready = (
            not faulted
            and arm_state == self._api.Common.ARMSTATE_SERVOING_READY
            and servoing_mode == self._api.Base.SINGLE_LEVEL_SERVOING
        )
        return KortexHealth(
            arm_state,
            servoing_mode,
            fault_bank_a,
            fault_bank_b,
            ready,
            faulted,
            feedback_state,
            state_connection_id,
            command_connection_id,
            feedback_observed_at,
        )

    def read_pose(self):
        if self._cyclic is None:
            raise RuntimeError("Kinova device is not connected")
        return pose_from_feedback(self._cyclic.RefreshFeedback(options=self._options()).base)

    def close(self) -> None:
        self.connected = False
        self._base = None
        self._cyclic = None
        self._tcp_router = None
        self._api = None
        if self._resources is not None:
            resources, self._resources = self._resources, None
            resources.close()
