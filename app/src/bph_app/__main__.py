"""Point d'entrée de l'application : python -m bph_app"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QStandardPaths, Qt, QTranslator
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from bph_app.main_window import APP_NAME, MainWindow
from bph_app.store import Store


def light_palette() -> QPalette:
    """Thème unique clair (Architecture technique §1.2)."""
    p = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#f6f8fa",
        QPalette.ColorRole.WindowText: "#1f2328",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#eef1f4",
        QPalette.ColorRole.Text: "#1f2328",
        QPalette.ColorRole.Button: "#ffffff",
        QPalette.ColorRole.ButtonText: "#1f2328",
        QPalette.ColorRole.Highlight: "#0b6e4f",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.Mid: "#9aa4ae",
        QPalette.ColorRole.ToolTipBase: "#1f2328",
        QPalette.ColorRole.ToolTipText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#6e7781",
    }
    for role, value in colors.items():
        p.setColor(role, QColor(value))
    # état désactivé lisible : sans cela, un bouton inactif ressemble à un bouton actif
    disabled = QPalette.ColorGroup.Disabled
    for role in (QPalette.ColorRole.ButtonText, QPalette.ColorRole.Text, QPalette.ColorRole.WindowText):
        p.setColor(disabled, role, QColor("#a0a8b0"))
    p.setColor(disabled, QPalette.ColorRole.Button, QColor("#eef1f4"))
    return p


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
    app.setStyle("Fusion")
    install_french(app)
    app.setPalette(light_palette())
    root = data_dir()
    store = Store(root / "bibliotheque.sqlite")
    window = MainWindow(store, root / "videos")
    window.show()
    code = app.exec()
    store.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
