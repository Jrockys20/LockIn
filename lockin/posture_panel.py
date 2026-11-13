"""Controles de postura y ausencia; solo se actualizan desde la GUI."""

import time

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QLabel, QWidget

from lockin.widgets import ScrollSafeDoubleSpinBox

from lockin.posture import MAX_POSTURE_GAP, PostureSettings


class PosturePanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker = None
        self._request_time: float | None = None
        self.angle_limit = self._spin(5, 60, 20, 5, 0, "°", "Margen de giro permitido")
        self.head_seconds = self._spin(0.5, 10, 2, 0.5, 1, " s", "Tiempo de cabeza apartada")
        self.absence_seconds = self._spin(0.5, 30, 3, 0.5, 1, " s", "Tiempo sin rostro")
        self.head_state = QLabel(self)
        self.angle_label = QLabel(self)
        self.head_counter = QLabel(self)
        self.head_signal = QLabel(self)
        self.head_message = QLabel(self)
        self.absence_state = QLabel(self)
        self.absence_counter = QLabel(self)
        self.absence_signal = QLabel(self)
        self.absence_message = QLabel(self)
        # La composición pertenece a AlertsView; no se crea otro formulario oculto.
        for label in (
            self.head_state, self.angle_label, self.head_counter, self.head_signal,
            self.head_message, self.absence_state, self.absence_counter,
            self.absence_signal, self.absence_message,
        ):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
        for spin in (self.angle_limit, self.head_seconds, self.absence_seconds):
            spin.setParent(self)
            spin.valueChanged.connect(self._settings_changed)
        self.reset()

    @staticmethod
    def _spin(lower, upper, value, step, decimals, suffix, name):
        spin = ScrollSafeDoubleSpinBox()
        spin.setRange(lower, upper)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setAccessibleName(name)
        return spin

    def settings(self) -> PostureSettings:
        return PostureSettings(
            self.angle_limit.value(), self.head_seconds.value(), self.absence_seconds.value()
        )

    def _clear(self, message: str, waiting: bool = False) -> None:
        self.head_state.setText("Postura: pendiente de calibración" if waiting else "Postura: no evaluable")
        self.angle_label.setText("Desviación respecto a la referencia: —")
        self.head_counter.setText(f"Fuera del margen: 0.0 / {self.head_seconds.value():.1f} s")
        self.head_signal.setText("Señal de postura: sin evaluar")
        self.head_signal.setStyleSheet("")
        self.head_message.setText(message)
        self.absence_state.setText("Ausencia de rostro: en espera" if waiting else "Ausencia de rostro: no evaluable")
        self.absence_counter.setText(f"Sin rostro: 0.0 / {self.absence_seconds.value():.1f} s")
        self.absence_signal.setText("Señal de ausencia: sin evaluar")
        self.absence_signal.setStyleSheet("")
        self.absence_message.setText(message)

    @Slot(object)
    def bind_worker(self, worker) -> None:
        self.reset()
        self._worker = worker
        worker.request_posture_settings(self.settings())

    @Slot()
    def _settings_changed(self) -> None:
        self._clear("Opciones actualizadas; se reinician ambos contadores.")
        if self._worker is not None:
            self._worker.request_posture_settings(self.settings())

    @Slot(float)
    def calibration_requested(self, at: float) -> None:
        self._request_time = at
        self._clear("Calibrando postura; ambas reglas están en espera.", waiting=True)

    @Slot(object)
    def update_snapshot(self, snapshot) -> None:
        if self._worker is None:
            return
        if snapshot is None or snapshot.phase != "ready":
            message = snapshot.error if snapshot is not None and snapshot.phase == "error" else "Esperando al analizador."
            self._clear(message)
            return
        if self._request_time is not None:
            acknowledged = snapshot.calibration.requested_at
            if acknowledged is None or acknowledged < self._request_time:
                self._clear("Solicitud de calibración enviada; ambas reglas están en espera.", waiting=True)
                return
            self._request_time = None
        status = snapshot.posture
        if status.settings != self.settings():
            self._clear("Aplicando las nuevas opciones; se reinician ambos contadores.")
            return
        if snapshot.calibration.reference is None:
            self._clear("Completa «Calibrar postura» para habilitar ambas reglas.", waiting=True)
            return
        if (snapshot.captured_at is None
                or time.monotonic() - snapshot.captured_at > MAX_POSTURE_GAP):
            self._clear("Sin datos recientes; este intervalo no se cuenta.")
            return
        head, absence = status.head, status.absence
        self.head_state.setText(f"Postura: {head.state}")
        angle = "—" if head.angle is None else f"{head.angle:.1f}°"
        self.angle_label.setText(f"Desviación respecto a la referencia: {angle}")
        self.head_counter.setText(
            f"Fuera del margen: {head.elapsed:.1f} / {self.head_seconds.value():.1f} s"
        )
        self.head_signal.setText(
            "Señal de postura: cabeza apartada sostenida" if head.rule_met else
            "Señal de postura: no cumplida" if head.angle is not None else "Señal de postura: sin evaluar"
        )
        self.head_signal.setStyleSheet("font-weight: bold;" if head.rule_met else "")
        self.head_message.setText(head.message)
        self.absence_state.setText(f"Ausencia de rostro: {absence.state}")
        self.absence_counter.setText(
            f"Sin rostro: {absence.elapsed:.1f} / {self.absence_seconds.value():.1f} s"
        )
        self.absence_signal.setText(
            "Señal de ausencia: rostro ausente sostenido" if absence.rule_met else
            "Señal de ausencia: no cumplida" if absence.state in ("rostro visible", "rostro ausente")
            else "Señal de ausencia: sin evaluar"
        )
        self.absence_signal.setStyleSheet("font-weight: bold;" if absence.rule_met else "")
        self.absence_message.setText(absence.message)

    @Slot()
    def reset(self) -> None:
        self._worker = None
        self._request_time = None
        self._clear("Inicia la cámara y completa «Calibrar postura».", waiting=True)
