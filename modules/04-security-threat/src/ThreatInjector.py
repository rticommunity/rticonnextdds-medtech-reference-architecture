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

import sys
import math
import time
import threading

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QFrame,
    QHBoxLayout, QVBoxLayout, QGridLayout, QPushButton, QTextEdit,
    QSizePolicy, QSlider
)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal, QObject
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPixmap, QIcon
)

import rti.connextdds as dds
import DdsUtils
import PySide6.QtAsyncio as QtAsyncio

# Import OR types (path added by DdsUtils)
from Types import SurgicalRobot, Orchestrator, Common

# ─── RTI Brand Colors ────────────────────────────────────────────────────
RTI_BLUE    = "#004C97"
RTI_ORANGE  = "#ED8B00"
BG_MAIN     = "#0A0E17"
BG_PANEL    = "#0F1822"
BG_HEADER   = "#071020"
BORDER_DIM  = "#1A2535"
COLOR_OK     = "#00E676"
COLOR_WARN   = "#ED8B00"
COLOR_BLOCKED    = "#FF4444"
COLOR_IDLE       = "#445566"
COLOR_ATTEMPTING = "#1E88E5"
COLOR_GRANTED    = "#00C853"

UPDATE_MS = 100

# ─── Left-panel button styles ─────────────────────────────────────────────
_STYLE_MODE_INACTIVE = (
    f"QPushButton {{ background-color: #0D1824; color: #4A6070; "
    f"border: 1px solid #1A2A38; border-radius: 5px; padding: 0px 12px; "
    f"font-size: 13px; font-weight: bold; text-align: left; }}"
    f"QPushButton:hover {{ background-color: #162030; color: #90AAB8; border-color: #2A3A4A; }}"
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
    f"QPushButton {{ background-color: #0D1824; color: #4A6070; "
    f"border: 1px solid #1A2A38; border-radius: 5px; padding: 0px 12px; "
    f"font-size: 12px; font-weight: bold; text-align: left; }}"
    f"QPushButton:hover {{ background-color: #162030; color: #90AAB8; border-color: #2A3A4A; }}"
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
    f"QPushButton {{ background-color: #0D1520; color: #2A3848; "
    f"border: 1px solid #182028; border-radius: 5px; padding: 0px 12px; "
    f"font-size: 13px; font-weight: bold; }}"
)

# Joint colors matching module 01
JOINT_COLORS = {
    SurgicalRobot.Motors.BASE:     "#004C97",
    SurgicalRobot.Motors.SHOULDER: "#ED8B00",
    SurgicalRobot.Motors.ELBOW:    "#00BFFF",
    SurgicalRobot.Motors.WRIST:    "#7CFC00",
    SurgicalRobot.Motors.HAND:     "#DA70D6",
}

JOINT_NAMES = {
    SurgicalRobot.Motors.BASE:     "BASE",
    SurgicalRobot.Motors.SHOULDER: "SHOULDER",
    SurgicalRobot.Motors.ELBOW:    "ELBOW",
    SurgicalRobot.Motors.WRIST:    "WRIST",
    SurgicalRobot.Motors.HAND:     "HAND",
}

_MOTORS_ORDERED = [
    SurgicalRobot.Motors.BASE,
    SurgicalRobot.Motors.SHOULDER,
    SurgicalRobot.Motors.ELBOW,
    SurgicalRobot.Motors.WRIST,
    SurgicalRobot.Motors.HAND,
]

INITIAL_ANGLES = {
    SurgicalRobot.Motors.BASE:     204.0,
    SurgicalRobot.Motors.SHOULDER: 176.0,
    SurgicalRobot.Motors.ELBOW:    156.0,
    SurgicalRobot.Motors.WRIST:    165.0,
    SurgicalRobot.Motors.HAND:     151.0,
}

# Attack mode constants
MODE_UNSECURE     = "UNSECURE"
MODE_ROGUE_CA     = "ROGUE CA"
MODE_FORGED_PERMS = "FORGED PERMS"
MODE_EXPIRED_CERT = "EXPIRED CERT"

# Attack type constants
ATTACK_MOTOR_INJECT    = "MOTOR INJECT"
ATTACK_CMD_PAUSE       = "CMD INJECT (PAUSE)"
ATTACK_CMD_SHUTDOWN    = "CMD INJECT (SHUTDOWN)"

