"""Consulta de dispositivos de DirectShow; no abre capturas de video."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

import cv2
from cv2_enumerate_cameras import enumerate_cameras
from PySide6.QtCore import QThread


@dataclass(frozen=True)
class CameraDevice:
    index: int
    name: str
    path: str = ""
    backend: int = cv2.CAP_DSHOW

    @property
    def identity(self) -> tuple:
        if self.path:
            return (self.backend, self.path.casefold())
        return (self.backend, self.index, self.name)


def list_cameras() -> list[CameraDevice]:
    # El backend explícito evita listar dos veces la misma webcam con MSMF y DSHOW.
    return [
        CameraDevice(info.index, info.name.strip() or "Cámara sin nombre",
                     info.path or "", info.backend)
        for info in enumerate_cameras(cv2.CAP_DSHOW)
    ]


def camera_labels(devices: list[CameraDevice]) -> list[str]:
    totals = Counter(device.name for device in devices)
    counts: Counter = Counter()
    labels = []
    for device in devices:
        counts[device.name] += 1
        suffix = f" ({counts[device.name]})" if totals[device.name] > 1 else ""
        labels.append(device.name + suffix)
    return labels


def resolve_camera(
    selected: CameraDevice,
    provider: Callable = list_cameras,
) -> CameraDevice:
    """Reconsulta el índice actual sin abrir la webcam ni elegir otra por posición."""
    devices = provider()
    if selected.path:
        matches = [d for d in devices if d.identity == selected.identity]
    else:
        # Algunas cámaras virtuales no publican DevicePath. Solo aceptamos un
        # nombre único, para evitar adivinar entre dispositivos indistinguibles.
        matches = [
            d for d in devices
            if d.backend == selected.backend and d.name == selected.name
        ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise RuntimeError(
            "Windows no permite distinguir esta cámara de otra con el mismo "
            "identificador o nombre. Desconecta una de ellas y pulsa «Actualizar cámaras»."
        )
    raise RuntimeError(
        "La cámara seleccionada ya no está disponible. "
        "Comprueba la conexión y pulsa «Actualizar cámaras»."
    )


class CameraDiscoveryWorker(QThread):
    def __init__(self, provider: Callable = list_cameras) -> None:
        super().__init__()
        self._provider = provider
        self.devices: list[CameraDevice] = []
        self.error: str | None = None

    def run(self) -> None:
        try:
            self.devices = self._provider()
        except Exception as exc:
            self.error = (
                f"No se pudo consultar la lista de cámaras: {exc}. "
                "Comprueba los dispositivos y pulsa «Actualizar cámaras»."
            )