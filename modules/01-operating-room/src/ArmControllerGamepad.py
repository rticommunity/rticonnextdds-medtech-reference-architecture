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
"""Xbox gamepad input adapter for the Module 01 ArmController DDS role."""

from __future__ import annotations

import os
import signal
import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)
from UiTheme import apply_application_font

CONTROL_PERIOD_SEC = 0.02
HEARTBEAT_PERIOD_SEC = 0.05
AXIS_DEAD_ZONE = 0.35
TELEOP_AXES = ("X", "Y", "ROLL", "GRIPPER")
RTI_BLUE = "#004C97"
RTI_ORANGE = "#ED8B00"
BG_MAIN = "#0A0E17"
BG_PANEL = "#0F1822"
BG_HEADER = "#071020"
COLOR_TEXT = "#E0E8F0"
COLOR_MUTED = "#8FA6BA"
COLOR_CONNECTED = "#00E676"
COLOR_DISCONNECTED = "#FF4444"


def _axis_direction(value: float, *, invert: bool = False) -> str:
    if invert:
        value = -value
    if abs(value) < AXIS_DEAD_ZONE:
        return "STOPPED"
    return "POSITIVE" if value > 0 else "NEGATIVE"


def teleop_directions_from_controls(
    left_x: float,
    left_y: float,
    roll: float,
    gripper_open: bool,
    gripper_close: bool,
) -> dict[str, str]:
    """Translate Xbox controls into the GTK controller's TeleopControl axes."""
    gripper_direction = "STOPPED"
    if gripper_open != gripper_close:
        gripper_direction = "POSITIVE" if gripper_open else "NEGATIVE"

    return {
        "X": _axis_direction(left_x),
        "Y": _axis_direction(left_y, invert=True),
        "ROLL": _axis_direction(roll, invert=True),
        "GRIPPER": gripper_direction,
    }


def active_controls_from_directions(directions: dict[str, str]) -> dict[str, bool]:
    return {
        "LEFT STICK": any(directions[axis] != "STOPPED" for axis in ("X", "Y")),
        "RIGHT STICK": directions["ROLL"] != "STOPPED",
        "LEFT TRIGGER": directions["GRIPPER"] == "POSITIVE",
        "RIGHT TRIGGER": directions["GRIPPER"] == "NEGATIVE",
    }


class GamepadControllerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTI Connext - Xbox Arm Controller")
        self.setMinimumSize(680, 420)
        self.setStyleSheet(
            f"QMainWindow, QWidget {{ background-color: {BG_MAIN}; color: {COLOR_TEXT}; }}"
        )

        icon = QPixmap("../../resource/images/rti_logo.png")
        if not icon.isNull():
            self.setWindowIcon(QIcon(icon))

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(76)
        header.setStyleSheet(f"background-color: {BG_HEADER}; border-bottom: 2px solid {RTI_BLUE};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        if not icon.isNull():
            logo = QLabel()
            logo.setPixmap(
                icon.scaled(
                    48,
                    48,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            header_layout.addWidget(logo)

        brand = QLabel("RTI Connext")
        brand.setStyleSheet(f"color: {RTI_BLUE}; font-size: 20px; font-weight: bold;")
        header_layout.addWidget(brand)

        title = QLabel("|  Xbox Arm Controller")
        title.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 23px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.device_status = QLabel("ON")
        self.device_status.setStyleSheet(
            f"color: #000; background-color: {COLOR_CONNECTED}; font-size: 14px; "
            "font-weight: bold; padding: 5px 12px; border-radius: 4px;"
        )
        header_layout.addWidget(self.device_status)
        root.addWidget(header)

        body = QWidget()
        body.setStyleSheet(f"background-color: {BG_MAIN};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 20)
        body_layout.setSpacing(16)

        connection_card = QFrame()
        connection_card.setStyleSheet(
            f"QFrame {{ background-color: {BG_PANEL}; border: 1px solid #24384B; "
            "border-radius: 8px; }"
        )
        connection_layout = QHBoxLayout(connection_card)
        connection_layout.setContentsMargins(18, 14, 18, 14)
        caption = QLabel("INPUT DEVICE")
        caption.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 12px; font-weight: bold;")
        connection_layout.addWidget(caption)
        connection_layout.addStretch()
        self.connection_status = QLabel()
        self.set_controller_connected(False, "No supported gamepad connected; waiting")
        connection_layout.addWidget(self.connection_status)
        body_layout.addWidget(connection_card)

        controls_card = QFrame()
        controls_card.setStyleSheet(
            f"QFrame {{ background-color: {BG_PANEL}; border: 1px solid #24384B; "
            "border-radius: 8px; }"
        )
        controls_layout = QVBoxLayout(controls_card)
        controls_layout.setContentsMargins(18, 16, 18, 16)
        controls_layout.setSpacing(12)
        controls_title = QLabel("TELEOPERATION CONTROLS")
        controls_title.setStyleSheet(
            f"color: {RTI_ORANGE}; font-size: 13px; font-weight: bold; background: transparent;"
        )
        controls_layout.addWidget(controls_title)
        controls = (
            ("LEFT STICK", "Jog end effector in planar X / Y"),
            ("RIGHT STICK", "Rotate gripper wrist"),
            ("LEFT TRIGGER", "Open gripper"),
            ("RIGHT TRIGGER", "Close gripper"),
        )
        self.control_labels = {}
        for control_name, description in controls:
            row = QHBoxLayout()
            name = QLabel(control_name)
            name.setMinimumWidth(190)
            name.setStyleSheet(self._control_label_style(active=False))
            row.addWidget(name)
            self.control_labels[control_name] = name
            detail = QLabel(description)
            detail.setStyleSheet(f"color: {COLOR_MUTED};")
            row.addWidget(detail)
            row.addStretch()
            controls_layout.addLayout(row)
        body_layout.addWidget(controls_card)
        body_layout.addStretch()

        instruction = QLabel("Hold a control to jog. Return it to neutral to stop that axis.")
        instruction.setStyleSheet(
            f"color: {COLOR_MUTED}; font-size: 12px; background: transparent;"
        )
        body_layout.addWidget(instruction)
        root.addWidget(body, 1)

        footer = QLabel("RTI Connext  ·  MedTech Reference Architecture")
        footer.setFixedHeight(38)
        footer.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        footer.setContentsMargins(20, 0, 20, 0)
        footer.setStyleSheet(
            f"background-color: {BG_HEADER}; color: {COLOR_MUTED}; border-top: 1px solid #1A2A3A;"
        )
        root.addWidget(footer)
        self.setCentralWidget(central)

    def set_controller_connected(self, connected: bool, name: str) -> None:
        if connected:
            self.connection_status.setText(f"●  {name.upper()} CONNECTED")
            color = COLOR_CONNECTED
        else:
            self.connection_status.setText(f"●  {name.upper()}")
            color = COLOR_DISCONNECTED
        self.connection_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def set_device_status(self, status: str) -> None:
        colors = {"ON": COLOR_CONNECTED, "PAUSED": RTI_ORANGE, "OFF": COLOR_DISCONNECTED}
        color = colors.get(status, COLOR_DISCONNECTED)
        self.device_status.setText(status)
        self.device_status.setStyleSheet(
            f"color: #000; background-color: {color}; font-size: 14px; "
            "font-weight: bold; padding: 5px 12px; border-radius: 4px;"
        )

    def set_active_controls(self, active_controls: dict[str, bool]) -> None:
        for name, label in self.control_labels.items():
            is_active = active_controls[name]
            label.setStyleSheet(self._control_label_style(active=is_active))

    @staticmethod
    def _control_label_style(*, active: bool) -> str:
        if active:
            return (
                f"QLabel {{ background-color: #0A332B; color: {COLOR_CONNECTED}; "
                f"border: 1px solid {COLOR_CONNECTED}; border-radius: 4px; "
                "padding: 4px 6px; font-weight: bold; }"
            )
        return (
            f"QLabel {{ background-color: #0D1824; color: {COLOR_TEXT}; "
            "border: 1px solid #24384B; border-radius: 4px; "
            "padding: 4px 6px; font-weight: bold; }"
        )


class ArmControllerGamepadApp:
    def __init__(self):
        self._running = True
        self._participant = None
        self._status = None
        self._status_writer = None
        self._heartbeat_writer = None
        self._teleop_writer = None
        self._command_reader = None
        self._common_types = None
        self._orchestrator_types = None
        self._robot_types = None
        self._teleop_axes = {}
        self._teleop_directions = {}
        self._last_teleop_directions = dict.fromkeys(TELEOP_AXES, "STOPPED")
        self._next_teleop_publish = dict.fromkeys(TELEOP_AXES, 0.0)
        self._next_heartbeat = 0.0
        self._controller_api = None
        self._controller = None
        self._controller_instance_id = None
        self._controller_name = "No supported gamepad connected; waiting"
        self._qt_app = None
        self._window = None
        self._timer = None
        self._shutting_down = False

    def _setup_dds(self) -> None:
        import rti.connextdds as dds
        from DdsUtils import register_type
        from Types import Common, DdsEntities, Orchestrator, SurgicalRobot

        register_type(Common.DeviceStatus)
        register_type(Common.DeviceHeartbeat)
        register_type(Orchestrator.DeviceCommand)
        register_type(SurgicalRobot.TeleopControl)

        entities = DdsEntities.Constants
        self._participant = dds.QosProvider.default.create_participant_from_config(
            entities.ARM_CONTROLLER_DP
        )
        self._status_writer = dds.DataWriter(self._participant.find_datawriter(entities.STATUS_DW))
        self._heartbeat_writer = dds.DataWriter(self._participant.find_datawriter(entities.HB_DW))
        self._teleop_writer = dds.DataWriter(
            self._participant.find_datawriter(entities.TELEOP_CONTROL_DW)
        )
        self._command_reader = dds.DataReader(
            self._participant.find_datareader(entities.DEVICE_COMMAND_DR)
        )

        self._common_types = Common
        self._orchestrator_types = Orchestrator
        self._robot_types = SurgicalRobot
        self._teleop_axes = {
            "X": SurgicalRobot.TeleopAxes.X,
            "Y": SurgicalRobot.TeleopAxes.Y,
            "ROLL": SurgicalRobot.TeleopAxes.ROLL,
            "GRIPPER": SurgicalRobot.TeleopAxes.GRIPPER,
        }
        self._teleop_directions = {
            "STOPPED": SurgicalRobot.TeleopDirections.STOPPED,
            "POSITIVE": SurgicalRobot.TeleopDirections.POSITIVE,
            "NEGATIVE": SurgicalRobot.TeleopDirections.NEGATIVE,
        }
        self._status = Common.DeviceStatus(
            device=Common.DeviceType.ARM_CONTROLLER,
            status=Common.DeviceStatuses.ON,
        )
        self._status_writer.write(self._status)

    def _set_status(self, status) -> None:
        if self._status.status != status:
            self._status.status = status
            self._status_writer.write(self._status)
        if self._window is not None:
            self._window.set_device_status(status.name)

    def _publish_teleop_direction(self, axis_name: str, direction: str) -> None:
        if self._status.status != self._common_types.DeviceStatuses.ON:
            return
        sample = self._robot_types.TeleopControl(
            axis=self._teleop_axes[axis_name],
            direction=self._teleop_directions[direction],
        )
        self._teleop_writer.write(sample)
        self._last_teleop_directions[axis_name] = direction
        self._next_teleop_publish[axis_name] = time.monotonic() + CONTROL_PERIOD_SEC

    def _stop_active_teleop_axes(self) -> None:
        for axis_name, direction in self._last_teleop_directions.items():
            if direction != "STOPPED":
                self._publish_teleop_direction(axis_name, "STOPPED")

    def _process_device_commands(self) -> None:
        for sample in self._command_reader.take_data():
            commands = self._orchestrator_types.DeviceCommands
            if sample.command == commands.PAUSE:
                print("Arm Controller received PAUSE command")
                self._stop_active_teleop_axes()
                self._set_status(self._common_types.DeviceStatuses.PAUSED)
            elif sample.command == commands.START:
                print("Arm Controller received START command")
                self._set_status(self._common_types.DeviceStatuses.ON)
            else:
                print("Arm Controller received SHUTDOWN command")
                self._stop_active_teleop_axes()
                self._set_status(self._common_types.DeviceStatuses.OFF)
                self._running = False
                break

    def _publish_due_teleop_commands(self, desired: dict[str, str], now: float) -> None:
        if self._status.status != self._common_types.DeviceStatuses.ON:
            return

        for axis_name, direction in desired.items():
            previous = self._last_teleop_directions[axis_name]
            if direction != previous or (
                direction != "STOPPED" and now >= self._next_teleop_publish[axis_name]
            ):
                self._publish_teleop_direction(axis_name, direction)

    def _publish_heartbeat_if_due(self, now: float) -> None:
        if now < self._next_heartbeat:
            return
        heartbeat = self._common_types.DeviceHeartbeat(
            device=self._common_types.DeviceType.ARM_CONTROLLER
        )
        self._heartbeat_writer.write(heartbeat)
        self._next_heartbeat = now + HEARTBEAT_PERIOD_SEC

    def _connect_controller(self, device_index: int) -> None:
        if self._controller is not None or not self._controller_api.is_controller(device_index):
            return

        self._controller = self._controller_api.Controller(device_index)
        joystick = self._controller.as_joystick()
        self._controller_instance_id = joystick.get_instance_id()
        self._controller_name = joystick.get_name()
        if not self._controller_name:
            self._controller_name = "Xbox-style controller"
        if self._window is not None:
            self._window.set_controller_connected(True, self._controller_name)
        print(f"Connected gamepad: {self._controller_name}")

    def _disconnect_controller(self) -> None:
        if self._controller is not None:
            self._controller.quit()
        self._controller = None
        self._controller_instance_id = None
        self._controller_name = "No supported gamepad connected; waiting"
        if self._window is not None:
            self._window.set_controller_connected(False, self._controller_name)
        self._stop_active_teleop_axes()
        print(self._controller_name)

    def _handle_events(self, pygame) -> None:
        for event in pygame.event.get():
            if event.type == pygame.CONTROLLERDEVICEADDED:
                self._connect_controller(event.device_index)
            elif (
                event.type == pygame.CONTROLLERDEVICEREMOVED
                and event.instance_id == self._controller_instance_id
            ):
                self._disconnect_controller()

    @staticmethod
    def _normalize_axis(value: int) -> float:
        return max(-1.0, min(1.0, value / 32767.0))

    @staticmethod
    def _normalize_trigger(value: int) -> float:
        return max(0.0, min(1.0, value / 32767.0))

    def _read_gamepad_teleop_directions(self) -> dict[str, str]:
        if self._controller is None:
            return dict.fromkeys(TELEOP_AXES, "STOPPED")

        try:
            return teleop_directions_from_controls(
                self._normalize_axis(self._controller.get_axis(self._pygame.CONTROLLER_AXIS_LEFTX)),
                self._normalize_axis(self._controller.get_axis(self._pygame.CONTROLLER_AXIS_LEFTY)),
                self._normalize_axis(
                    self._controller.get_axis(self._pygame.CONTROLLER_AXIS_RIGHTX)
                ),
                self._normalize_trigger(
                    self._controller.get_axis(self._pygame.CONTROLLER_AXIS_TRIGGERLEFT)
                )
                > AXIS_DEAD_ZONE,
                self._normalize_trigger(
                    self._controller.get_axis(self._pygame.CONTROLLER_AXIS_TRIGGERRIGHT)
                )
                > AXIS_DEAD_ZONE,
            )
        except self._pygame.error as exc:
            print(f"Gamepad input unavailable: {exc}", file=sys.stderr)
            self._disconnect_controller()
            return dict.fromkeys(TELEOP_AXES, "STOPPED")

    def _shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True

        if self._controller is not None:
            self._controller.quit()
            self._controller = None

        try:
            if (
                self._status is not None
                and self._status_writer is not None
                and self._status.status != self._common_types.DeviceStatuses.OFF
            ):
                self._stop_active_teleop_axes()
                self._set_status(self._common_types.DeviceStatuses.OFF)
        finally:
            if self._participant is not None:
                self._participant.close_contained_entities()
                self._participant.close()
                self._participant = None

    def _tick(self, pygame) -> None:
        if not self._running:
            self._qt_app.quit()
            return

        pygame.event.pump()
        self._handle_events(pygame)
        self._process_device_commands()
        if not self._running:
            self._qt_app.quit()
            return

        now = time.monotonic()
        desired = self._read_gamepad_teleop_directions()
        self._publish_due_teleop_commands(desired, now)
        self._publish_heartbeat_if_due(now)
        self._window.set_device_status(self._status.status.name)
        self._window.set_active_controls(active_controls_from_directions(desired))

    def run(self) -> int:
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        try:
            import pygame
            from pygame._sdl2 import controller
            from PySide6.QtWidgets import QApplication
        except ImportError as exc:
            print(
                "The Xbox controller variant requires Pygame CE and PySide6. "
                "Install the root requirements.txt.",
                file=sys.stderr,
            )
            print(exc, file=sys.stderr)
            return 1

        self._pygame = pygame
        self._controller_api = controller
        self._qt_app = QApplication(sys.argv)
        self._qt_app.setStyle("Fusion")
        apply_application_font(self._qt_app)
        self._window = GamepadControllerWindow()
        previous_handlers = {}
        controller_initialized = False

        try:
            pygame.joystick.init()
            pygame.display.init()
            controller.init()
            controller_initialized = True
            self._setup_dds()

            pygame.event.pump()
            pygame.event.clear()
            for device_index in range(controller.get_count()):
                self._connect_controller(device_index)
                if self._controller is not None:
                    break
            if self._controller is None:
                print(self._controller_name)

            for signal_number in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signal_number] = signal.getsignal(signal_number)
                signal.signal(signal_number, self._request_stop)

            self._timer = QTimer(self._window)
            self._timer.timeout.connect(lambda: self._tick(pygame))
            self._timer.start(int(CONTROL_PERIOD_SEC * 1000))
            self._qt_app.aboutToQuit.connect(self._shutdown)
            self._window.show()
            print("Started Xbox Arm Controller")
            return self._qt_app.exec()
        finally:
            try:
                self._shutdown()
            finally:
                if controller_initialized:
                    controller.quit()
                pygame.quit()
                for signal_number, handler in previous_handlers.items():
                    signal.signal(signal_number, handler)

    def _request_stop(self, _signal_number, _frame) -> None:
        self._running = False
        if self._qt_app is not None:
            self._qt_app.quit()


def main() -> int:
    return ArmControllerGamepadApp().run()


if __name__ == "__main__":
    sys.exit(main())
