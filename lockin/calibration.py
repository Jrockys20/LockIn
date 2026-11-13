"""Referencia temporal de postura; no clasifica atención ni distracción."""

from dataclasses import dataclass
import math

import numpy as np

from lockin.eyes import EyeMeasurement


@dataclass(frozen=True)
class HeadPose:
    rotation: tuple[float, ...]  # matriz 3 x 3, por filas
    center: tuple[float, float]  # coordenadas normalizadas de la cara
    scale: float               # ancho relativo de la cara

    def valid(self) -> bool:
        if len(self.rotation) != 9 or len(self.center) != 2:
            return False
        values = (*self.rotation, *self.center, self.scale)
        if not all(math.isfinite(v) for v in values):
            return False
        r = np.asarray(self.rotation).reshape(3, 3)
        return (
            0 < self.scale <= 2 and all(0 <= v <= 1 for v in self.center)
            and np.allclose(r.T @ r, np.eye(3), atol=0.02)
            and abs(np.linalg.det(r) - 1) < 0.02
        )


@dataclass(frozen=True)
class FaceObservation:
    count: int = 0
    pose: HeadPose | None = None
    boxes: tuple[tuple[float, float, float, float], ...] = ()
    eyes: EyeMeasurement | None = None
    eyes_reason: str = ""


@dataclass(frozen=True)
class CalibrationStatus:
    state: str = "pendiente"
    progress: float = 0.0
    message: str = "Mira cómodamente la pantalla y pulsa «Calibrar postura»."
    reference: HeadPose | None = None
    requested_at: float | None = None


def rotation_distance(a: HeadPose, b: HeadPose) -> float:
    ra = np.asarray(a.rotation).reshape(3, 3)
    rb = np.asarray(b.rotation).reshape(3, 3)
    cosine = float(np.clip((np.trace(ra.T @ rb) - 1) / 2, -1, 1))
    return math.degrees(math.acos(cosine))


class Calibrator:
    def __init__(self, duration: float = 3.0, max_gap: float = 0.75) -> None:
        if duration <= 0 or max_gap <= 0:
            raise ValueError("Los tiempos de calibración deben ser positivos.")
        self.duration = duration
        self.max_gap = max_gap
        self.status = CalibrationStatus()
        self._requested_at = 0.0
        self._first_at: float | None = None
        self._last_at: float | None = None
        self._anchor: HeadPose | None = None
        self._sum = np.zeros(12)
        self._count = 0

    def start(self, now: float) -> None:
        # Recalibrar descarta la referencia anterior, incluso si el intento falla.
        self.status = CalibrationStatus(
            "calibrando", 0.0, f"Mantén una postura cómoda y estable durante {self.duration:g} segundos.",
            requested_at=now,
        )
        self._requested_at = now
        self._first_at = self._last_at = None
        self._anchor = None
        self._sum.fill(0)
        self._count = 0

    def fail(self, message: str) -> None:
        self.status = CalibrationStatus(
            "fallida", 0.0, message + " Vuelve a calibrar.", requested_at=self._requested_at
        )

    def check_timeout(self, now: float) -> None:
        last = self._last_at if self._last_at is not None else self._requested_at
        if self.status.state == "calibrando" and now - last > self.max_gap:
            self.fail("No llegaron observaciones recientes de forma continua.")

    def update(self, observation: FaceObservation, captured_at: float) -> None:
        if self.status.state != "calibrando" or captured_at < self._requested_at:
            return
        if self._last_at is not None and captured_at <= self._last_at:
            return
        if observation.count != 1:
            self.fail("Se necesita un solo rostro visible durante todo el intento.")
            return
        pose = observation.pose
        if pose is None or not pose.valid():
            self.fail("No se pudo estimar una postura válida.")
            return
        if self._last_at is not None and captured_at - self._last_at > self.max_gap:
            self.fail("Hubo una interrupción entre observaciones.")
            return
        if self._anchor is None:
            self._anchor = pose
            self._first_at = captured_at
        anchor = self._anchor
        position_change = math.dist(anchor.center, pose.center)
        size_change = abs(pose.scale / anchor.scale - 1)
        # Son tolerancias de estabilidad de calibración, no reglas de distracción.
        if rotation_distance(anchor, pose) > 6 or position_change > 0.035 or size_change > 0.08:
            self.fail("Hubo demasiado movimiento durante la calibración.")
            return
        self._last_at = captured_at
        self._sum += np.asarray((*pose.rotation, *pose.center, pose.scale))
        self._count += 1
        elapsed = captured_at - self._first_at
        progress = min(elapsed / self.duration, 1.0)
        if progress < 1:
            self.status = CalibrationStatus(
                "calibrando", progress,
                f"Mantén la postura: {max(0, self.duration - elapsed):.1f} s restantes.",
                requested_at=self._requested_at,
            )
            return
        mean = self._sum / self._count
        u, _, vt = np.linalg.svd(mean[:9].reshape(3, 3))
        rotation = u @ vt
        reference = HeadPose(tuple(rotation.ravel()), tuple(mean[9:11]), float(mean[11]))
        self.status = CalibrationStatus(
            "completada", 1.0, "Referencia guardada en memoria para esta sesión.", reference,
            requested_at=self._requested_at,
        )