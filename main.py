"""Punto de entrada de LockIn."""

import sys
import argparse
from pathlib import Path

from PySide6.QtWidgets import QApplication

from lockin.window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="LockIn")
    parser.add_argument("--self-test", action="store_true", help="Diagnóstico sintético sin cámara ni micrófono")
    parser.add_argument("--report", type=Path, help="Archivo JSON de resultados del diagnóstico")
    parser.add_argument("--test-video", type=Path, help="Clip sintético opcional para probar el reproductor")
    options, qt_options = parser.parse_known_args()
    if options.self_test and options.report is None:
        parser.error("--self-test necesita --report con una ruta de archivo")
    app = QApplication([sys.argv[0], *qt_options])
    app.setApplicationName("LockIn")
    if options.self_test:
        from lockin.self_test import run
        return run(app, options.report, options.test_video)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
