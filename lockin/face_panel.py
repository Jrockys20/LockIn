"""Estados de rostro y calibración; todos los widgets se actualizan en la GUI."""

import time

from PySide6.QtCore import QTimer, Signal, Slot
from PySide6.QtWidgets import QGroupBox, QLabel, QProgressBar, QPushButton, QVBoxLayout

from lockin.face import AnalysisWorker, MAX_RESULT_AGE


class FacePanel(QGroupBox):
    presentation_changed = Signal()
    face_boxes_changed = Signal(object)
    analysis_started = Signal(object)
    analysis_updated = Signal(object)
    analysis_stopped = Signal()
    calibration_requested = Signal(float)

    def __init__(self, parent=None, worker_factory=AnalysisWorker) -> None:
        super().__init__("01 · Postura de referencia", parent)
        self._factory = worker_factory
        self._worker = None
        self._last = None
        self._requested = False
        self._request_time = 0.0
        self._boxes = ()
        self.face_status = QLabel("Rostro: sin analizar · cámara detenida")
        self.calibration_status = QLabel("Calibración: pendiente")
        self.message = QLabel("Inicia la cámara para detectar un rostro y calibrar.")
        self.message.setWordWrap(True)
        self.calibrate_button = QPushButton("Calibrar postura")
        self.calibrate_button.setEnabled(False)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setAccessibleName("Progreso de calibración")
        self.setProperty("role", "reference")
        self.readiness = QLabel("Sin referencia")
        self.readiness.setProperty("role", "muted")
        instructions = QLabel("Mira al centro de la pantalla y mantén una postura cómoda y estable durante 3 segundos.")
        instructions.setWordWrap(True)
        instructions.setProperty("role", "muted")
        for label in (self.face_status, self.calibration_status, self.readiness):
            label.setWordWrap(True)
        self.calibrate_button.setProperty("role", "primary")
        self.calibrate_button.setToolTip("Toma una referencia de postura. Repetir descarta la referencia anterior.")
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(self.readiness)
        layout.addWidget(instructions)
        layout.addWidget(self.calibration_status)
        layout.addWidget(self.progress)
        layout.addWidget(self.calibrate_button)
        layout.addWidget(self.message)
        # La presencia del rostro se muestra junto a la vista previa compartida.
        self.face_status.setParent(self)
        self.face_status.hide()
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)
        self.calibrate_button.clicked.connect(self.calibrate)

    def _set_boxes(self, boxes) -> None:
        boxes = tuple(boxes)
        if boxes != self._boxes:
            self._boxes = boxes
            self.face_boxes_changed.emit(boxes)

    def start(self, camera) -> None:
        if self._worker is not None:
            return
        self._last = None
        self._requested = False
        self._set_boxes(())
        self._worker = self._factory()
        self.analysis_started.emit(self._worker)
        camera.set_frame_consumer(self._worker.submit)
        self.face_status.setText("Rostro: iniciando análisis…")
        self.message.setText("Cargando el modelo local de rostro.")
        self._timer.start()
        self._worker.start()
        self.presentation_changed.emit()

    @Slot()
    def _poll(self) -> None:
        if self._worker is None:
            return
        snapshot = self._worker.take_snapshot()
        if snapshot is not None:
            self._last = snapshot
            acknowledged = snapshot.calibration.state == "calibrando"
            recent_outcome = (
                snapshot.calibration.state in ("completada", "fallida")
                and snapshot.captured_at is not None
                and snapshot.captured_at >= self._request_time
            )
            request_acknowledged = (
                snapshot.calibration.requested_at is not None
                and snapshot.calibration.requested_at >= self._request_time
            )
            if request_acknowledged or acknowledged or recent_outcome:
                self._requested = False
        current = self._last
        self.analysis_updated.emit(current)
        if current is None or current.phase == "loading":
            self.calibrate_button.setEnabled(False)
            self._set_boxes(())
            self.presentation_changed.emit()
            return
        if current.phase == "error":
            self._requested = False
            self.calibrate_button.setEnabled(False)
            self._set_boxes(())
            self.face_status.setText("Rostro: error de análisis")
            self.calibration_status.setText("Calibración: no disponible")
            self.progress.setValue(0)
            self.message.setText(current.error)
            self.presentation_changed.emit()
            return

        status = current.calibration
        if self._requested:
            # Un resultado anterior a la petición no debe volver a mostrar pendiente.
            self.calibration_status.setText("Calibración: iniciando")
            self.progress.setValue(0)
            self.message.setText("Solicitud enviada. Esperando una observación reciente…")
        else:
            self.calibration_status.setText(f"Calibración: {status.state}")
            self.progress.setValue(round(status.progress * 100))
            self.message.setText(status.message)
        self.calibrate_button.setText(
            "Recalibrar postura" if status.reference is not None else "Calibrar postura"
        )

        observation = current.observation
        fresh = (
            current.captured_at is not None
            and time.monotonic() - current.captured_at <= MAX_RESULT_AGE
        )
        can_calibrate = False
        if current.captured_at is None:
            self.face_status.setText("Rostro: esperando imagen")
            self._set_boxes(())
        elif not fresh:
            self.face_status.setText("Rostro: sin datos recientes")
            self._set_boxes(())
        elif observation is None or observation.count == 0:
            self.face_status.setText("Rostro: no detectado")
            self._set_boxes(())
        else:
            self._set_boxes(observation.boxes)
            if observation.count > 1:
                self.face_status.setText("Rostro: varios detectados · deja solo uno visible")
            elif observation.pose is None:
                self.face_status.setText("Rostro: detectado · postura no disponible")
            else:
                self.face_status.setText("Rostro: detectado")
                can_calibrate = status.state != "calibrando" and not self._requested

        # Cambiar de False a True en cada sondeo cancelaba una pulsación en curso.
        # Se aplica únicamente el estado final, sin deshabilitar primero el botón.
        self.calibrate_button.setEnabled(can_calibrate)
        self.presentation_changed.emit()

    @Slot()
    def calibrate(self) -> None:
        if self._worker is None or not self.calibrate_button.isEnabled():
            return
        self._requested = True
        self._request_time = time.monotonic()
        self.calibration_requested.emit(self._request_time)
        self.calibrate_button.setEnabled(False)
        self.calibration_status.setText("Calibración: iniciando")
        self.message.setText("Solicitud enviada. Esperando una observación reciente…")
        self.progress.setValue(0)
        self._worker.request_calibration()
        self.presentation_changed.emit()

    def request_stop(self) -> None:
        self.analysis_stopped.emit()
        self._timer.stop()
        self._last = None
        self._set_boxes(())
        self.face_status.setText("Rostro: análisis detenido")
        self.calibration_status.setText("Calibración: pendiente")
        self.progress.setValue(0)
        self.calibrate_button.setEnabled(False)
        if self._worker is not None:
            self._worker.request_stop()
        self.presentation_changed.emit()

    def finish_stop(self) -> bool:
        if self._worker is not None:
            if not self._worker.wait(0):
                return False
            self._worker.deleteLater()
            self._worker = None
        self._last = None
        self._requested = False
        self._set_boxes(())
        self.face_status.setText("Rostro: sin analizar · cámara detenida")
        self.calibration_status.setText("Calibración: pendiente")
        self.calibrate_button.setText("Calibrar postura")
        self.progress.setValue(0)
        self.message.setText("Inicia la cámara para detectar un rostro y calibrar.")
        self.presentation_changed.emit()
        return True
