"""Orientación relativa y ausencia sostenida; solo señales observables."""

from dataclasses import dataclass, field
import math

from lockin.calibration import FaceObservation, HeadPose, rotation_distance


MAX_POSTURE_GAP = 0.75


@dataclass(frozen=True)
class PostureSettings:
    angle_limit: float = 20.0
    head_duration: float = 2.0
    absence_duration: float = 3.0

    def __post_init__(self) -> None:
        for value, lower, upper, name in (
            (self.angle_limit, 5, 60, "El margen de giro"),
            (self.head_duration, 0.5, 10, "El tiempo de cabeza apartada"),
            (self.absence_duration, 0.5, 30, "El tiempo sin rostro"),
        ):
            if not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError(f"{name} debe estar entre {lower:g} y {upper:g}.")


@dataclass(frozen=True)
class HeadStatus:
    state: str = "pendiente de calibración"
    angle: float | None = None
    elapsed: float = 0.0
    rule_met: bool = False
    message: str = "Pulsa «Calibrar postura» y completa la referencia."


@dataclass(frozen=True)
class AbsenceStatus:
    state: str = "en espera"
    armed: bool = False
    elapsed: float = 0.0
    rule_met: bool = False
    message: str = "Se habilita tras calibrar postura con un rostro visible."


@dataclass(frozen=True)
class PostureStatus:
    settings: PostureSettings = field(default_factory=PostureSettings)
    head: HeadStatus = field(default_factory=HeadStatus)
    absence: AbsenceStatus = field(default_factory=AbsenceStatus)


class PostureEngine:
    def __init__(self, settings: PostureSettings | None = None) -> None:
        self.settings = settings or PostureSettings()
        self._reference: HeadPose | None = None
        self._armed = False
        self._last: float | None = None
        self._head_since: float | None = None
        self._absence_since: float | None = None
        self.status = PostureStatus(self.settings)

    def _reset_counters(self) -> None:
        self._head_since = self._absence_since = None

    def _unavailable(self, message: str) -> None:
        self._reset_counters()
        if self._reference is None:
            self.status = PostureStatus(self.settings)
        else:
            self.status = PostureStatus(
                self.settings, HeadStatus("no evaluable", message=message),
                AbsenceStatus("no evaluable", self._armed, message=message),
            )

    def sync_reference(self, reference: HeadPose | None) -> None:
        reference = reference if reference is not None and reference.valid() else None
        if reference != self._reference:
            self._reference = reference
            self._armed = False
            self._last = None
            self._unavailable("Esperando una observación reciente con la nueva referencia.")

    def configure(self, settings: PostureSettings) -> None:
        self.settings = settings
        self._last = None
        self._unavailable("Opciones actualizadas; se reinician ambos contadores.")

    def check_timeout(self, now: float) -> None:
        if self._last is not None and now - self._last > MAX_POSTURE_GAP:
            self._unavailable("Sin datos recientes; este intervalo no se cuenta.")

    def update(self, observation: FaceObservation | None, reference: HeadPose | None,
               at: float, now: float) -> None:
        self.sync_reference(reference)
        if (not math.isfinite(at) or not math.isfinite(now)
                or at > now or now - at > MAX_POSTURE_GAP):
            self._unavailable("El resultado no es reciente; este intervalo no se cuenta.")
            return
        if self._last is not None and at <= self._last:
            self.check_timeout(now)
            return
        if self._last is not None and at - self._last > MAX_POSTURE_GAP:
            self._reset_counters()
        self._last = at
        if self._reference is None:
            self._unavailable("Calibra la postura antes de evaluar.")
            return
        if observation is None:
            self._unavailable("No hay una observación válida del analizador.")
            return
        if observation.count == 0:
            self._head_since = None
            head = HeadStatus(
                "no evaluable", message="Sin rostro; no se puede medir su orientación."
            )
            if self._armed:
                if self._absence_since is None:
                    self._absence_since = at
                elapsed = at - self._absence_since
                met = elapsed >= self.settings.absence_duration
                absence = AbsenceStatus(
                    "rostro ausente", True, elapsed, met,
                    "Señal observable: rostro ausente de forma sostenida." if met
                    else "Contando imágenes recientes sin rostro detectado.",
                )
            else:
                absence = AbsenceStatus()
            self.status = PostureStatus(self.settings, head, absence)
            return
        if observation.count != 1:
            self._unavailable("Hay varios rostros; no se elige una persona para evaluar.")
            return

        # Un rostro visible con referencia completa habilita la ausencia en esta sesión.
        self._armed = True
        self._absence_since = None
        absence = AbsenceStatus(
            "rostro visible", True, message="Un rostro detectado; contador de ausencia en cero."
        )
        current = observation.pose
        if current is None or not current.valid():
            self._head_since = None
            head = HeadStatus(
                "no evaluable", message="Se ve el rostro, pero no se pudo estimar su orientación."
            )
        else:
            angle = rotation_distance(self._reference, current)
            if angle <= self.settings.angle_limit + 1e-6:
                self._head_since = None
                head = HeadStatus(
                    "dentro del margen", angle, message="Orientación dentro del margen calibrado."
                )
            else:
                if self._head_since is None:
                    self._head_since = at
                elapsed = at - self._head_since
                met = elapsed >= self.settings.head_duration
                head = HeadStatus(
                    "fuera del margen", angle, elapsed, met,
                    "Señal observable: cabeza apartada de forma sostenida." if met
                    else "Contando tiempo fuera del margen de orientación.",
                )
        self.status = PostureStatus(self.settings, head, absence)
