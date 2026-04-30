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
import signal

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QFrame,
    QHBoxLayout, QVBoxLayout, QSizePolicy, QScrollArea
)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal, QObject
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QConicalGradient, QPainterPath,
    QPixmap, QIcon
)

import rti.connextdds as dds
from Types import Common, SurgicalRobot, Orchestrator, DdsEntities
from DdsUtils import register_type

# ─── RTI Brand Colors ────────────────────────────────────────────────────
RTI_BLUE   = "#004C97"
RTI_ORANGE = "#ED8B00"
BG_MAIN    = "#0A0E17"
BG_PANEL   = "#0F1822"
BG_ROW_ALT = "#0D1520"
BG_HEADER  = "#071020"
BORDER_DIM = "#1A2A3A"

# Per-joint color palette
JOINT_COLORS = {
    SurgicalRobot.Motors.BASE:     RTI_BLUE,
    SurgicalRobot.Motors.SHOULDER: RTI_ORANGE,
    SurgicalRobot.Motors.ELBOW:    "#00BFFF",   # Electric blue
    SurgicalRobot.Motors.WRIST:    "#7CFC00",   # Lime green
    SurgicalRobot.Motors.HAND:     "#DA70D6",   # Orchid
}

JOINT_NAMES = {
    SurgicalRobot.Motors.BASE:     "BASE",
    SurgicalRobot.Motors.SHOULDER: "SHOULDER",
    SurgicalRobot.Motors.ELBOW:    "ELBOW",
    SurgicalRobot.Motors.WRIST:    "WRIST",
    SurgicalRobot.Motors.HAND:     "HAND",
}

UPDATE_MS   = 100  # refresh rate ms (~10 fps)

# Starting joint angles shown before the first DDS sample arrives
INITIAL_ANGLES = {
    SurgicalRobot.Motors.BASE:     204.0,
    SurgicalRobot.Motors.SHOULDER: 176.0,
    SurgicalRobot.Motors.ELBOW:    156.0,
    SurgicalRobot.Motors.WRIST:    165.0,
    SurgicalRobot.Motors.HAND:     151.0,
}


