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
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QFrame,
    QGridLayout, QHBoxLayout, QVBoxLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor, QPalette, QFontDatabase, QPixmap, QIcon

import pyqtgraph as pg

import rti.connextdds as dds
from Types import Common, PatientMonitor, Orchestrator
import DdsUtils

# ─── RTI Brand Colors ───────────────────────────────────────────────────────
RTI_BLUE   = "#004C97"
RTI_ORANGE = "#ED8B00"
BG_MAIN    = "#0A0E17"   # Very dark navy
BG_PANEL   = "#0F1822"   # Panel background
BG_HEADER  = "#071020"   # Header strip
BORDER_DIM = "#1A2A3A"   # Subtle panel borders

# Per-vital colour scheme (matches real ICU monitors)
COLOR_HR    = "#00E676"   # Bright green   – ECG
COLOR_SPO2  = "#00B0FF"   # Cyan-blue      – SpO2 / plethysmograph
COLOR_ETCO2 = "#FFD600"   # Amber-yellow   – Capnography
COLOR_NIBP  = "#FF7043"   # Warm orange    – NiBP

# ─── Waveform generators ────────────────────────────────────────────────────
SAMPLE_RATE = 200          # samples / second for waveform buffer
DISPLAY_SECS = 6           # seconds visible in the strip
BUFFER_LEN   = SAMPLE_RATE * DISPLAY_SECS


def _ecg_template(n_pts: int = SAMPLE_RATE) -> np.ndarray:
    """One beat of a synthetic PQRST waveform (normalised 0-1)."""
    t = np.linspace(0, 1, n_pts)
    # P wave
    p = 0.15 * np.exp(-((t - 0.12) ** 2) / (2 * 0.008 ** 2))
    # Q dip
    q = -0.08 * np.exp(-((t - 0.22) ** 2) / (2 * 0.004 ** 2))
    # R spike
    r = 1.00 * np.exp(-((t - 0.26) ** 2) / (2 * 0.003 ** 2))
    # S dip
    s = -0.15 * np.exp(-((t - 0.30) ** 2) / (2 * 0.004 ** 2))
    # T wave
    tw = 0.30 * np.exp(-((t - 0.42) ** 2) / (2 * 0.015 ** 2))
    return p + q + r + s + tw


def _pleth_template(n_pts: int = SAMPLE_RATE) -> np.ndarray:
    """One beat of a plethysmograph waveform (smooth hill)."""
    t = np.linspace(0, 1, n_pts)
    return np.clip(
        np.exp(-((t - 0.35) ** 2) / (2 * 0.05 ** 2))
        + 0.25 * np.exp(-((t - 0.55) ** 2) / (2 * 0.04 ** 2)),
        0, 1
    )


def _capno_template(n_pts: int = SAMPLE_RATE) -> np.ndarray:
    """One respiratory cycle capnography waveform."""
    t = np.linspace(0, 1, n_pts)
    # rise phase (0.3-0.6), plateau (0.6-0.85), fall (0.85-0.95)
    w = np.zeros(n_pts)
    rise   = (t >= 0.30) & (t < 0.60)
    plat   = (t >= 0.60) & (t < 0.85)
    fall   = (t >= 0.85) & (t < 0.95)
    w[rise] = (t[rise] - 0.30) / 0.30
    w[plat] = 1.0
    w[fall] = 1.0 - (t[fall] - 0.85) / 0.10
    return np.clip(w, 0, 1)


# ─── DDS → Qt bridge ────────────────────────────────────────────────────────
class DdsBridge(QObject):
    vitals_received = pyqtSignal(float, float, float, float, float)  # hr, spo2, etco2, nibp_s, nibp_d
    shutdown_received = pyqtSignal()
    status_changed = pyqtSignal(str)   # "ON" / "PAUSED"


