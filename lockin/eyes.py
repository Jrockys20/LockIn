"""Medición de apertura y regla temporal; no determina sueño ni atención."""

from collections import deque
from dataclasses import dataclass, field, replace
import math

import numpy as np

# Contornos del ojo del sujeto según los índices oficiales de MediaPipe.
LEFT_EYE = (362, 385, 387, 263, 373, 380)
RIGHT_EYE = (33, 160, 158, 133, 153, 144)
MAX_EYE_GAP = 0.35
CLOSED_RATIO = 0.55
OPEN_RATIO = 0.75


@dataclass(frozen=True)
class EyeMeasurement:
    left: float
    right: float

    def valid(self) -> bool:
        return all(math.isfinite(v) and 0 <= v <= 0.8
                   for v in (self.left, self.right))


@dataclass(frozen=True)
class EyeReference:
    left: float
    right: float


@dataclass(frozen=True)
class EyeCalibrationStatus:
    state: str = "pendiente"
    progress: float = 0.0
    message: str = "Calibra la apertura habitual de tus ojos antes de evaluar."
    reference: EyeReference | None = None
    requested_at: float | None = None


@dataclass(frozen=True)
class EyeStatus:
    state: str = "no evaluables"
    closed_for: float = 0.0
    rule_met: bool = False
    message: str = "Inicia la cámara y calibra los ojos abiertos."
    required_duration: float = 2.0
    left_ratio: float | None = None
    right_ratio: float | None = None
    calibration: EyeCalibrationStatus = field(default_factory=EyeCalibrationStatus)


def measure_eyes(landmarks, width: int, height: int, rotation) -> tuple[EyeMeasurement | None, str]:
    if width <= 0 or height <= 0 or len(landmarks) <= max(*LEFT_EYE, *RIGHT_EYE):
        return None, "Faltan puntos de los ojos o dimensiones válidas."
    if rotation is None or len(rotation) != 9:
        return None, "La postura no permite comprobar la medición de los ojos."
    r = np.asarray(rotation, dtype=float).reshape(3, 3)
    if not np.isfinite(r).all() or abs(r[2, 2]) < math.cos(math.radians(35)):
        return None, "Coloca el rostro más de frente para medir ambos ojos."

    ratios, widths = [], []
    for indices in (LEFT_EYE, RIGHT_EYE):
        normalized = np.asarray([(landmarks[i].x, landmarks[i].y) for i in indices])
        if not np.isfinite(normalized).all() or np.any(normalized < 0) or np.any(normalized > 1):
            return None, "Los puntos de los ojos quedan fuera de la imagen o no son válidos."
        # Corrige la proporción de la imagen: x e y deben estar en píxeles.
        points = normalized * np.asarray((width, height))
        eye_width = float(np.linalg.norm(points[0] - points[3]))
        if eye_width < 12:
            return None, "Acércate a la cámara: los ojos ocupan muy pocos píxeles."
        opening = float(
            (np.linalg.norm(points[1] - points[5])
             + np.linalg.norm(points[2] - points[4])) / (2 * eye_width)
        )
        ratios.append(opening)
        widths.append(eye_width)
    if min(widths) / max(widths) < 0.5:
        return None, "No se observan ambos ojos con una geometría comparable."
    measurement = EyeMeasurement(*ratios)
    if not measurement.valid():
        return None, "La geometría de los párpados no permite una medición válida."
    return measurement, ""


class EyeCalibrator:
    def __init__(self, duration: float = 2.0, max_gap: float = MAX_EYE_GAP) -> None:
        if not math.isfinite(duration) or duration <= 0 or not math.isfinite(max_gap) or max_gap <= 0:
            raise ValueError("Los tiempos de calibración de ojos deben ser positivos.")
        self.duration, self.max_gap = duration, max_gap
        self.status = EyeCalibrationStatus()
        self._requested = 0.0
        self._first: float | None = None
        self._last: float | None = None
        self._samples = deque(maxlen=512)  # solo números, nunca fotogramas

    def start(self, now: float) -> None:
        self._requested = now
        self._first = self._last = None
        self._samples.clear()
        self.status = EyeCalibrationStatus(
            "calibrando", 0.0,
            f"Mira de frente y mantén los ojos abiertos con naturalidad durante {self.duration:g} s.",
            requested_at=now,
        )

    def fail(self, message: str) -> None:
        self._samples.clear()
        self.status = EyeCalibrationStatus(
            "fallida", 0.0, message + " Vuelve a calibrar los ojos abiertos.",
            requested_at=self._requested,
        )

    def check_timeout(self, now: float) -> None:
        last = self._last if self._last is not None else self._requested
        if self.status.state == "calibrando" and now - last > self.max_gap:
            self.fail("La medición de los ojos se interrumpió.")

    def update(self, measurement: EyeMeasurement | None, at: float) -> None:
        if self.status.state != "calibrando" or at < self._requested:
            return
        if self._last is not None and at <= self._last:
            return
        if measurement is None or not measurement.valid():
            self.fail("No se pudieron medir ambos ojos.")
            return
        if self._last is not None and at - self._last > self.max_gap:
            self.fail("Hubo una interrupción entre mediciones.")
            return
        if self._first is None:
            self._first = at
        self._last = at
        self._samples.append((measurement.left, measurement.right))
        progress = min((at - self._first) / self.duration, 1.0)
        if progress < 1:
            self.status = EyeCalibrationStatus(
                "calibrando", progress,
                f"Mantén los ojos abiertos: {max(0, self.duration - (at - self._first)):.1f} s restantes.",
                requested_at=self._requested,
            )
            return
        # Percentil alto para que un parpadeo breve no reduzca la apertura de referencia.
        left, right = np.quantile(np.asarray(self._samples), 0.8, axis=0)
        self._samples.clear()
        if not all(0.1 <= value <= 0.65 for value in (left, right)):
            self.fail("La apertura de referencia es insuficiente o incoherente.")
            return
        reference = EyeReference(float(left), float(right))
        self.status = EyeCalibrationStatus(
            "completada", 1.0, "Referencia de ojos guardada en memoria.", reference,
            requested_at=self._requested,
        )


