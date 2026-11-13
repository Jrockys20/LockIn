"""Presentación de Alertas con los controles y coordinadores existentes."""

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout,
    QToolButton, QVBoxLayout, QWidget,
)

from lockin.session_view import host, text_label
from lockin.theme import set_tone
from lockin.widgets import AlertSelector, ResponsiveColumns, ScrollSafeDoubleSpinBox


def alert_heading(message, *, enabled, active):
    """Etiqueta de presentación; no decide activaciones ni modifica el motor."""
    if active:
        return "Reproduciendo alerta", "waiting"
    lower = message.lower()
    if "no se pudo" in lower or "error" in lower or "fallo" in lower:
        return "Revisa el error", "danger"
    if not enabled:
        return "Alertas desactivadas", "neutral"
    if "ya avisado" in lower:
        return "Señal ya avisada", "waiting"
    if message.startswith("Esperando antes"):
        return "Espera entre alertas", "waiting"
    if "prueba manual" in lower:
        return "Prueba de video en curso", "waiting"
    if message.startswith("Alertas preparadas"):
        return "Alertas listas", "good"
    if "calibr" in lower:
        return "Calibración pendiente", "waiting"
    if "video local" in lower:
        return "Selecciona un video", "waiting"
    if "al menos una señal" in lower:
        return "Selecciona una señal", "waiting"
    return "Preparación pendiente", "waiting"


def mirrored_spin(source):
    """Dos editores para el mismo ajuste; el control original sigue siendo la fuente."""
    spin = ScrollSafeDoubleSpinBox()
    spin.setDecimals(source.decimals())
    spin.setRange(source.minimum(), source.maximum())
    spin.setSingleStep(source.singleStep())
    spin.setSuffix(source.suffix())
    spin.setValue(source.value())
    spin.setAccessibleName(source.accessibleName() + " en Alertas")
    spin.valueChanged.connect(source.setValue)
    source.valueChanged.connect(spin.setValue)
    return spin


