"""Prepara icono, versión y avisos de terceros sin descargar ni abrir cámaras."""
from importlib import metadata
from pathlib import Path
import re
import shutil
import sys

from PIL import Image
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from lockin.model import read_model
    read_model()  # El build se rechaza si falta el modelo o está dañado.
    version = (ROOT / "packaging/version.txt").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("packaging/version.txt debe tener formato mayor.menor.parche.")
    app = QApplication.instance() or QApplication(["LockIn build", "-platform", "offscreen"])
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QSvgRenderer(str(ROOT / "lockin/assets/lockin-mark.svg")).render(painter, QRectF(8, 30, 240, 196))
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("No se pudo generar el icono.")
    import io
    Image.open(io.BytesIO(bytes(data))).save(
        ROOT / "packaging/LockIn.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    prepared = ROOT / "build/metadata"
    licenses = prepared / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "packaging/licenses").glob("*"):
        if source.is_file():
            shutil.copyfile(source, licenses / source.name)
    inventory = []
    requirement_lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    for line in requirement_lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name = line.split("==")[0]
        dist = metadata.distribution(name)
        inventory.append(f"{dist.metadata['Name']} {dist.version}\n{dist.metadata.get('Home-page', '')}\n")
        for entry in dist.files or ():
            lower = str(entry).lower()
            if ".dist-info/" not in lower or not any(word in lower for word in ("license", "copying", "notice", "copyright")):
                continue
            source = Path(dist.locate_file(entry))
            if source.is_file():
                relative = Path(*entry.parts[1:])
                dest = licenses / name / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
    # El entorno embebido puede omitir el texto; se exige una copia de CPython.
    python_license = next((p for p in (
        Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE",
        ROOT / "packaging/licenses/Python-LICENSE.txt",
    ) if p.is_file()), None)
    if python_license is None:
        raise RuntimeError("Falta el aviso de CPython: packaging/licenses/Python-LICENSE.txt.")
    shutil.copyfile(python_license, licenses / "Python-LICENSE.txt")
    (licenses / "DEPENDENCIES.txt").write_text("\n".join(inventory), encoding="utf-8")
    shutil.copyfile(ROOT / "models/README.md", licenses / "MODELO.md")
    parts = tuple(map(int, version.split("."))) + (0,)
    (prepared / "version_info.txt").write_text(f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={parts!r}, prodvers={parts!r}, mask=0x3f,
                   flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', 'LockIn'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('InternalName', 'LockIn'),
    StringStruct('OriginalFilename', 'LockIn.exe'),
    StringStruct('ProductName', 'LockIn'),
    StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
''', encoding="utf-8")
    print(f"Recursos de LockIn {version} preparados; modelo verificado.")


if __name__ == "__main__":
    main()
