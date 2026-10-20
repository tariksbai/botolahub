"""Boîtes de dialogue : fiche de match, grille de codes, test de précision du lecteur."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QDate, QObject, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtMultimedia import QVideoSink
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bph_app.counter_code import make as make_counter_video
from bph_app.player import FramePlayer
from bph_app.seek_check import Report, SeekCheck
from bph_app.store import Match, Store
from bph_engine.video import VideoError, probe

# Touches réservées au lecteur : interdites comme raccourcis de codes.
RESERVED_KEYS = {"SPACE", "LEFT", "RIGHT", "UP", "DOWN", "HOME", "END", "DEL", "DELETE", "J", "K", "L", "I", "O"}


class MatchDialog(QDialog):
    """Saisie des métadonnées d'un match (import et modification)."""

    def __init__(self, store: Store, match: Match | None = None, video_name: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fiche du match" if match else f"Importer — {video_name}")
        form = QFormLayout()
        self.client = QComboBox(editable=True)
        self.client.addItems([""] + store.clients())
        line = self.client.lineEdit()
        if line is not None:
            line.setPlaceholderText("club ou client (analyste indépendant)")
        self.season = QComboBox(editable=True)
        self.season.addItems(store.seasons() or [_current_season()])
        self.competition = QLineEdit(placeholderText="Botola Pro D1, Coupe du Trône…")
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.date.setDate(QDate.currentDate())
        self.home, self.away = QLineEdit(), QLineEdit()
        self.home_score, self.away_score = _score_box(), _score_box()
        scores = QHBoxLayout()
        scores.addWidget(self.home_score)
        scores.addWidget(QLabel("–"))
        scores.addWidget(self.away_score)
        scores.addStretch()
        form.addRow("Client", self.client)
        form.addRow("Saison", self.season)
        form.addRow("Compétition", self.competition)
        form.addRow("Date", self.date)
        form.addRow("Équipe à domicile", self.home)
        form.addRow("Équipe à l'extérieur", self.away)
        form.addRow("Score (optionnel)", scores)
        if match:
            self.client.setCurrentText(match.client)
            self.season.setCurrentText(match.season)
            self.competition.setText(match.competition)
            if match.match_date:
                self.date.setDate(QDate.fromString(match.match_date, "yyyy-MM-dd"))
            self.home.setText(match.home_team)
            self.away.setText(match.away_team)
            self.home_score.setValue(-1 if match.home_score is None else match.home_score)
            self.away_score.setValue(-1 if match.away_score is None else match.away_score)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)
        self.home.setFocus()

    def values(self) -> dict[str, object]:
        def score(box: QSpinBox) -> int | None:
            return None if box.value() < 0 else box.value()

        return {
            "client": self.client.currentText().strip(),
            "season": self.season.currentText().strip(),
            "competition": self.competition.text().strip(),
            "match_date": self.date.date().toString("yyyy-MM-dd"),
            "home_team": self.home.text().strip(),
            "away_team": self.away.text().strip(),
            "home_score": score(self.home_score),
            "away_score": score(self.away_score),
        }


def _score_box() -> QSpinBox:
    box = QSpinBox(minimum=-1, maximum=99, value=-1)
    box.setSpecialValueText("—")
    box.setFixedWidth(60)
    return box


def _current_season() -> str:
    d = QDate.currentDate()
    y = d.year() if d.month() >= 7 else d.year() - 1
    return f"{y}-{y + 1}"


