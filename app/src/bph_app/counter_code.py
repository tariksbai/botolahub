"""Code-barres de numéro d'image, utilisé par la vidéo de test du jalon J1.

20 cases noires ou blanches donnent le numéro en binaire ; une seconde rangée porte les
bits inversés. Une image dont les deux rangées ne sont pas complémentaires est rejetée
(image mélangée ou mal décodée) : la vérification ne peut pas produire de faux positif.
Module sans Qt, partagé par le générateur (tools/counter_video.py) et le test intégré.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import numpy as np

from bph_engine.video import VideoError, available_encoder, find_tool

BITS = 20
STRIP_H = 48          # hauteur de chaque rangée de code-barres, en pixels


def encode_strip(frame_no: int, width: int) -> np.ndarray:
    cell = width // BITS
    bits = np.array([(frame_no >> b) & 1 for b in range(BITS)], dtype=np.uint8)
    row = np.repeat(bits * 255, cell)
    row = np.pad(row, (0, width - row.size), constant_values=128)
    top = np.tile(row, (STRIP_H, 1))
    inv = np.where(top == 128, 128, 255 - top).astype(np.uint8)
    return np.vstack([top, inv])


def decode_gray(img: np.ndarray) -> int | None:
    """Numéro d'image lu dans une image en niveaux de gris, ou None si illisible."""
    h, w = img.shape[:2]
    if h < 2 * STRIP_H or w < BITS:
        return None
    cell = w // BITS
    centers = [b * cell + cell // 2 for b in range(BITS)]
    top = img[STRIP_H // 2, centers].astype(int)
    bottom = img[STRIP_H + STRIP_H // 2, centers].astype(int)
    if np.any(np.abs(top - 128) < 64) or np.any(np.abs(bottom - 128) < 64):
        return None
    top_bits, bottom_bits = top > 128, bottom > 128
    if np.any(top_bits == bottom_bits):
        return None
    return int(sum(1 << b for b in range(BITS) if top_bits[b]))


def make(output: str | Path, minutes: float = 5, fps: int = 25, width: int = 1280, height: int = 720,
         gop_seconds: int = 10, encoder: str | None = None,
         on_progress: Callable[[float], None] | None = None) -> int:
    """Produit la vidéo de test et renvoie son nombre d'images.

    Réglages par défaut proches d'une vraie captation : une image clé toutes les dix
    secondes et des images B, pour que le test de saut soit exigeant."""
    frames = int(minutes * 60 * fps)
    if encoder is None:
        encoder = available_encoder()
    text = (
        "drawtext=text='%{frame_num}':start_number=0:fontsize=" + str(height // 5)
        + ":fontcolor=white:box=1:boxcolor=black@0.6:x=(w-text_w)/2:y=(h-text_h)/2"
    )

    def run(vf: list[str]) -> int:
        cmd = [find_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray",
               "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", *vf, "-c:v", encoder,
               "-pix_fmt", "yuv420p", "-g", str(gop_seconds * fps), str(output)]
        if encoder == "libx264":
            cmd[-1:-1] = ["-bf", "2", "-crf", "18"]
        else:
            cmd[-1:-1] = ["-b:v", "4M"]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.stdin is not None
        base = np.full((height, width), 90, np.uint8)
        try:
            for i in range(frames):
                if on_progress and i % 250 == 0:
                    on_progress(i / frames)
                img = base.copy()
                img[: 2 * STRIP_H] = encode_strip(i, width)
                proc.stdin.write(img.tobytes())
            proc.stdin.close()
        except BrokenPipeError:
            pass
        return proc.wait()

    if run(["-vf", text]) != 0 and run([]) != 0:   # sans police disponible : code-barres seul
        raise VideoError("ffmpeg n'a pas pu produire la vidéo de test")
    return frames