# ─── Waveform strip panel ─────────────────────────────────────────────────
class VitalPanel(QFrame):
    """A self-contained vital-signs panel: large numeric + scrolling waveform."""

    def __init__(self, vital_name: str, unit: str, color: str,
                 y_min: float, y_max: float, parent=None):
        super().__init__(parent)
        self.vital_name = vital_name
        self.unit = unit
        self.color = color
        self.y_min = y_min
        self.y_max = y_max

        # Waveform state
        self.buf = np.zeros(BUFFER_LEN)
        self.buf_ptr = 0          # write pointer (circular)
        self.phase = 0.0          # current beat phase (0–1)
        self.beat_rate = 1.0      # beats per second (driven by live value)
        self.live_value = 0.0
        self.amplitude = 1.0

        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────
    def _build_ui(self):
        self.setFrameShape(QFrame.Box)
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

        # ── Top row: name + value ─────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(0)

        name_lbl = QLabel(self.vital_name)
        name_lbl.setStyleSheet(f"color: {self.color}; font-size: 20px; font-weight: bold; background: transparent;")
        top.addWidget(name_lbl)

        top.addStretch()

        self.unit_lbl = QLabel(self.unit)
        self.unit_lbl.setStyleSheet(f"color: {self.color}88; font-size: 16px; background: transparent;")
        self.unit_lbl.setAlignment(Qt.AlignBottom | Qt.AlignRight)
        top.addWidget(self.unit_lbl)
        root.addLayout(top)

        # ── Numeric value ─────────────────────────────────────────────
        self.value_lbl = QLabel("---")
        self.value_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.value_lbl.setStyleSheet(
            f"color: {self.color}; font-size: 54px; font-weight: bold; "
            f"font-family: 'Courier New', monospace; background: transparent; "
            f"letter-spacing: -2px;"
        )
        root.addWidget(self.value_lbl)

        # ── Waveform plot ─────────────────────────────────────────────
        self.plot_widget = pg.PlotWidget(background=BG_PANEL)
        self.plot_widget.setMinimumHeight(150)
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot_widget.hideAxis("left")
        self.plot_widget.hideAxis("bottom")
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setMenuEnabled(False)
        pen = pg.mkPen(color=self.color, width=2)
        self.curve = self.plot_widget.plot(pen=pen)
        self.plot_widget.setYRange(self.y_min, self.y_max, padding=0.05)
        root.addWidget(self.plot_widget)

    # ── Waveform advance ──────────────────────────────────────────────
    def advance_waveform(self, template: np.ndarray, n_new: int):
        """Advance n_new samples through the cyclic waveform template."""
        t_len = len(template)
        for _ in range(n_new):
            idx = int(self.phase * t_len) % t_len
            self.buf[self.buf_ptr % BUFFER_LEN] = template[idx] * self.amplitude
            self.buf_ptr += 1
            self.phase += self.beat_rate / SAMPLE_RATE
            if self.phase >= 1.0:
                self.phase -= 1.0

    def get_display_buffer(self) -> np.ndarray:
        """Return the circular buffer in chronological order."""
        ptr = self.buf_ptr % BUFFER_LEN
        return np.roll(self.buf, -ptr)

    def set_value(self, val, fmt=".0f"):
        self.value_lbl.setText(f"{val:{fmt}}")
        self.live_value = float(val)

    def update_curve(self):
        data = self.get_display_buffer()
        self.curve.setData(data)


