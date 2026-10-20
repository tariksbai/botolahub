"""Test de précision du lecteur — critère de sortie du jalon J1.

Sur une vidéo à compteur incrusté (tools/counter_video.py), effectue des sauts aléatoires
puis des pas image par image, et vérifie à chaque fois que :
    numéro demandé == numéro affiché par le logiciel == numéro lu dans l'image.

Utilisable depuis l'application (menu Outils), en ligne de commande
(tools/j1_seek_test.py) et dans les tests automatisés.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import QElapsedTimer, QObject, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QVideoFrame

from bph_app.counter_code import decode_gray
from bph_app.player import FramePlayer

SETTLE_TIMEOUT_MS = 4000


def frame_to_gray(video_frame: QVideoFrame) -> np.ndarray:
    img = video_frame.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    w, h, stride = img.width(), img.height(), img.bytesPerLine()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8, count=stride * h)
    return buf.reshape(h, stride)[:, :w].copy()


@dataclass
class CheckResult:
    kind: str          # "saut" ou "pas"
    target: int
    shown: int
    decoded: int | None
    ms: int

    @property
    def ok(self) -> bool:
        return self.target == self.shown == self.decoded


@dataclass
class Report:
    results: list[CheckResult] = field(default_factory=list)
    aborted: str = ""

    @property
    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if not r.ok]

    @property
    def passed(self) -> bool:
        return not self.aborted and bool(self.results) and not self.failures

    def summary(self) -> str:
        if self.aborted:
            return f"ÉCHEC — {self.aborted}"
        jumps = [r for r in self.results if r.kind == "saut"]
        steps = [r for r in self.results if r.kind == "pas"]
        slowest = max((r.ms for r in self.results), default=0)
        head = "RÉUSSI" if self.passed else "ÉCHEC"
        lines = [
            f"{head} — {len(self.results) - len(self.failures)}/{len(self.results)} positions exactes "
            f"({len(jumps)} sauts aléatoires, {len(steps)} pas image par image). Saut le plus lent : {slowest} ms."
        ]
        for r in self.failures[:20]:
            lines.append(f"  {r.kind} vers {r.target} : affiché {r.shown}, image réelle {r.decoded}")
        return "\n".join(lines)


class SeekCheck(QObject):
    progress = Signal(int, int)
    finished = Signal(object)  # Report

    def __init__(self, player: FramePlayer, jumps: int = 500, steps: int = 100, seed: int | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.player = player
        rng = random.Random(seed)
        n = player.frame_count
        plan: list[tuple[str, int]] = [("saut", rng.randrange(n)) for _ in range(jumps)]
        for _ in range(steps):  # un pas = un saut d'amorce puis +1 ou -1
            start = rng.randrange(1, n - 1)
            plan += [("amorce", start), ("pas", start + rng.choice((-1, 1)))]
        self.plan = plan
        self.report = Report()
        self._i = -1
        self._done = False
        self._clock = QElapsedTimer()
        self._poll = QTimer(self, interval=2)
        self._poll.timeout.connect(self._tick)

    def start(self) -> None:
        if self.player.frame_count < 3:
            self._finish("vidéo non chargée")
            return
        self.player.pause()
        self._next()

    def cancel(self) -> None:
        if not self._done:
            self._finish("test interrompu")

    def _next(self) -> None:
        self._i += 1
        if self._i >= len(self.plan):
            self._finish("")
            return
        kind, target = self.plan[self._i]
        self._clock.start()
        if kind == "pas":
            self.player.step(target - self.player.frame)
        else:
            self.player.seek(target)
        self._poll.start()

    def _tick(self) -> None:
        kind, target = self.plan[self._i]
        settled = not self.player.busy and self.player.frame == target
        if not settled and self._clock.elapsed() < SETTLE_TIMEOUT_MS:
            return
        self._poll.stop()
        if kind != "amorce":
            vf = self.player.last_video_frame
            decoded = decode_gray(frame_to_gray(vf)) if vf is not None and vf.isValid() else None
            if not self.report.results and decoded is None:
                self._finish("aucun compteur lisible dans l'image : utiliser une vidéo produite par "
                             "tools/counter_video.py")
                return
            self.report.results.append(
                CheckResult(kind, target, self.player.frame, decoded, int(self._clock.elapsed())))
            self.progress.emit(len(self.report.results), sum(1 for k, _ in self.plan if k != "amorce"))
        self._next()

    def _finish(self, aborted: str) -> None:
        self._done = True
        self._poll.stop()
        self.report.aborted = aborted
        self._i = len(self.plan)
        self.finished.emit(self.report)
