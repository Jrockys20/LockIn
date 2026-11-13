"""Presentación de Sesión; utiliza los controles y resultados existentes."""

import time

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lockin.posture import MAX_POSTURE_GAP
from lockin.theme import set_tone
from lockin.widgets import AlertSelector, ResponsiveColumns
from lockin.navigation import ui_icon


def text_label(text="", role=None):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if role:
        label.setProperty("role", role)
    return label


def host():
    widget = QWidget()
    widget.setProperty("role", "plain")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    return widget


class SignalRow(QFrame):
    def __init__(self, name):
        super().__init__()
        self.setProperty("role", "signalRow")
        self.icon = text_label("—")
        self.icon.setFixedWidth(20)
        self.state = text_label("Sin analizar", "muted")
        self.counter = text_label("", "counter")
        self.counter.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        description = QVBoxLayout()
        description.setSpacing(3)
        description.addWidget(text_label(name, "sectionTitle"))
        description.addWidget(self.state)
        description.addWidget(self.counter)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.addWidget(self.icon)
        layout.addLayout(description, 1)

    def display(self, state, counter, tone, hint=""):
        self.state.setText(state)
        self.counter.setText(counter.replace(".", ","))
        self.setToolTip(hint)
        self.icon.setText({"good": "✓", "waiting": "!", "danger": "×"}.get(tone, "—"))
        set_tone(self.icon, tone)