# ─── NiBP Panel (no waveform — spot measurement readout) ─────────────────
class NiBPPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Box)
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
        name_lbl.setStyleSheet(f"color: {COLOR_NIBP}; font-size: 20px; font-weight: bold; background: transparent;")
        top.addWidget(name_lbl)
        top.addStretch()
        unit_lbl = QLabel("mmHg")
        unit_lbl.setStyleSheet(f"color: {COLOR_NIBP}88; font-size: 16px; background: transparent;")
        top.addWidget(unit_lbl)
        root.addLayout(top)

        root.addStretch()

        # sys / dia
        bp_row = QHBoxLayout()
        bp_row.setAlignment(Qt.AlignCenter)

        self.sys_lbl = QLabel("---")
        self.sys_lbl.setStyleSheet(
            f"color: {COLOR_NIBP}; font-size: 54px; font-weight: bold; "
            f"font-family: 'Courier New', monospace; background: transparent;"
        )
        bp_row.addWidget(self.sys_lbl)

        sep = QLabel("/")
        sep.setStyleSheet(f"color: {COLOR_NIBP}88; font-size: 42px; background: transparent;")
        bp_row.addWidget(sep)

        self.dia_lbl = QLabel("---")
        self.dia_lbl.setStyleSheet(
            f"color: {COLOR_NIBP}; font-size: 54px; font-weight: bold; "
            f"font-family: 'Courier New', monospace; background: transparent;"
        )
        bp_row.addWidget(self.dia_lbl)
        root.addLayout(bp_row)

        sub_row = QHBoxLayout()
        sub_row.setAlignment(Qt.AlignCenter)
        sub_lbl = QLabel("Systolic  /  Diastolic")
        sub_lbl.setStyleSheet(f"color: {COLOR_NIBP}66; font-size: 20px; background: transparent;")
        sub_row.addWidget(sub_lbl)
        root.addLayout(sub_row)

        root.addStretch()

        # MAP estimate
        self.map_lbl = QLabel("MAP: ---")
        self.map_lbl.setAlignment(Qt.AlignCenter)
        self.map_lbl.setStyleSheet(
            f"color: {COLOR_NIBP}AA; font-size: 20px; background: transparent;"
        )
        root.addWidget(self.map_lbl)

    def set_values(self, s, d):
        self.sys_lbl.setText(f"{s:.0f}")
        self.dia_lbl.setText(f"{d:.0f}")
        _map = (s + 2 * d) / 3
        self.map_lbl.setText(f"MAP: {_map:.0f}")


