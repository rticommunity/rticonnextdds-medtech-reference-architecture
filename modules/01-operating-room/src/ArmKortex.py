#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.

"""Supervised Kinova Gen3 Cartesian twist application.

This application uses a software re-arm gate and best-effort zero-twist RPCs.
Commands are bounded by the demo and device-reported hard limits, which are
not physical safety limits. Neither the gate nor operator watchdog assertion
is a physical safety system or a guaranteed stop watchdog.
"""

from __future__ import annotations

import asyncio
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import rti.asyncio  # noqa: F401 - installs Connext's asyncio integration
import rti.connextdds as dds
from ArmCommand import clamp_vector
from DemoUiSupport import (
    DemoUiState,
    create_demo_ui,
    log_failure,
    participant_security_enabled,
    run_app_task,
    run_demo_ui,
)
from HeartbeatPresence import publish_heartbeats
from KortexDevice import KortexDevice, KortexHealth, _load_kortex_api
from MedTech import DdsEntities, Device, Geometry, Robot
from MedTechTypes import device_status_after_command, register_type
from PhysicalMotionGate import MotionConditions, PhysicalMotionGate
from rti_demo_ui import CommandConfirmation

TITLE = "Kinova Gen3 Kortex Arm"
BACKEND_LABEL = "KINOVA · SUPERVISED MOTION"
PREVIEW_LABEL = "KINOVA · OFFLINE PREVIEW"
ARM_ID = "arm-1"
CONTROL_PERIOD = 0.02
TELEMETRY_PERIOD = 0.05
MAX_LINEAR_SPEED = 0.05
MAX_ANGULAR_SPEED = 0.5
_ZERO = (0.0, 0.0, 0.0)
HEALTH_PERIOD = 0.1
HEALTH_MAX_AGE_SECONDS = 0.25
LIVE_WATCHDOG_ACK_ENV = "KORTEX_LIVE_WATCHDOG"
LIVE_WATCHDOG_ACK_VALUE = "VERIFIED_KORTEX_CONNECTION_TIMEOUT_STOP"


def require_live_watchdog_ack() -> None:
    """Require the operator's assertion; this check does not verify stop behavior."""
    if os.environ.get(LIVE_WATCHDOG_ACK_ENV) != LIVE_WATCHDOG_ACK_VALUE:
        raise RuntimeError(
            f"Set {LIVE_WATCHDOG_ACK_ENV}={LIVE_WATCHDOG_ACK_VALUE} to assert that "
            "Kortex connection-timeout stop behavior has been verified; this application "
            "does not test or guarantee that behavior"
        )


def offline_preview() -> bool:
    if LIVE_WATCHDOG_ACK_ENV not in os.environ:
        return True
    require_live_watchdog_ack()
    return False


def _load_control_config_client():
    try:
        from kortex_api.autogen.client_stubs.ControlConfigClientRpc import ControlConfigClient
    except ImportError as exc:
        raise RuntimeError("Kinova motion requires the Kortex ControlConfig client") from exc
    return ControlConfigClient


def bounded_twist(
    linear: tuple[float, float, float],
    angular: tuple[float, float, float],
    linear_limit: float,
    angular_limit: float,
) -> tuple[float, float, float, float, float, float]:
    """Validate DDS m/s and rad/s rates, converting angular rates to deg/s."""
    try:
        linear_values = tuple(float(value) for value in linear)
        angular_values = tuple(float(value) for value in angular)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Kinova twist must contain finite numeric vectors") from exc
    if len(linear_values) != 3 or len(angular_values) != 3:
        raise ValueError("Kinova twist vectors must each contain three values")
    if not all(math.isfinite(value) for value in (*linear_values, *angular_values)):
        raise ValueError("Kinova twist contains a non-finite value")
    bounded_linear = clamp_vector(linear_values, min(MAX_LINEAR_SPEED, linear_limit))
    bounded_angular = clamp_vector(angular_values, min(MAX_ANGULAR_SPEED, angular_limit))
    return (*bounded_linear, *(math.degrees(value) for value in bounded_angular))


