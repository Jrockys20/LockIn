"""Diagnóstico explícito del paquete con datos sintéticos; nunca abre la cámara."""
from pathlib import Path
import json
import sys
import time
import traceback


def run(app, report_path: Path, video_path: Path | None = None) -> int:
    """Escribe solo resultados técnicos en la ruta solicitada por el operador."""
    result = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)), "checks": []}
    window = detector = playback = None
    app.setQuitOnLastWindowClosed(False)

    def wait_until(predicate, seconds=15):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() >= deadline:
                raise TimeoutError("El diagnóstico agotó su espera.")
            app.processEvents()
            time.sleep(.01)

    try:
        import numpy as np
        from PySide6.QtCore import QSize
        from PySide6.QtMultimedia import QAudioBufferOutput, QMediaPlayer
        from lockin.face import FaceLandmarkerDetector
        from lockin.model import read_model
        from lockin.navigation import ui_icon
        from lockin.video import PlaybackWindow
        from lockin.window import MainWindow

        read_model()
        result["checks"].append("modelo_sha256")
        for icon in ("session", "calibrate", "bell", "shield", "refresh", "lockin-mark"):
            if ui_icon(icon).pixmap(QSize(24, 24)).isNull():
                raise RuntimeError("Falta un icono: " + icon)
        result["checks"].append("iconos_svg")
        detector = FaceLandmarkerDetector()
        if detector.process(np.zeros((240, 320, 3), dtype=np.uint8), 0).count != 0:
            raise RuntimeError("La imagen sintética no devolvió el resultado esperado.")
        detector.close()
        detector = None
        result["checks"].append("mediapipe_dll_inferencia_sintetica")

        def forbidden_camera(*args):
            raise AssertionError("El diagnóstico no permite abrir cámaras.")

        window = MainWindow(worker_factory=forbidden_camera, device_provider=lambda: [])
        window.show()
        wait_until(lambda: window._discovery is None)
        for index in (0, 1, 2, 0):
            window.nav.setCurrentIndex(index)
            app.processEvents()
            if window.pages.currentIndex() != index:
                raise RuntimeError("La navegación no refleja la vista seleccionada.")
        if window._worker is not None or window.alert_panel.enabled.isChecked():
            raise RuntimeError("El inicio debe conservar cámara y alertas desactivadas.")
        result["checks"].append("tres_vistas_camara_alertas_apagadas")
        if video_path is not None:
            frames, buffers = [], []
            playback = PlaybackWindow()
            audio = QAudioBufferOutput(playback)
            playback.player.setAudioBufferOutput(audio)
            audio.audioBufferReceived.connect(lambda b: buffers.append(True) if b.isValid() else None)
            playback.video_widget.videoSink().videoFrameChanged.connect(
                lambda f: frames.append(True) if f.isValid() else None
            )
            playback.start_video(video_path, muted=True, fullscreen=True, repeat=True)
            wait_until(lambda: bool(frames and buffers) or playback._closing)
            if not frames or not buffers or playback._closing:
                raise RuntimeError("No se decodificaron video y audio: " + playback._result)
            if not playback.isFullScreen() or playback.player.loops() != QMediaPlayer.Loops.Infinite:
                raise RuntimeError("No se aplicó la reproducción automática.")
            playback.escape_shortcut.activated.emit()
            app.processEvents()
            if not playback.player.source().isEmpty() or playback.isVisible():
                raise RuntimeError("El cierre no liberó el reproductor.")
            result["checks"].append("qt_video_audio_decodificados_silenciados_fullscreen_bucle_cierre")
        result["ok"] = True
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        if detector is not None:
            detector.close()
        if playback is not None:
            playback.close()
        if window is not None:
            window.close()
            wait_until(lambda: window._discovery is None and window._worker is None)
        app.processEvents()
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
