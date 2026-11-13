"""Decisiones de alerta, sin ventanas, cámara ni reproducción."""

from dataclasses import dataclass
import math

from lockin.eyes import MAX_EYE_GAP
from lockin.posture import MAX_POSTURE_GAP


EYES_SIGNAL = "ojos cerrados sostenidos"
HEAD_SIGNAL = "cabeza apartada sostenida"
ABSENCE_SIGNAL = "rostro ausente sostenido"

@dataclass(frozen=True)
class AlertSettings:
    enabled: bool = False
    eyes: bool = True
    head: bool = True
    absence: bool = True
    cooldown: float = 15.0
    recovery: float = 1.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.cooldown) or not 0 <= self.cooldown <= 300:
            raise ValueError("La espera entre alertas debe estar entre 0 y 300 segundos.")
        if not math.isfinite(self.recovery) or not 0.5 <= self.recovery <= 5:
            raise ValueError("La recuperación debe estar entre 0.5 y 5 segundos.")

    @property
    def any_rule(self) -> bool:
        return self.eyes or self.head or self.absence


@dataclass(frozen=True)
class AlertEvidence:
    at: float | None = None
    ready: bool = False
    reasons: tuple[str, ...] = ()
    recovered: bool = False
    max_gap: float = MAX_POSTURE_GAP
    message: str = "Esperando mediciones."
    recovered_rules: tuple[str, ...] = ()


def evaluate_snapshot(snapshot, settings: AlertSettings, now: float) -> AlertEvidence:
    gap = MAX_EYE_GAP if settings.eyes else MAX_POSTURE_GAP
    if not settings.any_rule:
        return AlertEvidence(message="Selecciona al menos una señal.", max_gap=gap)
    if snapshot is None or snapshot.phase != "ready":
        message = snapshot.error if snapshot is not None and snapshot.phase == "error" else "Esperando al analizador."
        return AlertEvidence(message=message, max_gap=gap)
    at = snapshot.captured_at
    if at is None or not math.isfinite(at) or not math.isfinite(now) or at > now:
        return AlertEvidence(message="Sin una observación reciente.", max_gap=gap)
    age = now - at
    if age > MAX_POSTURE_GAP:
        return AlertEvidence(message="Sin datos recientes; no se considera recuperación.", max_gap=gap)
    eyes, posture = snapshot.eyes, snapshot.posture
    if settings.eyes and (
        eyes.calibration.state != "completada" or eyes.calibration.reference is None
    ):
        return AlertEvidence(at, message="Completa «Calibrar ojos abiertos».", max_gap=gap)
    if (settings.head or settings.absence) and (
        snapshot.calibration.state != "completada" or snapshot.calibration.reference is None
    ):
        return AlertEvidence(at, message="Completa «Calibrar postura».", max_gap=gap)
    if settings.absence and not posture.absence.armed:
        return AlertEvidence(at, message="Esperando habilitar la ausencia con un rostro visible.", max_gap=gap)
    observation = snapshot.observation
    if observation is None:
        return AlertEvidence(at, message="Sin observación válida.", max_gap=gap)

    reasons = []
    recovered_rules = []
    recovered = True
    if settings.eyes:
        valid = (age <= MAX_EYE_GAP and observation.count == 1
                 and observation.eyes is not None and observation.eyes.valid())
        if valid and eyes.state == "cerrados" and eyes.rule_met:
            reasons.append(EYES_SIGNAL)
        if valid and eyes.state == "abiertos":
            recovered_rules.append(EYES_SIGNAL)
        recovered &= valid and eyes.state == "abiertos"
    if settings.head:
        head = posture.head
        valid = (observation.count == 1 and observation.pose is not None
                 and observation.pose.valid() and head.angle is not None
                 and math.isfinite(head.angle))
        if valid and head.state == "fuera del margen" and head.rule_met:
            reasons.append(HEAD_SIGNAL)
        if valid and head.state == "dentro del margen":
            recovered_rules.append(HEAD_SIGNAL)
        recovered &= valid and head.state == "dentro del margen"
    if settings.absence:
        absence = posture.absence
        if observation.count == 0 and absence.state == "rostro ausente" and absence.rule_met:
            reasons.append(ABSENCE_SIGNAL)
        if observation.count == 1 and absence.state == "rostro visible":
            recovered_rules.append(ABSENCE_SIGNAL)
        recovered &= observation.count == 1 and absence.state == "rostro visible"
    return AlertEvidence(
        at, True, tuple(reasons), bool(recovered), gap,
        "Mediciones de recuperación válidas." if recovered else
        "Las señales aún no permiten confirmar recuperación; Esc cierra el video.",
        recovered_rules=tuple(recovered_rules),
    )


@dataclass(frozen=True)
class AlertDecision:
    action: str = ""
    message: str = ""
    reasons: tuple[str, ...] = ()
    remaining: float = 0.0
    recovered_for: float = 0.0


