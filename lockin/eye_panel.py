"""Controles y estados de ojos; recibe resultados en el hilo de la interfaz."""

import time

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from lockin.widgets import ScrollSafeDoubleSpinBox

from lockin.eyes import MAX_EYE_GAP


class EyePanel(QGroupBox):
    presentation_changed = Signal()
    calibration_requested = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__("02 · Ojos abiertos", parent)
        self._worker = None
        self._requested = False
        self._request_time = 0.0
        self.state_label = QLabel("Ojos: no evaluables")
        self.duration_label = QLabel("Cierre continuo: 0.0 / 2.0 s")
        self.signal_label = QLabel("Señal: sin evaluar")
        self.relative_label = QLabel("Apertura relativa: —")
        self.calibration_label = QLabel("Referencia de ojos: pendiente")
        self.calibrate_button = QPushButton("Calibrar ojos abiertos")
        self.calibrate_button.setEnabled(False)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setAccessibleName("Progreso de referencia de ojos abiertos")
        self.hold_seconds = ScrollSafeDoubleSpinBox()
        self.hold_seconds.setRange(0.5, 10)
        self.hold_seconds.setSingleStep(0.5)
        self.hold_seconds.setDecimals(1)
        self.hold_seconds.setSuffix(" s")
        self.hold_seconds.setValue(2)
        self.hold_seconds.setAccessibleName("Tiempo de cierre sostenido")
        self.message = QLabel("Inicia la cámara y calibra los ojos abiertos durante 2 segundos.")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)

        self.setProperty("role", "reference")
        self.readiness = QLabel("Sin referencia")
        self.readiness.setProperty("role", "muted")
        instructions = QLabel("Mira de frente y mantén ambos ojos abiertos con naturalidad durante 2 segundos.")
        instructions.setProperty("role", "muted")
        instructions.setWordWrap(True)
        for label in (self.readiness, self.calibration_label, self.state_label, self.signal_label, self.relative_label):
            label.setWordWrap(True)
        self.calibrate_button.setToolTip("Toma la apertura habitual de tus ojos. Repetir descarta esa referencia.")
        self.calibrate_button.setProperty("role", "primary")
        rule = QHBoxLayout()
        rule.addWidget(QLabel("Cierre sostenido:"))
        rule.addWidget(self.hold_seconds)
        rule.addStretch()
        self.details = QWidget()
        self.details.setProperty("role", "plain")
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(0, 4, 0, 0)
        details_layout.addLayout(rule)
        for label in (self.state_label, self.duration_label, self.signal_label, self.relative_label):
            details_layout.addWidget(label)
        self.details_toggle = QToolButton()
        self.details_toggle.setText("Ajustes y mediciones de ojos")
        self.details_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.details_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.details_toggle.setCheckable(True)
        self.details_toggle.setToolTip("Muestra el tiempo de cierre sostenido y las mediciones actuales, sin cambiar valores.")
        self.details_toggle.toggled.connect(self._toggle_details)
        self.details.hide()
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(self.readiness)
        layout.addWidget(instructions)
        layout.addWidget(self.calibration_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.calibrate_button)
        layout.addWidget(self.message)
        layout.addWidget(self.details_toggle)
        layout.addWidget(self.details)
        self.calibrate_button.clicked.connect(self.calibrate)
        self.hold_seconds.valueChanged.connect(self._duration_changed)

    @Slot(bool)
    def _toggle_details(self, expanded):
        self.details.setVisible(expanded)
        self.details_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    @Slot(object)
    def bind_worker(self, worker) -> None:
        self.reset()
        self._worker = worker
        worker.request_eye_duration(self.hold_seconds.value())

    @Slot(float)
    def _duration_changed(self, value: float) -> None:
        self.duration_label.setText(f"Cierre continuo: 0.0 / {value:.1f} s")
        self.signal_label.setText("Señal: sin evaluar")
        self.signal_label.setStyleSheet("")
        self.state_label.setText("Ojos: no evaluables")
        self.relative_label.setText("Apertura relativa: —")
        if self._worker is not None:
            self._worker.request_eye_duration(value)
        self.presentation_changed.emit()

    @Slot()
    def calibrate(self) -> None:
        if self._worker is None or not self.calibrate_button.isEnabled():
            return
        self._requested = True
        self._request_time = time.monotonic()
        self.calibration_requested.emit(self._request_time)
        self.calibrate_button.setEnabled(False)
        self.calibration_label.setText("Referencia de ojos: iniciando")
        self.progress.setValue(0)
        self.message.setText("Solicitud enviada. Mira de frente con los ojos abiertos.")
        self._worker.request_eye_calibration()
        self.presentation_changed.emit()

    @Slot(object)
    def update_snapshot(self, snapshot) -> None:
        if self._worker is None:
            return
        if snapshot is None or snapshot.phase != "ready":
            self.calibrate_button.setEnabled(False)
            self.state_label.setText("Ojos: no evaluables")
            self.duration_label.setText(
                f"Cierre continuo: 0.0 / {self.hold_seconds.value():.1f} s"
            )
            self.signal_label.setText("Señal: sin evaluar")
            self.relative_label.setText("Apertura relativa: —")
            self.signal_label.setStyleSheet("")
            if snapshot is not None and snapshot.phase == "error":
                self._requested = False
                self.calibration_label.setText("Referencia de ojos: no disponible")
                self.progress.setValue(0)
            self.message.setText(
                snapshot.error if snapshot is not None and snapshot.phase == "error"
                else "Esperando al analizador de rostro."
            )
            self.presentation_changed.emit()
            return

        status = snapshot.eyes
        calibration = status.calibration
        if (calibration.requested_at is not None
                and calibration.requested_at >= self._request_time):
            self._requested = False
        if self._requested:
            self.calibration_label.setText("Referencia de ojos: iniciando")
            self.progress.setValue(0)
        else:
            self.calibration_label.setText(f"Referencia de ojos: {calibration.state}")
            self.progress.setValue(round(calibration.progress * 100))
        self.calibrate_button.setText(
            "Recalibrar ojos abiertos" if calibration.reference else "Calibrar ojos abiertos"
        )

        fresh = (snapshot.captured_at is not None
                 and time.monotonic() - snapshot.captured_at <= MAX_EYE_GAP)
        applied = abs(status.required_duration - self.hold_seconds.value()) < 1e-6
        visible_state = status.state if fresh and applied and not self._requested else "no evaluables"
        closed_for = status.closed_for if visible_state == "cerrados" else 0
        met = visible_state == "cerrados" and status.rule_met
        self.state_label.setText(f"Ojos: {visible_state}")
        self.duration_label.setText(
            f"Cierre continuo: {closed_for:.1f} / {self.hold_seconds.value():.1f} s"
        )
        self.signal_label.setText(
            "Señal: ojos cerrados sostenidos" if met else
            "Señal: no cumplida" if visible_state != "no evaluables" else "Señal: sin evaluar"
        )
        self.signal_label.setStyleSheet("font-weight: bold;" if met else "")
        if fresh and status.left_ratio is not None and status.right_ratio is not None:
            self.relative_label.setText(
                f"Apertura relativa: izquierda {status.left_ratio * 100:.0f} % · "
                f"derecha {status.right_ratio * 100:.0f} %"
            )
        else:
            self.relative_label.setText("Apertura relativa: —")
        self.message.setText(
            "Solicitud enviada. Mira de frente con los ojos abiertos." if self._requested
            else "Aplicando el nuevo tiempo; se reinicia el contador." if not applied
            else calibration.message if calibration.state == "fallida"
            else status.message if fresh else "Esperando mediciones recientes de ambos ojos."
        )
        observation = snapshot.observation
        can_calibrate = (
            fresh and observation is not None and observation.count == 1
            and observation.eyes is not None and observation.eyes.valid()
            and calibration.state != "calibrando" and not self._requested
        )
        # Se aplica el estado final una vez; no cancela clics durante el sondeo.
        self.calibrate_button.setEnabled(can_calibrate)
        self.presentation_changed.emit()

    @Slot()
    def reset(self) -> None:
        self._worker = None
        self._requested = False
        self._request_time = 0.0
        self.state_label.setText("Ojos: no evaluables")
        self.duration_label.setText(f"Cierre continuo: 0.0 / {self.hold_seconds.value():.1f} s")
        self.signal_label.setText("Señal: sin evaluar")
        self.signal_label.setStyleSheet("")
        self.relative_label.setText("Apertura relativa: —")
        self.calibration_label.setText("Referencia de ojos: pendiente")
        self.calibrate_button.setText("Calibrar ojos abiertos")
        self.calibrate_button.setEnabled(False)
        self.progress.setValue(0)
        self.message.setText("Inicia la cámara y calibra los ojos abiertos durante 2 segundos.")
        self.presentation_changed.emit()
