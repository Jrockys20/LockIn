"""Modelo de MediaPipe fijado; no realiza descargas al ejecutar la aplicación."""

import hashlib
from pathlib import Path
import sys

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "face_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"


def read_model(path: Path = MODEL_PATH) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exc:
        if getattr(sys, "frozen", False):
            raise RuntimeError("Falta el modelo local o no se puede leer. Reinstala LockIn para restaurarlo.") from exc
        raise RuntimeError(
            "Falta el modelo local o no se puede leer. Ejecuta "
            r".\.venv\Scripts\python.exe scripts\download_model.py"
        ) from exc
    if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
        if getattr(sys, "frozen", False):
            raise RuntimeError("El modelo local está dañado. Reinstala LockIn para restaurarlo.")
        raise RuntimeError(
            "El modelo local no coincide con la versión verificada. "
            "Revisa models/README.md para restaurarlo."
        )
    return data