class CodeGridDialog(QDialog):
    """Édition de la grille de codes : libellé, raccourci, couleur, secondes avant / après."""

    HEADERS = ["Libellé", "Raccourci", "Couleur", "Avant (s)", "Après (s)"]

    def __init__(self, store: Store, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Grille de codes")
        self.resize(620, 460)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._pick_color)
        for c in store.codes():
            self._add_row(c.id, c.label, c.shortcut, c.color, c.lead_seconds, c.lag_seconds)
        add = QPushButton("Ajouter un code")
        add.clicked.connect(lambda: self._add_row(None, "Nouveau code", "", "#1f6feb", 5, 5))
        remove = QPushButton("Supprimer")
        remove.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        up, down = QPushButton("Monter"), QPushButton("Descendre")
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        row = QHBoxLayout()
        for b in (add, remove, up, down):
            row.addWidget(b)
        row.addStretch()
        hint = QLabel("Double-cliquez sur une couleur pour la changer. Touches réservées au lecteur : "
                      "Espace, flèches, Début/Fin, Suppr, J, K, L, I, O.")
        hint.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        lay.addLayout(row)
        lay.addWidget(hint)
        lay.addWidget(buttons)

    def _add_row(self, cid: int | None, label: str, key: str, color: str, lead: float, lag: float) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        name = QTableWidgetItem(label)
        name.setData(Qt.ItemDataRole.UserRole, cid)
        self.table.setItem(r, 0, name)
        self.table.setItem(r, 1, QTableWidgetItem(key))
        swatch = QTableWidgetItem(color)
        swatch.setBackground(QColor(color))
        swatch.setFlags(swatch.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(r, 2, swatch)
        for col, val in ((3, lead), (4, lag)):
            spin = QDoubleSpinBox(minimum=0, maximum=120, decimals=1, value=val, suffix=" s")
            self.table.setCellWidget(r, col, spin)

    def _item(self, row: int, col: int) -> QTableWidgetItem:
        item = self.table.item(row, col)
        assert item is not None
        return item

    def _pick_color(self, row: int, col: int) -> None:
        if col != 2:
            return
        item = self._item(row, 2)
        color = QColorDialog.getColor(QColor(item.text()), self, "Couleur du code")
        if color.isValid():
            item.setText(color.name())
            item.setBackground(color)

    def _move(self, delta: int) -> None:
        r = self.table.currentRow()
        target = r + delta
        if r < 0 or not 0 <= target < self.table.rowCount():
            return
        rows = self._rows()
        rows[r], rows[target] = rows[target], rows[r]
        self.table.setRowCount(0)
        for values in rows:
            self._add_row(*values)
        self.table.setCurrentCell(target, 0)

    def _rows(self) -> list[tuple[int | None, str, str, str, float, float]]:
        rows = []
        for r in range(self.table.rowCount()):
            name = self._item(r, 0)
            key_item = self.table.item(r, 1)
            lead = self.table.cellWidget(r, 3)
            lag = self.table.cellWidget(r, 4)
            assert isinstance(lead, QDoubleSpinBox) and isinstance(lag, QDoubleSpinBox)
            rows.append((name.data(Qt.ItemDataRole.UserRole), name.text().strip(),
                         (key_item.text() if key_item else "").strip(), self._item(r, 2).text(),
                         lead.value(), lag.value()))
        return rows

    def _save(self) -> None:
        rows = self._rows()
        for _cid, label, key, *_ in rows:
            if not label:
                QMessageBox.warning(self, "Grille de codes", "Chaque code doit avoir un libellé.")
                return
            seq = QKeySequence(key)
            if key and (seq.count() != 1 or not seq.toString()):
                QMessageBox.warning(self, "Grille de codes", f"Raccourci invalide pour « {label} » : {key}")
                return
            if key.upper() in RESERVED_KEYS:
                QMessageBox.warning(self, "Grille de codes", f"La touche {key} est réservée au lecteur.")
                return
        try:
            self.store.save_codes(rows)
        except ValueError as e:
            QMessageBox.warning(self, "Grille de codes", str(e).capitalize() + ".")
            return
        self.accept()


class _Bridge(QObject):
    progress = Signal(float)
    done = Signal(str)   # chemin produit, ou "" en cas d'échec
    error = Signal(str)


class SeekCheckDialog(QDialog):
    """Test de précision du lecteur (critère du jalon J1), lancé depuis l'application."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Test de précision du lecteur (jalon J1)")
        self.resize(560, 360)
        self.status = QLabel(
            "Le test fabrique une vidéo de 5 minutes dont chaque image porte son numéro, "
            "effectue 500 sauts aléatoires et 100 pas image par image, et vérifie qu'à chaque "
            "fois le numéro affiché par le logiciel est exactement celui de l'image."
        )
        self.status.setWordWrap(True)
        self.bar = QProgressBar()
        self.log = QPlainTextEdit(readOnly=True)
        self.start_btn = QPushButton("Lancer le test")
        self.start_btn.clicked.connect(self._generate)
        close = QPushButton("Fermer")
        close.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.start_btn)
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(self.status)
        lay.addWidget(self.bar)
        lay.addWidget(self.log)
        lay.addLayout(row)
        self._bridge = _Bridge(self)
        self._bridge.progress.connect(lambda p: self.bar.setValue(int(p * 100)))
        self._bridge.done.connect(self._run)
        self._bridge.error.connect(self._fail)
        self._tmp = tempfile.TemporaryDirectory(prefix="bph-j1-")
        self.player: FramePlayer | None = None
        self.check: SeekCheck | None = None

    def _generate(self) -> None:
        self.start_btn.setEnabled(False)
        self.log.appendPlainText("Fabrication de la vidéo à compteur…")
        path = str(Path(self._tmp.name) / "compteur.mp4")

        def work() -> None:
            try:
                make_counter_video(path, on_progress=self._bridge.progress.emit)
                self._bridge.done.emit(path)
            except (VideoError, OSError) as e:
                self._bridge.error.emit(str(e))

        threading.Thread(target=work, daemon=True).start()

    def _fail(self, message: str) -> None:
        self.log.appendPlainText(f"ÉCHEC — {message}")
        self.start_btn.setEnabled(True)

    def _run(self, path: str) -> None:
        try:
            info = probe(path)
        except VideoError as e:
            self._fail(str(e))
            return
        self.log.appendPlainText("Sauts en cours…")
        self.bar.setValue(0)
        self.player = FramePlayer(self)
        self._sink = QVideoSink(self)
        self.player.set_sink(self._sink)

        def loaded() -> None:
            assert self.player is not None
            self.check = SeekCheck(self.player, parent=self)
            self.check.progress.connect(lambda i, n: self.bar.setValue(int(i * 100 / n)))
            self.check.finished.connect(self._report)
            self.check.start()

        self.player.loaded.connect(loaded)
        self.player.failed.connect(self._fail)
        self.player.load(path, info.fps_float, info.frame_count)

    def _report(self, report: Report) -> None:
        self.log.appendPlainText(report.summary())
        self.status.setText("<b>Test réussi.</b>" if report.passed else "<b>Test échoué.</b>")
        self.start_btn.setEnabled(True)

    def reject(self) -> None:
        if self.check is not None:
            self.check.cancel()
        if self.player is not None:
            self.player.player.stop()
        super().reject()
