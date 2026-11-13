"""Descarga explícita del modelo fijado. La aplicación no usa la red."""

import hashlib
from pathlib import Path
import sys
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lockin.model import MODEL_PATH, MODEL_SHA256, MODEL_URL


def main() -> int:
    if MODEL_PATH.exists():
        if hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() == MODEL_SHA256:
            print("El modelo verificado ya está disponible.")
            return 0
        print("El archivo existente no coincide. Revisa models/README.md; no se sobrescribe.")
        return 1
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MODEL_PATH.with_suffix(".task.download")
    created = False
    try:
        with urlopen(MODEL_URL, timeout=30) as source:
            with temporary.open("xb") as target:
                created = True
                while data := source.read(65536):
                    target.write(data)
        data = temporary.read_bytes()
        if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
            raise RuntimeError("La descarga no coincide con el SHA-256 verificado.")
        temporary.replace(MODEL_PATH)
        print("Modelo de rostro descargado y verificado.")
        return 0
    except Exception as exc:
        print(f"No se pudo descargar el modelo: {exc}")
        return 1
    finally:
        if created:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())