class SessionView(QWidget):
    def __init__(self, camera_selector, start_button, stop_button, refresh_button,
                 camera_status, camera_detail, eye_panel, posture_panel, alert_panel):
        super().__init__()
        self._camera_status, self._camera_detail = camera_status, camera_detail
        self._eyes, self._posture, self._alerts = eye_panel, posture_panel, alert_panel
        self._snapshot = None
        self._shutting_down = False
        self._ever_enabled = False
        self._start_button, self._stop_button = start_button, stop_button
        self.subtitle = text_label("Cámara detenida · Alertas desactivadas", "muted")
        self.last_event = text_label("Última activación: —", "muted")
        self.alert_selector = AlertSelector(alert_panel.enabled, "Sesión")
        self._alerts.enabled.toggled.connect(self._enabled_changed)
        headings = host()
        headings.layout().setSpacing(4)
        headings.layout().addWidget(text_label("Sesión", "pageTitle"))
        headings.layout().addWidget(self.subtitle)
        actions = host()
        actions.layout().addWidget(self.alert_selector)
        header = ResponsiveColumns(headings, actions, breakpoint=680, stretch=(3, 1))

        camera = QFrame()
        camera.setProperty("role", "section")
        camera_layout = QVBoxLayout(camera)
        camera_layout.setContentsMargins(0, 0, 0, 0)
        camera_layout.setSpacing(12)
        camera_layout.addWidget(text_label("Cámara", "sectionTitle"))
        camera_tools = QWidget()
        camera_tools.setProperty("role", "plain")
        camera_tools_layout = QHBoxLayout(camera_tools)
        camera_tools_layout.setContentsMargins(0, 0, 0, 0)
        camera_tools_layout.addWidget(camera_selector, 1)
        refresh_button.setIcon(ui_icon("refresh"))
        refresh_button.setAccessibleName("Actualizar cámaras disponibles")
        camera_tools_layout.addWidget(refresh_button)
        camera_layout.addWidget(camera_tools)
        self.preview_host = host()
        camera_layout.addWidget(self.preview_host, 1)
        buttons = QHBoxLayout()
        start_button.setProperty("role", "primary")
        stop_button.setProperty("role", "primary")
        buttons.addWidget(start_button)
        buttons.addWidget(stop_button)
        buttons.addStretch()
        camera_layout.addLayout(buttons)

        signals = QFrame()
        signals.setProperty("role", "section")
        signal_layout = QVBoxLayout(signals)
        signal_layout.setContentsMargins(8, 0, 0, 0)
        signal_layout.addWidget(text_label("Señales en vivo", "sectionTitle"))
        self.eyes_row, self.head_row, self.face_row = SignalRow("Ojos"), SignalRow("Cabeza"), SignalRow("Rostro")
        for row in (self.eyes_row, self.head_row, self.face_row):
            signal_layout.addWidget(row)
        signal_layout.addStretch()
        operating = QFrame()
        operating.setObjectName("operatingState")
        operating_layout = QVBoxLayout(operating)
        self.operating_title = text_label("Alertas desactivadas", "sectionTitle")
        self.operating_detail = text_label("", "muted")
        self.wait = text_label("Espera restante: 0,0 s", "counter")
        operating_layout.addWidget(self.operating_title)
        operating_layout.addWidget(self.operating_detail)
        operating_layout.addWidget(self.wait)
        operating_layout.addWidget(self.last_event)
        signal_layout.addWidget(operating)
        self.columns = ResponsiveColumns(camera, signals, breakpoint=850, stretch=(3, 2))
        self.video_host = host()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 12)
        layout.setSpacing(14)
        layout.addWidget(header)
        layout.addWidget(self.columns, 1)
        layout.addWidget(self.video_host)

    @Slot(bool)
    def _enabled_changed(self, enabled):
        self._ever_enabled |= enabled
        self.refresh()

    @Slot(object)
    def update_snapshot(self, snapshot):
        if self._shutting_down:
            return
        self._snapshot = snapshot
        self.refresh()

    @Slot()
    def reset_signals(self):
        self._snapshot = None
        self.refresh()

    @Slot()
    def refresh(self):
        if self._shutting_down:
            return
        enabled = self._alerts.enabled.isChecked()
        camera = self._camera_status.text().removeprefix("Estado: ")
        # Misma zona, conservando los botones y las transiciones originales.
        capturing = camera in ("iniciando", "activa") or self._stop_button.isEnabled()
        self._start_button.setVisible(not capturing)
        self._stop_button.setVisible(capturing)
        self.subtitle.setText(f"Cámara {camera} · Alertas {'activadas' if enabled else 'desactivadas'}")
        self.last_event.setText(self._alerts.trigger_label.text())
        self.wait.setText(self._alerts.wait_label.text().replace(".", ","))
        if self._alerts.engine.active:
            title, tone, detail = "Reproduciendo video", "waiting", self._alerts.status.text()
        elif camera == "error":
            title, tone, detail = "Error de cámara", "danger", self._camera_detail.text()
        elif self._snapshot is not None and self._snapshot.phase == "error":
            title, tone, detail = "Error de análisis", "danger", self._snapshot.error
        elif not enabled:
            title, tone = "Alertas pausadas" if self._ever_enabled else "Alertas desactivadas", "neutral"
            detail = ("La cámara y el análisis continúan. Puedes reanudar las alertas."
                      if camera == "activa" else "Inicia la cámara para recibir mediciones.")
        else:
            detail = self._alerts.status.text()
            if detail.startswith("Alertas preparadas"):
                title, tone = "Alertas listas", "good"
            elif "ya avisado" in detail.lower():
                title, tone = "Señal ya avisada", "waiting"
            elif detail.startswith("Esperando antes"):
                title, tone = "Espera entre alertas", "waiting"
            elif "Error" in detail or "No se pudo" in detail:
                title, tone = "Revisa el estado", "danger"
            else:
                title, tone = "Preparación pendiente", "waiting"
        self.operating_title.setText(title)
        self.operating_detail.setText(detail)
        set_tone(self.operating_title, tone)
        snapshot = self._snapshot
        fresh = (
            camera == "activa" and snapshot is not None and snapshot.phase == "ready"
            and snapshot.captured_at is not None
            and time.monotonic() - snapshot.captured_at <= MAX_POSTURE_GAP
        )
        if not fresh:
            message = ("Error de análisis" if snapshot is not None and snapshot.phase == "error"
                       else "Sin analizar" if camera != "activa" else "Esperando datos recientes")
            for row in (self.eyes_row, self.head_row, self.face_row):
                row.display(message, "", "danger" if "Error" in message else "neutral")
            return
        state = self._eyes.state_label.text().removeprefix("Ojos: ")
        tone = "good" if state == "abiertos" else "waiting" if state == "cerrados" else "neutral"
        self.eyes_row.display(state.capitalize(),
            self._eyes.duration_label.text().replace("Cierre continuo:", "Cierre:"),
            tone, self._eyes.message.text())
        state = self._posture.head_state.text().removeprefix("Postura: ")
        tone = "good" if state == "dentro del margen" else "waiting" if state == "fuera del margen" else "neutral"
        self.head_row.display(state.capitalize(),
            self._posture.head_counter.text().replace("Fuera del margen:", "Desvío:"),
            tone, self._posture.head_message.text())
        observation = snapshot.observation
        count = observation.count if observation is not None else None
        state = ("Visible" if count == 1 else "No detectado" if count == 0
                 else "Varios rostros" if count else "No evaluable")
        self.face_row.display(state, self._posture.absence_counter.text(),
            "good" if count == 1 else "waiting" if count == 0 else "neutral",
            self._posture.absence_message.text())

    def shutdown(self):
        self._shutting_down = True
        self.alert_selector.shutdown()
        self._snapshot = None
        self._camera_status = self._camera_detail = None
        self._eyes = self._posture = self._alerts = None
        self._start_button = self._stop_button = None
