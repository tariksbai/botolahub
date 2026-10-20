"""Fenêtre principale : bibliothèque de matchs et espace de travail (P02)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStackedWidget

from bph_app import __version__
from bph_app.dialogs import CodeGridDialog, SeekCheckDialog
from bph_app.library import LibraryPage
from bph_app.store import Store
from bph_app.workspace import WorkspacePage
from bph_engine.video import SUPPORTED_EXTENSIONS

APP_NAME = "Bottola Analyse"
KeySpec = str | QKeySequence | QKeySequence.StandardKey


class MainWindow(QMainWindow):
    def __init__(self, store: Store, media_dir: Path) -> None:
        super().__init__()
        self.store = store
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 880)
        self.setAcceptDrops(True)

        self.library = LibraryPage(store, media_dir)
        self.workspace = WorkspacePage(store)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.library)
        self.pages.addWidget(self.workspace)
        self.setCentralWidget(self.pages)

        self.library.openRequested.connect(self.open_match)
        self.workspace.backRequested.connect(self.show_library)
        self.workspace.editCodesRequested.connect(self.edit_codes)
        self._build_menus()
        self.statusBar().showMessage("Traitement intégralement local : aucune vidéo ne quitte cet ordinateur.")

    def _action(self, menu_name: str, text: str, slot: object, shortcut: KeySpec | None = None) -> QAction:
        menu = self._menus[menu_name]
        act = QAction(text, self)
        if shortcut is not None:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(slot)
        menu.addAction(act)
        return act

    def _build_menus(self) -> None:
        bar = self.menuBar()
        self._menus = {name: bar.addMenu(name) for name in ("&Fichier", "&Tagging", "&Outils", "&Aide")}
        self._action("&Fichier", "Importer une vidéo…", lambda: self.library.import_video(), "Ctrl+I")
        self._action("&Fichier", "Bibliothèque", self.show_library, "Ctrl+B")
        self._menus["&Fichier"].addSeparator()
        self._action("&Fichier", "Quitter", self.close, QKeySequence.StandardKey.Quit)
        self._action("&Tagging", "Modifier la grille de codes…", self.edit_codes, "Ctrl+G")
        self._action("&Tagging", "Rétablir la grille par défaut", self.reset_codes)
        self._action("&Outils", "Test de précision du lecteur (J1)…", lambda: SeekCheckDialog(self).exec())
        self._action("&Aide", "Raccourcis clavier", self.show_shortcuts, "F1")
        self._action("&Aide", f"À propos de {APP_NAME}", self.about)

    # --- navigation ------------------------------------------------------------------
    def open_match(self, match_id: int) -> None:
        try:
            match = self.store.match(match_id)
        except KeyError:
            return
        if not Path(match.video_path).is_file():
            QMessageBox.warning(self, "Vidéo introuvable",
                                f"Le fichier vidéo de ce match est introuvable :\n{match.video_path}")
            return
        self.workspace.open_match(match)
        self.pages.setCurrentWidget(self.workspace)
        self.setWindowTitle(f"{match.title} — {APP_NAME}")
        self.workspace.setFocus()

    def show_library(self) -> None:
        self.workspace.close_match()
        self.library.refresh()
        self.pages.setCurrentWidget(self.library)
        self.setWindowTitle(APP_NAME)

    def edit_codes(self) -> None:
        if CodeGridDialog(self.store, self).exec():
            self.workspace.reload_codes()

    def reset_codes(self) -> None:
        answer = QMessageBox.question(self, "Grille de codes",
                                      "Remplacer la grille actuelle par la grille par défaut ?")
        if answer == QMessageBox.StandardButton.Yes:
            self.store.reset_codes()
            self.workspace.reload_codes()

    def show_shortcuts(self) -> None:
        from bph_app import workspace

        doc = (workspace.__doc__ or "").split("Clavier (aucune souris nécessaire) :", 1)[-1]
        box = QMessageBox(self)
        box.setWindowTitle("Raccourcis clavier")
        box.setText("<pre>" + doc.strip("\n") + "</pre>")
        box.exec()

    def about(self) -> None:
        QMessageBox.about(
            self, APP_NAME,
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Analyse vidéo football. Traitement intégralement local : "
            "aucune vidéo ne quitte cet ordinateur.</p>")

    # --- glisser-déposer d'une vidéo -----------------------------------------------------
    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        urls = e.mimeData().urls()
        if urls and urls[0].isLocalFile() and urls[0].toLocalFile().lower().endswith(SUPPORTED_EXTENSIONS):
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        path = e.mimeData().urls()[0].toLocalFile()
        self.show_library()
        self.library.import_video(path)

    def closeEvent(self, e: QCloseEvent) -> None:
        self.workspace.close_match()
        e.accept()
