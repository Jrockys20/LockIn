# -*- mode: python ; coding: utf-8 -*-
"""Distribución Windows x64 con recursos locales y DLL reemplazables."""
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH).parent
prepared = root / "build" / "metadata"

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=collect_dynamic_libs("mediapipe"),
    datas=[
        (str(root / "lockin" / "assets"), "lockin/assets"),
        (str(root / "models" / "face_landmarker.task"), "models"),
        (str(prepared / "licenses"), "licenses"),
    ] + collect_data_files("mediapipe"),
    hiddenimports=["mediapipe.tasks.c"],
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": ["Agg"]}},
    runtime_hooks=[],
    excludes=["pytest", "tkinter", "IPython", "PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="LockIn",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / "packaging" / "LockIn.ico"),
    version=str(prepared / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LockIn")