class KortexDriver(KortexDevice):
    """Owns Kortex sessions and exposes only feedback, health, twist and close."""

    def __init__(self) -> None:
        super().__init__()
        self._twist_limits: tuple[float, float] | None = None

    def open(self) -> None:
        require_live_watchdog_ack()
        super().open()
        try:
            limits = _load_control_config_client()(self._tcp_router).GetKinematicHardLimits(
                options=self._options()
            )
            for name, limit in (
                ("demo linear m/s", MAX_LINEAR_SPEED),
                ("demo angular rad/s", MAX_ANGULAR_SPEED),
                ("device linear m/s", limits.twist_linear),
                ("device angular deg/s", limits.twist_angular),
            ):
                if not math.isfinite(limit) or limit <= 0:
                    raise ValueError(f"Invalid Kinova {name} limit: {limit}")
            angular_limit = math.radians(limits.twist_angular)
            if angular_limit <= 0:
                raise ValueError("Invalid Kinova device angular rad/s limit after conversion")
            self._twist_limits = (
                min(MAX_LINEAR_SPEED, limits.twist_linear),
                min(MAX_ANGULAR_SPEED, angular_limit),
            )
        except Exception as error:
            try:
                self.close()
            except Exception as cleanup_error:
                raise RuntimeError(
                    f"Kinova limit validation failed ({error}); cleanup failed ({cleanup_error})"
                ) from error
            raise

    def close(self) -> None:
        self._twist_limits = None
        super().close()

    def stop(self) -> None:
        if self._base is None:
            raise RuntimeError("Kinova motion driver is not connected")
        self._base.Stop(options=self._options())

    def send_twist(
        self,
        linear: tuple[float, float, float],
        angular: tuple[float, float, float],
    ) -> None:
        if self._base is None or self._api is None or self._twist_limits is None:
            raise RuntimeError("Kinova motion driver is not connected")
        vx, vy, vz, wx, wy, wz = bounded_twist(linear, angular, *self._twist_limits)
        command = self._api.Base.TwistCommand(
            reference_frame=self._api.Common.CARTESIAN_REFERENCE_FRAME_BASE,
            twist=self._api.Base.Twist(
                linear_x=vx,
                linear_y=vy,
                linear_z=vz,
                angular_x=wx,
                angular_y=wy,
                angular_z=wz,
            ),
        )
        self._base.SendTwistCommand(command, options=self._options())


