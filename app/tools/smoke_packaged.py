"""Contrôle de l'application empaquetée (dist/BottolaAnalyse), exécuté en CI après PyInstaller.

    python tools/smoke_packaged.py dist/BottolaAnalyse

Vérifie, avec l'exécutable seul (sans Python ni FFmpeg du système) :
1. le mode moteur répond (`--engine probe`) sur une vidéo produite par le FFmpeg livré ;
2. la normalisation fonctionne avec le codeur H.264 livré (licence compatible LGPL) ;
3. l'interface démarre et se ferme proprement.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    dist = Path(sys.argv[1]).resolve()
    exe = dist / ("BottolaAnalyse.exe" if os.name == "nt" else "BottolaAnalyse")
    ffmpeg = dist / "ffmpeg" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    assert exe.is_file(), f"exécutable absent : {exe}"
    assert ffmpeg.is_file(), f"FFmpeg livré absent : {ffmpeg}"

    banner = subprocess.run([str(ffmpeg), "-hide_banner", "-buildconf"], capture_output=True, text=True).stdout
    assert "--enable-gpl" not in banner, "le FFmpeg livré est compilé en GPL"
    print("FFmpeg livré : sans --enable-gpl")

    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    env.pop("BPH_FFMPEG_DIR", None)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "camera.avi"
        subprocess.run([str(ffmpeg), "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25",
                        "-t", "4", "-c:v", "mpeg4", str(src)], check=True)

        probe = subprocess.run([str(exe), "--engine", "probe", str(src)], capture_output=True, text=True,
                               env=env, timeout=120)
        assert probe.returncode == 0, probe.stderr
        info = json.loads(probe.stdout)
        assert info["frame_count"] == 100 and info["needs_normalization"], info
        print("moteur : probe OK")

        out = Path(tmp) / "norm.mp4"
        norm = subprocess.run([str(exe), "--engine", "normalize", str(src), str(out)], capture_output=True,
                              text=True, env=env, timeout=300)
        assert norm.returncode == 0, norm.stderr
        again = json.loads(subprocess.run([str(exe), "--engine", "probe", str(out)], capture_output=True,
                                          text=True, env=env, timeout=120).stdout)
        assert again["codec"] == "h264" and not again["needs_normalization"], again
        assert again["frame_count"] == 100, again
        print("moteur : normalisation H.264 OK")

        gui = subprocess.run([str(exe)], env={**env, "BPH_SMOKE_QUIT_MS": "4000", "BPH_DATA_DIR": tmp},
                             capture_output=True, text=True, timeout=120)
        assert gui.returncode == 0, gui.stderr
        assert (Path(tmp) / "bibliotheque.sqlite").is_file(), "la bibliothèque n'a pas été créée"
        print("interface : démarrage OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
