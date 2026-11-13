"""Vista guiada de calibración; presenta los resultados existentes, sin inferencia."""

import math
import time

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QFrame, QProgressBar, QVBoxLayout, QWidget

from lockin.posture import MAX_POSTURE_GAP
from lockin.session_view import host, text_label
from lockin.theme import set_tone
from lockin.widgets import ResponsiveColumns


def step_state(status, requested, available, phase):
    """Describe preparación sin convertir la disponibilidad en una referencia."""
    if phase == "error":
        return "No disponible", "danger"
    if requested:
        return "Iniciando", "waiting"
    if status is not None:
        if status.state == "calibrando":
            return "Capturando", "waiting"
        if status.state == "fallida":
            return "Fallida · vuelve a intentarlo", "danger"
        if status.state == "completada" and status.reference is not None:
            return "Completada", "good"
    return ("Preparado", "good") if available else ("Sin referencia", "neutral")


class CalibrationView(QWidget):
    def __init__(self, face_panel, eye_panel, posture_panel, alert_panel):
        super().__init__()
        self._face, self._eyes = face_panel, eye_panel
        self._posture, self._alerts = posture_panel, alert_panel
        self._shutting_down = False

        heading = host()
        heading.layout().addWidget(text_label("Calibración", "pageTitle"))
        heading.layout().addWidget(text_label(
            "Mira al centro de la pantalla y siéntate como lo haces al trabajar.", "muted"
        ))
        camera = QFrame()
        camera.setProperty("role", "section")
        camera_layout = QVBoxLayout(camera)
        camera_layout.setContentsMargins(0, 0, 8, 0)
        camera_layout.setSpacing(9)
        camera_layout.addWidget(text_label("Vista previa", "sectionTitle"))
        self.camera_hint = text_label("Inicia la cámara desde Sesión.", "muted")
        camera_layout.addWidget(self.camera_hint)
        self.preview_host = host()
        camera_layout.addWidget(self.preview_host, 1)
        camera_layout.addWidget(text_label("Vista previa compartida · Las imágenes no se guardan", "muted"))

        steps = host()
        steps.layout().setSpacing(12)
        steps.layout().addWidget(text_label("Referencias", "sectionTitle"))
        steps.layout().addWidget(face_panel)
        steps.layout().addWidget(eye_panel)
        steps.layout().addStretch()
        self.columns = ResponsiveColumns(camera, steps, breakpoint=850, stretch=(3, 2))

        check = QFrame()
        check.setProperty("role", "plain")
        check_layout = QVBoxLayout(check)
        check_layout.setContentsMargins(0, 10, 0, 0)
        check_layout.addWidget(text_label("Comprobación de postura", "sectionTitle"))
        self.orientation_status = text_label("Calibra la postura para comparar la orientación.")
        self.orientation_value = text_label("Desviación total: —", "counter")
        check_layout.addWidget(self.orientation_status)
        check_layout.addWidget(self.orientation_value)
        self.orientation_bar = QProgressBar()
        self.orientation_bar.setObjectName("orientationBar")
        self.orientation_bar.setRange(0, 1800)
        self.orientation_bar.setTextVisible(False)
        self.orientation_bar.setAccessibleName("Desviación angular total respecto a la referencia, de 0 a 180 grados")
        self.orientation_bar.setToolTip(
            "Rotación total respecto a la referencia. No mide la dirección de la mirada."
        )
        check_layout.addWidget(self.orientation_bar)
        self.references = text_label("", "muted")
        check_layout.addWidget(self.references)
        check_layout.addWidget(text_label(
            "Puedes repetir cada paso. Recalibrar descarta su referencia anterior; "
            "las referencias se pierden al detener la cámara.", "muted"
        ))

        self.alert_status = text_label("", "muted")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 12)
        layout.setSpacing(12)
        layout.addWidget(heading)
        layout.addWidget(self.columns, 1)
        camera_layout.addWidget(check)
        layout.addWidget(self.alert_status)

        face_panel.presentation_changed.connect(self.refresh)
        eye_panel.presentation_changed.connect(self.refresh)
        alert_panel.presentation_changed.connect(self.refresh)
        posture_panel.angle_limit.valueChanged.connect(self.refresh)
        self.refresh()

    @Slot()
    def refresh(self):
        if self._shutting_down:
            return
        current = self._face._last
        phase = current.phase if current is not None else None
        pose_status = current.calibration if current is not None else None
        eye_status = current.eyes.calibration if current is not None else None
        for panel, status, label in (
            (self._face, pose_status, self._face.readiness),
            (self._eyes, eye_status, self._eyes.readiness),
        ):
            state, tone = step_state(status, panel._requested, panel.calibrate_button.isEnabled(), phase)
            label.setText(state)
            set_tone(label, tone)

        first = self._face if pose_status is None or pose_status.reference is None else self._eyes
        if not first.calibrate_button.isEnabled():
            first = self._eyes if self._eyes.calibrate_button.isEnabled() else self._face
        for panel in (self._face, self._eyes):
            role = "primary" if panel is first else "secondary"
            button = panel.calibrate_button
            if button.property("role") != role:
                button.setProperty("role", role)
                button.style().unpolish(button)
                button.style().polish(button)

        self.camera_hint.setText(self._face.face_status.text())
        self.alert_status.setText("Alertas · " + self._alerts.status.text())
        pose_reference = pose_status is not None and pose_status.reference is not None and not self._face._requested
        eye_reference = eye_status is not None and eye_status.reference is not None and not self._eyes._requested
        self.references.setText(
            "Referencias en memoria · Postura: " + ("disponible" if pose_reference else "pendiente")
            + " · Ojos: " + ("disponible" if eye_reference else "pendiente")
        )

        now = time.monotonic()
        fresh = (
            current is not None and phase == "ready" and current.captured_at is not None
            and 0 <= now - current.captured_at <= MAX_POSTURE_GAP
        )
        observation = current.observation if current is not None else None
        head = current.posture.head if current is not None else None
        limit = self._posture.angle_limit.value()
        valid = (
            fresh and pose_reference and pose_status.state == "completada"
            and observation is not None and observation.count == 1
            and observation.pose is not None and observation.pose.valid()
            and head.angle is not None and math.isfinite(head.angle)
            and 0 <= head.angle <= 180
            and current.posture.settings == self._posture.settings()
        )
        self.orientation_bar.setEnabled(bool(valid))
        self.orientation_bar.setValue(round(head.angle * 10) if valid else 0)
        if valid:
            within = head.angle <= limit + 1e-6
            self.orientation_status.setText("✓ Dentro del margen" if within else "! Fuera del margen")
            set_tone(self.orientation_status, "good" if within else "waiting")
            set_tone(self.orientation_bar, "good" if within else "waiting")
            self.orientation_value.setText(
                f"Desviación total: {head.angle:.1f}° · Margen: {limit:g}° · Escala: 0–180°".replace(".", ",")
            )
        else:
            set_tone(self.orientation_bar, "neutral")
            if phase == "error":
                message = current.error
            elif self._face._worker is None:
                message = "Inicia la cámara desde Sesión."
            elif not pose_reference:
                message = "Completa el paso 01 para comparar tu postura."
            elif not fresh:
                message = "Esperando una medición reciente de la postura."
            elif observation is None or observation.count != 1:
                message = "Se necesita un solo rostro visible para comprobar la orientación."
            else:
                message = "Esperando una medición válida con el margen actual."
            self.orientation_status.setText(message)
            set_tone(self.orientation_status, "danger" if phase == "error" else "neutral")
            self.orientation_value.setText(f"Desviación total: — · Margen: {limit:g}°".replace(".", ","))

    def shutdown(self):
        self._shutting_down = True
        self._face = self._eyes = self._posture = self._alerts = None

