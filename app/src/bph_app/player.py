"""Lecteur vidéo à l'image près (tâche P04).

La position exposée est un numéro d'image, calculé à partir de l'horodatage de l'image
réellement livrée à l'affichage — jamais de la position déclarée par QMediaPlayer, qui
peut précéder l'image visible. Un saut vise le milieu de l'image demandée, ce qui
absorbe les arrondis à la milliseconde des horodatages.

Pendant un scrubbing rapide, les sauts sont regroupés : un seul saut est en cours à la
fois et seule la dernière cible demandée est exécutée ensuite.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QPainter, QResizeEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QWidget

SEEK_TIMEOUT_MS = 1500


class FramePlayer(QObject):
    frameChanged = Signal(int)
    playingChanged = Signal(bool)
    loaded = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.fps = 25.0
        self.frame_count = 0
        self._frame = 0
        self._last_frame: QVideoFrame | None = None
        self._seeking: int | None = None
        self._queued: int | None = None
        self._sink: QVideoSink | None = None
        self._announced = False  # `loaded` n'est émis qu'une fois par chargement
        self._seek_timer = QTimer(self, singleShot=True, interval=SEEK_TIMEOUT_MS)
        self._seek_timer.timeout.connect(self._seek_done)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.playbackStateChanged.connect(
            lambda s: self.playingChanged.emit(s == QMediaPlayer.PlaybackState.PlayingState))
        self.player.errorOccurred.connect(lambda _e, msg: self.failed.emit(msg))

    # --- branchement -------------------------------------------------------------
    def set_sink(self, sink: QVideoSink) -> None:
        if self._sink is not None:
            self._sink.videoFrameChanged.disconnect(self._on_frame)
        self._sink = sink
        self.player.setVideoSink(sink)
        sink.videoFrameChanged.connect(self._on_frame)

    def load(self, path: str, fps: float, frame_count: int) -> None:
        self.fps, self.frame_count = fps, frame_count
        self._frame, self._seeking, self._queued, self._last_frame = 0, None, None, None
        self._announced = False
        self.player.setSource(QUrl.fromLocalFile(path))

    def _on_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia and not self._announced:
            # Qt repasse par LoadedMedia après certains sauts : on n'annonce que le premier.
            self._announced = True
            self.player.pause()
            self.loaded.emit()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.pause()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.failed.emit(self.player.errorString() or "vidéo illisible")

    # --- position ----------------------------------------------------------------
    @property
    def frame(self) -> int:
        return self._frame

    @property
    def last_video_frame(self) -> QVideoFrame | None:
        return self._last_frame

    def frame_of(self, video_frame: QVideoFrame) -> int:
        return max(0, round(video_frame.startTime() * self.fps / 1_000_000))

    def _on_frame(self, video_frame: QVideoFrame) -> None:
        if not video_frame.isValid():
            return
        n = min(self.frame_of(video_frame), max(0, self.frame_count - 1))
        self._last_frame = video_frame
        if n != self._frame or self._seeking is not None:
            self._frame = n
            self.frameChanged.emit(n)
        if self._seeking is not None and n == self._seeking:
            self._seek_done()

    def seek(self, frame: int) -> None:
        frame = max(0, min(int(frame), self.frame_count - 1))
        if self._seeking is not None:
            self._queued = frame
            return
        self._seeking = frame
        self._seek_timer.start()
        self.player.setPosition(int((frame + 0.5) * 1000 / self.fps))

    def _seek_done(self) -> None:
        self._seek_timer.stop()
        self._seeking = None
        if self._queued is not None:
            target, self._queued = self._queued, None
            if target != self._frame:
                self.seek(target)

    @property
    def busy(self) -> bool:
        return self._seeking is not None or self._queued is not None

    def step(self, delta: int) -> None:
        self.pause()
        base = self._queued if self._queued is not None else (
            self._seeking if self._seeking is not None else self._frame)
        self.seek(base + delta)

    def step_seconds(self, seconds: float) -> None:
        self.step(round(seconds * self.fps))

    # --- lecture -----------------------------------------------------------------
    @property
    def playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def play(self) -> None:
        if self._frame >= self.frame_count - 1:
            self.seek(0)
        self.player.play()

    def pause(self) -> None:
        self.player.pause()

    def toggle(self) -> None:
        self.pause() if self.playing else self.play()

    def set_rate(self, rate: float) -> None:
        self.player.setPlaybackRate(rate)

    @property
    def rate(self) -> float:
        return float(self.player.playbackRate())


class VideoView(QGraphicsView):
    """Surface vidéo dans une scène graphique : les calques de télestration s'y ajouteront
    au-dessus de l'image (tâche P20)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.video_item = QGraphicsVideoItem()
        self.scene().addItem(self.video_item)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setStyleSheet("background: #000")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.video_item.nativeSizeChanged.connect(lambda _s: self._fit())

    def sink(self) -> QVideoSink:
        return self.video_item.videoSink()

    def _fit(self) -> None:
        size = self.video_item.nativeSize()
        if size.isEmpty():
            return
        self.video_item.setSize(size)
        self.scene().setSceneRect(QRectF(0, 0, size.width(), size.height()))
        self.fitInView(self.video_item, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()
