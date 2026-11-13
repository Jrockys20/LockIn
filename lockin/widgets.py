"""Controles cuya rueda desplaza el contenedor sin cambiar sus ajustes."""

from PySide6.QtCore import QEvent, QPointF, QRectF, QSignalBlocker, QSize, Qt, Slot
from PySide6.QtGui import QColor, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractScrollArea, QApplication, QBoxLayout, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLayout, QSlider, QWidget,
)

from .theme import SWITCH_COLORS


def _scroll_container(widget, event):
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            viewport = parent.viewport()
            forwarded = QWheelEvent(
                QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())),
                event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                event.buttons(), event.modifiers(), event.phase(), event.inverted(),
                event.source(),
            )
            QApplication.sendEvent(viewport, forwarded)
            # Consume el original para no desplazar dos veces por propagación nativa.
            event.accept()
            return
        parent = parent.parentWidget()
    event.ignore()


class ScrollSafeDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("Escribe el valor o usa las flechas. La rueda desplaza la ventana.")
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.lineEdit() and event.type() == QEvent.Type.Wheel:
            _scroll_container(self, event)
            return True
        return super().eventFilter(watched, event)

    def wheelEvent(self, event):
        # También con foco: un clic accidental no habilita cambios por rueda.
        _scroll_container(self, event)


class ScrollSafeSlider(QSlider):
    def wheelEvent(self, event):
        _scroll_container(self, event)


class ScrollSafeComboBox(QComboBox):
    def wheelEvent(self, event):
        _scroll_container(self, event)


class AlertSwitch(QAbstractButton):
    """Interruptor accesible con estado marcado y rueda reservada al scroll."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(80, 36)
        self.toggled.connect(self._state_changed)
        self._state_changed(False)

    @Slot(bool)
    def _state_changed(self, enabled):
        self.setText("ON" if enabled else "OFF")
        self.setAccessibleDescription("Activadas" if enabled else "Desactivadas")
        self.update()

    def wheelEvent(self, event):
        _scroll_container(self, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        enabled = self.isChecked()
        colors = SWITCH_COLORS
        track = QRectF(3, 3, 74, 30)
        painter.setPen(QPen(QColor(colors["border"]), 1))
        painter.setBrush(QColor(colors["on"] if enabled else colors["off"]))
        painter.drawRoundedRect(track, 15, 15)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors["thumb"]))
        painter.drawEllipse(QRectF(50 if enabled else 6, 6, 24, 24))
        font = self.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(colors["on_text"] if enabled else colors["off_text"]))
        painter.drawText(QRectF(8 if enabled else 31, 3, 39, 30), Qt.AlignmentFlag.AlignCenter, self.text())
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(colors["focus"]), 1, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(QRectF(0.5, 0.5, 79, 35), 17, 17)


class AlertSelector(QWidget):
    """Editor visible del mismo estado de activación que usa el coordinador."""

    def __init__(self, source, context):
        super().__init__()
        self._source = source
        self.setProperty("role", "plain")
        label = QLabel("Alertas automáticas")
        self.switch = AlertSwitch()
        self.switch.setAccessibleName("Alertas automáticas en " + context)
        self.switch.setChecked(source.isChecked())
        self.switch.setToolTip(
            "Desactivarlas mantiene la cámara y el análisis. La rueda desplaza la ventana."
        )
        label.setBuddy(self.switch)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(label)
        layout.addWidget(self.switch)
        self.switch.toggled.connect(self._selected)
        source.toggled.connect(self._sync)

    @Slot(bool)
    def _selected(self, enabled):
        if self._source is not None:
            self._source.setChecked(enabled)

    @Slot(bool)
    def _sync(self, enabled):
        # Reflejar la otra vista no debe reenviar una segunda modificación.
        with QSignalBlocker(self.switch):
            self.switch.setChecked(enabled)
            self.switch._state_changed(enabled)

    def shutdown(self):
        self._source = None


class ResponsiveColumns(QWidget):
    """Reorganiza dos áreas sin recrear sus controles ni conexiones."""

    def __init__(self, first, second, *, breakpoint=900, stretch=(3, 2), parent=None):
        super().__init__(parent)
        self.setProperty("role", "plain")
        self.breakpoint = breakpoint
        self._stretch = stretch
        self._vertical = None
        self._box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(14)
        self._box.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._box.addWidget(first)
        self._box.addWidget(second)

    def minimumSizeHint(self):
        if not hasattr(self, "_box"):
            return super().minimumSizeHint()
        widths = [
            self._box.itemAt(i).widget().minimumSizeHint().expandedTo(
                self._box.itemAt(i).widget().minimumSize()
            ).width() for i in range(self._box.count())
        ]
        return QSize(max(widths, default=0), self._box.minimumSize().height())

    @property
    def is_stacked(self):
        return self._vertical

    def resizeEvent(self, event):
        super().resizeEvent(event)
        vertical = self.width() < self.breakpoint
        if vertical != self._vertical:
            self._vertical = vertical
            self._box.setDirection(
                QBoxLayout.Direction.TopToBottom if vertical else QBoxLayout.Direction.LeftToRight
            )
            for index, value in enumerate(self._stretch):
                self._box.setStretch(index, 0 if vertical else value)
            self.updateGeometry()
