# Empaquetage PyInstaller de Bottola Analyse (dossier autonome, sans Python à installer).
#
#     pyinstaller packaging/bottola.spec --noconfirm
#
# Résultat : dist/BottolaAnalyse/ avec BottolaAnalyse(.exe). Le même exécutable sert de
# moteur (`BottolaAnalyse --engine …`). FFmpeg et ffprobe sont copiés dans
# dist/BottolaAnalyse/ffmpeg/ par le workflow de packaging.
# ruff: noqa
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent  # noqa: F821 (fourni par PyInstaller)

# Traductions françaises des boutons standard de Qt (Enregistrer, Annuler…).
qt_translations = [
    (src, dest) for src, dest in collect_data_files("PySide6", includes=["Qt/translations/qtbase_fr.qm",
                                                                          "translations/qtbase_fr.qm"])
]

a = Analysis(  # noqa: F821
    [str(ROOT / "src" / "bph_app" / "launch.py")],
    pathex=[str(ROOT / "src")],
    datas=qt_translations,
    hiddenimports=["bph_engine.cli", "bph_app.__main__", "PySide6.QtSvg", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization",
              "torch", "ultralytics"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BottolaAnalyse",
    console=False,          # application fenêtrée : aucune console à l'ouverture
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="BottolaAnalyse", upx=False)  # noqa: F821