class AlertEngine:
    def __init__(self, settings: AlertSettings | None = None) -> None:
        self.settings = settings or AlertSettings()
        self.active = False
        self._notified: set[str] = set()
        self._rule_recovery: dict[str, tuple[float, float]] = {}
        self._stop_requested = False
        self._finished_at: float | None = None
        self._recovery_since: float | None = None
        self._last_recovery: float | None = None

    @property
    def _latched(self) -> bool:
        return bool(self._notified)

    def reset_recovery(self) -> None:
        self._recovery_since = self._last_recovery = None
        self._rule_recovery.clear()

    def configure(self, settings: AlertSettings) -> None:
        self.settings = settings
        self.reset_recovery()

    def reset_episode(self) -> None:
        # Una parada explícita empieza una nueva sesión, conservando la espera.
        if not self.active:
            self._notified.clear()
        self.reset_recovery()

    def remaining(self, now: float) -> float:
        if self._finished_at is None:
            return 0.0
        return max(0.0, self._finished_at + self.settings.cooldown - now)

    def playback_finished(self, now: float) -> None:
        if self.active:
            self.active = False
            self._stop_requested = False
            self._finished_at = now
            self.reset_recovery()
            # Esc/error conserva solo los bloqueos de las señales ya avisadas.

    def _rearm_recovered_rules(self, evidence: AlertEvidence, now: float) -> None:
        at = evidence.at
        for reason in tuple(self._notified):
            gap = MAX_EYE_GAP if reason == EYES_SIGNAL else MAX_POSTURE_GAP
            if (not evidence.ready or reason not in evidence.recovered_rules
                    or at is None or not math.isfinite(at) or at > now or now - at > gap):
                self._rule_recovery.pop(reason, None)
                continue
            previous = self._rule_recovery.get(reason)
            if previous is None or at - previous[1] > gap:
                since = at
            elif at < previous[1]:
                self._rule_recovery.pop(reason, None)
                continue
            else:
                since = previous[0]
            self._rule_recovery[reason] = (since, at)
            if at - since >= self.settings.recovery:
                self._notified.remove(reason)
                self._rule_recovery.pop(reason, None)

    def _recovery_time(self, evidence: AlertEvidence, now: float) -> float:
        at = evidence.at
        if (not evidence.ready or not evidence.recovered or at is None
                or not math.isfinite(at) or at > now or now - at > evidence.max_gap):
            self._recovery_since = self._last_recovery = None
            return 0.0
        if self._last_recovery is not None and at < self._last_recovery:
            self._recovery_since = self._last_recovery = None
            return 0.0
        if self._last_recovery is None or at - self._last_recovery > evidence.max_gap:
            self._recovery_since = at
        self._last_recovery = at
        return max(0.0, at - self._recovery_since)

    def update(self, evidence: AlertEvidence, now: float, *,
               busy: bool = False, video_available: bool = True) -> AlertDecision:
        remaining = self.remaining(now)
        if not self.settings.enabled or not self.settings.any_rule:
            self.reset_recovery()
            return AlertDecision(
                message="Alertas automáticas desactivadas." if not self.settings.enabled
                else "Selecciona al menos una señal.", remaining=remaining,
            )
        if self.active:
            # La ventana ya está avisando: registra señales nuevas sin abrir otra.
            self._notified.update(evidence.reasons)
        self._rearm_recovered_rules(evidence, now)
        if self.active:
            recovered_for = self._recovery_time(evidence, now)
            if recovered_for >= self.settings.recovery and not self._stop_requested:
                self._stop_requested = True
                return AlertDecision("stop", "Recuperación observable estable.", recovered_for=recovered_for)
            return AlertDecision(
                message="Alerta en reproducción. " + evidence.message,
                recovered_for=recovered_for,
            )
        eligible = tuple(reason for reason in evidence.reasons if reason not in self._notified)
        if self._notified and not eligible:
            reasons = ", ".join(sorted(self._notified))
            return AlertDecision(
                message=f"Episodio ya avisado para: {reasons}. "
                        "Cada señal se habilita al observar su propia recuperación estable; "
                        "otras señales pueden alertar al terminar la espera.",
                remaining=remaining,
                recovered_for=max(
                    (last - since for since, last in self._rule_recovery.values()),
                    default=0.0,
                ),
            )
        if remaining > 0:
            return AlertDecision(message="Esperando antes de permitir otra alerta.", remaining=remaining)
        if busy:
            return AlertDecision(message="Hay una prueba manual de video en curso.")
        if not video_available:
            return AlertDecision(message="Elige un video local para activar las alertas.")
        if not evidence.ready:
            return AlertDecision(message=evidence.message)
        if eligible:
            # Reserva antes de abrir la ventana; no reintenta en bucle si Qt falla.
            self.active = True
            self._notified.update(evidence.reasons)
            self._stop_requested = False
            self.reset_recovery()
            return AlertDecision("start", "Abriendo alerta automática.", eligible)
        return AlertDecision(message="Alertas preparadas. Esperando una señal sostenida.")
