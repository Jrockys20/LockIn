"""Tema compartido del escritorio LockIn, sin cambios en la lógica."""

from pathlib import Path
import os

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

SWITCH_COLORS = {
    "off": "#55585E", "on": "#FFAE78", "border": "#70747C",
    "thumb": "#F3F1EE", "off_text": "#F3F1EE", "on_text": "#201B17",
    "focus": "#FFAE78",
}

STYLE = """
QWidget { background: #18191C; color: #F3F1EE; font-family: "Segoe UI"; font-size: 14px; }
QLabel, QWidget[role="plain"] { background: transparent; }
QLabel#cameraPreview { background: #111215; color: #B0B4BE; border: 1px solid #34373D; border-radius: 5px; }
QWidget#sidebar { background: #1D1F23; border-right: 1px solid #34373D; }
QListWidget#navigation { background: transparent; border: none; outline: 0; font-size: 14px; }
QListWidget#navigation::item { border-left: 3px solid transparent; border-radius: 4px; padding-left: 9px; margin: 3px 0; }
QListWidget#navigation::item:selected { background: #34373D; border-left-color: #FFAE78; color: #F3F1EE; }
QListWidget#navigation::item:hover { background: #292C32; }
QListWidget#navigation[keyboardFocus="true"]::item:selected { border: 1px solid #FFAE78; border-left-width: 3px; }
QLabel[role="footer"], QLabel#privacy { font-size: 12px; color: #B0B4BE; }
QFrame[role="section"] { background: transparent; border: none; }
QGroupBox[role="reference"] { background: transparent; border: none; border-bottom: 1px solid #34373D; border-radius: 0; }
QGroupBox[role="reference"]::title { font-size: 17px; }
QCheckBox[role="ruleTitle"] { font-size: 20px; font-weight: 600; }
QWidget#brandGroup { background: transparent; }
QFrame#sectionDivider { background: #34373D; border: none; margin: 0; }
QLabel[role="stateTitle"] { font-size: 20px; font-weight: 600; }
QLabel[role="measurement"] { font-family: "Consolas"; font-size: 14px; }
QLabel[role="fieldLabel"] { font-size: 13px; color: #B0B4BE; }
QLabel#brand { font-size: 23px; font-weight: 700; }
QLabel[role="pageTitle"] { font-size: 28px; font-weight: 600; }
QLabel[role="sectionTitle"] { font-size: 19px; font-weight: 600; }
QLabel[role="muted"] { color: #B0B4BE; }
QLabel[role="counter"] { color: #D5D6D4; font-family: "Consolas"; font-size: 12px; }
QLabel[tone="good"] { color: #A7D6AA; }
QLabel[tone="waiting"] { color: #E5BB76; }
QLabel[tone="danger"] { color: #ED9898; }
QLabel[tone="neutral"] { color: #B0B4BE; }
QFrame[role="surface"], QGroupBox {
    background: #222429; border: 1px solid #34373D; border-radius: 5px;
}
QGroupBox { margin-top: 12px; padding: 14px 12px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #F3F1EE; }
QFrame[role="surface"] QLabel, QGroupBox QLabel, QWidget[role="plain"] { background: transparent; }
QFrame[role="signalRow"] { background: transparent; border: none; border-bottom: 1px solid #34373D; }
QFrame#operatingState { background: #262A2D; border: 1px solid #4A5055; border-radius: 5px; }
QPushButton {
    background: #292D30; color: #F3F1EE; border: 1px solid #555B60;
    border-radius: 5px; padding: 7px 11px; min-height: 20px;
}
QPushButton:hover { background: #34393D; border-color: #899299; }
QPushButton:pressed { background: #41464A; }
QPushButton:disabled { color: #858B90; background: #222429; border-color: #34373D; }
QPushButton[role="primary"] { background: #FFAE78; color: #201B17; border-color: #FFAE78; font-weight: 600; }
QPushButton[role="primary"]:hover { background: #FFC49D; }
QPushButton[role="primary"]:disabled { background: #61452F; color: #BDA995; border-color: #61452F; }
QPushButton:focus, QComboBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QCheckBox:focus { border: 1px solid #FFAE78; }
QComboBox, QDoubleSpinBox, QLineEdit {
    background: #1C1F21; color: #F3F1EE; border: 1px solid #555B60;
    border-radius: 4px; padding: 5px 7px; min-height: 20px;
}
QComboBox:disabled, QDoubleSpinBox:disabled { color: #858B90; border-color: #34373D; }
QComboBox QAbstractItemView { background: #222429; color: #F3F1EE; selection-background-color: #74472B; }
QLineEdit#videoPath { background: transparent; border: none; padding-left: 0; font-weight: 600; }
QCheckBox { background: transparent; spacing: 7px; padding: 4px 2px; border: 1px solid transparent; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #899299; border-radius: 3px; background: #1C1F21; }
QCheckBox::indicator:checked { background: #FFAE78; border-color: #FFAE78; image: url("@ASSETS@/check.svg"); }
QCheckBox::indicator:disabled { border-color: #555B60; background: #34373D; }
QComboBox::drop-down { subcontrol-origin: border; subcontrol-position: top right; width: 23px; border-left: 1px solid #555B60; }
QComboBox::down-arrow { image: url("@ASSETS@/chevron-down.svg"); width: 12px; height: 12px; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { subcontrol-origin: border; width: 19px; background: #292D30; border-left: 1px solid #555B60; }
QDoubleSpinBox::up-button { subcontrol-position: top right; }
QDoubleSpinBox::down-button { subcontrol-position: bottom right; }
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover { background: #41464A; }
QDoubleSpinBox::up-arrow { image: url("@ASSETS@/chevron-up.svg"); width: 10px; height: 10px; }
QDoubleSpinBox::down-arrow { image: url("@ASSETS@/chevron-down.svg"); width: 10px; height: 10px; }
QToolButton { background: transparent; color: #B0B4BE; padding: 5px; border: 1px solid transparent; border-radius: 4px; }
QToolButton:hover { background: #34393D; }
QToolButton:focus { border-color: #FFAE78; }
QProgressBar { background: #3B3F42; border: none; border-radius: 4px; text-align: center; min-height: 15px; }
QProgressBar::chunk { background: #FFAE78; border-radius: 4px; }
QProgressBar#orientationBar[tone="good"]::chunk { background: #A7D6AA; }
QProgressBar#orientationBar[tone="waiting"]::chunk { background: #E5BB76; }
QProgressBar#orientationBar[tone="neutral"]::chunk { background: #555B60; }
QSlider::groove:horizontal { height: 5px; background: #555B60; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #FFAE78; border-radius: 2px; }
QSlider::handle:horizontal { width: 15px; margin: -5px 0; border-radius: 7px; background: #F3F1EE; }
QScrollArea { border: none; background: #18191C; }
QScrollBar:vertical { background: #1B1E20; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #545C62; min-height: 30px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QToolTip { background: #292D30; color: #F3F1EE; border: 1px solid #70777D; padding: 5px; }
"""

