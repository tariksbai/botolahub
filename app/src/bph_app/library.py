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
    QFrame,
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

from bph_app import theme
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
        self.search.addAction(theme.icon("search", theme.MUTED, size=16), QLineEdit.ActionPosition.LeadingPosition)
        self.client = QComboBox()
        self.season = QComboBox()
        self.client.setMinimumWidth(200)
        self.season.setMinimumWidth(140)
        self.search.textChanged.connect(self.refresh)
        for c in (self.client, self.season):
            c.currentIndexChanged.connect(self.refresh)

        import_btn = theme.decorate(QPushButton("Importer une vidéo"), "import", "primary")
        import_btn.clicked.connect(lambda: self.import_video())
        self.open_btn = theme.decorate(QPushButton("Ouvrir"), "open", "primary")
        self.open_btn.clicked.connect(self._open_selected)
        self.edit_btn = theme.decorate(QPushButton("Modifier la fiche"), "edit", "ghost")
        self.edit_btn.clicked.connect(self._edit_selected)
        self.delete_btn = theme.decorate(QPushButton("Retirer"), "trash", "danger")
        self.delete_btn.clicked.connect(self._delete_selected)
        for b in (import_btn, self.open_btn, self.edit_btn, self.delete_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        # en-tête : titre, nombre de matchs, action principale
        self.count = theme.style(QLabel(), role="badge")
        title = theme.style(QLabel("Bibliothèque de matchs"), role="title")
        subtitle = theme.style(QLabel("Vos matchs, classés par date. Double-cliquez pour analyser."),
                               role="subtitle")
        heading = QVBoxLayout()
        heading.setSpacing(2)
        row = QHBoxLayout()
        row.addWidget(title)
        row.addWidget(self.count, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch()
        heading.addLayout(row)
        heading.addWidget(subtitle)
        header = QHBoxLayout()
        header.addLayout(heading, 1)
        header.addWidget(import_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        filters = QHBoxLayout()
        filters.setSpacing(10)
        filters.addWidget(self.search, 3)
        filters.addWidget(theme.style(QLabel("Client"), role="section"))
        filters.addWidget(self.client, 1)
        filters.addWidget(theme.style(QLabel("Saison"), role="section"))
        filters.addWidget(self.season, 1)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _i: self._open_selected())
        self.table.itemSelectionChanged.connect(self._sync_buttons)

        self.empty = self._empty_state()
        self.stack = QStackedLayout()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)

        self.actions_bar = QHBoxLayout()
        self.actions_bar.addStretch()
        for b in (self.delete_btn, self.edit_btn, self.open_btn):
            self.actions_bar.addWidget(b)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 26, 32, 22)
        lay.setSpacing(16)
        lay.addLayout(header)
        lay.addLayout(filters)
        lay.addLayout(self.stack, 1)
        lay.addLayout(self.actions_bar)
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
        total = len(self.store.matches())
        self.count.setText(f"{total} match" + ("s" if total > 1 else ""))
        self.count.setVisible(total > 0)
        self.stack.setCurrentWidget(self.table if total else self.empty)
        for b in (self.open_btn, self.edit_btn, self.delete_btn):
            b.setVisible(total > 0)
        self._sync_buttons()

    def _empty_state(self) -> QWidget:
        box = theme.named(QFrame(), "card")
        v = QVBoxLayout(box)
        v.addStretch()
        badge = theme.style(QLabel(), role="emptyIcon")
        badge.setFixedSize(72, 72)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(theme.pixmap("film", theme.ACCENT, 34))
        title = QLabel("Aucun match pour l'instant")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        text = theme.style(QLabel("Importez la vidéo d'un match — MP4, MKV, AVI ou MOV — ou glissez-la dans "
                                  "la fenêtre.\nLa vidéo reste sur cet ordinateur."), role="subtitle")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cta = theme.decorate(QPushButton("Importer une vidéo"), "import", "primary")
        cta.setCursor(Qt.CursorShape.PointingHandCursor)
        cta.clicked.connect(lambda: self.import_video())
        for w in (badge, title, text, cta):
            v.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)
            v.addSpacing(6)
        v.addStretch()
        return box

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