MODE_TO_FQN = {
    MODE_UNSECURE:     DdsUtils.injector_unsecure_dp_fqn,
    MODE_ROGUE_CA:     DdsUtils.injector_rogue_ca_dp_fqn,
    MODE_FORGED_PERMS: DdsUtils.injector_forged_perms_dp_fqn,
    MODE_EXPIRED_CERT: DdsUtils.injector_expired_cert_dp_fqn,
}


# ─── Arm Visualisation (reused from Arm.py style) ────────────────────────
class ArmVizWidget(QWidget):
    SEGMENT_LEN = 70
    JOINT_R     = 12
    EE_SIZE     = 16
    GROUND_W    = 80
    GROUND_LINES = 6

    _GREY = "#334455"
    _GREY_DIM = "#222C38"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angles = {m: 180.0 for m in _MOTORS_ORDERED}
        self._active = False
        self.setMinimumWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background-color: {BG_PANEL};")

    def set_active(self, active: bool):
        self._active = active
        self.update()

    def update_angles(self, angles: dict):
        self._angles = dict(angles)
        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG_PANEL))

        p.setPen(QPen(QColor("#445566")))
        p.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        p.drawText(12, 20, "ARM VISUALIZATION")

        usable_h = h - 70
        seg = int(usable_h * 0.90 / len(_MOTORS_ORDERED))
        seg = max(seg, 36)

        bx = w / 2.0
        by = h - 36.0

        gw = self.GROUND_W
        ground_pen = QPen(QColor("#334455"), 2)
        p.setPen(ground_pen)
        p.drawLine(QPointF(bx - gw, by), QPointF(bx + gw, by))
        hatch_dx = gw / (self.GROUND_LINES + 1)
        for i in range(self.GROUND_LINES):
            hx = bx - gw + hatch_dx * (i + 1)
            p.drawLine(QPointF(hx, by), QPointF(hx - 10, by + 12))

        cumul_dir = math.pi / 2.0
        x, y = bx, by
        points = [(x, y)]
        for motor in _MOTORS_ORDERED:
            angle = self._angles.get(motor, 180.0)
            delta_rad = (angle - 180.0) * math.pi / 180.0
            cumul_dir += delta_rad
            nx = x + seg * math.cos(cumul_dir)
            ny = y - seg * math.sin(cumul_dir)
            points.append((nx, ny))
            x, y = nx, ny

        for i, motor in enumerate(_MOTORS_ORDERED):
            color = QColor(JOINT_COLORS[motor]) if self._active else QColor(self._GREY)
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            pen = QPen(color, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

        ee_color = QColor(JOINT_COLORS[SurgicalRobot.Motors.HAND]) if self._active else QColor(self._GREY)
        p.setPen(QPen(ee_color, 2))
        ex, ey = points[-1]
        es = self.EE_SIZE
        diamond = QPainterPath()
        diamond.moveTo(ex, ey - es)
        diamond.lineTo(ex + es, ey)
        diamond.lineTo(ex, ey + es)
        diamond.lineTo(ex - es, ey)
        diamond.closeSubpath()
        p.setBrush(QBrush(ee_color.darker(180)))
        p.drawPath(diamond)

        jr = self.JOINT_R
        for i, motor in enumerate(_MOTORS_ORDERED):
            color = QColor(JOINT_COLORS[motor]) if self._active else QColor(self._GREY)
            cx2, cy2 = points[i]
            p.setPen(QPen(color, 2))
            p.setBrush(QBrush(color.darker(200) if self._active else QColor(self._GREY_DIM)))
            p.drawEllipse(QPointF(cx2, cy2), jr, jr)
            name = JOINT_NAMES[motor][:3]
            p.setPen(QPen(color))
            p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            p.drawText(QPointF(cx2 + jr + 4, cy2 + 5), name)

        p.setFont(QFont("Courier New", 9))
        for i, motor in enumerate(_MOTORS_ORDERED):
            color = QColor(JOINT_COLORS[motor]) if self._active else QColor(self._GREY)
            p.setPen(QPen(color.lighter(130) if self._active else color))
            mx = (points[i][0] + points[i + 1][0]) / 2 + 8
            my = (points[i][1] + points[i + 1][1]) / 2
            p.drawText(QPointF(mx, my), f"{self._angles.get(motor, 180.0):.0f}°")

        p.end()


# ─── Main Window ─────────────────────────────────────────────────────────
class ThreatInjectorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTI Connext — Threat Injector")
        self.setMinimumSize(900, 680)
        self.resize(1100, 720)
        self.setStyleSheet(f"background-color: {BG_MAIN};")

        _icon_px = QPixmap("../../resource/images/rti_logo.ico")
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
        body.addWidget(self._build_log_panel(), 1)

        body_widget = QWidget()
        body_widget.setStyleSheet(f"background-color: {BG_MAIN};")
        body_widget.setLayout(body)
        root.addWidget(body_widget, 1)

        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(80)
        header.setStyleSheet(
            f"background-color: {BG_HEADER}; border-bottom: 2px solid {RTI_BLUE};"
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(20, 0, 20, 0)

        _logo_px = QPixmap("../../resource/images/rti_logo.ico")
        if not _logo_px.isNull():
            logo = QLabel()
            logo.setStyleSheet("background: transparent;")
            logo.setPixmap(_logo_px.scaled(52, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            h.addWidget(logo)

        rti_lbl = QLabel("RTI Connext")
        rti_lbl.setStyleSheet(
            f"color: {RTI_BLUE}; font-size: 26px; font-weight: bold; background: transparent;"
        )
        h.addWidget(rti_lbl)

        sep = QLabel("|")
        sep.setStyleSheet("color: #334455; font-size: 28px; background: transparent;")
        h.addWidget(sep)

        title = QLabel("Threat Injector")
        title.setStyleSheet(
            "color: #E0E8F0; font-size: 34px; font-weight: bold; background: transparent;"
        )
        h.addWidget(title)
        h.addStretch()

        self.status_badge = QLabel("IDLE")
        self.status_badge.setStyleSheet(
            f"color: #fff; background-color: {COLOR_IDLE}; font-size: 18px; "
            f"font-weight: bold; padding: 4px 12px; border-radius: 4px; margin-left: 10px;"
        )
        h.addWidget(self.status_badge)
        return header

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setFixedHeight(44)
        footer.setStyleSheet(
            f"background-color: {BG_HEADER}; border-top: 1px solid {BORDER_DIM};"
        )
        f = QHBoxLayout(footer)
        f.setContentsMargins(20, 0, 20, 0)
        lbl = QLabel(
            "Real-Time Innovations  ·  RTI Connext  ·  MedTech Reference Architecture"
        )
        lbl.setStyleSheet(f"color: {COLOR_IDLE}; font-size: 18px; background: transparent;")
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
        for mode in [MODE_UNSECURE, MODE_ROGUE_CA, MODE_FORGED_PERMS, MODE_EXPIRED_CERT]:
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
            f"color: {RTI_ORANGE}; font-size: 12px; font-weight: bold; background: transparent; letter-spacing: 1px;"
        )
        layout.addWidget(freq_hdr)
        self.freq_slider = QSlider(Qt.Orientation.Horizontal)
        self.freq_slider.setMinimum(1)
        self.freq_slider.setMaximum(20)
        self.freq_slider.setValue(5)
        self.freq_slider.setStyleSheet(
            f"QSlider::handle:horizontal {{ background: {RTI_ORANGE}; border-radius: 5px; width: 12px; height: 12px; }}"
        )
        layout.addWidget(self.freq_slider)
        self.freq_lbl = QLabel("5 Hz")
        self.freq_lbl.setStyleSheet(f"color: #C0D0E0; font-size: 12px; background: transparent;")
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
        self.arm_viz = ArmVizWidget()
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

        hdr = QLabel("Activity Log")
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
                font-family: 'Courier New', monospace;
                font-size: 12px;
                border: none;
            }}
        """)
        v.addWidget(self.log_text)
        return frame

    # ── Public update methods ─────────────────────────────────────────────

    def set_data_status(self, status: str):
        """status: 'IDLE', 'ACCESS GRANTED', 'ATTACKING', 'NO ACCESS', 'ATTACK FAILED'"""
        colors = {
            "IDLE":          (COLOR_IDLE,       "#fff"),
            "ACCESS GRANTED":(COLOR_GRANTED,    "#000"),
            "ATTACKING":     (COLOR_GRANTED,    "#000"),
            "NO ACCESS":     (COLOR_WARN,       "#000"),
            "ATTACK FAILED": (COLOR_BLOCKED,    "#fff"),
        }
        bg, fg = colors.get(status, (COLOR_IDLE, "#fff"))
        self.status_badge.setText(status)
        self.status_badge.setStyleSheet(
            f"color: {fg}; background-color: {bg}; font-size: 18px; "
            f"font-weight: bold; padding: 4px 12px; border-radius: 4px; margin-left: 10px;"
        )

    def highlight_mode_button(self, active_mode: str | None) -> None:
        for mode, btn in self._mode_buttons.items():
            if mode == active_mode:
                style = _STYLE_MODE_ACTIVE_UNSECURE if mode == MODE_UNSECURE else _STYLE_MODE_ACTIVE_THREAT
                btn.setStyleSheet(style)
            else:
                btn.setStyleSheet(_STYLE_MODE_INACTIVE)
        is_active = active_mode is not None
        self._stop_btn.setEnabled(is_active)
        self._stop_btn.setStyleSheet(_STYLE_STOP_ENABLED if is_active else _STYLE_STOP_DISABLED)

    def highlight_attack_button(self, active_attack: str | None) -> None:
        for atk, btn in self._attack_buttons.items():
            btn.setStyleSheet(_STYLE_ATTACK_ACTIVE if atk == active_attack else _STYLE_ATTACK_INACTIVE)

    def set_attack_buttons_enabled(self, enabled: bool) -> None:
        for btn in self._attack_buttons.values():
            btn.setEnabled(enabled)

    def log(self, level: str, msg: str):
        """Append a coloured log entry. level: 'OK', 'WARN', 'BLOCKED', 'INFO', 'SECURITY'"""
        colors = {
            "OK":       COLOR_OK,
            "WARN":     COLOR_WARN,
            "BLOCKED":  COLOR_BLOCKED,
            "INFO":     "#6699AA",
            "SECURITY": "#FF6D00",
        }
        c = colors.get(level, "#C0D0E0")
        self.log_text.append(
            f'<span style="color:{c}; font-weight:bold;">[{level}]</span>'
            f' <span style="color:#C0D0E0;">{msg}</span>'
        )
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

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
        self._inject_directions = {m: SurgicalRobot.MotorDirections.INCREMENT for m in _MOTORS_ORDERED}
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

            fqn = MODE_TO_FQN.get(mode, DdsUtils.injector_unsecure_dp_fqn)
            try:
                qos_provider = dds.QosProvider.default
                self._participant = qos_provider.create_participant_from_config(fqn)
                self._motor_writer = dds.DataWriter(
                    self._participant.find_datawriter(DdsUtils.motor_control_dw_fqn)
                )
                self._cmd_writer = dds.DataWriter(
                    self._participant.find_datawriter(DdsUtils.device_command_dw_fqn)
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

            # Update local visualisation angle
            if direction == SurgicalRobot.MotorDirections.INCREMENT:
                self._angles[motor] = (self._angles[motor] + 2.0) % 360.0
            else:
                self._angles[motor] = (self._angles[motor] - 2.0) % 360.0
            self.window.arm_viz.update_angles(self._angles)
            self._motor_idx = (self._motor_idx + 1) % len(_MOTORS_ORDERED)

            with self._participant_lock:
                if self._motor_writer is None:
                    self.window.set_data_status("NO ACCESS")
                    return
                try:
                    self._motor_writer.write(sample)
                    d_str = "INCREMENT" if direction == SurgicalRobot.MotorDirections.INCREMENT else "DECREMENT"
                    level = "OK" if self._prev_matched else "WARN"
                    self.window.log(level, f"Writing MotorControl — joint: {JOINT_NAMES[motor]}, direction: {d_str}")
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
            self.window.log("INFO", f"Attack launched — mode: {self._current_mode}, type: {self._current_attack}")

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
        QtAsyncio.run(self._async_main(app), keep_running=True)


if __name__ == "__main__":
    ThreatInjectorApp().run()
