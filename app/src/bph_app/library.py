"""Page Bibliothèque : matchs classés par date, filtrables par client, saison et texte (P02).

L'import (P03) inspecte la vidéo ; si elle n'est pas directement lisible à l'image près,
le moteur la normalise dans un processus séparé et la copie normalisée rejoint la
bibliothèque. Un fichier déjà conforme est référencé sans copie.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bph_app.dialogs import MatchDialog
from bph_app.engine_runner import EngineJob
from bph_app.store import Store
from bph_engine.video import SUPPORTED_EXTENSIONS, VideoError, VideoInfo, probe

COLUMNS = ["Date", "Domicile", "Extérieur", "Score", "Compétition", "Saison", "Client", "Durée"]


class LibraryPage(QWidget):
    openRequested = Signal(int)

    def __init__(self, store: Store, media_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store, self.media_dir = store, media_dir
        self.search = QLineEdit(placeholderText="Rechercher une équipe ou une compétition…", clearButtonEnabled=True)
        self.client = QComboBox()
        self.season = QComboBox()
        for w in (self.search,):
            w.textChanged.connect(self.refresh)
        for c in (self.client, self.season):
            c.currentIndexChanged.connect(self.refresh)
        import_btn = QPushButton("Importer une vidéo…")
        import_btn.setDefault(True)
        import_btn.clicked.connect(self.import_video)
        self.open_btn = QPushButton("Ouvrir")
        self.open_btn.clicked.connect(self._open_selected)
        self.edit_btn = QPushButton("Modifier la fiche")
        self.edit_btn.clicked.connect(self._edit_selected)
        self.delete_btn = QPushButton("Retirer")
        self.delete_btn.clicked.connect(self._delete_selected)

        filters = QHBoxLayout()
        filters.addWidget(self.search, 3)
        filters.addWidget(QLabel("Client"))
        filters.addWidget(self.client, 1)
        filters.addWidget(QLabel("Saison"))
        filters.addWidget(self.season, 1)
        filters.addWidget(import_btn)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _i: self._open_selected())
        self.table.itemSelectionChanged.connect(self._sync_buttons)

        self.empty = QLabel(
            "<h2>Aucun match dans la bibliothèque</h2>"
            "<p>Importez la vidéo d'un match (MP4, MKV, AVI, MOV) pour commencer.<br>"
            "La vidéo reste sur cet ordinateur.</p>"
        )
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack = QStackedLayout()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)

        actions = QHBoxLayout()
        actions.addStretch()
        for b in (self.open_btn, self.edit_btn, self.delete_btn):
            actions.addWidget(b)

        title = QLabel("<h1>Bibliothèque de matchs</h1>")
        lay = QVBoxLayout(self)
        lay.addWidget(title)
        lay.addLayout(filters)
        lay.addLayout(self.stack, 1)
        lay.addLayout(actions)
        self._reload_filters()
        self.refresh()

    # --- liste -------------------------------------------------------------------
    def _reload_filters(self) -> None:
        for combo, values, label in ((self.client, self.store.clients(), "Tous"),
                                     (self.season, self.store.seasons(), "Toutes")):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(label, "")
            for v in values:
                combo.addItem(v, v)
            idx = combo.findData(current)
            combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)

    def refresh(self) -> None:
        matches = self.store.matches(self.search.text().strip(), self.client.currentData() or "",
                                     self.season.currentData() or "")
        self.table.setRowCount(len(matches))
        for r, m in enumerate(matches):
            score = "" if m.home_score is None or m.away_score is None else f"{m.home_score} – {m.away_score}"
            minutes = round(m.frame_count / m.fps / 60)
            date = "/".join(reversed(m.match_date.split("-"))) if m.match_date else ""
            for c, text in enumerate([date, m.home_team, m.away_team, score, m.competition, m.season,
                                      m.client, f"{minutes} min"]):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, m.id)
                self.table.setItem(r, c, item)
        has_any = bool(self.store.matches())
        self.stack.setCurrentWidget(self.table if has_any else self.empty)
        self._sync_buttons()

    def _selected_id(self) -> int | None:
        items = self.table.selectedItems()
        return int(items[0].data(Qt.ItemDataRole.UserRole)) if items else None

    def _sync_buttons(self) -> None:
        enabled = self._selected_id() is not None
        for b in (self.open_btn, self.edit_btn, self.delete_btn):
            b.setEnabled(enabled)

    def _open_selected(self) -> None:
        mid = self._selected_id()
        if mid is not None:
            self.openRequested.emit(mid)

    def _edit_selected(self) -> None:
        mid = self._selected_id()
        if mid is None:
            return
        dlg = MatchDialog(self.store, self.store.match(mid), parent=self)
        if dlg.exec():
            self.store.update_match(mid, **dlg.values())
            self._reload_filters()
            self.refresh()

    def _delete_selected(self) -> None:
        mid = self._selected_id()
        if mid is None:
            return
        m = self.store.match(mid)
        answer = QMessageBox.question(
            self, "Retirer le match",
            f"Retirer « {m.title} » de la bibliothèque, avec ses tags ?\n"
            "Le fichier vidéo d'origine n'est pas supprimé.")
        if answer == QMessageBox.StandardButton.Yes:
            self.store.delete_match(mid)
            self._reload_filters()
            self.refresh()

    # --- import ------------------------------------------------------------------
    def import_video(self, path: str | None = None) -> None:
        if not path:
            patterns = " ".join(f"*{e}" for e in SUPPORTED_EXTENSIONS)
            path, _ = QFileDialog.getOpenFileName(self, "Importer la vidéo d'un match", "",
                                                  f"Vidéos ({patterns});;Tous les fichiers (*)")
            if not path:
                return
        try:
            info = probe(path)
        except VideoError as e:
            QMessageBox.warning(self, "Import impossible", str(e))
            return
        dlg = MatchDialog(self.store, video_name=Path(path).name, parent=self)
        if not dlg.exec():
            return
        meta = dlg.values()
        if not info.needs_normalization():
            self._register(info, path, meta)
            return
        target = self.media_dir / f"{uuid.uuid4().hex}.mp4"
        progress = QProgressDialog("Préparation de la vidéo pour la lecture image par image…", "Annuler",
                                   0, 100, self)
        progress.setWindowTitle("Import")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        job = EngineJob("normalize", path, str(target), parent=self)
        job.progress.connect(lambda p: progress.setValue(int(p * 100)))
        progress.canceled.connect(job.cancel)

        def finished(ok: bool, message: str) -> None:
            progress.close()
            job.deleteLater()
            if not ok:
                target.unlink(missing_ok=True)
                if message != "opération annulée":
                    QMessageBox.warning(self, "Import impossible", message)
                return
            try:
                self._register(probe(target), path, meta)
            except VideoError as e:
                QMessageBox.warning(self, "Import impossible", str(e))

        job.finished.connect(finished)
        job.start()

    def _register(self, info: VideoInfo, source: str, meta: dict[str, object]) -> None:
        mid = self.store.add_match(
            video_path=info.path, source_path=source, fps_num=info.fps.numerator, fps_den=info.fps.denominator,
            frame_count=info.frame_count, width=info.width, height=info.height, **meta,  # type: ignore[arg-type]
        )
        self._reload_filters()
        self.refresh()
        self.openRequested.emit(mid)
