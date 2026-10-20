"""Timeline : règle graduée, tête de lecture, plages des tags, scrubbing et zoom (tâche P04).

Clic ou glisser : déplace la tête de lecture (scrubbing). Molette : défilement.
Ctrl + molette : zoom autour du curseur, jusqu'à voir chaque image séparément.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from bph_app.store import timecode

RULER_H = 22
STEPS_SECONDS = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800)


@dataclass(frozen=True)
class Marker:
    frame: int
    frame_in: int
    frame_out: int
    color: str
    selected: bool = False


class Timeline(QWidget):
    seekRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.frame_count = 1
        self.fps = 25.0
        self.frame = 0
        self.view_start = 0.0          # première image visible
        self.view_len = 1.0            # nombre d'images visibles
        self.markers: list[Marker] = []
        self._hover: int | None = None
        self._dragging = False

    # --- données ---------------------------------------------------------------
    def set_media(self, frame_count: int, fps: float) -> None:
        self.frame_count, self.fps = max(1, frame_count), fps
        self.view_start, self.view_len = 0.0, float(self.frame_count)
        self.update()

    def set_frame(self, frame: int) -> None:
        self.frame = frame
        outside = frame < self.view_start or frame > self.view_start + self.view_len
        if outside and not self._dragging:  # garde la tête de lecture visible pendant la lecture
            self.view_start = self._clamp_start(frame - self.view_len * 0.1)
        self.update()

    def set_markers(self, markers: list[Marker]) -> None:
        self.markers = markers
        self.update()

    # --- géométrie ---------------------------------------------------------------
    def _clamp_start(self, start: float) -> float:
        return max(0.0, min(start, self.frame_count - self.view_len))

    def x_of(self, frame: float) -> float:
        return (frame - self.view_start) / self.view_len * self.width()

    def frame_at(self, x: float) -> int:
        f = self.view_start + x / max(1, self.width()) * self.view_len
        return max(0, min(self.frame_count - 1, int(f)))

    # --- interactions ------------------------------------------------------------
    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.seekRequested.emit(self.frame_at(e.position().x()))

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        self._hover = self.frame_at(e.position().x())
        if self._dragging:
            self.seekRequested.emit(self._hover)
        self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._dragging = False

    def leaveEvent(self, _e: object) -> None:
        self._hover = None
        self.update()

    def wheelEvent(self, e: QWheelEvent) -> None:
        steps = e.angleDelta().y() / 120
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            anchor = self.view_start + e.position().x() / max(1, self.width()) * self.view_len
            new_len = max(20.0, min(float(self.frame_count), self.view_len * (0.8 ** steps)))
            ratio = (anchor - self.view_start) / self.view_len
            self.view_len = new_len
            self.view_start = self._clamp_start(anchor - ratio * new_len)
        else:
            self.view_start = self._clamp_start(self.view_start - steps * self.view_len * 0.1)
        self.update()

    def zoom_reset(self) -> None:
        self.view_start, self.view_len = 0.0, float(self.frame_count)
        self.update()

    # --- dessin --------------------------------------------------------------------
    def paintEvent(self, _e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        pal = self.palette()
        p.fillRect(0, 0, w, h, pal.base())
        p.fillRect(0, 0, w, RULER_H, pal.alternateBase())

        # graduations : pas choisi pour garder ~90 px entre deux libellés
        seconds_visible = self.view_len / self.fps
        step = next((s for s in STEPS_SECONDS if s / seconds_visible * w >= 90), STEPS_SECONDS[-1])
        step_frames = step * self.fps
        first = int(self.view_start // step_frames) * step_frames
        p.setPen(pal.text().color())
        font = p.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
        p.setFont(font)
        f = first
        while f <= self.view_start + self.view_len:
            x = self.x_of(f)
            p.drawLine(QPointF(x, RULER_H - 6), QPointF(x, RULER_H))
            p.drawText(QPointF(x + 3, RULER_H - 8), timecode(int(f), self.fps)[:8])
            f += step_frames
        # images individuelles visibles quand le zoom est fort
        if w / self.view_len >= 6:
            p.setPen(QPen(pal.mid().color()))
            for fr in range(int(self.view_start), int(self.view_start + self.view_len) + 1):
                x = self.x_of(fr)
                p.drawLine(QPointF(x, RULER_H - 3), QPointF(x, RULER_H))

        # plages des tags
        lane_top, lane_h = RULER_H + 6, h - RULER_H - 12
        for m in self.markers:
            x0, x1 = self.x_of(m.frame_in), self.x_of(m.frame_out + 1)
            if x1 < 0 or x0 > w:
                continue
            c = QColor(m.color)
            c.setAlpha(110 if not m.selected else 200)
            p.fillRect(QRectF(x0, lane_top, max(2.0, x1 - x0), lane_h), c)
            p.fillRect(QRectF(self.x_of(m.frame) - 1, lane_top, 2, lane_h), QColor(m.color))
            if m.selected:
                p.setPen(QPen(pal.text().color(), 1))
                p.drawRect(QRectF(x0, lane_top, max(2.0, x1 - x0), lane_h))

        # survol et tête de lecture
        if self._hover is not None:
            p.setPen(QPen(pal.mid().color(), 1, Qt.PenStyle.DashLine))
            x = self.x_of(self._hover)
            p.drawLine(QPointF(x, RULER_H), QPointF(x, h))
        x = self.x_of(self.frame)
        p.fillRect(QRectF(x - 1, 0, 2, h), pal.highlight())
        p.end()
