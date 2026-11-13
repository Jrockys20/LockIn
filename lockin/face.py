"""Face Landmarker y análisis con un solo fotograma pendiente."""

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Condition, Event
import time

import numpy as np
from PySide6.QtCore import QThread

from lockin.calibration import (
    CalibrationStatus, Calibrator, FaceObservation, HeadPose,
)
from lockin.model import read_model
from lockin.eyes import EyesEngine, EyeStatus, measure_eyes
from lockin.posture import PostureEngine, PostureSettings, PostureStatus

MAX_RESULT_AGE = 1.0


def estimate_pose(matrix, landmarks) -> HeadPose | None:
    matrix = np.asarray(matrix, dtype=float)
    points = np.asarray([(p.x, p.y) for p in landmarks], dtype=float)
    if matrix.shape != (4, 4) or points.ndim != 2 or points.shape[0] < 3:
        return None
    if not np.isfinite(matrix).all() or not np.isfinite(points).all():
        return None
    u, singular, vt = np.linalg.svd(matrix[:3, :3])
    if min(singular) < 1e-6:
        return None
    rotation = u @ vt  # elimina escala; no son ángulos clínicos
    lower, upper = points.min(axis=0), points.max(axis=0)
    center = (lower + upper) / 2
    pose = HeadPose(tuple(rotation.ravel()), tuple(center), float(upper[0] - lower[0]))
    return pose if pose.valid() else None


def face_bounds(landmarks) -> tuple[float, float, float, float] | None:
    points = np.asarray([(p.x, p.y) for p in landmarks], dtype=float)
    if points.ndim != 2 or points.shape[0] < 3 or not np.isfinite(points).all():
        return None
    lower, upper = points.min(axis=0), points.max(axis=0)
    if np.any(upper <= lower):
        return None
    padding = (upper - lower) * 0.08
    lower = np.clip(lower - padding, 0, 1)
    upper = np.clip(upper + padding, 0, 1)
    if np.any(upper <= lower):
        return None
    return (float(lower[0]), float(lower[1]), float(upper[0]), float(upper[1]))


class FaceLandmarkerDetector:
    def __init__(self) -> None:
        # Importación y creación costosas dentro del trabajador, nunca en la GUI.
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        self._mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_buffer=read_model(),
                delegate=mp.tasks.BaseOptions.Delegate.CPU,
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=2,  # impide calibrar eligiendo arbitrariamente entre personas
            output_facial_transformation_matrixes=True,
            output_face_blendshapes=False,
        )
        self._detector = vision.FaceLandmarker.create_from_options(options)

    def process(self, rgb: np.ndarray, timestamp_ms: int) -> FaceObservation:
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect_for_video(image, timestamp_ms)
        count = len(result.face_landmarks)
        pose = None
        if count == 1 and result.facial_transformation_matrixes:
            pose = estimate_pose(
                result.facial_transformation_matrixes[0], result.face_landmarks[0]
            )
        boxes = tuple(
            bounds for landmarks in result.face_landmarks
            if (bounds := face_bounds(landmarks)) is not None
        )
        measurement = None
        reason = "Sin rostro visible." if count == 0 else "Se necesita un solo rostro para medir los ojos."
        if count == 1:
            height, width = rgb.shape[:2]
            measurement, reason = measure_eyes(
                result.face_landmarks[0], width, height,
                pose.rotation if pose is not None else None,
            )
        return FaceObservation(count, pose, boxes, measurement, reason)

    def close(self) -> None:
        self._detector.close()


@dataclass(frozen=True)
class AnalysisSnapshot:
    phase: str = "loading"
    observation: FaceObservation | None = None
    captured_at: float | None = None
    calibration: CalibrationStatus = field(default_factory=CalibrationStatus)
    error: str = ""
    eyes: EyeStatus = field(default_factory=EyeStatus)
    posture: PostureStatus = field(default_factory=PostureStatus)


