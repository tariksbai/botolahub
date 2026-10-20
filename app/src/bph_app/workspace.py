"""Espace de travail d'un match : lecteur, timeline, grille de codes et tags (P04, P06).

Tout se fait au clavier, sans souris : voir SHORTCUTS.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QHideEvent, QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
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

from bph_app import theme
from bph_app.player import FramePlayer, VideoView
from bph_app.store import Code, Match, Store, Tag, timecode
from bph_app.timeline import Marker, Timeline

RATES = (0.25, 0.5, 1.0, 1.5, 2.0, 4.0)
SHORTCUTS = [
    ("Espace", "lecture / pause"),
    ("← / →", "image précédente / suivante"),
    ("Maj + ← / →", "± 1 seconde"),
    ("Ctrl + ← / →", "± 10 secondes"),
    ("J / K / L", "recul de 5 s / pause / lecture puis ×2, ×4"),
    ("Début / Fin", "début / fin du match"),
    ("Touches de la grille", "créer un tag à l'image courante"),
    ("I / O", "début / fin du tag sélectionné à la position courante"),
    ("Suppr", "supprimer le tag sélectionné"),
    ("Ctrl + molette", "zoom de la timeline, jusqu'à l'image près"),
    ("Ctrl + 0", "timeline entière"),
]
KeySpec = str | QKeySequence | QKeySequence.StandardKey


def _tint(color: str, alpha: int) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


class CodeButton(QPushButton):
    """Bouton de code : pastille de couleur, libellé, badge de la touche."""

    def __init__(self, code: Code, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(42)
        self.setToolTip(f"{code.label} — touche {code.shortcut}" if code.shortcut else code.label)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 10, 0)
        row.setSpacing(9)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background: {code.color}; border-radius: 5px;")
        label = QLabel(code.label)
        label.setStyleSheet(f"font-weight: 650; color: {theme.TEXT};")
        row.addWidget(dot)
        row.addWidget(label, 1)
        if code.shortcut:
            key = QLabel(code.shortcut)
            key.setAlignment(Qt.AlignmentFlag.AlignCenter)
            key.setFixedHeight(22)
            key.setMinimumWidth(24)
            key.setStyleSheet(f"background: {theme.SURFACE}; border: 1px solid {_tint(code.color, 90)};"
                              f" border-radius: 6px; padding: 1px 6px; font-weight: 700; font-size: 12px;"
                              f" color: {code.color};")
            row.addWidget(key, 0, Qt.AlignmentFlag.AlignVCenter)
        for w in self.findChildren(QLabel):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet(
            f"QPushButton {{ background: {_tint(code.color, 22)}; border: 1px solid {_tint(code.color, 60)};"
            f" border-radius: 10px; }}"
            f"QPushButton:hover {{ background: {_tint(code.color, 40)}; border-color: {_tint(code.color, 110)}; }}"
            f"QPushButton:pressed {{ background: {_tint(code.color, 70)}; }}")


class CodeGrid(QWidget):
    tagRequested = Signal(object)   # Code

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setSpacing(8)
        self.grid.setContentsMargins(0, 0, 0, 0)

    def set_codes(self, codes: list[Code]) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        for i, code in enumerate(codes):
            b = CodeButton(code)
            b.clicked.connect(lambda _=False, c=code: self.tagRequested.emit(c))
            self.grid.addWidget(b, i // 2, i % 2)


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = theme.named(QFrame(), "card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    return frame, lay


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

        # --- en-tête : retour, titre du match, compétition
        back = theme.decorate(QToolButton(), "back")
        back.setToolTip("Revenir à la bibliothèque (Ctrl+B)")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.backRequested.emit)
        self.title = theme.style(QLabel(), role="title")
        self.title.setStyleSheet("font-size: 19px;")
        self.subtitle = theme.style(QLabel(), role="badge")
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(back)
        header.addWidget(self.title)
        header.addWidget(self.subtitle, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addStretch()

        # --- barre de transport
        def tool(icon_name: str, tip: str, slot: object) -> QToolButton:
            b = theme.decorate(QToolButton(), icon_name, size=20)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            return b

        self.play_btn = theme.decorate(QToolButton(), "play", "play", size=22)
        self.play_btn.setToolTip("Lecture / pause (Espace)")
        self.play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self.player.toggle)
        self.tc_label = theme.style(QLabel("00:00:00:00"), role="mono")
        self.frame_label = theme.style(QLabel(), role="monoMuted")
        position = QVBoxLayout()
        position.setSpacing(0)
        position.addWidget(self.tc_label)
        position.addWidget(self.frame_label)
        self.rate = QComboBox()
        self.rate.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rate.setToolTip("Vitesse de lecture (L pour accélérer)")
        for r in RATES:
            self.rate.addItem(f"×{r:g}", r)
        self.rate.setCurrentIndex(RATES.index(1.0))
        self.rate.currentIndexChanged.connect(lambda _i: self.player.set_rate(self.rate.currentData()))

        transport = QHBoxLayout()
        transport.setSpacing(4)
        transport.addLayout(position)
        transport.addStretch()
        for b in (
            tool("skip-start", "Début du match (Début)", lambda: self.player.seek(0)),
            tool("second-back", "Une seconde en arrière (Maj+←)", lambda: self.player.step_seconds(-1)),
            tool("frame-back", "Image précédente (←)", lambda: self.player.step(-1)),
        ):
            transport.addWidget(b)
        transport.addSpacing(6)
        transport.addWidget(self.play_btn)
        transport.addSpacing(6)
        for b in (
            tool("frame-forward", "Image suivante (→)", lambda: self.player.step(1)),
            tool("second-forward", "Une seconde en avant (Maj+→)", lambda: self.player.step_seconds(1)),
            tool("skip-end", "Fin du match (Fin)", lambda: self.player.seek(self.player.frame_count - 1)),
        ):
            transport.addWidget(b)
        transport.addStretch()
        speed = QLabel()
        speed.setPixmap(theme.pixmap("speed", theme.MUTED, 18))
        transport.addWidget(speed)
        transport.addWidget(self.rate)

        self.timeline = Timeline()
        self.timeline.seekRequested.connect(self.player.seek)

        video_frame = theme.named(QFrame(), "videoFrame")
        vf = QVBoxLayout(video_frame)
        vf.setContentsMargins(0, 0, 0, 0)
        vf.addWidget(self.view)

        controls, cl = card()
        cl.addLayout(transport)
        cl.addWidget(self.timeline)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(12)
        lv.addLayout(header)
        lv.addWidget(video_frame, 1)
        lv.addWidget(controls)

        # --- panneau de tagging
        self.codes = CodeGrid()
        self.codes.tagRequested.connect(self.add_tag)
        edit_codes = theme.decorate(QPushButton("Modifier"), "grid", "ghost", size=16)
        edit_codes.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        edit_codes.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_codes.clicked.connect(self.editCodesRequested.emit)
        self.tag_table = QTableWidget(0, 4)
        self.tag_table.setHorizontalHeaderLabels(["Temps", "Code", "Durée", "Note"])
        self.tag_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tag_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tag_table.setShowGrid(False)
        self.tag_table.verticalHeader().hide()
        self.tag_table.verticalHeader().setDefaultSectionSize(38)
        self.tag_table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.tag_table.horizontalHeader().setHighlightSections(False)
        self.tag_table.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.tag_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tag_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tag_table.cellDoubleClicked.connect(self._jump_to_row)
        self.tag_table.itemChanged.connect(self._note_edited)
        self.tag_table.itemSelectionChanged.connect(self._refresh_markers)
        self.tag_count = theme.style(QLabel("0"), role="badge")

        codes_card, ccl = card()
        head = QHBoxLayout()
        head.addWidget(theme.style(QLabel("GRILLE DE CODES"), role="section"))
        head.addStretch()
        head.addWidget(edit_codes)
        ccl.addLayout(head)
        ccl.addWidget(self.codes)

        tags_card, tcl = card()
        tags_head = QHBoxLayout()
        tags_head.addWidget(theme.style(QLabel("TAGS"), role="section"))
        tags_head.addWidget(self.tag_count)
        tags_head.addStretch()
        hint = theme.style(QLabel("double-clic : revoir · I / O : bornes · Suppr"), role="subtitle")
        hint.setStyleSheet("font-size: 11px;")
        tags_head.addWidget(hint)
        tcl.addLayout(tags_head)
        tcl.addWidget(self.tag_table, 1)

        right = QWidget()
        right.setMinimumWidth(360)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(12)
        rv.addWidget(codes_card)
        rv.addWidget(tags_card, 1)

        split = QSplitter()
        split.setChildrenCollapsible(False)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 380])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
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
        self.title.setText(match.title)
        self.subtitle.setText(" · ".join(x for x in (match.competition, match.season) if x))
        self.subtitle.setVisible(bool(match.competition or match.season))
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
        self.tc_label.setText(timecode(frame, self.match.fps))
        self.frame_label.setText(f"image {frame:,} / {self.match.frame_count - 1:,}".replace(",", "\u202f"))

    def _on_playing(self, playing: bool) -> None:
        self.play_btn.setIcon(theme.icon("pause" if playing else "play", "#ffffff", size=22))

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
                    item.setIcon(theme.dot(t.color))
                if c != 3:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(r, c, item)
            if t.id == select:
                table.selectRow(r)
                table.scrollToItem(table.item(r, 0) or QTableWidgetItem())
        table.blockSignals(False)
        self.tag_count.setText(str(len(self.tags)))
        self._refresh_markers()

    def _refresh_markers(self) -> None:
        sel = self._selected_tag()
        self.timeline.set_markers([
            Marker(t.frame, t.frame_in, t.frame_out, t.color, selected=sel is not None and t.id == sel.id)
            for t in self.tags
        ])
