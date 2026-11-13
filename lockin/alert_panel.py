"""Coordinación de señales y video en el hilo de la interfaz."""

import time

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QCheckBox, QLabel, QWidget

from lockin.widgets import ScrollSafeDoubleSpinBox

from lockin.alerts import AlertEngine, AlertEvidence, AlertSettings, evaluate_snapshot


class AlertPanel(QWidget):
    presentation_changed = Signal()

    def __init__(self, video_panel, parent=None, *,
                 eye_duration=None, posture_settings=None, clock=time.monotonic) -> None:
        super().__init__(parent)
        self._video = video_panel
        self._clock = clock
        self._eye_duration = eye_duration
        self._posture_settings = posture_settings
        self._snapshot = None
        self._source_running = False
        self._valid_after = 0.0
        self._eye_requested = self._pose_requested = None
        self._shutting_down = False
        self.engine = AlertEngine()
        self.enabled = QCheckBox("Activar alertas automáticas", self)
        self.eyes = QCheckBox("Ojos cerrados", self)
        self.head = QCheckBox("Cabeza apartada", self)
        self.absence = QCheckBox("Rostro ausente", self)
        for checkbox in (self.eyes, self.head, self.absence):
            checkbox.setChecked(True)
        self.cooldown = ScrollSafeDoubleSpinBox(self)
        self.cooldown.setRange(0, 300)
        self.cooldown.setDecimals(1)
        self.cooldown.setSingleStep(5)
        self.cooldown.setSuffix(" s")
        self.cooldown.setValue(15)
        self.cooldown.setAccessibleName("Espera entre alertas")
        self.recovery = ScrollSafeDoubleSpinBox(self)
        self.recovery.setRange(0.5, 5)
        self.recovery.setDecimals(1)
        self.recovery.setSingleStep(0.5)
        self.recovery.setSuffix(" s")
        self.recovery.setValue(1)
        self.recovery.setAccessibleName("Tiempo de recuperación estable")
        self.status = QLabel("Alertas automáticas desactivadas.", self)
        self.wait_label = QLabel("Espera restante: 0.0 s", self)
        self.recovery_label = QLabel("Recuperación observada: 0.0 / 1.0 s", self)
        self.trigger_label = QLabel("Última activación: —", self)
        # Las vistas colocan los controles; este objeto solo los coordina.
        for checkbox in (self.enabled, self.eyes, self.head, self.absence):
            checkbox.toggled.connect(self._settings_changed)
        for label in (self.status, self.wait_label, self.recovery_label, self.trigger_label):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
        self.cooldown.valueChanged.connect(self._settings_changed)
        self.recovery.valueChanged.connect(self._settings_changed)
        self._video.playback_finished.connect(self._playback_finished)
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def settings(self) -> AlertSettings:
        return AlertSettings(
            self.enabled.isChecked(), self.eyes.isChecked(), self.head.isChecked(),
            self.absence.isChecked(), self.cooldown.value(), self.recovery.value(),
        )

    @Slot()
    def _settings_changed(self) -> None:
        self._video.stop_automatic("Alerta cancelada al cambiar las opciones de alertas.")
        self.engine.configure(self.settings())
        self.invalidate_measurements()

    @Slot()
    def invalidate_measurements(self) -> None:
        self._valid_after = self._clock()
        self._snapshot = None
        self.engine.reset_recovery()
        self.recovery_label.setText(f"Recuperación observada: 0.0 / {self.recovery.value():.1f} s")

    @Slot(float)
    def eye_calibration_requested(self, at: float) -> None:
        self._eye_requested = at
        self.invalidate_measurements()

    @Slot(float)
    def posture_calibration_requested(self, at: float) -> None:
        self._pose_requested = at
        self.invalidate_measurements()

    @Slot(object)
    def source_started(self, worker) -> None:
        self._source_running = True
        self._eye_requested = self._pose_requested = None
        self.invalidate_measurements()

    @Slot()
    def source_stopped(self) -> None:
        self._source_running = False
        self.invalidate_measurements()
        # Un fallo del análisis no equivale a recuperación; Esc sigue disponible.

    @Slot(object)
    def update_snapshot(self, snapshot) -> None:
        self._snapshot = snapshot

    def _evidence(self, now: float) -> AlertEvidence:
        snapshot, settings = self._snapshot, self.engine.settings
        if not self._source_running:
            return AlertEvidence(message="Cámara o análisis detenidos; no se considera recuperación.")
        if snapshot is not None and snapshot.phase != "ready":
            return evaluate_snapshot(snapshot, settings, now)
        if (snapshot is None or snapshot.captured_at is None
                or snapshot.captured_at < self._valid_after):
            return AlertEvidence(message="Esperando mediciones posteriores al cambio.")
        if settings.eyes:
            requested = snapshot.eyes.calibration.requested_at
            if (self._eye_requested is not None
                    and (requested is None or requested < self._eye_requested)):
                return AlertEvidence(message="Esperando la nueva calibración de ojos.")
            if self._eye_duration is not None and snapshot.eyes.required_duration != self._eye_duration():
                return AlertEvidence(message="Aplicando el tiempo de ojos cerrados.")
        if settings.head or settings.absence:
            requested = snapshot.calibration.requested_at
            if (self._pose_requested is not None
                    and (requested is None or requested < self._pose_requested)):
                return AlertEvidence(message="Esperando la nueva calibración de postura.")
            if (self._posture_settings is not None
                    and snapshot.posture.settings != self._posture_settings()):
                return AlertEvidence(message="Aplicando las opciones de postura.")
        return evaluate_snapshot(snapshot, settings, now)

    @Slot()
    def _tick(self) -> None:
        if self._shutting_down:
            return
        now = self._clock()
        decision = self.engine.update(
            self._evidence(now), now, busy=self._video.is_playing,
            video_available=self._video.has_video,
        )
        self.status.setText(decision.message)
        self.wait_label.setText(f"Espera restante: {decision.remaining:.1f} s")
        self.recovery_label.setText(
            f"Recuperación observada: {decision.recovered_for:.1f} / {self.recovery.value():.1f} s"
        )
        if decision.action == "start":
            self.trigger_label.setText("Última activación: " + ", ".join(decision.reasons))
            if not self._video.start_automatic():
                self.engine.playback_finished(self._clock())
                self.status.setText("No se pudo iniciar la alerta. Revisa el mensaje del video.")
        elif decision.action == "stop":
            self._video.stop_automatic("Video cerrado por recuperación observable estable.")
        self.presentation_changed.emit()

    @Slot(bool, str)
    def _playback_finished(self, automatic: bool, message: str) -> None:
        if automatic:
            self.engine.playback_finished(self._clock())
            self.status.setText(message)
            self.presentation_changed.emit()

    def cancel_for_stop(self) -> None:
        self._video.stop_automatic("Alerta cancelada al detener la cámara.")
        self.engine.reset_episode()
        self.source_stopped()

    def shutdown(self) -> None:
        self._shutting_down = True
        self._timer.stop()
        self._eye_duration = self._posture_settings = None
        self._video.stop_automatic("Alerta cancelada al cerrar LockIn.")
        self.engine.reset_episode()
        self._snapshot = None
