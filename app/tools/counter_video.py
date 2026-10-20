"""Vidéo de test à compteur incrusté, pour le critère du jalon J1.

Chaque image porte son numéro en clair (vérification à l'œil) et en code-barres
(vérification automatique, voir src/bph_app/counter_code.py).

    python tools/counter_video.py compteur.mp4 --minutes 5 --fps 25
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from bph_app.counter_code import make  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("output", type=Path)
    p.add_argument("--minutes", type=float, default=5)
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    a = p.parse_args()
    n = make(a.output, a.minutes, a.fps, a.width, a.height)
    print(f"{a.output} : {n} images à {a.fps} im/s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