class AlertsView(QWidget):
    def __init__(self, alert_panel, posture_panel, eye_panel):
        super().__init__()
        self._alerts = alert_panel
        self._shutting_down = False
        for panel in (alert_panel, posture_panel):
            panel.setParent(self)
            panel.hide()

        heading = host()
        heading.layout().addWidget(text_label("Alertas", "pageTitle"))
        heading.layout().addWidget(text_label("Los cambios se aplican durante esta sesión.", "muted"))
        self.alert_selector = AlertSelector(alert_panel.enabled, "Alertas")
        header = ResponsiveColumns(heading, self.alert_selector, breakpoint=680, stretch=(3, 1))

        rules = QFrame()
        rules.setProperty("role", "surface")
        rules_layout = QVBoxLayout(rules)
        rules_layout.setContentsMargins(16, 14, 16, 0)
        rules_layout.setSpacing(0)
        rules_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        rules_layout.addWidget(text_label("Señales que activan el video", "sectionTitle"))
        rules_layout.addWidget(self._separator())
        self.eye_seconds = mirrored_spin(eye_panel.hold_seconds)
        self.eye_seconds.setToolTip(
            "Tiempo continuo con ambos ojos cerrados. Es el mismo ajuste de Calibración. "
            "La rueda desplaza la ventana."
        )
        rules_layout.addWidget(self._rule(
            alert_panel.eyes, (("Duración mínima", self.eye_seconds),),
            "Ambos ojos cerrados durante el tiempo indicado. Requiere calibrar ojos abiertos.",
        ))
        rules_layout.addWidget(self._rule(
            alert_panel.head,
            (("Margen angular", posture_panel.angle_limit), ("Duración mínima", posture_panel.head_seconds)),
            "Desviación respecto a la postura calibrada superior al margen durante el tiempo indicado.",
        ))
        rules_layout.addWidget(self._rule(
            alert_panel.absence, (("Duración mínima", posture_panel.absence_seconds),),
            "Rostro no detectado durante el tiempo indicado. Se habilita tras calibrar y ver un rostro.",
        ))

        operating = QFrame()
        operating.setProperty("role", "surface")
        operating_layout = QVBoxLayout(operating)
        operating_layout.setContentsMargins(16, 14, 16, 14)
        operating_layout.setSpacing(10)
        operating_layout.addWidget(text_label("Estado de las alertas", "sectionTitle"))
        operating_layout.addWidget(self._separator())
        self.state_title = text_label("Alertas desactivadas", "stateTitle")
        operating_layout.addWidget(self.state_title)
        alert_panel.status.setProperty("role", "muted")
        operating_layout.addWidget(alert_panel.status)
        self.last_event = text_label("—")
        self.wait_value = text_label("", "measurement")
        self.recovery_value = text_label("", "measurement")
        for caption, value in (
            ("Última activación", self.last_event),
            ("Espera restante", self.wait_value),
            ("Recuperación observada", self.recovery_value),
        ):
            operating_layout.addWidget(self._fact(caption, value))
        operating_layout.addWidget(self._separator())
        operating_layout.addWidget(text_label("Repetición y recuperación", "sectionTitle"))

        cooldown = host()
        cooldown.layout().setSpacing(5)
        cooldown.layout().addWidget(text_label("Espera tras cerrar", "muted"))
        cooldown.layout().addWidget(alert_panel.cooldown)
        recovery = host()
        recovery.layout().setSpacing(5)
        recovery.layout().addWidget(text_label("Recuperación estable", "muted"))
        recovery.layout().addWidget(alert_panel.recovery)
        operating_layout.addWidget(ResponsiveColumns(cooldown, recovery, breakpoint=320, stretch=(1, 1)))
        alert_panel.cooldown.setToolTip(
            "Espera común después de cerrar una alerta. No sustituye la recuperación de cada señal. "
            "La rueda desplaza la ventana."
        )
        alert_panel.recovery.setToolTip(
            "Tiempo continuo con mediciones válidas de recuperación de las señales seleccionadas. "
            "La rueda desplaza la ventana."
        )
        operating_layout.addWidget(text_label(
            "Esc cierra el video. Cada señal debe recuperarse y respetar la espera para volver a avisar.",
            "muted",
        ))
        operating_layout.addStretch()

        self.details = host()
        for label in (
            posture_panel.head_state, posture_panel.angle_label, posture_panel.head_counter,
            posture_panel.head_signal, posture_panel.head_message, posture_panel.absence_state,
            posture_panel.absence_counter, posture_panel.absence_signal, posture_panel.absence_message,
        ):
            self.details.layout().addWidget(label)
        self.details_toggle = QToolButton()
        self.details_toggle.setText("Mediciones de cabeza y rostro")
        self.details_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.details_toggle.setCheckable(True)
        self.details_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.details_toggle.toggled.connect(self._toggle_details)
        self.details.hide()

        self.columns = ResponsiveColumns(rules, operating, breakpoint=850, stretch=(3, 2))
        self.video_host = host()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 12)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addWidget(self.columns, 1)
        layout.addWidget(self.details_toggle)
        layout.addWidget(self.details)
        layout.addWidget(self.video_host)
        alert_panel.presentation_changed.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _separator():
        line = QFrame()
        line.setObjectName("sectionDivider")
        line.setFixedHeight(1)
        return line

    @staticmethod
    def _fact(caption, value):
        row = host()
        layout = row.layout()
        layout.setSpacing(3)
        label = text_label(caption, "muted")
        layout.addWidget(label)
        layout.addWidget(value)
        return row

    @staticmethod
    def _rule(checkbox, fields, explanation):
        rule = QFrame()
        rule.setProperty("role", "signalRow")
        layout = QVBoxLayout(rule)
        layout.setContentsMargins(0, 12, 0, 12)
        description = host()
        description.layout().setSpacing(6)
        description.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        checkbox.setProperty("role", "ruleTitle")
        description.layout().addWidget(checkbox)
        description.layout().addWidget(text_label(explanation, "muted"))
        editors = host()
        editors.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        editors_layout = QHBoxLayout()
        editors_layout.setContentsMargins(0, 0, 0, 0)
        editors_layout.setSpacing(10)
        for title, widget in fields:
            field = host()
            field.layout().setSpacing(5)
            field.layout().addWidget(text_label(title, "fieldLabel"))
            widget.setMaximumWidth(112)
            field.layout().addWidget(widget)
            editors_layout.addWidget(field)
        editors.layout().addLayout(editors_layout)
        editors.setMaximumWidth(234 if len(fields) > 1 else 112)
        layout.addWidget(ResponsiveColumns(description, editors, breakpoint=480, stretch=(3, 2)))
        return rule

    @Slot(bool)
    def _toggle_details(self, expanded):
        self.details.setVisible(expanded)
        self.details_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    @Slot()
    def refresh(self):
        if self._shutting_down:
            return
        message = self._alerts.status.text()
        title, tone = alert_heading(
            message, enabled=self._alerts.enabled.isChecked(), active=self._alerts.engine.active,
        )
        self.state_title.setText(title)
        set_tone(self.state_title, tone)
        self._alerts.status.setVisible(message != "Alertas automáticas desactivadas.")
        self.last_event.setText(self._alerts.trigger_label.text().partition(": ")[2] or "—")
        self.wait_value.setText(self._alerts.wait_label.text().partition(": ")[2].replace(".", ","))
        self.recovery_value.setText(self._alerts.recovery_label.text().partition(": ")[2].replace(".", ","))

    def shutdown(self):
        self._shutting_down = True
        self.alert_selector.shutdown()
        self._alerts = None

