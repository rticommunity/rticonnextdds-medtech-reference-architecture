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

import sys
import math
import time
import threading
import signal
from pathlib import Path

import numpy as np

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QFrame,
    QHBoxLayout, QVBoxLayout, QPushButton,
    QTextEdit, QSizePolicy, QGridLayout
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QFont, QColor, QPalette, QPixmap, QIcon

import pyqtgraph as pg

import rti.connextdds as dds
import PySide6.QtAsyncio as QtAsyncio

# Import OR types
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
if str(PROJECT_ROOT / "modules" / "01-operating-room" / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "modules" / "01-operating-room" / "src"))
import DdsUtils
from Types import PatientMonitor, DdsEntities
from ThreatTypes import ThreatEntities
threat_entities = ThreatEntities.Constants
entities = DdsEntities.Constants

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

COLOR_HR    = "#00E676"
COLOR_SPO2  = "#00B0FF"
COLOR_ETCO2 = "#FFD600"
COLOR_NIBP  = "#FF7043"

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

UPDATE_MS = 100
DATA_TIMEOUT_S = 2.0

# Attack mode constants
MODE_UNSECURE     = "UNSECURE"
MODE_ROGUE_CA     = "ROGUE CA"
MODE_FORGED_PERMS = "FORGED PERMS"
MODE_EXPIRED_CERT = "EXPIRED CERT"

MODE_TO_DP_NAME = {
    MODE_UNSECURE:     threat_entities.EXFILTRATOR_UNSECURE_DP,
    MODE_ROGUE_CA:     threat_entities.EXFILTRATOR_ROGUE_CA_DP,
    MODE_FORGED_PERMS: threat_entities.EXFILTRATOR_FORGED_PERMS_DP,
    MODE_EXPIRED_CERT: threat_entities.EXFILTRATOR_EXPIRED_CERT_DP,
}

SAMPLE_RATE  = 200
DISPLAY_SECS = 6
BUFFER_LEN   = SAMPLE_RATE * DISPLAY_SECS


def _ecg_template(n_pts=SAMPLE_RATE):
    t = np.linspace(0, 1, n_pts)
    p  = 0.15 * np.exp(-((t - 0.12) ** 2) / (2 * 0.008 ** 2))
    q  = -0.08 * np.exp(-((t - 0.22) ** 2) / (2 * 0.004 ** 2))
    r  = 1.00 * np.exp(-((t - 0.26) ** 2) / (2 * 0.003 ** 2))
    s  = -0.15 * np.exp(-((t - 0.30) ** 2) / (2 * 0.004 ** 2))
    tw = 0.30 * np.exp(-((t - 0.42) ** 2) / (2 * 0.015 ** 2))
    return p + q + r + s + tw


def _pleth_template(n_pts=SAMPLE_RATE):
    t = np.linspace(0, 1, n_pts)
    return np.clip(
        np.exp(-((t - 0.35) ** 2) / (2 * 0.05 ** 2))
        + 0.25 * np.exp(-((t - 0.55) ** 2) / (2 * 0.04 ** 2)),
        0, 1
    )


def _capno_template(n_pts=SAMPLE_RATE):
    t = np.linspace(0, 1, n_pts)
    w = np.zeros(n_pts)
    rise  = (t >= 0.30) & (t < 0.60)
    plat  = (t >= 0.60) & (t < 0.85)
    fall  = (t >= 0.85) & (t < 0.95)
    w[rise] = (t[rise] - 0.30) / 0.30
    w[plat] = 1.0
    w[fall] = 1.0 - (t[fall] - 0.85) / 0.10
    return np.clip(w, 0, 1)


