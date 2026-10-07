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