# ─── Main Window ──────────────────────────────────────────────────────────
class PatientMonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTI Connext — Patient Monitor")
        self.setMinimumSize(900, 600)
        self.resize(1100, 720)
        self._apply_global_style()

        # ── Build vitals panels ──────────────────────────────────────
        self.hr_panel    = VitalPanel("ECG / Heart Rate", "bpm",  COLOR_HR,    -0.2, 1.1)
        self.spo2_panel  = VitalPanel("SpO₂",             "%",    COLOR_SPO2,  -0.1, 1.1)
        self.etco2_panel = VitalPanel("EtCO₂",            "mmHg", COLOR_ETCO2, -0.1, 1.1)
        self.nibp_panel  = NiBPPanel()

        # Waveform templates (precomputed once)
        self._ecg_tpl   = _ecg_template(SAMPLE_RATE)
        self._pleth_tpl = _pleth_template(SAMPLE_RATE)
        self._capno_tpl = _capno_template(SAMPLE_RATE)

        # DDS-driven values
        self._hr     = 60.0
        self._spo2   = 98.0
        self._etco2  = 38.0
        self._nibp_s = 120.0
        self._nibp_d = 80.0
        self.paused  = False

        # Frames per tick derived from timer interval
        self._timer_ms = 40
        self._new_per_tick = int(SAMPLE_RATE * self._timer_ms / 1000)

        self._build_ui()
        self._set_icon()

        # ── Animation timer ──────────────────────────────────────────
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(self._timer_ms)    # 25 fps

    # ── Window icon ─────────────────────────────────────────────────
    def _set_icon(self):
        _px = QPixmap("../../resource/images/rti_logo.ico")
        if not _px.isNull():
            self.setWindowIcon(QIcon(_px))

    # ── Style ────────────────────────────────────────────────────────
    def _apply_global_style(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget#central {{
                background-color: {BG_MAIN};
            }}
        """)

    # ── Layout ───────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        central.setStyleSheet(f"background-color: {BG_MAIN};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ───────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(80)
        header.setStyleSheet(f"background-color: {BG_HEADER}; border-bottom: 2px solid {RTI_BLUE};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)

        _logo_px = QPixmap("../../resource/images/rti_logo.ico")
        if not _logo_px.isNull():
            logo_lbl = QLabel()
            logo_lbl.setStyleSheet("background: transparent;")
            logo_lbl.setPixmap(_logo_px.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            h_layout.addWidget(logo_lbl)

        rti_lbl = QLabel("RTI Connext")
        rti_lbl.setStyleSheet(f"color: {RTI_BLUE}; font-size: 34px; font-weight: bold; background: transparent;")
        h_layout.addWidget(rti_lbl)

        bar = QLabel("|")
        bar.setStyleSheet(f"color: #334455; font-size: 34px; background: transparent;")
        h_layout.addWidget(bar)

        title_lbl = QLabel("Patient Monitor")
        title_lbl.setStyleSheet("color: #E0E8F0; font-size: 34px; font-weight: bold; background: transparent;")
        h_layout.addWidget(title_lbl)

        h_layout.addStretch()

        self.status_lbl = QLabel("● CONNECTED — Streaming QoS")
        self.status_lbl.setStyleSheet(f"color: {COLOR_HR}; font-size: 20px; background: transparent;")
        h_layout.addWidget(self.status_lbl)

        self.state_lbl = QLabel("ON")
        self.state_lbl.setStyleSheet(
            f"color: #000; background-color: {COLOR_HR}; font-size: 20px; "
            f"font-weight: bold; padding: 3px 10px; border-radius: 4px; margin-left: 10px;"
        )
        h_layout.addWidget(self.state_lbl)

        root.addWidget(header)

        # ── Vital grid ────────────────────────────────────────────────
        grid_container = QWidget()
        grid_container.setStyleSheet(f"background-color: {BG_MAIN};")
        grid = QGridLayout(grid_container)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setSpacing(10)

        grid.addWidget(self.hr_panel,    0, 0)
        grid.addWidget(self.spo2_panel,  0, 1)
        grid.addWidget(self.etco2_panel, 1, 0)
        grid.addWidget(self.nibp_panel,  1, 1)

        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        root.addWidget(grid_container, 1)

        # ── Footer bar ────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(44)
        footer.setStyleSheet(f"background-color: {BG_HEADER}; border-top: 1px solid {BORDER_DIM};")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(20, 0, 20, 0)
        f_lbl = QLabel("Real-Time Innovations  ·  RTI Connext  ·  MedTech Reference Architecture")
        f_lbl.setStyleSheet("color: #445566; font-size: 20px; background: transparent;")
        f_layout.addWidget(f_lbl)
        f_layout.addStretch()
        root.addWidget(footer)

    # ── Animation tick ───────────────────────────────────────────────
    def _tick(self):
        if self.paused:
            return
        # ECG — rate driven by HR (beats per minute → bps)
        self.hr_panel.beat_rate    = self._hr / 60.0
        # SpO2 — same rate as HR (plethysmograph synced to cardiac cycle)
        self.spo2_panel.beat_rate  = self._hr / 60.0
        # EtCO2 — respiratory rate ≈ HR/4, capped 8-30 breaths/min
        rr = max(8.0, min(30.0, self._hr / 4.0))
        self.etco2_panel.beat_rate = rr / 60.0

        self.hr_panel.advance_waveform(self._ecg_tpl,   self._new_per_tick)
        self.spo2_panel.advance_waveform(self._pleth_tpl, self._new_per_tick)
        self.etco2_panel.advance_waveform(self._capno_tpl, self._new_per_tick)
        # EtCO2 - capnogram height, capped to 60 mmHg for stability in the UI
        self.etco2_panel.amplitude = max(0.0, min(60.0, self._etco2)) / 60.0

        self.hr_panel.update_curve()
        self.spo2_panel.update_curve()
        self.etco2_panel.update_curve()

    # ── DDS value update (called from polling timer in main app) ─────
    def update_vitals(self, hr, spo2, etco2, nibp_s, nibp_d):
        self._hr     = hr
        self._spo2   = spo2
        self._etco2  = etco2
        self._nibp_s = nibp_s
        self._nibp_d = nibp_d

        self.hr_panel.set_value(hr)
        self.spo2_panel.set_value(spo2)
        self.etco2_panel.set_value(etco2)
        self.nibp_panel.set_values(nibp_s, nibp_d)

    def set_state(self, state: str):
        self.paused = (state == "PAUSED")
        colors = {"ON": COLOR_HR, "PAUSED": RTI_ORANGE, "OFF": "#FF4444"}
        c = colors.get(state, "#888")
        self.state_lbl.setText(state)
        self.state_lbl.setStyleSheet(
            f"color: #000; background-color: {c}; font-size: 20px; "
            f"font-weight: bold; padding: 3px 10px; border-radius: 4px; margin-left: 10px;"
        )


# ─── Application class ────────────────────────────────────────────────────
class PatientMonitorApp:
    def __init__(self):
        self.pm_status      = None
        self.status_writer  = None
        self.hb_writer      = None
        self.vitals_reader  = None
        self.cmd_reader     = None
        self.bridge         = DdsBridge()
        self.window         = None

    # ── DDS heartbeat thread ─────────────────────────────────────────
    def write_hb(self):
        while self.pm_status.status != Common.DeviceStatuses.OFF:
            hb = Common.DeviceHeartbeat()
            hb.device = Common.DeviceType.PATIENT_MONITOR
            self.hb_writer.write(hb)
            time.sleep(0.05)

    # ── DDS polling (called by Qt timer every 150 ms) ────────────────
    def _poll_dds(self):
        # Vitals
        if self.pm_status.status == Common.DeviceStatuses.ON:
            samples = self.vitals_reader.take_data()
            for sample in samples:
                self.window.update_vitals(
                    float(sample.hr),
                    float(sample.spo2),
                    float(sample.etco2),
                    float(sample.nibp_s),
                    float(sample.nibp_d),
                )
        # Commands
        cmd_samples = self.cmd_reader.take_data()
        for sample in cmd_samples:
            if sample.command == Orchestrator.DeviceCommands.START:
                print("Patient Monitor received Start command")
                self.pm_status.status = Common.DeviceStatuses.ON
                self.window.set_state("ON")
            elif sample.command == Orchestrator.DeviceCommands.PAUSE:
                print("Patient Monitor received Pause command")
                self.pm_status.status = Common.DeviceStatuses.PAUSED
                self.window.set_state("PAUSED")
            else:
                print("Patient Monitor received Shutdown command")
                self.pm_status.status = Common.DeviceStatuses.OFF
                self.window.set_state("OFF")
                QApplication.quit()
            self.status_writer.write(self.pm_status)

    # ── Connext setup ────────────────────────────────────────────────
    def connext_setup(self):
        DdsUtils.register_type(Common.DeviceStatus)
        DdsUtils.register_type(Common.DeviceHeartbeat)
        DdsUtils.register_type(Orchestrator.DeviceCommand)
        DdsUtils.register_type(PatientMonitor.Vitals)

        qos_provider = dds.QosProvider.default
        participant = qos_provider.create_participant_from_config(
            DdsUtils.patient_monitor_dp_fqn
        )

        self.status_writer = dds.DataWriter(
            participant.find_datawriter(DdsUtils.status_dw_fqn)
        )
        self.hb_writer = dds.DataWriter(
            participant.find_datawriter(DdsUtils.device_hb_dw_fqn)
        )
        self.vitals_reader = dds.DataReader(
            participant.find_datareader(DdsUtils.vitals_dr_fqn)
        )
        self.cmd_reader = dds.DataReader(
            participant.find_datareader(DdsUtils.device_command_dr_fqn)
        )
        self.pm_status = Common.DeviceStatus(
            device=Common.DeviceType.PATIENT_MONITOR,
            status=Common.DeviceStatuses.ON,
        )
        self.status_writer.write(self.pm_status)

    # ── Entry point ──────────────────────────────────────────────────
    def run(self):
        app = QApplication(sys.argv)
        app.setStyle("Fusion")

        self.window = PatientMonitorWindow()
        self.connext_setup()

        # DDS polling timer (Qt timer — same thread, no locking needed)
        dds_timer = QTimer()
        dds_timer.timeout.connect(self._poll_dds)
        dds_timer.start(150)

        # Heartbeat in background thread
        hb_thread = threading.Thread(target=self.write_hb, daemon=True)
        hb_thread.start()

        self.window.show()
        print("Started Patient Monitor")

        app.exec_()

        print("Shutting down Patient Monitor")
        self.pm_status.status = Common.DeviceStatuses.OFF


if __name__ == "__main__":
    PatientMonitorApp().run()
