"""Navegación lateral con los índices de las vistas existentes."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QListWidget, QListWidgetItem


def ui_icon(name):
    return QIcon(str(Path(__file__).resolve().parent / "assets" / f"{name}.svg"))


class Navigation(QListWidget):
    currentChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("navigation")
        self.setAccessibleName("Secciones de LockIn")
        self.setIconSize(QSize(21, 21))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for title, icon in (("Sesión", "session"), ("Calibración", "calibrate"), ("Alertas", "bell")):
            item = QListWidgetItem(ui_icon(icon), title)
            item.setSizeHint(QSize(156, 48))
            self.addItem(item)
        self.setCurrentRow(0)
        self.currentRowChanged.connect(self.currentChanged)

    def currentIndex(self):
        return self.currentRow()

    def setCurrentIndex(self, index):
        if 0 <= index < self.count():
            self.setCurrentRow(index)

    def tabText(self, index):
        return self.item(index).text()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Left):
            offset = 1 if event.key() == Qt.Key.Key_Right else -1
            self.setCurrentIndex(max(0, min(self.count() - 1, self.currentRow() + offset)))
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.setProperty("keyboardFocus", True)
        self.style().unpolish(self)
        self.style().polish(self)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setProperty("keyboardFocus", False)
        self.style().unpolish(self)
        self.style().polish(self)