class EyeClosureRule:
    def __init__(self, duration: float = 2.0, max_gap: float = MAX_EYE_GAP) -> None:
        if not math.isfinite(max_gap) or max_gap <= 0:
            raise ValueError("El intervalo entre mediciones debe ser positivo.")
        self.max_gap = max_gap
        self._since: float | None = None
        self._last: float | None = None
        self.set_duration(duration)

    def reset(self) -> None:
        self._since = self._last = None

    def set_duration(self, value: float) -> None:
        if not math.isfinite(value) or not 0.5 <= value <= 10:
            raise ValueError("El tiempo de cierre debe estar entre 0.5 y 10 segundos.")
        self.duration = value
        self.reset()

    def evaluate(self, measurement: EyeMeasurement, reference: EyeReference, at: float) -> EyeStatus:
        if (not math.isfinite(at) or not measurement.valid() or not all(
                math.isfinite(v) and v > 0 for v in (reference.left, reference.right))):
            self.reset()
            return EyeStatus(message="La medición o la referencia no es válida.",
                             required_duration=self.duration)
        if self._last is not None and at <= self._last:
            raise ValueError("Las mediciones deben avanzar en el tiempo.")
        gap = self._last is not None and at - self._last > self.max_gap
        left, right = measurement.left / reference.left, measurement.right / reference.right
        self._last = at
        if left <= CLOSED_RATIO and right <= CLOSED_RATIO:
            if self._since is None or gap:
                self._since = at
            elapsed = max(0.0, at - self._since)
            met = elapsed >= self.duration
            return EyeStatus(
                "cerrados", elapsed, met,
                "Señal observable: ojos cerrados sostenidos." if met
                else "Midiendo la duración del cierre de ambos ojos.",
                self.duration, left, right,
            )
        self._since = None
        if left >= OPEN_RATIO and right >= OPEN_RATIO:
            return EyeStatus("abiertos", message="Ambos ojos se estiman abiertos.",
                             required_duration=self.duration, left_ratio=left, right_ratio=right)
        return EyeStatus(
            message="Apertura intermedia o asimétrica; se reinicia el contador.",
            required_duration=self.duration, left_ratio=left, right_ratio=right,
        )


class EyesEngine:
    def __init__(self, calibration_duration: float = 2.0, duration: float = 2.0) -> None:
        self.calibrator = EyeCalibrator(calibration_duration)
        self.rule = EyeClosureRule(duration)
        self.status = EyeStatus(required_duration=duration)
        self._last: float | None = None

    def _unavailable(self, message: str) -> None:
        self.rule.reset()
        self.status = EyeStatus(
            message=message, required_duration=self.rule.duration,
            calibration=self.calibrator.status,
        )

    def start_calibration(self, at: float) -> None:
        self.calibrator.start(at)
        self._unavailable("Calibrando ojos abiertos; la regla está en espera.")

    def set_duration(self, duration: float) -> None:
        self.rule.set_duration(duration)
        self._unavailable("Tiempo actualizado. Se inicia un nuevo conteo con la siguiente medición.")

    def check_timeout(self, now: float) -> None:
        before = self.calibrator.status
        self.calibrator.check_timeout(now)
        if (self._last is not None and now - self._last > MAX_EYE_GAP
                or before != self.calibrator.status):
            self._unavailable("Sin mediciones recientes de ambos ojos.")

    def update(self, measurement: EyeMeasurement | None, at: float,
               now: float, reason: str = "") -> None:
        if self._last is not None and at <= self._last:
            return
        if not math.isfinite(at) or not math.isfinite(now) or now - at > MAX_EYE_GAP:
            self.calibrator.check_timeout(now)
            self._unavailable("La medición llegó tarde; no se cuenta ese intervalo.")
            return
        self._last = at
        self.calibrator.update(measurement, at)
        if measurement is None or not measurement.valid():
            self._unavailable(reason or "No se pueden medir ambos ojos con suficiente geometría.")
            return
        reference = self.calibrator.status.reference
        if reference is None:
            self._unavailable(self.calibrator.status.message)
            return
        result = self.rule.evaluate(measurement, reference, at)
        self.status = replace(result, calibration=self.calibrator.status)