class AnalysisWorker(QThread):
    def __init__(
        self, detector_factory: Callable = FaceLandmarkerDetector,
        calibrator_factory: Callable = Calibrator, clock: Callable = time.monotonic,
        eye_engine_factory: Callable = EyesEngine,
        posture_engine_factory: Callable = PostureEngine,
    ) -> None:
        super().__init__()
        self._detector_factory = detector_factory
        self._calibrator_factory = calibrator_factory
        self._clock = clock
        self._eye_engine_factory = eye_engine_factory
        self._posture_engine_factory = posture_engine_factory
        self._condition = Condition()
        self._stop = Event()
        self._pending: tuple[np.ndarray, float] | None = None
        self._request_at: float | None = None
        self._eye_request_at: float | None = None
        self._eye_duration: float | None = None
        self._posture_settings: PostureSettings | None = None
        self._snapshot: AnalysisSnapshot | None = AnalysisSnapshot()

    def submit(self, rgb: np.ndarray, captured_at: float) -> None:
        # El productor no vuelve a modificar rgb. Sustituye la referencia, sin cola.
        with self._condition:
            if not self._stop.is_set():
                self._pending = (rgb, captured_at)
                self._condition.notify()

    def request_calibration(self) -> None:
        with self._condition:
            if not self._stop.is_set():
                self._request_at = self._clock()
                self._condition.notify()

    def request_eye_calibration(self) -> None:
        with self._condition:
            if not self._stop.is_set():
                self._eye_request_at = self._clock()
                self._condition.notify()

    def request_eye_duration(self, duration: float) -> None:
        if not np.isfinite(duration) or not 0.5 <= duration <= 10:
            raise ValueError("El cierre sostenido debe estar entre 0.5 y 10 segundos.")
        with self._condition:
            if not self._stop.is_set():
                self._eye_duration = duration
                self._condition.notify()

    def request_posture_settings(self, settings: PostureSettings) -> None:
        if not isinstance(settings, PostureSettings):
            raise TypeError("Las opciones de postura deben ser PostureSettings.")
        with self._condition:
            if not self._stop.is_set():
                self._posture_settings = settings
                self._condition.notify()

    def request_stop(self) -> None:
        with self._condition:
            self._stop.set()
            self._pending = None
            self._request_at = None
            self._eye_request_at = None
            self._eye_duration = None
            self._posture_settings = None
            self._snapshot = None
            self._condition.notify()

    def take_snapshot(self) -> AnalysisSnapshot | None:
        with self._condition:
            snapshot, self._snapshot = self._snapshot, None
            return snapshot

    def _publish(self, snapshot: AnalysisSnapshot) -> None:
        with self._condition:
            if not self._stop.is_set():
                self._snapshot = snapshot

    def run(self) -> None:
        detector = None
        observation = None
        captured_at = None
        last_timestamp_ms = -1
        try:
            if self._stop.is_set():
                return
            calibration = self._calibrator_factory()
            eyes = self._eye_engine_factory()
            posture = self._posture_engine_factory()
            detector = self._detector_factory()

            def snapshot():
                return AnalysisSnapshot(
                    "ready", observation, captured_at, calibration.status,
                    eyes=eyes.status, posture=posture.status,
                )

            self._publish(snapshot())
            while not self._stop.is_set():
                with self._condition:
                    self._condition.wait_for(
                        lambda: self._stop.is_set() or self._pending is not None
                        or self._request_at is not None or self._eye_request_at is not None
                        or self._eye_duration is not None or self._posture_settings is not None, timeout=0.1,
                    )
                    if self._stop.is_set():
                        break
                    pending, self._pending = self._pending, None
                    request_at, self._request_at = self._request_at, None
                    eye_request, self._eye_request_at = self._eye_request_at, None
                    duration, self._eye_duration = self._eye_duration, None
                    options, self._posture_settings = self._posture_settings, None

                old_calibration, old_eyes, old_posture = calibration.status, eyes.status, posture.status
                if request_at is not None:
                    calibration.start(request_at)
                if options is not None:
                    posture.configure(options)
                if duration is not None:
                    eyes.set_duration(duration)
                if eye_request is not None:
                    eyes.start_calibration(eye_request)
                now = self._clock()
                calibration.check_timeout(now)
                eyes.check_timeout(now)
                posture.sync_reference(calibration.status.reference)
                posture.check_timeout(now)
                if pending is None:
                    if (old_calibration != calibration.status or old_eyes != eyes.status
                            or old_posture != posture.status or options is not None
                            or request_at is not None or eye_request is not None or duration is not None):
                        self._publish(snapshot())
                    continue
                rgb, sample_at = pending
                now = self._clock()
                if now - sample_at > MAX_RESULT_AGE:
                    eyes.update(None, sample_at, now, "Fotograma antiguo.")
                    posture.update(None, calibration.status.reference, sample_at, now)
                    self._publish(snapshot())
                    continue
                if captured_at is not None and sample_at <= captured_at:
                    continue
                timestamp_ms = max(last_timestamp_ms + 1, int(sample_at * 1000))
                last_timestamp_ms = timestamp_ms
                result = detector.process(rgb, timestamp_ms)
                if self._stop.is_set():
                    break
                now = self._clock()
                if now - sample_at <= MAX_RESULT_AGE:
                    observation, captured_at = result, sample_at
                    calibration.update(result, sample_at)
                    posture.update(result, calibration.status.reference, sample_at, now)
                    eyes.update(
                        result.eyes if result.count == 1 else None,
                        sample_at, now, result.eyes_reason,
                    )
                else:
                    eyes.update(None, sample_at, now, "La inferencia tardó demasiado.")
                    posture.update(None, calibration.status.reference, sample_at, now)
                calibration.check_timeout(now)
                eyes.check_timeout(now)
                posture.sync_reference(calibration.status.reference)
                posture.check_timeout(now)
                self._publish(snapshot())
        except Exception as exc:
            self._publish(AnalysisSnapshot(
                "error", error=f"No se pudo analizar el rostro: {exc}"
            ))
        finally:
            try:
                if detector is not None:
                    detector.close()
            except Exception as exc:
                self._publish(AnalysisSnapshot(
                    "error", error=f"No se pudo cerrar el analizador: {exc}"
                ))
            with self._condition:
                self._stop.set()
                self._pending = None
