"""Espace de travail d'un match : lecteur, timeline, grille de codes et tags (P04, P06).

Clavier (aucune souris nécessaire) :
    Espace          lecture / pause          K             pause
    ← / →           image précédente/suivante L            lecture, puis ×2, ×4
    Maj + ← / →     ± 1 seconde              J             recul de 5 secondes
    Ctrl + ← / →    ± 10 secondes            Début / Fin   début / fin du match
    I / O           début / fin du tag sélectionné à la position courante
    Suppr           supprimer le tag sélectionné
    touches de la grille : créer un tag à l'image courante
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QHideEvent, QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from bph_app.player import FramePlayer, VideoView
from bph_app.store import Code, Match, Store, Tag, timecode
from bph_app.timeline import Marker, Timeline

RATES = (0.25, 0.5, 1.0, 1.5, 2.0, 4.0)
KeySpec = str | QKeySequence | QKeySequence.StandardKey


class CodeGrid(QWidget):
    tagRequested = Signal(object)   # Code

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setSpacing(4)
        self.grid.setContentsMargins(0, 0, 0, 0)

    def set_codes(self, codes: list[Code]) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        for i, code in enumerate(codes):
            b = QPushButton(f"{code.label}" + (f"   [{code.shortcut}]" if code.shortcut else ""))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setMinimumHeight(34)
            text = "#ffffff" if QColor(code.color).lightness() < 150 else "#000000"
            b.setStyleSheet(f"QPushButton {{ background: {code.color}; color: {text}; border: none;"
                            f" border-radius: 4px; font-weight: 600; text-align: left; padding: 0 8px; }}"
                            f"QPushButton:pressed {{ border: 2px solid #000; }}")
            b.clicked.connect(lambda _=False, c=code: self.tagRequested.emit(c))
            self.grid.addWidget(b, i // 2, i % 2)


class WorkspacePage(QWidget):
    backRequested = Signal()
    editCodesRequested = Signal()

    def __init__(self, store: Store, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.match: Match | None = None
        self.tags: list[Tag] = []
        self._code_shortcuts: list[QShortcut] = []
        self._all_shortcuts: list[QShortcut] = []

        self.view = VideoView()
        self.player = FramePlayer(self)
        self.player.set_sink(self.view.sink())
        self.player.frameChanged.connect(self._on_frame)
        self.player.playingChanged.connect(self._on_playing)
        self.player.failed.connect(lambda msg: QMessageBox.warning(self, "Lecture impossible", msg))

        # barre de transport
        def tool(text: str, tip: str, slot: object) -> QToolButton:
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(slot)
            return b

        self.play_btn = tool("▶", "Lecture / pause (Espace)", self.player.toggle)
        self.play_btn.setMinimumWidth(48)
        self.pos_label = QLabel()
        self.pos_label.setStyleSheet("font-family: monospace; font-size: 15px;")
        self.rate = QComboBox()
        self.rate.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for r in RATES:
            self.rate.addItem(f"×{r:g}", r)
        self.rate.setCurrentIndex(RATES.index(1.0))
        self.rate.currentIndexChanged.connect(lambda _i: self.player.set_rate(self.rate.currentData()))
        back = tool("← Bibliothèque", "Revenir à la bibliothèque", self.backRequested.emit)
        transport = QHBoxLayout()
        transport.addWidget(back)
        transport.addStretch()
        for b in (
            tool("⏮", "Début (Début)", lambda: self.player.seek(0)),
            tool("−1 s", "Une seconde en arrière (Maj+←)", lambda: self.player.step_seconds(-1)),
            tool("◀|", "Image précédente (←)", lambda: self.player.step(-1)),
            self.play_btn,
            tool("|▶", "Image suivante (→)", lambda: self.player.step(1)),
            tool("+1 s", "Une seconde en avant (Maj+→)", lambda: self.player.step_seconds(1)),
        ):
            transport.addWidget(b)
        transport.addSpacing(12)
        transport.addWidget(self.pos_label)
        transport.addStretch()
        transport.addWidget(QLabel("Vitesse"))
        transport.addWidget(self.rate)

        self.timeline = Timeline()
        self.timeline.seekRequested.connect(self.player.seek)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 16px; font-weight: 600;")

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.title)
        lv.addWidget(self.view, 1)
        lv.addLayout(transport)
        lv.addWidget(self.timeline)

        # panneau de tagging
        self.codes = CodeGrid()
        self.codes.tagRequested.connect(self.add_tag)
        edit_codes = QPushButton("Modifier la grille…")
        edit_codes.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        edit_codes.clicked.connect(self.editCodesRequested.emit)
        self.tag_table = QTableWidget(0, 4)
        self.tag_table.setHorizontalHeaderLabels(["Image", "Code", "Durée", "Note"])
        self.tag_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tag_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tag_table.verticalHeader().hide()
        self.tag_table.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.tag_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tag_table.cellDoubleClicked.connect(self._jump_to_row)
        self.tag_table.itemChanged.connect(self._note_edited)
        self.tag_table.itemSelectionChanged.connect(self._refresh_markers)
        self.tag_count = QLabel()

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(QLabel("<b>Grille de codes</b>"))
        head.addStretch()
        head.addWidget(edit_codes)
        rv.addLayout(head)
        rv.addWidget(self.codes)
        rv.addSpacing(8)
        rv.addWidget(self.tag_count)
        rv.addWidget(self.tag_table, 1)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 340])
        lay = QVBoxLayout(self)
        lay.addWidget(split)

        self._install_shortcuts()
        self.reload_codes()

    # --- raccourcis ----------------------------------------------------------------
    def _shortcut(self, key: KeySpec, slot: object, autorepeat: bool = True) -> QShortcut:
        # Rattaché à la fenêtre : le tagging fonctionne quel que soit le widget qui a le focus.
        # Les champs de saisie gardent la priorité sur les touches imprimables (ShortcutOverride).
        sc = QShortcut(QKeySequence(key), self)
        sc.setContext(Qt.ShortcutContext.WindowShortcut)
        sc.setAutoRepeat(autorepeat)
        sc.setEnabled(self.isVisible())
        sc.activated.connect(slot)
        self._all_shortcuts.append(sc)
        return sc

    def showEvent(self, e: QShowEvent) -> None:
        super().showEvent(e)
        for sc in self._all_shortcuts:
            sc.setEnabled(True)

    def hideEvent(self, e: QHideEvent) -> None:
        super().hideEvent(e)
        for sc in self._all_shortcuts:   # inactifs sur la page Bibliothèque
            sc.setEnabled(False)

    def _install_shortcuts(self) -> None:
        p = self.player
        self._shortcut("Space", p.toggle, autorepeat=False)
        self._shortcut("K", p.pause)
        self._shortcut("L", self._faster, autorepeat=False)
        self._shortcut("J", lambda: p.step_seconds(-5))
        self._shortcut("Left", lambda: p.step(-1))
        self._shortcut("Right", lambda: p.step(1))
        self._shortcut("Shift+Left", lambda: p.step_seconds(-1))
        self._shortcut("Shift+Right", lambda: p.step_seconds(1))
        self._shortcut("Ctrl+Left", lambda: p.step_seconds(-10))
        self._shortcut("Ctrl+Right", lambda: p.step_seconds(10))
        self._shortcut("Home", lambda: p.seek(0))
        self._shortcut("End", lambda: p.seek(p.frame_count - 1))
        self._shortcut("I", lambda: self._set_bound("in"), autorepeat=False)
        self._shortcut("O", lambda: self._set_bound("out"), autorepeat=False)
        self._shortcut(QKeySequence.StandardKey.Delete, self.delete_selected_tag, autorepeat=False)
        self._shortcut("Ctrl+0", self.timeline.zoom_reset)

    def _faster(self) -> None:
        if not self.player.playing:
            self.rate.setCurrentIndex(RATES.index(1.0))
            self.player.play()
        else:
            i = self.rate.currentIndex()
            self.rate.setCurrentIndex(min(i + 1, len(RATES) - 1))

    def reload_codes(self) -> None:
        codes = self.store.codes()
        self.codes.set_codes(codes)
        for sc in self._code_shortcuts:
            sc.setEnabled(False)
            self._all_shortcuts.remove(sc)
            sc.deleteLater()
        self._code_shortcuts = [
            self._shortcut(c.shortcut, lambda c=c: self.add_tag(c), autorepeat=False) for c in codes if c.shortcut
        ]
        self.reload_tags()

    # --- match ---------------------------------------------------------------------
    def open_match(self, match: Match) -> None:
        self.match = match
        self.title.setText(match.title + (f"  ·  {match.competition}" if match.competition else ""))
        self.timeline.set_media(match.frame_count, match.fps)
        self.player.load(match.video_path, match.fps, match.frame_count)
        self.reload_tags()
        self._on_frame(0)
        self.setFocus()

    def close_match(self) -> None:
        self.player.pause()
        self.player.player.setSource(QUrl())  # libère le fichier
        self.match = None

    def _on_frame(self, frame: int) -> None:
        if self.match is None:
            return
        self.timeline.set_frame(frame)
        self.pos_label.setText(f"{timecode(frame, self.match.fps)}   image {frame} / {self.match.frame_count - 1}")

    def _on_playing(self, playing: bool) -> None:
        self.play_btn.setText("⏸" if playing else "▶")

    # --- tags ------------------------------------------------------------------------
    def add_tag(self, code: Code) -> None:
        if self.match is None:
            return
        tid = self.store.add_tag(self.match, code, self.player.frame)
        self.reload_tags(select=tid)

    def _selected_tag(self) -> Tag | None:
        rows = self.tag_table.selectionModel().selectedRows() if self.tag_table.selectionModel() else []
        if not rows:
            return None
        tid = self._row_tag_id(rows[0].row())
        return next((t for t in self.tags if t.id == tid), None)

    def _row_tag_id(self, row: int) -> int:
        item = self.tag_table.item(row, 0)
        assert item is not None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def delete_selected_tag(self) -> None:
        tag = self._selected_tag()
        if tag is not None:
            self.store.delete_tag(tag.id)
            self.reload_tags()

    def _set_bound(self, which: str) -> None:
        tag = self._selected_tag()
        if tag is None:
            return
        f = self.player.frame
        if which == "in":
            self.store.update_tag(tag.id, frame_in=min(f, tag.frame))
        else:
            self.store.update_tag(tag.id, frame_out=max(f, tag.frame))
        self.reload_tags(select=tag.id)

    def _jump_to_row(self, row: int, _col: int) -> None:
        tid = self._row_tag_id(row)
        tag = next((t for t in self.tags if t.id == tid), None)
        if tag is not None:
            self.player.pause()
            self.player.seek(tag.frame_in)
            self.setFocus()

    def _note_edited(self, item: QTableWidgetItem) -> None:
        if item.column() != 3:
            return
        tid = self._row_tag_id(item.row())
        self.store.update_tag(tid, note=item.text())

    def reload_tags(self, select: int | None = None) -> None:
        if self.match is None:
            self.tags = []
        else:
            self.tags = self.store.tags(self.match.id)
        fps = self.match.fps if self.match else 25.0
        table = self.tag_table
        table.blockSignals(True)
        table.setRowCount(len(self.tags))
        for r, t in enumerate(self.tags):
            cells = [timecode(t.frame, fps), t.label, f"{(t.frame_out - t.frame_in + 1) / fps:.1f} s", t.note]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, t.id)
                if c == 1:
                    item.setForeground(QColor(t.color))
                if c != 3:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(r, c, item)
            if t.id == select:
                table.selectRow(r)
                table.scrollToItem(table.item(r, 0) or QTableWidgetItem())
        table.blockSignals(False)
        self.tag_count.setText(f"<b>Tags</b> — {len(self.tags)}")
        self._refresh_markers()

    def _refresh_markers(self) -> None:
        sel = self._selected_tag()
        self.timeline.set_markers([
            Marker(t.frame, t.frame_in, t.frame_out, t.color, selected=sel is not None and t.id == sel.id)
            for t in self.tags
        ])
