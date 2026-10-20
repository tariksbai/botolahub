"""Point d'entrée de l'application : python -m bph_app"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QStandardPaths, Qt, QTimer, QTranslator
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from bph_app import theme
from bph_app.main_window import APP_NAME, MainWindow
from bph_app.store import Store


def apply_theme(app: QApplication) -> None:
    """Thème unique clair (Architecture technique §1.2) et boutons standard en français."""
    app.setStyle("Fusion")
    app.setPalette(theme.palette())
    font = QFont(app.font())
    font.setPointSizeF(max(font.pointSizeF(), 10.0))
    app.setFont(font)
    app.setStyleSheet(theme.stylesheet())
    install_french(app)


def install_french(app: QApplication) -> None:
    """Boutons standard de Qt en français (Enregistrer, Annuler…)."""
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    translator = QTranslator(app)
    if translator.load(QLocale(QLocale.Language.French), "qtbase", "_", path):
        app.installTranslator(translator)


def data_dir() -> Path:
    override = os.environ.get("BPH_DATA_DIR")
    if override:
        return Path(override)
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Bottola Performance Hub")
    apply_theme(app)
    root = data_dir()
    store = Store(root / "bibliotheque.sqlite")
    window = MainWindow(store, root / "videos")
    window.show()
    smoke = os.environ.get("BPH_SMOKE_QUIT_MS")   # contrôle de démarrage de l'exécutable en CI
    if smoke:
        QTimer.singleShot(int(smoke), app.quit)
    code = app.exec()
    store.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