# ─── Vital Panel (mirrors PatientMonitor.py VitalPanel) ──────────────────
class VitalPanel(QFrame):
    def __init__(self, vital_name, unit, color, y_min, y_max, parent=None):
        super().__init__(parent)
        self.vital_name = vital_name
        self.unit = unit
        self.color = color
        self.y_min = y_min
        self.y_max = y_max
        self.buf = np.zeros(BUFFER_LEN)
        self.buf_ptr = 0
        self.phase = 0.0
        self.beat_rate = 1.0
        self.live_value = 0.0
        self.amplitude = 1.0
        self._build_ui()

    def _build_ui(self):
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet(f"""
            VitalPanel {{
                background-color: {BG_PANEL};
                border: 1px solid {self.color}55;
                border-radius: 8px;
            }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(4)

        top = QHBoxLayout()
        name_lbl = QLabel(self.vital_name)
        name_lbl.setStyleSheet(
            f"color: {self.color}; font-size: 18px; font-weight: bold; background: transparent;"
        )
        top.addWidget(name_lbl)
        top.addStretch()
        unit_lbl = QLabel(self.unit)
        unit_lbl.setStyleSheet(
            f"color: {self.color}88; font-size: 14px; background: transparent;"
        )
        unit_lbl.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        top.addWidget(unit_lbl)
        root.addLayout(top)

        self.value_lbl = QLabel("---")
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.value_lbl.setStyleSheet(
            f"color: {self.color}; font-size: 48px; font-weight: bold; "
            f"font-family: 'Courier New', monospace; background: transparent; letter-spacing: -2px;"
        )
        root.addWidget(self.value_lbl)

        self.plot_widget = pg.PlotWidget(background=BG_PANEL)
        self.plot_widget.setMinimumHeight(120)
        self.plot_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.plot_widget.hideAxis("left")
        self.plot_widget.hideAxis("bottom")
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setMenuEnabled(False)
        pen = pg.mkPen(color=self.color, width=2)
        self.curve = self.plot_widget.plot(pen=pen)
        self.plot_widget.setYRange(self.y_min, self.y_max, padding=0.05)
        root.addWidget(self.plot_widget)

    def advance_waveform(self, template, n_new):
        t_len = len(template)
        for _ in range(n_new):
            idx = int(self.phase * t_len) % t_len
            self.buf[self.buf_ptr % BUFFER_LEN] = template[idx] * self.amplitude
            self.buf_ptr += 1
            self.phase += self.beat_rate / SAMPLE_RATE
            if self.phase >= 1.0:
                self.phase -= 1.0

    def get_display_buffer(self):
        ptr = self.buf_ptr % BUFFER_LEN
        return np.roll(self.buf, -ptr)

    def set_value(self, val, fmt=".0f"):
        self.value_lbl.setText(f"{val:{fmt}}")
        self.live_value = float(val)

    def reset_to_dashes(self):
        self.value_lbl.setText("---")
        self.buf[:] = 0
        self.buf_ptr = 0
        self.update_curve()

    def update_curve(self):
        self.curve.setData(self.get_display_buffer())


# ─── NiBP Panel ──────────────────────────────────────────────────────────
class NiBPPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet(f"""
            NiBPPanel {{
                background-color: {BG_PANEL};
                border: 1px solid {COLOR_NIBP}55;
                border-radius: 8px;
            }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        name_lbl = QLabel("NiBP")
        name_lbl.setStyleSheet(
            f"color: {COLOR_NIBP}; font-size: 18px; font-weight: bold; background: transparent;"
        )
        top.addWidget(name_lbl)
        top.addStretch()
        unit_lbl = QLabel("mmHg")
        unit_lbl.setStyleSheet(
            f"color: {COLOR_NIBP}88; font-size: 14px; background: transparent;"
        )
        top.addWidget(unit_lbl)
        root.addLayout(top)

        root.addStretch()

        bp_row = QHBoxLayout()
        bp_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sys_lbl = QLabel("---")
        self.sys_lbl.setStyleSheet(
            f"color: {COLOR_NIBP}; font-size: 48px; font-weight: bold; "
            f"font-family: 'Courier New', monospace; background: transparent;"
        )
        bp_row.addWidget(self.sys_lbl)
        sep = QLabel("/")
        sep.setStyleSheet(f"color: {COLOR_NIBP}88; font-size: 36px; background: transparent;")
        bp_row.addWidget(sep)
        self.dia_lbl = QLabel("---")
        self.dia_lbl.setStyleSheet(self.sys_lbl.styleSheet())
        bp_row.addWidget(self.dia_lbl)
        root.addLayout(bp_row)

        sub_row = QHBoxLayout()
        sub_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl = QLabel("Systolic  /  Diastolic")
        sub_lbl.setStyleSheet(f"color: {COLOR_NIBP}66; font-size: 18px; background: transparent;")
        sub_row.addWidget(sub_lbl)
        root.addLayout(sub_row)

        root.addStretch()

        self.map_lbl = QLabel("MAP: ---")
        self.map_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.map_lbl.setStyleSheet(
            f"color: {COLOR_NIBP}AA; font-size: 18px; background: transparent;"
        )
        root.addWidget(self.map_lbl)

    def set_values(self, s, d):
        self.sys_lbl.setText(f"{s:.0f}")
        self.dia_lbl.setText(f"{d:.0f}")
        self.map_lbl.setText(f"MAP: {(s + 2 * d) / 3:.0f}")

    def reset_to_dashes(self):
        self.sys_lbl.setText("---")
        self.dia_lbl.setText("---")
        self.map_lbl.setText("MAP: ---")


# ─── Main Window ─────────────────────────────────────────────────────────
class ThreatExfiltratorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTI Connext — Threat Exfiltrator")
        self.setMinimumSize(900, 680)
        self.resize(1200, 760)
        self.setStyleSheet(f"background-color: {BG_MAIN};")

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
        body.addWidget(self._build_vitals_area(), 2)
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

        _logo_px = QPixmap("../../resource/images/rti_logo.png")
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
        title = QLabel("Threat Exfiltrator")
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
        panel.setFixedWidth(270)
        panel.setStyleSheet(
            f"background-color: {BG_PANEL}; border: 1px solid {RTI_BLUE}33; border-radius: 6px;"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        mode_lbl = QLabel("ATTACK MODE")
        mode_lbl.setStyleSheet(
            f"color: {RTI_BLUE}; font-size: 12px; font-weight: bold; background: transparent; "
            f"letter-spacing: 1px; border-bottom: 1px solid {RTI_BLUE}44; padding-bottom: 6px;"
        )
        layout.addWidget(mode_lbl)

        self._mode_buttons: dict[str, QPushButton] = {}
        for mode in [MODE_UNSECURE, MODE_ROGUE_CA, MODE_FORGED_PERMS, MODE_EXPIRED_CERT]:
            btn = QPushButton(mode)
            btn.setFixedHeight(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_STYLE_MODE_INACTIVE)
            self._mode_buttons[mode] = btn
            layout.addWidget(btn)

        layout.addSpacing(6)

        self._stop_btn = QPushButton("\u25a0  STOP ATTACK")
        self._stop_btn.setFixedHeight(38)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(_STYLE_STOP_DISABLED)
        layout.addWidget(self._stop_btn)

        layout.addSpacing(10)

        info_lbl = QLabel(
            "Select an attack mode above\n"
            "to launch the exfiltrator and\n"
            "attempt to access patient vitals.\n\n"
            "Click \u25a0 STOP ATTACK to cancel\n"
            "and return to idle at any time."
        )
        info_lbl.setStyleSheet(
            f"color: #607080; font-size: 12px; background: transparent; padding: 4px;"
        )
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        layout.addStretch()
        return panel

    def _build_vitals_area(self) -> QWidget:
        outer = QFrame()
        outer.setFrameShape(QFrame.Shape.Box)
        outer.setStyleSheet(
            f"background-color: {BG_PANEL}; border: 1px solid {RTI_BLUE}33; border-radius: 6px;"
        )
        v = QVBoxLayout(outer)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)

        lbl = QLabel("STOLEN: Patient Vitals")
        lbl.setStyleSheet(
            f"color: {COLOR_BLOCKED}; font-size: 14px; font-weight: bold; background: transparent; "
            f"border-bottom: 1px solid {COLOR_BLOCKED}44; padding-bottom: 4px;"
        )
        v.addWidget(lbl)

        self.hr_panel    = VitalPanel("ECG / Heart Rate", "bpm",  COLOR_HR,    -0.2, 1.1)
        self.spo2_panel  = VitalPanel("SpO₂",             "%",    COLOR_SPO2,  -0.1, 1.1)
        self.etco2_panel = VitalPanel("EtCO₂",            "mmHg", COLOR_ETCO2, -0.1, 1.1)
        self.nibp_panel  = NiBPPanel()

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.addWidget(self.hr_panel,    0, 0)
        grid.addWidget(self.spo2_panel,  0, 1)
        grid.addWidget(self.etco2_panel, 1, 0)
        grid.addWidget(self.nibp_panel,  1, 1)
        v.addLayout(grid, 1)
        return outer

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

    def set_data_status(self, status: str):
        """status: 'IDLE', 'ACCESS GRANTED', 'NO ACCESS', 'ATTACK FAILED'"""
        colors = {
            "IDLE":          (COLOR_IDLE,       "#fff"),
            "ACCESS GRANTED":(COLOR_GRANTED,    "#000"),
            "NO ACCESS":     (COLOR_WARN,       "#000"),
            "ATTACK FAILED": (COLOR_BLOCKED,    "#fff"),
        }
        bg, fg = colors.get(status, (COLOR_IDLE, "#fff"))
        self.status_badge.setText(status)
        self.status_badge.setStyleSheet(
            f"color: {fg}; background-color: {bg}; font-size: 18px; "
            f"font-weight: bold; padding: 4px 12px; border-radius: 4px; margin-left: 10px;"
        )

    def log(self, level: str, msg: str):
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

    def reset_vitals(self):
        self.hr_panel.reset_to_dashes()
        self.spo2_panel.reset_to_dashes()
        self.etco2_panel.reset_to_dashes()
        self.nibp_panel.reset_to_dashes()


# ─── Application class ────────────────────────────────────────────────────
class ThreatExfiltratorApp:
    def __init__(self):
        self.window: ThreatExfiltratorWindow = None
        self._participant = None
        self._vitals_reader = None
        self._current_mode: str | None = None
        self._participant_lock = threading.Lock()
        self._last_sample_time = 0.0
        self._cert_invalid = False
        self._prev_matched = None
        self._ecg_tpl   = _ecg_template()
        self._pleth_tpl = _pleth_template()
        self._capno_tpl = _capno_template()
        self._prev_poll_time = time.monotonic()

    # ── DDS participant lifecycle ─────────────────────────────────────────

    def _setup_participant(self, mode: str):
        with self._participant_lock:
            if self._participant is not None:
                self.window.log("INFO", "Participant destroyed — switching mode")
                try:
                    self._participant.close()
                except Exception:
                    pass
                self._participant = None
                self._vitals_reader = None
                self._cert_invalid = False
                self._current_mode = None
                self._prev_matched = None

            dp_name = MODE_TO_DP_NAME.get(mode, threat_entities.EXFILTRATOR_UNSECURE_DP)
            try:
                qos_provider = dds.QosProvider.default
                self._participant = qos_provider.create_participant_from_config(dp_name)
                self._vitals_reader = dds.DataReader(
                    self._participant.find_datareader(entities.VITALS_DR)
                )
                self.window.log("INFO", f"Participant created — {mode}")

                self.window.highlight_mode_button(mode)
                self.window.reset_vitals()
                self._current_mode = mode
            except dds.Error as exc:
                self.window.log("BLOCKED", f"Participant creation blocked by security: {exc}")
                self._cert_invalid = True
                self.window.set_data_status("ATTACK FAILED")
                self.window.highlight_mode_button(None)
                self._participant = None
                self._vitals_reader = None
                self._current_mode = None
            except Exception as exc:
                self.window.log("WARN", f"Participant creation failed: {exc}")
                self.window.set_data_status("ATTACK FAILED")
                self.window.highlight_mode_button(None)
                self._participant = None
                self._vitals_reader = None
                self._current_mode = None

    # ── DDS poll ──────────────────────────────────────────────────────────

    def _poll_dds(self):
        now = time.monotonic()
        elapsed = now - self._prev_poll_time
        self._prev_poll_time = now
        n_new = max(1, int(elapsed * SAMPLE_RATE))

        with self._participant_lock:
            if self._vitals_reader is None:
                self._update_waveform_display()
                return

            # Poll subscription matched status
            matched = self._vitals_reader.subscription_matched_status.current_count > 0
            if matched != self._prev_matched:
                self._prev_matched = matched
                if matched:
                    self.window.set_data_status("ACCESS GRANTED")
                    self.window.log("OK", "Subscription matched — receiving data")
                else:
                    self.window.set_data_status("NO ACCESS")
                    self.window.log("BLOCKED", "No subscription match — access denied by security")

            try:
                samples = self._vitals_reader.take_data()
            except Exception:
                samples = []

        for sample in samples:
            hr    = float(sample.hr)
            spo2  = float(sample.spo2)
            etco2 = float(sample.etco2)
            nibp_s = float(sample.nibp_s)
            nibp_d = float(sample.nibp_d)

            self.window.hr_panel.set_value(hr)
            self.window.spo2_panel.set_value(spo2)
            self.window.etco2_panel.set_value(etco2)
            self.window.nibp_panel.set_values(nibp_s, nibp_d)

            self.window.hr_panel.beat_rate    = hr / 60.0
            self.window.hr_panel.amplitude    = 1.0
            self.window.spo2_panel.beat_rate  = hr / 60.0
            self.window.spo2_panel.amplitude  = 1.0
            self.window.etco2_panel.beat_rate  = 15 / 60.0
            self.window.etco2_panel.amplitude  = 1.0

            self._last_sample_time = time.monotonic()
            self.window.set_data_status("ACCESS GRANTED")
            self.window.log(
                "OK",
                f"Received Vitals — patient_id: {sample.patient_id}, "
                f"hr: {sample.hr}, spo2: {sample.spo2}, "
                f"etco2: {sample.etco2}, nibp: {sample.nibp_s}/{sample.nibp_d}"
            )

        # Data timeout → reset panels to dashes
        if self._last_sample_time > 0 and (now - self._last_sample_time) > DATA_TIMEOUT_S:
            self.window.reset_vitals()
            self._last_sample_time = 0.0

        # Only animate waveforms when actively receiving data
        if self._last_sample_time > 0:
            self.window.hr_panel.advance_waveform(self._ecg_tpl, n_new)
            self.window.spo2_panel.advance_waveform(self._pleth_tpl, n_new)
            self.window.etco2_panel.advance_waveform(self._capno_tpl, n_new)
        self._update_waveform_display()

    def _advance_silent_waveforms(self, n_new: int):
        self.window.hr_panel.advance_waveform(self._ecg_tpl, n_new)
        self.window.spo2_panel.advance_waveform(self._pleth_tpl, n_new)
        self.window.etco2_panel.advance_waveform(self._capno_tpl, n_new)

    def _update_waveform_display(self):
        self.window.hr_panel.update_curve()
        self.window.spo2_panel.update_curve()
        self.window.etco2_panel.update_curve()

    # ── Mode selection and stop handlers ─────────────────────────────────

    def _on_mode_selected(self, mode: str):
        self._setup_participant(mode)

    def _stop_attack(self):
        with self._participant_lock:
            if self._participant is not None:
                self._participant.close()
                self._participant = None
            self._vitals_reader = None
            self._current_mode = None
            self._cert_invalid = False
            self._last_sample_time = 0.0
            self._prev_matched = None
        self.window.highlight_mode_button(None)
        self.window.set_data_status("IDLE")
        self.window.reset_vitals()
        self.window.log("INFO", "Attack stopped — returned to idle")

    # ── Entry point ───────────────────────────────────────────────────────

    async def _async_main(self, app: QApplication) -> None:
        self.window = ThreatExfiltratorWindow()

        for mode, btn in self.window._mode_buttons.items():
            btn.clicked.connect(lambda _, m=mode: self._on_mode_selected(m))
        self.window._stop_btn.clicked.connect(lambda _: self._stop_attack())

        DdsUtils.register_type(PatientMonitor.Vitals)

        self.window.set_data_status("IDLE")
        self.window.reset_vitals()

        self._dds_timer = QTimer()
        self._dds_timer.timeout.connect(self._poll_dds)
        self._dds_timer.start(UPDATE_MS)

        app.aboutToQuit.connect(self._cleanup)
        self.window.show()
        print("Started Threat Exfiltrator")

    def _cleanup(self) -> None:
        print("Shutting down Threat Exfiltrator")
        if self._participant is not None:
            self._participant.close()
            self._participant = None

    def run(self) -> None:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
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
    ThreatExfiltratorApp().run()
