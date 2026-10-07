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

from __future__ import annotations

import signal
import sys
import threading
from pathlib import Path

import rti.connextdds as dds
from PySide6 import QtAsyncio
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Import OR types
sys.path.insert(
    0,
    str(
        Path(__file__).parent.parent.parent.parent.resolve()
        / "modules"
        / "01-operating-room"
        / "src"
    ),
)
import DdsUtils
from Arm import (
    INITIAL_ANGLES,
    JOINT_NAMES,
    SurgicalArmVizWidget,
)
from ThreatTypes import ThreatEntities
from Types import Common, DdsEntities, Orchestrator, SurgicalRobot
from UiTheme import (
    LOG_TOGGLE_STYLE,
    UI_MONOSPACE_FAMILY,
    apply_application_font,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
threat_entities = ThreatEntities.Constants
entities = DdsEntities.Constants

# ─── RTI Brand Colors ────────────────────────────────────────────────────
RTI_BLUE = "#004C97"
RTI_ORANGE = "#ED8B00"
BG_MAIN = "#0A0E17"
BG_PANEL = "#0F1822"
BG_HEADER = "#071020"
BORDER_DIM = "#1A2535"
COLOR_OK = "#00E676"
COLOR_WARN = "#ED8B00"
COLOR_BLOCKED = "#FF4444"
COLOR_IDLE = "#445566"
COLOR_ATTEMPTING = "#1E88E5"
COLOR_GRANTED = "#00C853"

UPDATE_MS = 100

# ─── Left-panel button styles ─────────────────────────────────────────────
_STYLE_MODE_INACTIVE = (
    "QPushButton { background-color: #0D1824; color: #4A6070; "
    "border: 1px solid #1A2A38; border-radius: 5px; padding: 0px 12px; "
    "font-size: 13px; font-weight: bold; text-align: left; }"
    "QPushButton:hover { background-color: #162030; color: #90AAB8; border-color: #2A3A4A; }"
)
_STYLE_MODE_ACTIVE_UNSECURE = (
    f"QPushButton {{ background-color: #0A1E35; color: {COLOR_ATTEMPTING}; "
    f"border: 2px solid {COLOR_ATTEMPTING}; border-radius: 5px; padding: 0px 12px; "
    f"font-size: 13px; font-weight: bold; text-align: left; }}"
)
_STYLE_MODE_ACTIVE_THREAT = (
    f"QPushButton {{ background-color: #2A0C0C; color: {COLOR_BLOCKED}; "
    f"border: 2px solid {COLOR_BLOCKED}; border-radius: 5px; padding: 0px 12px; "
    f"font-size: 13px; font-weight: bold; text-align: left; }}"
)
_STYLE_ATTACK_INACTIVE = (
    "QPushButton { background-color: #0D1824; color: #4A6070; "
    "border: 1px solid #1A2A38; border-radius: 5px; padding: 0px 12px; "
    "font-size: 12px; font-weight: bold; text-align: left; }"
    "QPushButton:hover { background-color: #162030; color: #90AAB8; border-color: #2A3A4A; }"
)
_STYLE_ATTACK_ACTIVE = (
    f"QPushButton {{ background-color: #1E1200; color: {COLOR_WARN}; "
    f"border: 2px solid {COLOR_WARN}; border-radius: 5px; padding: 0px 12px; "
    f"font-size: 12px; font-weight: bold; text-align: left; }}"
)
_STYLE_STOP_ENABLED = (
    f"QPushButton {{ background-color: #1E0A0A; color: #FF5555; "
    f"border: 1px solid #FF444455; border-radius: 5px; padding: 0px 12px; "
    f"font-size: 13px; font-weight: bold; }}"
    f"QPushButton:hover {{ background-color: #2E1010; border-color: {COLOR_BLOCKED}; }}"
)
_STYLE_STOP_DISABLED = (
    "QPushButton { background-color: #0D1520; color: #2A3848; "
    "border: 1px solid #182028; border-radius: 5px; padding: 0px 12px; "
    "font-size: 13px; font-weight: bold; }"
)

_MOTORS_ORDERED = [
    SurgicalRobot.Motors.BASE,
    SurgicalRobot.Motors.SHOULDER,
    SurgicalRobot.Motors.ELBOW,
    SurgicalRobot.Motors.WRIST,
    SurgicalRobot.Motors.HAND,
]

# Attack mode constants
MODE_UNSECURE = "UNSECURE"
MODE_ROGUE_CA = "ROGUE CA"
MODE_FORGED_PERMS = "FORGED PERMS"
MODE_EXPIRED_CERT = "EXPIRED CERT"

# Attack type constants
ATTACK_MOTOR_INJECT = "MOTOR INJECT"
ATTACK_CMD_PAUSE = "CMD INJECT (PAUSE)"
ATTACK_CMD_SHUTDOWN = "CMD INJECT (SHUTDOWN)"

MODE_TO_DP_NAME = {
    MODE_UNSECURE: threat_entities.INJECTOR_UNSECURE_DP,
    MODE_ROGUE_CA: threat_entities.INJECTOR_ROGUE_CA_DP,
    MODE_FORGED_PERMS: threat_entities.INJECTOR_FORGED_PERMS_DP,
    MODE_EXPIRED_CERT: threat_entities.INJECTOR_EXPIRED_CERT_DP,
}


# ─── Main Window ─────────────────────────────────────────────────────────
class ThreatInjectorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTI Connext — Threat Injector")
        self.setMinimumSize(900, 680)
        self.resize(1100, 720)
        self.setStyleSheet(f"background-color: {BG_MAIN};")
        self._log_event_count = 0
        self.log_panel: QWidget | None = None
        self.log_toggle: QPushButton | None = None

        _icon_px = QPixmap("../../resource/images/rti_logo.png")
        if not _icon_px.isNull():
            self.setWindowIcon(QIcon(_icon_px))

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background-color: {BG_MAIN};")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(10, 10, 10, 10)
        body.setSpacing(10)

        body.addWidget(self._build_left_panel(), 0)
        body.addWidget(self._build_arm_viz(), 1)
        self.log_panel = self._build_log_panel()
        body.addWidget(self.log_panel, 1)

        body_widget = QWidget()
        body_widget.setStyleSheet(f"background-color: {BG_MAIN};")
        body_widget.setLayout(body)
        root.addWidget(body_widget, 1)

        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(80)
        header.setStyleSheet(f"background-color: {BG_HEADER}; border-bottom: 2px solid {RTI_BLUE};")
        h = QHBoxLayout(header)
        h.setContentsMargins(20, 0, 20, 0)

        _logo_px = QPixmap("../../resource/images/rti_logo.png")
        if not _logo_px.isNull():
            logo = QLabel()
            logo.setStyleSheet("background: transparent;")
            logo.setPixmap(
                _logo_px.scaled(
                    52,
                    52,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            h.addWidget(logo)

        rti_lbl = QLabel("RTI Connext")
        rti_lbl.setStyleSheet(
            f"color: {RTI_BLUE}; font-size: 20px; font-weight: bold; background: transparent;"
        )
        h.addWidget(rti_lbl)

        sep = QLabel("|")
        sep.setStyleSheet("color: #334455; font-size: 28px; background: transparent;")
        h.addWidget(sep)

        title = QLabel("Threat Injector")
        title.setStyleSheet(
            "color: #E0E8F0; font-size: 28px; font-weight: bold; background: transparent;"
        )
        h.addWidget(title)
        h.addStretch()

        simulation_lbl = QLabel("SIMULATION · NOT FOR CLINICAL USE")
        simulation_lbl.setStyleSheet(
            "color: #EDB252; font-size: 12px; font-weight: bold; background: transparent;"
        )
        h.addWidget(simulation_lbl)

        self.status_badge = QLabel("IDLE")
        self.status_badge.setStyleSheet(
            f"color: #fff; background-color: {COLOR_IDLE}; font-size: 16px; "
            f"font-weight: bold; padding: 4px 12px; border-radius: 4px; margin-left: 10px;"
        )
        h.addWidget(self.status_badge)

        self.log_toggle = QPushButton()
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(True)
        self.log_toggle.setStyleSheet(LOG_TOGGLE_STYLE)
        self.log_toggle.toggled.connect(self._set_log_visible)
        self._update_log_toggle_label()
        h.addWidget(self.log_toggle)
        return header

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setFixedHeight(44)
        footer.setStyleSheet(f"background-color: {BG_HEADER}; border-top: 1px solid {BORDER_DIM};")
        f = QHBoxLayout(footer)
        f.setContentsMargins(20, 0, 20, 0)
        lbl = QLabel("Real-Time Innovations  ·  RTI Connext  ·  MedTech Reference Architecture")
        lbl.setStyleSheet("color: #8FA6BA; font-size: 12px; background: transparent;")
        f.addWidget(lbl)
        f.addStretch()
        return footer

    def _build_left_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.Box)
        panel.setFixedWidth(310)
        panel.setStyleSheet(
            f"background-color: {BG_PANEL}; border: 1px solid {RTI_BLUE}33; border-radius: 6px;"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Attack Mode buttons ────────────────────────────────────
        mode_lbl = QLabel("ATTACK MODE")
        mode_lbl.setStyleSheet(
            f"color: {RTI_BLUE}; font-size: 12px; font-weight: bold; background: transparent; "
            f"letter-spacing: 1px; border-bottom: 1px solid {RTI_BLUE}44; padding-bottom: 6px;"
        )
        layout.addWidget(mode_lbl)

        self._mode_buttons: dict[str, QPushButton] = {}
        for mode in [
            MODE_UNSECURE,
            MODE_ROGUE_CA,
            MODE_FORGED_PERMS,
            MODE_EXPIRED_CERT,
        ]:
            btn = QPushButton(mode)
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_STYLE_MODE_INACTIVE)
            self._mode_buttons[mode] = btn
            layout.addWidget(btn)

        layout.addSpacing(6)

        # ── Attack Type buttons ────────────────────────────────────
        atk_lbl = QLabel("ATTACK TYPE")
        atk_lbl.setStyleSheet(
            f"color: {RTI_ORANGE}; font-size: 12px; font-weight: bold; background: transparent; "
            f"letter-spacing: 1px; border-bottom: 1px solid {RTI_ORANGE}44; padding-bottom: 6px;"
        )
        layout.addWidget(atk_lbl)

        self._attack_buttons: dict[str, QPushButton] = {}
        for atk in [ATTACK_MOTOR_INJECT, ATTACK_CMD_PAUSE, ATTACK_CMD_SHUTDOWN]:
            btn = QPushButton(atk)
            btn.setFixedHeight(38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_STYLE_ATTACK_INACTIVE)
            self._attack_buttons[atk] = btn
            layout.addWidget(btn)

        layout.addSpacing(6)

        # ── Frequency slider ───────────────────────────────────────
        freq_hdr = QLabel("Inject Frequency (Hz)")
        freq_hdr.setStyleSheet(
            f"color: {RTI_ORANGE}; "
            f"font-size: 12px; "
            f"font-weight: bold; "
            f"background: transparent; "
            f"letter-spacing: 1px;"
        )
        layout.addWidget(freq_hdr)
        self.freq_slider = QSlider(Qt.Orientation.Horizontal)
        self.freq_slider.setMinimum(1)
        self.freq_slider.setMaximum(20)
        self.freq_slider.setValue(5)
        self.freq_slider.setStyleSheet(
            f"QSlider::handle:horizontal "
            f"{{ background: {RTI_ORANGE}; border-radius: 5px; width: 12px; height: 12px; }}"
        )
        layout.addWidget(self.freq_slider)
        self.freq_lbl = QLabel("5 Hz")
        self.freq_lbl.setStyleSheet("color: #C0D0E0; font-size: 12px; background: transparent;")
        layout.addWidget(self.freq_lbl)
        self.freq_slider.valueChanged.connect(lambda v: self.freq_lbl.setText(f"{v} Hz"))

        layout.addSpacing(6)

        # ── Stop All button ────────────────────────────────────────
        self._stop_btn = QPushButton("\u25a0  STOP ATTACK")
        self._stop_btn.setFixedHeight(38)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(_STYLE_STOP_DISABLED)
        layout.addWidget(self._stop_btn)

        layout.addSpacing(4)

        # ── Launch/Stop injection button ───────────────────────────
        self.launch_btn = QPushButton("\u26a1  LAUNCH ATTACK")
        self.launch_btn.setFixedHeight(50)
        self.launch_btn.setEnabled(False)
        self.launch_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BLOCKED};
                color: #fff;
                font-size: 18px; font-weight: bold;
                border-radius: 6px;
                border: none;
            }}
            QPushButton:hover {{ background-color: #FF6666; }}
            QPushButton:pressed {{ background-color: #CC0000; }}
            QPushButton:disabled {{ background-color: #1A2535; color: #2A3848; }}
        """)
        layout.addWidget(self.launch_btn)

        layout.addStretch()
        return panel

    def _build_arm_viz(self) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.Box)
        frame.setStyleSheet(
            f"background-color: {BG_PANEL}; border: 1px solid {RTI_BLUE}33; border-radius: 6px;"
        )
        v = QVBoxLayout(frame)
        v.setContentsMargins(6, 6, 6, 6)
        self.arm_viz = SurgicalArmVizWidget()
        self.arm_viz.set_active(False)
        v.addWidget(self.arm_viz)
        return frame

    def _build_log_panel(self) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.Box)
        frame.setStyleSheet(
            f"background-color: {BG_PANEL}; border: 1px solid {RTI_BLUE}33; border-radius: 6px;"
        )
        v = QVBoxLayout(frame)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(4)

        hdr = QLabel("SECURITY ACTIVITY")
        hdr.setStyleSheet(
            f"color: {RTI_BLUE}; font-size: 14px; font-weight: bold; background: transparent; "
            f"border-bottom: 1px solid {RTI_BLUE}44; padding-bottom: 4px;"
        )
        v.addWidget(hdr)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #060C14;
                color: #A0B0C0;
                font-family: "{UI_MONOSPACE_FAMILY}";
                font-size: 10pt;
                border: none;
            }}
        """)
        v.addWidget(self.log_text)
        return frame

    # ── Public update methods ─────────────────────────────────────────────

    def set_data_status(self, status: str):
        """status: 'IDLE', 'ACCESS GRANTED', 'ATTACKING', 'NO ACCESS', 'ATTACK FAILED'"""
        colors = {
            "IDLE": (COLOR_IDLE, "#fff"),
            "ACCESS GRANTED": (COLOR_GRANTED, "#000"),
            "ATTACKING": (COLOR_GRANTED, "#000"),
            "NO ACCESS": (COLOR_WARN, "#000"),
            "ATTACK FAILED": (COLOR_BLOCKED, "#fff"),
        }
        bg, fg = colors.get(status, (COLOR_IDLE, "#fff"))
        self.status_badge.setText(status)
        self.status_badge.setStyleSheet(
            f"color: {fg}; background-color: {bg}; font-size: 16px; "
            f"font-weight: bold; padding: 4px 12px; border-radius: 4px; margin-left: 10px;"
        )

    def _set_log_visible(self, visible: bool) -> None:
        if self.log_panel is not None:
            self.log_panel.setVisible(visible)
        self._update_log_toggle_label()

    def _update_log_toggle_label(self) -> None:
        if self.log_toggle is None:
            return
        arrow = "▾" if self.log_toggle.isChecked() else "▸"
        event_word = "EVENT" if self._log_event_count == 1 else "EVENTS"
        self.log_toggle.setText(f"{arrow}  LOG · {self._log_event_count} {event_word}")

    def highlight_mode_button(self, active_mode: str | None) -> None:
        for mode, btn in self._mode_buttons.items():
            if mode == active_mode:
                style = (
                    _STYLE_MODE_ACTIVE_UNSECURE
                    if mode == MODE_UNSECURE
                    else _STYLE_MODE_ACTIVE_THREAT
                )
                btn.setStyleSheet(style)
            else:
                btn.setStyleSheet(_STYLE_MODE_INACTIVE)
        is_active = active_mode is not None
        self._stop_btn.setEnabled(is_active)
        self._stop_btn.setStyleSheet(_STYLE_STOP_ENABLED if is_active else _STYLE_STOP_DISABLED)

    def highlight_attack_button(self, active_attack: str | None) -> None:
        for atk, btn in self._attack_buttons.items():
            btn.setStyleSheet(
                _STYLE_ATTACK_ACTIVE if atk == active_attack else _STYLE_ATTACK_INACTIVE
            )

    def set_attack_buttons_enabled(self, enabled: bool) -> None:
        for btn in self._attack_buttons.values():
            btn.setEnabled(enabled)

    def log(self, level: str, msg: str):
        """Append a coloured log entry. level: 'OK', 'WARN', 'BLOCKED', 'INFO', 'SECURITY'"""
        self._log_event_count += 1
        self._update_log_toggle_label()
        colors = {
            "OK": COLOR_OK,
            "WARN": COLOR_WARN,
            "BLOCKED": COLOR_BLOCKED,
            "INFO": "#6699AA",
            "SECURITY": "#FF6D00",
        }
        c = colors.get(level, "#C0D0E0")
        self.log_text.append(
            f'<span style="color:{c}; font-weight:bold;">[{level}]</span>'
            f' <span style="color:#C0D0E0;">{msg}</span>'
        )
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def set_launch_btn_active(self, active: bool):
        if active:
            self.launch_btn.setText("■  STOP INJECTION")
            self.launch_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {RTI_ORANGE};
                    color: #000; font-size: 18px; font-weight: bold;
                    border-radius: 6px; border: none;
                }}
                QPushButton:hover {{ background-color: #FFB020; }}
                QPushButton:disabled {{ background-color: #1A2535; color: #2A3848; }}
            """)
        else:
            self.launch_btn.setText("⚡  LAUNCH ATTACK")
            self.launch_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_BLOCKED};
                    color: #fff; font-size: 18px; font-weight: bold;
                    border-radius: 6px; border: none;
                }}
                QPushButton:hover {{ background-color: #FF6666; }}
                QPushButton:pressed {{ background-color: #CC0000; }}
                QPushButton:disabled {{ background-color: #1A2535; color: #2A3848; }}
            """)

    def get_frequency(self) -> int:
        return self.freq_slider.value()


# ─── Application class ────────────────────────────────────────────────────
class ThreatInjectorApp:
    def __init__(self):
        self.window: ThreatInjectorWindow = None
        self._participant = None
        self._motor_writer = None
        self._cmd_writer = None
        self._current_mode: str | None = None
        self._current_attack = None
        self._attacking = False
        self._attack_timer = QTimer()
        self._attack_timer.timeout.connect(self._do_inject)
        self._angles = dict(INITIAL_ANGLES)
        self._inject_directions = {
            m: SurgicalRobot.MotorDirections.INCREMENT for m in _MOTORS_ORDERED
        }
        self._motor_idx = 0
        self._tick = 0
        self._participant_lock = threading.Lock()
        self._cert_invalid = False
        self._prev_matched = None

    def _update_slider_enabled(self):
        enabled = (
            self._current_mode is not None
            and self._current_attack == ATTACK_MOTOR_INJECT
            and not self._attacking
        )
        self.window.freq_slider.setEnabled(enabled)

    # ── DDS participant lifecycle ─────────────────────────────────────────

    def _setup_participant(self, mode: str):
        """Tear down any existing participant and create a new one for the given mode."""
        with self._participant_lock:
            if self._participant is not None:
                self.window.log("INFO", "Participant destroyed — switching mode")
                try:
                    self._participant.close()
                except Exception:
                    pass
                self._participant = None
                self._motor_writer = None
                self._cmd_writer = None
                self._cert_invalid = False
                self._prev_matched = None

            dp_name = MODE_TO_DP_NAME.get(mode, threat_entities.INJECTOR_UNSECURE_DP)
            try:
                qos_provider = dds.QosProvider.default
                self._participant = qos_provider.create_participant_from_config(dp_name)
                self._motor_writer = dds.DataWriter(
                    self._participant.find_datawriter(entities.MOTOR_CONTROL_DW)
                )
                self._cmd_writer = dds.DataWriter(
                    self._participant.find_datawriter(entities.DEVICE_COMMAND_DW)
                )
                self.window.log("INFO", f"Participant created — {mode}")

                self.window.highlight_mode_button(mode)
                self.window.launch_btn.setEnabled(True)
                self.window.set_attack_buttons_enabled(True)
                self.window.arm_viz.set_active(True)
                if self._current_attack is None:
                    self._current_attack = ATTACK_MOTOR_INJECT
                    self.window.highlight_attack_button(ATTACK_MOTOR_INJECT)
                self._current_mode = mode
                self._update_slider_enabled()
            except dds.Error as exc:
                self.window.log("BLOCKED", f"Participant creation blocked by security: {exc}")
                self._cert_invalid = True
                self.window.highlight_mode_button(None)
                self.window.set_data_status("ATTACK FAILED")
                self.window.launch_btn.setEnabled(False)
                self.window.set_attack_buttons_enabled(False)
                self.window.arm_viz.set_active(False)
                self._current_attack = None
                self.window.highlight_attack_button(None)
                self._participant = None
                self._motor_writer = None
                self._cmd_writer = None
                self._current_mode = None
                self._update_slider_enabled()
            except Exception as exc:
                self.window.log("WARN", f"Participant creation failed: {exc}")
                self.window.highlight_mode_button(None)
                self.window.set_data_status("ATTACK FAILED")
                self.window.launch_btn.setEnabled(False)
                self.window.set_attack_buttons_enabled(False)
                self.window.arm_viz.set_active(False)
                self._current_attack = None
                self.window.highlight_attack_button(None)
                self._participant = None
                self._motor_writer = None
                self._cmd_writer = None
                self._current_mode = None
                self._update_slider_enabled()

    # ── Attack logic ──────────────────────────────────────────────────────

    def _do_inject(self):
        """Called by the attack timer. Writes one sample to the DDS bus."""
        attack = self._current_attack

        if attack == ATTACK_MOTOR_INJECT:
            # Cycle through joints, alternating direction every few ticks
            motor = _MOTORS_ORDERED[self._motor_idx % len(_MOTORS_ORDERED)]
            self._tick += 1
            direction = (
                SurgicalRobot.MotorDirections.INCREMENT
                if (self._tick // 10) % 2 == 0
                else SurgicalRobot.MotorDirections.DECREMENT
            )
            sample = SurgicalRobot.MotorControl(id=motor, direction=direction)

            # Update local visualisation angle (0.3° matches Arm.py step size)
            if direction == SurgicalRobot.MotorDirections.INCREMENT:
                self._angles[motor] = (self._angles[motor] + 0.3) % 360.0
            else:
                self._angles[motor] = (self._angles[motor] - 0.3) % 360.0
            self.window.arm_viz.update_angles(self._angles)
            self._motor_idx = (self._motor_idx + 1) % len(_MOTORS_ORDERED)

            with self._participant_lock:
                if self._motor_writer is None:
                    self.window.set_data_status("NO ACCESS")
                    return
                try:
                    self._motor_writer.write(sample)
                    d_str = (
                        "INCREMENT"
                        if direction == SurgicalRobot.MotorDirections.INCREMENT
                        else "DECREMENT"
                    )
                    level = "OK" if self._prev_matched else "WARN"
                    self.window.log(
                        level,
                        f"Writing MotorControl — joint: {JOINT_NAMES[motor]}, direction: {d_str}",
                    )
                    self.window.set_data_status("ATTACKING" if self._prev_matched else "NO ACCESS")
                except Exception as exc:
                    self.window.log("BLOCKED", f"Write rejected: {exc}")
                    self.window.set_data_status("NO ACCESS")

        elif attack in (ATTACK_CMD_PAUSE, ATTACK_CMD_SHUTDOWN):
            # Command inject: send once per timer tick so it repeats
            cmd = (
                Orchestrator.DeviceCommands.PAUSE
                if attack == ATTACK_CMD_PAUSE
                else Orchestrator.DeviceCommands.SHUTDOWN
            )
            sample = Orchestrator.DeviceCommand(device=Common.DeviceType.ARM, command=cmd)
            cmd_str = "PAUSE" if cmd == Orchestrator.DeviceCommands.PAUSE else "SHUTDOWN"

            with self._participant_lock:
                if self._cmd_writer is None:
                    self.window.set_data_status("NO ACCESS")
                    return
                try:
                    self._cmd_writer.write(sample)
                    level = "OK" if self._prev_matched else "WARN"
                    self.window.log(level, f"Writing DeviceCommand — {cmd_str} → ARM")
                    self.window.set_data_status("ATTACKING" if self._prev_matched else "NO ACCESS")
                except Exception as exc:
                    self.window.log("BLOCKED", f"Write rejected: {exc}")
                    self.window.set_data_status("NO ACCESS")

    def _on_launch_clicked(self):
        if self._current_attack in (ATTACK_CMD_PAUSE, ATTACK_CMD_SHUTDOWN):
            # One-shot command injection
            if self._participant is None:
                return
            self._do_inject()
            return

        if self._attacking:
            self._attacking = False
            self._attack_timer.stop()
            self._prev_matched = None
            self.window.set_launch_btn_active(False)
            self._update_slider_enabled()
            self.window.log("INFO", "Injection stopped")
        else:
            if self._participant is None:
                return
            self._attacking = True
            hz = self.window.get_frequency()
            self._attack_timer.start(int(1000 / hz))
            self.window.set_launch_btn_active(True)
            self._update_slider_enabled()
            self.window.log(
                "INFO",
                f"Attack launched — mode: {self._current_mode}, type: {self._current_attack}",
            )

    def _poll_matched_status(self) -> None:
        """Periodically check publication matched status on the writers."""
        with self._participant_lock:
            writers = [w for w in [self._motor_writer, self._cmd_writer] if w is not None]
            if not writers:
                return
            matched = any(w.publication_matched_status.current_count > 0 for w in writers)

        if matched != self._prev_matched:
            self._prev_matched = matched
            if matched:
                if not self._attacking:
                    self.window.set_data_status("ACCESS GRANTED")
                self.window.log("OK", "Publication matched — remote subscriber found")
            else:
                if not self._attacking:
                    self.window.set_data_status("NO ACCESS")
                self.window.log("BLOCKED", "No publication match — access denied by security")

    def _on_mode_selected(self, mode: str):
        """Mode button clicked: stop any active injection and recreate participant."""
        if self._attacking:
            self._attacking = False
            self._attack_timer.stop()
            self.window.set_launch_btn_active(False)
        self._setup_participant(mode)

    def _on_attack_selected(self, attack: str):
        self._current_attack = attack
        self.window.highlight_attack_button(attack)
        self._update_slider_enabled()

    def _stop_all(self):
        if self._attacking:
            self._attacking = False
            self._attack_timer.stop()
            self.window.set_launch_btn_active(False)
        with self._participant_lock:
            if self._participant is not None:
                self._participant.close()
                self._participant = None
            self._motor_writer = None
            self._cmd_writer = None
            self._current_mode = None
            self._cert_invalid = False
            self._prev_matched = None
        self.window.highlight_mode_button(None)
        self.window.set_data_status("IDLE")
        self.window.launch_btn.setEnabled(False)
        self.window.set_attack_buttons_enabled(False)
        self.window.arm_viz.set_active(False)
        self._current_attack = None
        self.window.highlight_attack_button(None)
        self._update_slider_enabled()
        self.window.log("INFO", "Attack stopped — returned to idle")

    # ── Entry point ───────────────────────────────────────────────────────

    def _cleanup(self) -> None:
        print("Shutting down Threat Injector")
        if self._participant is not None:
            self._participant.close()
            self._participant = None

    async def _async_main(self, app: QApplication) -> None:
        self.window = ThreatInjectorWindow()

        for mode, btn in self.window._mode_buttons.items():
            btn.clicked.connect(lambda _, m=mode: self._on_mode_selected(m))
        for atk, btn in self.window._attack_buttons.items():
            btn.clicked.connect(lambda _, a=atk: self._on_attack_selected(a))
        self.window._stop_btn.clicked.connect(lambda _: self._stop_all())
        self.window.launch_btn.clicked.connect(self._on_launch_clicked)

        DdsUtils.register_type(SurgicalRobot.MotorControl)
        DdsUtils.register_type(Orchestrator.DeviceCommand)

        self.window.set_data_status("IDLE")
        self.window.highlight_attack_button(None)
        self.window.set_attack_buttons_enabled(False)
        self.window.freq_slider.setEnabled(False)

        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._poll_matched_status)
        self._status_timer.start(UPDATE_MS)

        app.aboutToQuit.connect(self._cleanup)
        self.window.show()
        print("Started Threat Injector")

    def run(self) -> None:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        apply_application_font(app)
        _icon = QIcon(QPixmap("../../resource/images/rti_logo.png"))
        if not _icon.isNull():
            app.setWindowIcon(_icon)
        # Allow Ctrl+C to cleanly quit the Qt event loop.
        # The QTimer is needed so the event loop periodically yields control
        # back to Python, enabling signal delivery.
        signal.signal(signal.SIGINT, lambda *_: app.quit())
        _sig_timer = QTimer()
        _sig_timer.timeout.connect(lambda: None)
        _sig_timer.start(300)
        QtAsyncio.run(self._async_main(app), keep_running=True)


if __name__ == "__main__":
    ThreatInjectorApp().run()
