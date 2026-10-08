#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

from PySide6.QtGui import QFont

UI_FONT_FAMILY = "DejaVu Sans"
UI_MONOSPACE_FAMILY = "DejaVu Sans Mono"
UI_BASE_FONT_SIZE_PT = 10
LOG_TOGGLE_STYLE = """
    QPushButton {
        background-color: transparent;
        color: #C8D8E8;
        border: 1px solid #29415A;
        border-radius: 5px;
        font-size: 12px;
        font-weight: bold;
        padding: 5px 10px;
    }
    QPushButton:hover {
        background-color: #14283D;
        border-color: #4D99FF;
    }
"""


def apply_application_font(application):
    application.setFont(QFont(UI_FONT_FAMILY, UI_BASE_FONT_SIZE_PT))