# ─── Circular Arc Gauge ──────────────────────────────────────────────────
class ArcGauge(QWidget):
    """Draws a 270° arc gauge showing angle 0-360°."""

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self._value = 180.0
        self.setFixedSize(110, 110)
        self.setStyleSheet("background: transparent;")

    def set_value(self, v: float):
        self._value = v % 360.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height()) - 10
        rect = QRectF((self.width() - side) / 2,
                      (self.height() - side) / 2,
                      side, side)

        # ── Background track ──────────────────────────────────────
        pen_bg = QPen(QColor("#1A2A40"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
        p.setPen(pen_bg)
        p.drawArc(rect, 225 * 16, -270 * 16)   # 270° arc, starts at 225°

        # ── Foreground arc (value / 360 × 270°) ───────────────────
        span = int((self._value / 360.0) * 270 * 16)
        grad_color = self.color
        pen_fg = QPen(grad_color, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
        p.setPen(pen_fg)
        p.drawArc(rect, 225 * 16, -span)

        # ── Needle ────────────────────────────────────────────────
        import math as _math
        cx, cy = self.width() / 2, self.height() / 2
        needle_r = (side / 2) * 0.72
        hub_r    = (side / 2) * 0.12
        # Qt arc: 0°=east, positive=CCW; our arc starts at 225° spanning -270°
        angle_deg = 225.0 - (self._value / 360.0) * 270.0
        angle_rad = _math.radians(angle_deg)
        tip_x  = cx + needle_r * _math.cos(angle_rad)
        tip_y  = cy - needle_r * _math.sin(angle_rad)
        # Back stub in opposite direction
        back_x = cx - hub_r * _math.cos(angle_rad)
        back_y = cy + hub_r * _math.sin(angle_rad)
        # Draw shadow
        pen_shadow = QPen(QColor("#000000"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen_shadow)
        p.drawLine(QPointF(back_x + 1, back_y + 1), QPointF(tip_x + 1, tip_y + 1))
        # Draw needle
        pen_needle = QPen(grad_color, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen_needle)
        p.drawLine(QPointF(back_x, back_y), QPointF(tip_x, tip_y))

        # ── Centre dot ────────────────────────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad_color))
        p.drawEllipse(QPointF(cx, cy), 4, 4)

        p.end()


# ─── Direction indicator ─────────────────────────────────────────────────
class DirectionBadge(QLabel):
    def __init__(self, parent=None):
        super().__init__("  —  ", parent)
        self._dir = "STATIONARY"
        self._update_style()

    def set_direction(self, direction: str):
        self._dir = direction
        symbols = {"INCREMENT": "  ▲  INC", "DECREMENT": "  ▼  DEC", "STATIONARY": "  —  "}
        self.setText(symbols.get(direction, "  —  "))
        self._update_style()

    def _update_style(self):
        colors = {
            "INCREMENT":  (RTI_ORANGE, "#1A0F00"),
            "DECREMENT":  ("#FF4444",  "#1A0505"),
            "STATIONARY": ("#445566",  "#0F151C"),
        }
        fg, bg = colors.get(self._dir, ("#445566", "#0F151C"))
        self.setStyleSheet(
            f"color: {fg}; background-color: {bg}; font-size: 26px; font-weight: bold; "
            f"padding: 4px 10px; border-radius: 4px; border: 1px solid {fg}44;"
        )


# ─── Single joint row widget ──────────────────────────────────────────────
class JointRow(QFrame):
    def __init__(self, motor: SurgicalRobot.Motors, parent=None):
        super().__init__(parent)
        self.motor = motor
        self.color = JOINT_COLORS[motor]
        self.name  = JOINT_NAMES[motor]
        self._angle = 180.0

        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet(f"""
            JointRow {{
                background-color: {BG_PANEL};
                border: 1px solid {self.color}33;
                border-radius: 6px;
            }}
        """)
        self._build_ui()

    def _build_ui(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)

        # Joint name
        name_lbl = QLabel(self.name)
        name_lbl.setFixedWidth(190)
        name_lbl.setStyleSheet(
            f"color: {self.color}; font-size: 26px; font-weight: bold; "
            f"background: transparent; letter-spacing: 1px;"
        )
        row.addWidget(name_lbl)

        # Arc gauge + value label below
        gauge_col = QVBoxLayout()
        gauge_col.setContentsMargins(0, 0, 0, 0)
        gauge_col.setSpacing(2)
        self.gauge = ArcGauge(self.color)
        self.gauge.set_value(180.0)
        gauge_col.addWidget(self.gauge, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.angle_lbl = QLabel("180.0°")
        self.angle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.angle_lbl.setStyleSheet(
            f"color: {self.color}; font-size: 20px; font-weight: bold; "
            f"background: transparent;"
        )
        gauge_col.addWidget(self.angle_lbl)
        row.addLayout(gauge_col)

        # Direction badge
        self.dir_badge = DirectionBadge()
        self.dir_badge.setVisible(False)

    def update_data(self, angle: float, direction: str):
        self._angle = angle
        self.gauge.set_value(angle)
        self.angle_lbl.setText(f"{angle:.1f}°")
        self.dir_badge.set_direction(direction)


# ─── 2-D Kinematic Arm Visualisation ──────────────────────────────────────
# Forward-kinematics: each joint angle is *relative* to the previous segment.
# 180° = no bend (straight continuation); values > 180 bend counter-clockwise,
# values < 180 bend clockwise, mirroring the arc-gauge convention in JointRow.
#
# Joint order: BASE → SHOULDER → ELBOW → WRIST → HAND (5 links, same as joints)
# A 6th "link" past HAND represents the end-effector stub.

_MOTORS_ORDERED = [
    SurgicalRobot.Motors.BASE,
    SurgicalRobot.Motors.SHOULDER,
    SurgicalRobot.Motors.ELBOW,
    SurgicalRobot.Motors.WRIST,
    SurgicalRobot.Motors.HAND,
]


class ArmVizWidget(QWidget):
    """Draws a simplified 2-D stick-figure robotic arm using QPainter.

    The arm is rooted at the bottom-centre of the widget and extends
    upward.  Each joint bends by (angle - 180°) relative to the incoming
    segment direction, so at 180° all segments are collinear (straight up).
    """

    SEGMENT_LEN = 70   # px — length of each arm link (scaled dynamically)
    JOINT_R     = 12   # px — radius of joint circles
    EE_SIZE     = 16   # px — half-size of end-effector marker
    GROUND_W    = 80   # px — half-width of ground hatch
    GROUND_LINES = 6   # number of hatch lines under base

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angles: dict = {m: 180.0 for m in _MOTORS_ORDERED}
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background-color: {BG_PANEL};")

    def update_angles(self, angles: dict):
        """Receive updated angle dict and schedule a repaint."""
        self._angles = dict(angles)
        self.update()   # schedules paintEvent on next event-loop iteration

    # ── painting ──────────────────────────────────────────────────────────
    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.fillRect(self.rect(), QColor(BG_PANEL))

        # Title
        p.setPen(QPen(QColor("#445566")))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(12, 22, "ARM VISUALIZATION")

        # Scale segment length so the full arm (5 links) fills ~90 % of the
        # widget height, leaving room for the title at top and ground at bottom.
        usable_h = h - 70   # subtract top title space + bottom ground space
        seg = int(usable_h * 0.90 / len(_MOTORS_ORDERED))
        seg = max(seg, 40)

        # Base point — bottom centre (leave room for ground symbol)
        bx = w / 2.0
        by = h - 36.0

        # ── Ground symbol ──────────────────────────────────────────────
        gw = self.GROUND_W
        ground_pen = QPen(QColor("#334455"), 2)
        p.setPen(ground_pen)
        p.drawLine(QPointF(bx - gw, by), QPointF(bx + gw, by))
        hatch_dx = gw / (self.GROUND_LINES + 1)
        for i in range(self.GROUND_LINES):
            hx = bx - gw + hatch_dx * (i + 1)
            p.drawLine(QPointF(hx, by), QPointF(hx - 10, by + 12))

        # ── Forward kinematics ─────────────────────────────────────────
        # Start pointing straight up (π/2 in unit-circle convention;
        # screen Y is inverted, so subtract when computing screen coords).
        cumul_dir = math.pi / 2.0
        x, y = bx, by

        points = [(x, y)]   # joint positions

        for motor in _MOTORS_ORDERED:
            angle = self._angles.get(motor, 180.0)
            delta_rad = (angle - 180.0) * math.pi / 180.0
            cumul_dir += delta_rad
            nx = x + seg * math.cos(cumul_dir)
            ny = y - seg * math.sin(cumul_dir)  # screen Y inverted
            points.append((nx, ny))
            x, y = nx, ny

        # ── Draw links ────────────────────────────────────────────────
        link_pen_width = 7
        for i, motor in enumerate(_MOTORS_ORDERED):
            color = QColor(JOINT_COLORS[motor])
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            pen = QPen(color, link_pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

        # ── Draw end-effector stub (past HAND) ────────────────────────
        ee_color = QColor(JOINT_COLORS[SurgicalRobot.Motors.HAND])
        ee_pen = QPen(ee_color, 2)
        p.setPen(ee_pen)
        ex, ey = points[-1]
        # Small diamond
        es = self.EE_SIZE
        diamond = QPainterPath()
        diamond.moveTo(ex,      ey - es)
        diamond.lineTo(ex + es, ey)
        diamond.lineTo(ex,      ey + es)
        diamond.lineTo(ex - es, ey)
        diamond.closeSubpath()
        p.setBrush(QBrush(ee_color.darker(180)))
        p.drawPath(diamond)

        # ── Draw joint circles + labels ───────────────────────────────
        jr = self.JOINT_R
        for i, motor in enumerate(_MOTORS_ORDERED):
            color = QColor(JOINT_COLORS[motor])
            cx, cy = points[i]
            # filled circle
            p.setPen(QPen(color, 2))
            p.setBrush(QBrush(color.darker(200)))
            p.drawEllipse(QPointF(cx, cy), jr, jr)
            # joint name label (abbreviated, 3 chars)
            name = JOINT_NAMES[motor][:3]
            p.setPen(QPen(color))
            p.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
            label_x = cx + jr + 8
            label_y = cy + 6
            p.drawText(QPointF(label_x, label_y), name)

        # ── Angle readouts next to each link midpoint ─────────────────
        p.setFont(QFont("Courier New", 14))
        for i, motor in enumerate(_MOTORS_ORDERED):
            color = QColor(JOINT_COLORS[motor])
            p.setPen(QPen(color.lighter(130)))
            mx = (points[i][0] + points[i + 1][0]) / 2 + 10
            my = (points[i][1] + points[i + 1][1]) / 2
            p.drawText(QPointF(mx, my), f"{self._angles.get(motor, 180.0):.0f}°")

        p.end()


# ─── Main Window ─────────────────────────────────────────────────────────
class ArmWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTI Connext — Surgical Arm Monitor")
        self.setMinimumSize(640, 650)
        self.setStyleSheet(f"background-color: {BG_MAIN};")
        _icon_px = QPixmap("../../resource/images/Arm-Monitor.png")
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

        # ── Header ───────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(80)
        header.setStyleSheet(
            f"background-color: {BG_HEADER}; border-bottom: 2px solid {RTI_BLUE};"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)

        _logo_px = QPixmap("../../resource/images/Arm-Monitor.png")
        if not _logo_px.isNull():
            logo_lbl = QLabel()
            logo_lbl.setStyleSheet("background: transparent;")
            logo_lbl.setPixmap(_logo_px.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            h_layout.addWidget(logo_lbl)

        rti_lbl = QLabel("RTI Connext")
        rti_lbl.setStyleSheet(
            f"color: {RTI_BLUE}; font-size: 28px; font-weight: bold; background: transparent;"
        )
        h_layout.addWidget(rti_lbl)

        bar = QLabel("|")
        bar.setStyleSheet("color: #334455; font-size: 30px; background: transparent;")
        h_layout.addWidget(bar)

        title_lbl = QLabel("Surgical Arm Monitor")
        title_lbl.setStyleSheet(
            "color: #E0E8F0; font-size: 38px; font-weight: bold; background: transparent;"
        )
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        self.state_lbl = QLabel("ON")
        self.state_lbl.setStyleSheet(
            f"color: #000; background-color: #00E676; font-size: 22px; "
            f"font-weight: bold; padding: 3px 12px; border-radius: 4px;"
        )
        h_layout.addWidget(self.state_lbl)

        qos_lbl = QLabel("Command QoS")
        qos_lbl.setStyleSheet(
            f"color: {RTI_ORANGE}88; font-size: 22px; background: transparent; margin-left: 12px;"
        )
        h_layout.addWidget(qos_lbl)

        root.addWidget(header)

        # ── Body: arm visualisation only ─────────────────────────
        self._arm_angles = dict(INITIAL_ANGLES)
        self.arm_viz = ArmVizWidget()
        self.arm_viz.update_angles(self._arm_angles)
        root.addWidget(self.arm_viz, 1)

        # ── Footer ───────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(44)
        footer.setStyleSheet(
            f"background-color: {BG_HEADER}; border-top: 1px solid {BORDER_DIM};"
        )
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(20, 0, 20, 0)
        f_lbl = QLabel(
            "Real-Time Innovations  ·  RTI Connext  ·  MedTech Reference Architecture"
        )
        f_lbl.setStyleSheet("color: #445566; font-size: 20px; background: transparent;")
        f_layout.addWidget(f_lbl)
        f_layout.addStretch()
        root.addWidget(footer)

    def update_joint(self, motor: SurgicalRobot.Motors, angle: float, direction: str):
        self._arm_angles[motor] = angle
        self.arm_viz.update_angles(self._arm_angles)

    def set_state(self, state: str):
        colors = {"ON": "#00E676", "PAUSED": RTI_ORANGE, "OFF": "#FF4444"}
        c = colors.get(state, "#888")
        self.state_lbl.setText(state)
        self.state_lbl.setStyleSheet(
            f"color: #000; background-color: {c}; font-size: 22px; "
            f"font-weight: bold; padding: 3px 12px; border-radius: 4px;"
        )


# ─── Application class ────────────────────────────────────────────────────
class ArmApp:
    def __init__(self):
        self.angles = {
            SurgicalRobot.Motors.BASE:     204.0,
            SurgicalRobot.Motors.SHOULDER: 176.0,
            SurgicalRobot.Motors.ELBOW:    156.0,
            SurgicalRobot.Motors.WRIST:    165.0,
            SurgicalRobot.Motors.HAND:     151.0,
        }
        self.directions = {
            SurgicalRobot.Motors.BASE: "STATIONARY",
            SurgicalRobot.Motors.SHOULDER: "STATIONARY",
            SurgicalRobot.Motors.ELBOW: "STATIONARY",
            SurgicalRobot.Motors.WRIST: "STATIONARY",
            SurgicalRobot.Motors.HAND: "STATIONARY",
        }

        self.arm_status        = None
        self.status_writer     = None
        self.hb_writer         = None
        self.motor_control_reader = None
        self.cmd_reader        = None
        self.window            = None
        self.cmd_waitset       = None

    # ── DDS heartbeat thread ─────────────────────────────────────────
    def write_hb(self, hb_writer):
        while self.arm_status.status != Common.DeviceStatuses.OFF:
            hb = Common.DeviceHeartbeat()
            hb.device = Common.DeviceType.ARM
            hb_writer.write(hb)
            time.sleep(0.05)

    # ── DDS poll timer callback (Qt main thread) ─────────────────────
    def _poll_dds(self):
        # Motor control samples
        samples = self.motor_control_reader.take_data()
        for sample in samples:
            if self.arm_status.status == Common.DeviceStatuses.ON:
                if sample.direction == SurgicalRobot.MotorDirections.INCREMENT:
                    self.angles[sample.id] = (self.angles[sample.id] + 0.3) % 360.0
                    self.directions[sample.id] = "INCREMENT"
                elif sample.direction == SurgicalRobot.MotorDirections.DECREMENT:
                    self.angles[sample.id] = (self.angles[sample.id] - 0.3) % 360.0
                    self.directions[sample.id] = "DECREMENT"
                else:
                    self.directions[sample.id] = "STATIONARY"
            self.window.update_joint(
                sample.id, self.angles[sample.id], self.directions[sample.id]
            )

        # Command samples
        cmd_samples = self.cmd_reader.take_data()
        for sample in cmd_samples:
            if sample.command == Orchestrator.DeviceCommands.START:
                print("Arm received Start Command")
                self.arm_status.status = Common.DeviceStatuses.ON
                self.window.set_state("ON")
            elif sample.command == Orchestrator.DeviceCommands.PAUSE:
                print("Arm received Pause Command")
                self.arm_status.status = Common.DeviceStatuses.PAUSED
                self.window.set_state("PAUSED")
            else:
                print("Arm received Shutdown Command")
                self.arm_status.status = Common.DeviceStatuses.OFF
                self.window.set_state("OFF")
                QApplication.quit()
            self.status_writer.write(self.arm_status)

    def _cleanup(self):
        print("Shutting down Arm")

    # ── Connext setup ─────────────────────────────────────────────────
    def connext_setup(self):
        entities = DdsEntities.Constants
        register_type(Common.DeviceStatus)
        register_type(Common.DeviceHeartbeat)
        register_type(Orchestrator.DeviceCommand)
        register_type(SurgicalRobot.MotorControl)

        qos_provider = dds.QosProvider.default
        participant = qos_provider.create_participant_from_config(entities.ARM_DP)

        self.status_writer = dds.DataWriter(
            participant.find_datawriter(entities.STATUS_DW)
        )
        self.hb_writer = dds.DataWriter(
            participant.find_datawriter(entities.HB_DW)
        )
        self.arm_status = Common.DeviceStatus(
            device=Common.DeviceType.ARM, status=Common.DeviceStatuses.ON
        )
        self.status_writer.write(self.arm_status)

        self.motor_control_reader = dds.DataReader(
            participant.find_datareader(entities.MOTOR_CONTROL_DR)
        )
        self.cmd_reader = dds.DataReader(
            participant.find_datareader(entities.DEVICE_COMMAND_DR)
        )

    # ── Entry point ───────────────────────────────────────────────────
    def run(self):
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        _icon = QIcon(QPixmap("../../resource/images/Arm-Monitor.png"))
        if not _icon.isNull():
            app.setWindowIcon(_icon)

        self.window = ArmWindow()
        self.connext_setup()

        # DDS poll timer
        dds_timer = QTimer()
        dds_timer.timeout.connect(self._poll_dds)
        dds_timer.start(UPDATE_MS)

        # Heartbeat in background thread
        hb_thread = threading.Thread(
            target=self.write_hb, args=[self.hb_writer], daemon=True
        )
        hb_thread.start()

        # Allow Ctrl+C to cleanly quit the Qt event loop.
        # The QTimer is needed so the event loop periodically yields control
        # back to Python, enabling signal delivery.
        signal.signal(signal.SIGINT, lambda *_: app.quit())
        _sig_timer = QTimer()
        _sig_timer.timeout.connect(lambda: None)
        _sig_timer.start(300)
        app.aboutToQuit.connect(self._cleanup)

        self.window.show()
        print("Started Arm")

        app.exec()

        self.arm_status.status = Common.DeviceStatuses.OFF


if __name__ == "__main__":
    arm = ArmApp()
    arm.run()

