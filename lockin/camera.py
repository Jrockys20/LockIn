"""Captura en segundo plano; nunca accede a widgets ni guarda imágenes."""

from collections.abc import Callable
from threading import Event, Lock
import time

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from lockin.devices import CameraDevice, resolve_camera


class CameraWorker(QThread):
    active = Signal()
    failed = Signal(str)

    def __init__(
        self,
        device: CameraDevice,
        capture_factory: Callable = cv2.VideoCapture,
        device_resolver: Callable = resolve_camera,
    ) -> None:
        super().__init__()
        self._device = device
        self._device_resolver = device_resolver
        self._capture_factory = capture_factory
        self._stop = Event()
        self._frame_lock = Lock()
        self._latest_frame: QImage | None = None
        self._frame_consumer: Callable | None = None

    def set_frame_consumer(self, consumer: Callable | None) -> None:
        with self._frame_lock:
            self._frame_consumer = consumer

    def request_stop(self) -> None:
        # Event también conserva una petición hecha antes de que arranque run().
        self._stop.set()

    def take_latest_frame(self) -> QImage | None:
        """Consume una sola imagen. La siguiente sustituye a la anterior."""
        with self._frame_lock:
            image = self._latest_frame
            self._latest_frame = None
        return image

    def run(self) -> None:
        capture = None
        try:
            if self._stop.is_set():
                return
            # Crear, abrir, leer y liberar se hace siempre en el mismo hilo.
            device = self._device_resolver(self._device)
            if self._stop.is_set():
                return
            capture = self._capture_factory()
            opened = capture.open(device.index, device.backend)
            if self._stop.is_set():
                return
            if not opened or not capture.isOpened():
                self.failed.emit(
                    f"No se pudo abrir la cámara «{self._device.name}». "
                    "Pulsa «Actualizar cámaras», cierra otras aplicaciones que la usen "
                    "y revisa los permisos de cámara para aplicaciones de escritorio "
                    "en la configuración de Windows."
                )
                return

            # Son preferencias: el controlador puede elegir otros valores.
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            first_frame = True
            while not self._stop.is_set():
                ok, frame = capture.read()
                captured_at = time.monotonic()
                if self._stop.is_set():
                    break
                if not ok or frame is None or frame.size == 0:
                    self.failed.emit(
                        f"La cámara «{self._device.name}» dejó de entregar imágenes. "
                        "Puede estar desconectada u ocupada, o haber fallado su "
                        "controlador. Revisa la conexión y vuelve a iniciar."
                    )
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width, _ = rgb.shape
                # copy() separa la imagen del búfer temporal de NumPy.
                image = QImage(
                    rgb.data, width, height, rgb.strides[0],
                    QImage.Format.Format_RGB888,
                ).copy()
                with self._frame_lock:
                    self._latest_frame = image
                    consumer = self._frame_consumer
                if consumer is not None:
                    consumer(rgb, captured_at)
                if first_frame:
                    self.active.emit()
                    first_frame = False
                # Evita un bucle intensivo con fuentes que no regulan su ritmo.
                self._stop.wait(0.001)
        except Exception as exc:
            if not self._stop.is_set():
                self.failed.emit(
                    f"Error al utilizar la cámara «{self._device.name}»: {exc}. "
                    "Revisa la conexión y vuelve a iniciar."
                )
        finally:
            try:
                if capture is not None:
                    capture.release()
            except Exception as exc:
                self.failed.emit(f"No se pudo liberar la cámara: {exc}.")
            finally:
                with self._frame_lock:
                    self._latest_frame = None
                    self._frame_consumer = None