def apply_theme(window):
    if "Segoe UI" not in QFontDatabase.families():
        for name in ("segoeui.ttf", "seguisb.ttf", "consola.ttf"):
            font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if font.exists():
                QFontDatabase.addApplicationFont(str(font))
    window.setFont(QFont("Segoe UI", 10))
    palette = window.palette()
    for role, color in (
        (QPalette.ColorRole.Window, "#18191C"),
        (QPalette.ColorRole.WindowText, "#F3F1EE"),
        (QPalette.ColorRole.Base, "#1C1F21"),
        (QPalette.ColorRole.Text, "#F3F1EE"),
        (QPalette.ColorRole.Button, "#292D30"),
        (QPalette.ColorRole.ButtonText, "#F3F1EE"),
        (QPalette.ColorRole.Mid, "#70777D"),
        (QPalette.ColorRole.Highlight, "#FFAE78"),
        (QPalette.ColorRole.HighlightedText, "#201B17"),
    ):
        palette.setColor(role, QColor(color))
    window.setPalette(palette)
    window.setStyleSheet(STYLE.replace("@ASSETS@", (Path(__file__).resolve().parent / "assets").as_posix()))


def set_tone(widget, tone):
    if widget.property("tone") == tone:
        return
    widget.setProperty("tone", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