class ArmKortexApp:
    def __init__(self, ui: DemoUiState, driver: KortexDriver | None = None) -> None:
        self.preview = offline_preview()
        entities = DdsEntities.Constants
        for data_type in (
            Device.Status,
            Device.Heartbeat,
            Device.Command,
            Robot.Arm.TeleopControl,
            Robot.Arm.Telemetry,
        ):
            register_type(data_type)
        provider = dds.QosProvider.default
        self.participant = provider.create_participant_from_config(entities.ARM_KORTEX_DP)
        self.status_writer = dds.DataWriter(self.participant.find_datawriter(entities.STATUS_DW))
        self.heartbeat_writer = dds.DataWriter(self.participant.find_datawriter(entities.HB_DW))
        self.teleop_reader = dds.DataReader(
            self.participant.find_datareader(entities.TELEOP_CONTROL_DR)
        )
        self.telemetry_writer = dds.DataWriter(
            self.participant.find_datawriter(entities.ARM_TELEMETRY_DW)
        )
        self.command_reader = dds.DataReader(
            self.participant.find_datareader(entities.DEVICE_COMMAND_DR)
        )
        self.status_sample = Device.Status(
            device=Device.DeviceType.ARM,
            status=Device.DeviceStatusKind.ON,
        )
        self._last_published_readiness = None
        self._last_diagnostic_at = {}
        self.failed = False
        self.ui = ui
        self.title = TITLE
        self.backend_label = PREVIEW_LABEL if self.preview else BACKEND_LABEL
        self.status = Device.DeviceStatusKind.ON
        self.motion_gate = PhysicalMotionGate()
        self._motion_cancelled = threading.Event()
        self._motion_cancelled.set()
        self.readiness = Device.DeviceReadinessKind.NOT_READY
        self.controller_connected = False
        self.telemetry_sequence = 0
        self.commands_fresh = False
        self.command_rates_neutral = False
        self._control_wake = asyncio.Event()
        self.ui.app.register_command(
            "rearm-motion",
            {"type": "object", "additionalProperties": False},
            self.request_motion_rearm,
            confirmation=CommandConfirmation(
                title="Re-arm software motion gate?",
                message=(
                    "This only changes the demo software gate; it does not establish "
                    "physical safety. Confirm the approved supervised procedure before "
                    "any physical motion."
                ),
            ),
        )
        self.driver = driver or KortexDriver()
        self._rpc_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kortex-rpc")
        self.arm_connected = False
        self.arm_healthy = False
        self._health_observed_at = None
        self._arm_faulted = False
        self._stop_required = False
        self._twist_active = False
        self.observed_pose = None
        self._last_health = None

    def apply_command(self, command: Device.DeviceCommandKind) -> None:
        if (
            self.status == Device.DeviceStatusKind.ERROR
            and command != Device.DeviceCommandKind.SHUTDOWN
        ):
            self._disarm_motion()
            self.ui.log("Kinova fault remains latched; restart after verified recovery", "error")
            return
        self.status = device_status_after_command(command)
        if self.readiness != Device.DeviceReadinessKind.FAULTED:
            self.readiness = Device.DeviceReadinessKind.NOT_READY
        was_armed = self.motion_gate.armed
        self._disarm_motion()
        if was_armed:
            self.ui.log(f"Software motion gate disarmed: received {command.name} command", "warn")
        if command in (Device.DeviceCommandKind.PAUSE, Device.DeviceCommandKind.SHUTDOWN):
            self.teleop_reader.take()

    def view(self) -> dict:
        position, orientation = self.observed_pose if self.observed_pose else (None, None)
        controller_connected = self.controller_connected
        controller_status = "CONTROLLER CONNECTED" if controller_connected else "NO CONTROLLER"
        header_badges = [{"label": "Arm backend", "value": self.backend_label, "tone": "warn"}]
        header_badges.extend(
            [
                {
                    "label": "Controller",
                    "value": controller_status,
                    "tone": "good" if controller_connected else "muted",
                },
                {
                    "label": "Arm readiness",
                    "value": self.readiness.name,
                    "tone": "good"
                    if self.readiness == Device.DeviceReadinessKind.READY
                    else "warn",
                },
            ]
        )
        control_groups = []
        gate_value = "ARMED" if self.motion_gate.armed else "DISARMED"
        header_badges.append(
            {
                "label": "Software motion gate",
                "value": gate_value,
                "tone": "good" if self.motion_gate.armed else "warn",
            }
        )
        control_groups.append(
            {
                "title": "MOTION PERMISSION",
                "layout": "motion-gate",
                "controls": [
                    {
                        "type": "button",
                        "label": "MOTION ARMED" if self.motion_gate.armed else "RE-ARM MOTION",
                        "command": "rearm-motion",
                        "payload": {},
                        "disabled": not self.motion_gate.can_rearm,
                        "className": "run-demo",
                    }
                ],
            }
        )
        return {
            "kind": "arm",
            "device_status": self.status.name,
            "title": self.title,
            "backend_label": self.backend_label,
            "status": self.status.name,
            "scene_available": False,
            "header_badges": header_badges,
            "control_groups": control_groups,
            "show_activity_toggle": True,
            "footer": True,
            "feedback": {
                "source": "reported",
                "publication_sequence": self.telemetry_sequence,
                "readiness": self.readiness.name,
                "status_known": True,
                "position": None if position is None else dict(zip("xyz", position)),
                "orientation": None if orientation is None else dict(zip("xyzw", orientation)),
                "opening_width": None,
            },
        }

    def request_motion_rearm(self, _payload: dict) -> dict[str, bool]:
        if self.preview:
            self.ui.log("Re-arm unavailable in offline preview", "warn")
            return {"armed": False}
        self.rates()
        self.update_motion_gate(connected=self.arm_connected, healthy=self.arm_healthy)
        armed = self.motion_gate.rearm()
        if armed:
            self._motion_cancelled = threading.Event()
        self.ui.log(
            "Software motion gate armed by operator"
            if armed
            else "Re-arm rejected; require a ready arm and fresh neutral commands",
            "ok" if armed else "warn",
        )
        self.ui.update(**self.view())
        return {"armed": armed}

    def update_motion_gate(self, *, connected: bool, healthy: bool) -> None:
        now = time.monotonic()
        health_age = None if self._health_observed_at is None else now - self._health_observed_at
        health_fresh = health_age is not None and 0 <= health_age <= HEALTH_MAX_AGE_SECONDS
        was_armed = self.motion_gate.armed
        self.motion_gate.update(
            MotionConditions(
                arm_connected=connected,
                arm_healthy=health_fresh and healthy and self.status == Device.DeviceStatusKind.ON,
                command_fresh=self.commands_fresh,
                controls_neutral=self.command_rates_neutral,
            )
        )
        if not self.motion_gate.armed:
            self._motion_cancelled.set()
            if was_armed:
                reasons = []
                if not connected:
                    reasons.append("arm disconnected")
                if self.status != Device.DeviceStatusKind.ON:
                    reasons.append(f"device status {self.status.name}")
                if not healthy:
                    reasons.append("arm health not ready")
                if not health_fresh:
                    age = "unavailable" if health_age is None else f"{health_age:.3f} s old"
                    reasons.append(f"health observation {age}")
                if not self.commands_fresh:
                    reasons.append("arm command unavailable or invalid")
                self.ui.log("Software motion gate disarmed: " + "; ".join(reasons), "warn")

    def _disarm_motion(self) -> None:
        self._motion_cancelled.set()
        self.motion_gate.disarm()

    def _controller_writers_match(self) -> bool:
        arm_writers = self.teleop_reader.subscription_matched_status.current_count
        return arm_writers > 0

    def _control_deadline_missed(self, name, reader) -> None:
        was_armed = self.motion_gate is not None and self.motion_gate.armed
        if self.motion_gate is None:
            reader.take()
        else:
            self._disarm_motion()
            self.teleop_reader.take()
        self.commands_fresh = False
        self.command_rates_neutral = False
        message = f"{name} command deadline missed; cached commands discarded"
        if was_armed:
            self.ui.log(message, "warn")
        else:
            self._diagnostic(message)
        self._control_wake.set()

    async def monitor_control_health(self) -> None:
        waitset = dds.WaitSet()
        stop = dds.GuardCondition()
        waitset.attach_condition(stop)
        conditions = []
        for name, reader in (("Arm", self.teleop_reader),):
            condition = dds.StatusCondition(reader)
            condition.enabled_statuses = dds.StatusMask.REQUESTED_DEADLINE_MISSED
            waitset.attach_condition(condition)
            conditions.append((condition, reader, name))
        try:
            while True:
                wait = asyncio.ensure_future(waitset.wait_async())
                try:
                    triggered = await asyncio.shield(wait)
                except asyncio.CancelledError:
                    stop.trigger_value = True
                    while not wait.done():
                        try:
                            await asyncio.shield(wait)
                        except asyncio.CancelledError:
                            continue
                    await wait
                    raise
                for condition, reader, name in conditions:
                    if (
                        condition in triggered
                        and reader.requested_deadline_missed_status.total_count_change
                    ):
                        self._control_deadline_missed(name, reader)
        finally:
            waitset.detach_all()

    async def run(self, app) -> None:
        heartbeat_stop = asyncio.Event()
        workers = []
        enabled = False
        self._heartbeat_stop = heartbeat_stop
        self._workers = workers

        async def task_failed() -> None:
            await self._handle_failure("Kinova background task failed", app)

        async def control_and_observe() -> None:
            loop = asyncio.get_running_loop()
            now = loop.time()
            next_health = now
            next_telemetry = now
            while self.status != Device.DeviceStatusKind.OFF:
                now = loop.time()
                try:
                    if self.preview:
                        self.controller_connected = self._controller_writers_match()
                    else:
                        if now >= next_health:
                            health = await self._rpc(self.driver.read_health)
                            self.apply_health(health)
                            next_health = loop.time() + HEALTH_PERIOD

                        await self.control_step()
                        if loop.time() >= next_telemetry:
                            pose = await self._rpc(self.driver.read_pose)
                            self.observed_pose = pose
                            self.write_telemetry()
                            self.telemetry_sequence += 1
                            self.controller_connected = self._controller_writers_match()
                            next_telemetry = loop.time() + TELEMETRY_PERIOD
                    self.write_readiness(self.readiness)
                    self.ui.update(**self.view())
                    try:
                        await asyncio.wait_for(
                            self._control_wake.wait(),
                            timeout=max(0.0, CONTROL_PERIOD - (loop.time() - now)),
                        )
                    except TimeoutError:
                        pass
                    self._control_wake.clear()
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    log_failure("Kinova control or observation", error)
                    await self._handle_failure(
                        f"Kinova control or observation failed: {error}", app
                    )
                    return

        async def receive_commands() -> None:
            async for sample in self.command_reader.take_data_async():
                command = sample.command
                try:
                    await self.handle_lifecycle_command(command)
                except Exception as error:
                    log_failure("Kinova lifecycle command", error)
                    await self._handle_failure(f"Kinova lifecycle command failed: {error}", app)
                    return
                if self.status == Device.DeviceStatusKind.OFF:
                    heartbeat_stop.set()
                    await app.stop()
                    for task in workers:
                        if task is not asyncio.current_task():
                            task.cancel()
                    return

        failure_context = "Kinova motion startup"
        try:
            self.participant.enable()
            enabled = True
            self.ui.update(dds_security=participant_security_enabled(self.participant))
            self.write_status(self.status)
            self.ui.update(**self.view())
            self.write_readiness(self.readiness)
            if self.preview:
                self.ui.log(
                    "Offline preview: no Kinova connection or motion. Restart with the "
                    "verified watchdog assertion for live operation.",
                    "warn",
                )
            else:
                await self._rpc(self.driver.open)
                self.arm_connected = True
                self.ui.log(
                    "Kinova motion connected; software re-arm required. Watchdog assertion is "
                    "operator-supplied and not verified by this application.",
                    "warn",
                )
            failure_context = "Kinova motion application"
            async with asyncio.TaskGroup() as tasks:
                workers.extend(
                    [
                        tasks.create_task(
                            run_app_task(control_and_observe, "Kinova motion", task_failed)
                        ),
                        tasks.create_task(
                            run_app_task(receive_commands, "Kinova lifecycle", task_failed)
                        ),
                        tasks.create_task(
                            run_app_task(self.monitor_control_health, "Kinova health", task_failed)
                        ),
                        tasks.create_task(
                            run_app_task(
                                lambda: publish_heartbeats(
                                    self.heartbeat_writer,
                                    Device.Heartbeat(device=Device.DeviceType.ARM),
                                    heartbeat_stop,
                                ),
                                "Kinova heartbeat",
                                task_failed,
                            )
                        ),
                    ]
                )
        except Exception as error:
            log_failure(failure_context, error)
            await self._handle_failure(f"{failure_context} failed: {error}", app)
        finally:
            heartbeat_stop.set()
            self._disarm_motion()
            try:
                await self._send_stop(force=True)
            except Exception as error:
                self.failed = True
                log_failure("Kinova final best-effort zero twist", error)
            if not self.preview:
                try:
                    await self._rpc(self.driver.close)
                except Exception as error:
                    self.failed = True
                    log_failure("Kinova SDK cleanup", error)
            try:
                if enabled:
                    if self.status != Device.DeviceStatusKind.OFF:
                        self.write_status(Device.DeviceStatusKind.OFF)
                    if self.readiness != Device.DeviceReadinessKind.FAULTED:
                        self.write_readiness(Device.DeviceReadinessKind.NOT_READY)
            except Exception as error:
                self.failed = True
                log_failure("Kinova final DDS write", error)
            finally:
                try:
                    self.participant.close()
                except Exception as error:
                    self.failed = True
                    log_failure("Kinova participant close", error)
            self._rpc_executor.shutdown(wait=True, cancel_futures=True)
            if self.failed:
                try:
                    await app.stop()
                except Exception as error:
                    log_failure("Kinova UI shutdown", error)

    def _command(self, reader):
        state = dds.DataState(dds.InstanceState.ALIVE)
        for sample in reader.select().state(state).read():
            if sample.info.valid and sample.data.arm_id == ARM_ID:
                return sample.data
        return None

    def _vector(self, value, limit: float) -> tuple[float, float, float]:
        result = (value.x, value.y, value.z)
        bounded = clamp_vector(result, limit)
        if bounded != result:
            self._diagnostic(f"Arm velocity clamped to demo limit {limit}")
        return bounded

    def rates(self):
        arm = self._command(self.teleop_reader)
        self.commands_fresh = arm is not None
        self.command_rates_neutral = False
        if arm is None:
            return _ZERO, _ZERO, 0.0, False
        try:
            linear = self._vector(arm.linear_velocity, MAX_LINEAR_SPEED)
            angular = self._vector(arm.angular_velocity, MAX_ANGULAR_SPEED)
        except ValueError as exc:
            self.commands_fresh = False
            self._diagnostic(str(exc))
            return _ZERO, _ZERO, 0.0, False
        self.command_rates_neutral = all(component == 0.0 for component in (*linear, *angular))
        return linear, angular, 0.0, True

    def _diagnostic(self, message: str) -> None:
        now = asyncio.get_running_loop().time()
        if now - self._last_diagnostic_at.get(message, -math.inf) >= 1.0:
            self.ui.log(message, "warn")
            self._last_diagnostic_at[message] = now

    def write_readiness(self, readiness: Device.DeviceReadinessKind) -> None:
        if readiness != self._last_published_readiness:
            self.status_sample.readiness = readiness
            self.status_writer.write(self.status_sample)
            self._last_published_readiness = readiness

    def write_telemetry(self) -> None:
        assert self.observed_pose is not None
        position, orientation = self.observed_pose
        self.telemetry_writer.write(
            Robot.Arm.Telemetry(
                arm_id=ARM_ID,
                tcp_pose=Geometry.Pose(
                    position=Geometry.Vector3(*position),
                    orientation=Geometry.Quaternion(*orientation),
                ),
                parallel_jaw=None,
            )
        )

    def write_status(self, status: Device.DeviceStatusKind) -> None:
        self.status_sample.status = status
        self.status_sample.readiness = (
            Device.DeviceReadinessKind.NOT_READY
            if status == Device.DeviceStatusKind.OFF
            and self.readiness != Device.DeviceReadinessKind.FAULTED
            else self.readiness
        )
        self.status_writer.write(self.status_sample)
        self._last_published_readiness = self.status_sample.readiness

    async def _rpc(self, function, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._rpc_executor, function, *args)

    def _send_twist(
        self, linear, angular, cancelled: threading.Event, health_observed_at: float | None
    ) -> bool:
        # Revalidate on the SDK worker, not before waiting in its executor queue.
        if (
            cancelled.is_set()
            or health_observed_at is None
            or not (0 <= time.monotonic() - health_observed_at <= HEALTH_MAX_AGE_SECONDS)
        ):
            return False
        self.driver.send_twist(linear, angular)
        return True

    async def _send_stop(self, *, force: bool = False) -> None:
        if not self.arm_connected or (not force and not self._twist_active):
            return
        stop_error = None
        if self._twist_active or force:
            try:
                await self._rpc(self.driver.stop)
            except Exception as error:
                stop_error = error
        try:
            await self._rpc(self.driver.send_twist, _ZERO, _ZERO)
        except Exception as zero_error:
            if stop_error is not None:
                raise RuntimeError(
                    f"Base.Stop failed ({stop_error}); zero twist also failed ({zero_error})"
                ) from stop_error
            raise
        if stop_error is not None:
            raise stop_error
        self._twist_active = False

    def _publish_fault(self, message: str) -> None:
        publish_status = self.status != Device.DeviceStatusKind.ERROR
        self.status = Device.DeviceStatusKind.ERROR
        self.readiness = Device.DeviceReadinessKind.FAULTED
        self.arm_healthy = False
        self._disarm_motion()
        if publish_status:
            self.write_status(self.status)
        if message != self._last_health:
            self.ui.log(message, "error")
            self._last_health = message

    def apply_health(self, health: KortexHealth) -> None:
        if not health.ready:
            was_armed = self.motion_gate.armed
            self._disarm_motion()
            if was_armed and not health.faulted:
                self.ui.log(
                    "Software motion gate disarmed: arm health not ready "
                    f"(ARMSTATE={health.arm_state}, servoing mode={health.servoing_mode})",
                    "warn",
                )
        if not health.ready and (self._health_observed_at is None or self.arm_healthy):
            self._stop_required = True
        self.arm_connected = True
        self.arm_healthy = health.ready
        self._health_observed_at = time.monotonic()
        self._arm_faulted = health.faulted
        if health.faulted:
            self._publish_fault(
                "Kinova fault reported "
                f"(ARMSTATE={health.arm_state}, fault banks "
                f"A=0x{health.fault_bank_a:08x}, B=0x{health.fault_bank_b:08x})"
            )
        elif not health.ready and self.status == Device.DeviceStatusKind.ON:
            self.readiness = Device.DeviceReadinessKind.NOT_READY

    async def control_step(self) -> None:
        linear, angular, _, rates_valid = self.rates()
        self.update_motion_gate(connected=self.arm_connected, healthy=self.arm_healthy)
        allowed = (
            self.status == Device.DeviceStatusKind.ON
            and self.arm_connected
            and self.arm_healthy
            and self.commands_fresh
            and rates_valid
            and self.motion_gate.armed
        )
        if allowed:
            command_active = any((*linear, *angular))
            if not command_active and self._twist_active:
                await self._send_stop()
                health = await self._rpc(self.driver.read_health)
                self.apply_health(health)
                _, _, _, rates_valid = self.rates()
                self.update_motion_gate(connected=self.arm_connected, healthy=self.arm_healthy)
                if (
                    self.status == Device.DeviceStatusKind.ON
                    and self.arm_healthy
                    and rates_valid
                    and self.commands_fresh
                    and self.motion_gate.armed
                ):
                    self.readiness = Device.DeviceReadinessKind.READY
                else:
                    self.readiness = (
                        Device.DeviceReadinessKind.FAULTED
                        if self.readiness == Device.DeviceReadinessKind.FAULTED
                        or self._arm_faulted
                        or self.status == Device.DeviceStatusKind.ERROR
                        else Device.DeviceReadinessKind.NOT_READY
                    )
                return
            if command_active:
                self._twist_active = True
            cancellation = self._motion_cancelled
            health_observed_at = self._health_observed_at
            sent = await self._rpc(
                self._send_twist, linear, angular, cancellation, health_observed_at
            )
            if not sent:
                cancelled = cancellation.is_set()
                health_age = (
                    "unavailable"
                    if health_observed_at is None
                    else f"{time.monotonic() - health_observed_at:.3f} s old"
                )
                self._disarm_motion()
                self.ui.log(
                    "Queued arm command discarded; motion permission expired "
                    f"(at completion: cancelled={cancelled}, health observation {health_age})",
                    "warn",
                )
            self._twist_active = command_active
            if self.status != Device.DeviceStatusKind.ON or not self.motion_gate.armed:
                await self._send_stop(force=True)
                self.readiness = (
                    Device.DeviceReadinessKind.FAULTED
                    if self.readiness == Device.DeviceReadinessKind.FAULTED
                    or self._arm_faulted
                    or self.status == Device.DeviceStatusKind.ERROR
                    else Device.DeviceReadinessKind.NOT_READY
                )
                return
            _, _, _, rates_valid = self.rates()
            self.update_motion_gate(connected=self.arm_connected, healthy=self.arm_healthy)
            if not rates_valid or not self.commands_fresh or not self.motion_gate.armed:
                await self._send_stop(force=True)
                if self.readiness != Device.DeviceReadinessKind.FAULTED:
                    self.readiness = Device.DeviceReadinessKind.NOT_READY
                return
            self.readiness = Device.DeviceReadinessKind.READY
            return

        self.readiness = (
            Device.DeviceReadinessKind.FAULTED
            if self.readiness == Device.DeviceReadinessKind.FAULTED
            or self._arm_faulted
            or self.status == Device.DeviceStatusKind.ERROR
            else Device.DeviceReadinessKind.NOT_READY
        )
        await self._send_stop(force=self._stop_required)
        self._stop_required = False

    async def _handle_failure(self, message: str, app) -> None:
        self.failed = True
        self._disarm_motion()
        try:
            await self._send_stop(force=True)
        except Exception as stop_error:
            log_failure("Kinova best-effort zero twist", stop_error)
        try:
            self._publish_fault(message)
        except Exception as status_error:
            log_failure("Kinova fault status", status_error)
        try:
            self.write_readiness(self.readiness)
        except Exception as readiness_error:
            log_failure("Kinova fault readiness", readiness_error)
        try:
            self.ui.update(**self.view())
        finally:
            self._heartbeat_stop.set()
            for task in self._workers:
                if task is not asyncio.current_task():
                    task.cancel()
            try:
                await app.stop()
            except Exception as stop_error:
                log_failure("Kinova UI shutdown", stop_error)

    async def handle_lifecycle_command(self, command) -> bool:
        self.apply_command(command)
        await self._send_stop(force=True)
        self.write_status(self.status)
        self.write_readiness(self.readiness)
        self.ui.log(f"Received {command.name} command from Orchestrator")
        self.ui.update(**self.view())
        return self.status == Device.DeviceStatusKind.OFF


def configure_ui(app):
    return DemoUiState(
        app,
        kind="arm",
        title=TITLE,
        description="Supervised Kinova Gen3 motion via base-frame twist commands.",
    )


def main() -> int:
    application = None
    result = 1
    try:
        if offline_preview():
            _load_kortex_api()
            _load_control_config_client()
        app = create_demo_ui(TITLE)
        ui = configure_ui(app)
        application = ArmKortexApp(ui)
        run_demo_ui(app, application.run)
        result = int(application.failed)
    except Exception as error:
        log_failure("Kinova motion setup or UI", error)
    finally:
        if application is not None:
            try:
                if not application.participant.closed:
                    application.participant.close()
            except Exception as error:
                log_failure("Kinova motion participant close", error)
                result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
