from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.*=false")


@pytest.fixture(scope="session")
def counter_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Vidéo à compteur de 40 s, image clé toutes les 10 s, images B."""
    from bph_app.counter_code import make

    path = tmp_path_factory.mktemp("video") / "compteur.mp4"
    make(path, minutes=40 / 60, width=640, height=360)
    return path


@pytest.fixture(scope="session")
def vfr_avi(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Vidéo non conforme (MPEG-4 Part 2 en AVI) : doit être normalisée à l'import."""
    import subprocess

    path = tmp_path_factory.mktemp("video") / "camera.avi"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "3", "-c:v", "mpeg4", "-c:a", "mp3",
                    str(path)], check=True)
    return path
