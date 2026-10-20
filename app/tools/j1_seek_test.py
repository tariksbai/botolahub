"""Critère de sortie du jalon J1, en ligne de commande.

    python tools/counter_video.py compteur.mp4
    python tools/j1_seek_test.py compteur.mp4 --jumps 500

Code de sortie 0 si toutes les positions sont exactes, 1 sinon. À exécuter sur Windows,
macOS et Linux. Le même test existe dans l'application : Outils › Test de précision du lecteur.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402
from PySide6.QtMultimedia import QVideoSink  # noqa: E402

from bph_app.player import FramePlayer  # noqa: E402
from bph_app.seek_check import Report, SeekCheck  # noqa: E402
from bph_engine.video import probe  # noqa: E402


def run(path: Path, jumps: int, steps: int, seed: int | None, verbose: bool = True) -> Report:
    info = probe(path)
    app = QCoreApplication.instance() or QCoreApplication([])
    player = FramePlayer()
    sink = QVideoSink()
    player.set_sink(sink)
    result: dict[str, Report] = {}

    def on_loaded() -> None:
        check = SeekCheck(player, jumps, steps, seed, parent=player)
        if verbose:
            check.progress.connect(lambda i, n: print(f"\r{i}/{n}", end="", flush=True) if i % 25 == 0 else None)
        check.finished.connect(lambda r: (result.update(r=r), app.quit()))
        check.start()

    player.loaded.connect(on_loaded)
    player.failed.connect(lambda msg: (result.update(r=Report(aborted=msg)), app.quit()))
    player.load(str(path), info.fps_float, info.frame_count)
    QTimer.singleShot(15 * 60 * 1000, app.quit)
    app.exec()
    if verbose:
        print()
    return result.get("r", Report(aborted="délai dépassé"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video", type=Path)
    p.add_argument("--jumps", type=int, default=500)
    p.add_argument("--steps", type=int, default=100)
    p.add_argument("--seed", type=int)
    a = p.parse_args()
    report = run(a.video, a.jumps, a.steps, a.seed)
    print(report.summary())
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
