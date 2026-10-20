"""Inspection et normalisation des vidéos via FFmpeg (tâche P03).

La normalisation produit un fichier que le lecteur parcourt à l'image près :
H.264, pixels yuv420p, cadence constante, une image clé toutes les deux secondes
(un saut sur la timeline ne décode jamais plus de 50 images), conteneur MP4.

LICENCE — le codeur H.264 détermine la licence effective du livrable. libopenh264
(BSD) laisse FFmpeg sous LGPL ; libx264 rend FFmpeg GPL. L'ordre de préférence
ci-dessous applique ce choix ; la configuration de compilation FFmpeg livrée doit
inclure libopenh264 et exclure libx264 (voir app/docs/ffmpeg.md).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

SUPPORTED_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".m4v", ".mts", ".webm")
ENCODER_PREFERENCE = ("libopenh264", "libx264")
GPL_ENCODERS = {"libx264"}
KEYFRAME_SECONDS = 2


class VideoError(Exception):
    """Fichier vidéo illisible ou FFmpeg absent."""


@dataclass(frozen=True)
class VideoInfo:
    path: str
    container: str
    codec: str
    pix_fmt: str
    width: int
    height: int
    fps: Fraction
    frame_count: int
    duration: float
    variable_frame_rate: bool
    has_audio: bool

    @property
    def fps_float(self) -> float:
        return float(self.fps)

    def needs_normalization(self) -> bool:
        return (
            self.codec != "h264"
            or self.pix_fmt != "yuv420p"
            or self.variable_frame_rate
            or self.container not in ("mov,mp4,m4a,3gp,3g2,mj2",)
        )


def find_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise VideoError(f"{name} introuvable : FFmpeg doit être installé avec l'application")
    return path


def _fraction(text: str | None) -> Fraction | None:
    if not text or text in ("0/0", "0"):
        return None
    try:
        f = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    return f if f > 0 else None


def probe(path: str | Path) -> VideoInfo:
    path = Path(path)
    if not path.is_file():
        raise VideoError(f"fichier introuvable : {path}")
    cmd = [
        find_tool("ffprobe"), "-v", "error", "-count_packets",
        "-show_entries",
        "format=format_name,duration:stream=codec_type,codec_name,pix_fmt,width,height,"
        "r_frame_rate,avg_frame_rate,nb_frames,nb_read_packets,duration",
        "-of", "json", str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise VideoError(f"ffprobe n'a pas pu lire {path.name} : {res.stderr.strip()[:300]}")
    data = json.loads(res.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise VideoError(f"{path.name} ne contient pas de piste vidéo")
    r_rate = _fraction(video.get("r_frame_rate"))
    avg_rate = _fraction(video.get("avg_frame_rate"))
    fps = r_rate or avg_rate
    if fps is None:
        raise VideoError(f"cadence d'images inconnue pour {path.name}")
    duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0.0)
    count = int(video.get("nb_read_packets") or video.get("nb_frames") or round(duration * fps))
    # Cadence variable si la cadence nominale et la cadence moyenne divergent de plus de deux
    # images sur la durée totale (une image de fin plus longue ne suffit pas), ou si les
    # intervalles réels entre images sont irréguliers (téléphones : métadonnées trompeuses).
    vfr = bool(r_rate and avg_rate and abs(float(r_rate) - float(avg_rate)) * duration > 2)
    vfr = vfr or _irregular_intervals(path, fps)
    return VideoInfo(
        path=str(path),
        container=data.get("format", {}).get("format_name", ""),
        codec=video.get("codec_name", ""),
        pix_fmt=video.get("pix_fmt", ""),
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        fps=fps,
        frame_count=count,
        duration=duration,
        variable_frame_rate=vfr,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


def _irregular_intervals(path: Path, fps: Fraction, seconds: int = 60) -> bool:
    """Vrai si plus de 2 % des intervalles entre images s'écartent de plus de 25 % de 1/fps."""
    cmd = [find_tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-read_intervals", f"%+{seconds}",
           "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(path)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    pts = sorted(float(x) for x in res.stdout.split() if x.replace(".", "", 1).lstrip("-").isdigit())
    if len(pts) < 10:
        return False
    expected = 1 / float(fps)
    gaps = [b - a for a, b in zip(pts, pts[1:], strict=False)]
    irregular = sum(1 for g in gaps if abs(g - expected) > 0.25 * expected)
    return irregular > 0.02 * len(gaps)


def available_encoder() -> str:
    res = subprocess.run([find_tool("ffmpeg"), "-hide_banner", "-encoders"], capture_output=True, text=True)
    names = set(re.findall(r"^\s*V\S*\s+(\S+)", res.stdout, re.M))
    for enc in ENCODER_PREFERENCE:
        if enc in names:
            return enc
    raise VideoError("aucun codeur H.264 disponible dans FFmpeg (libopenh264 attendu)")


def normalization_command(info: VideoInfo, output: Path, encoder: str) -> list[str]:
    fps = info.fps if not info.variable_frame_rate else Fraction(round(info.fps_float))
    gop = max(1, round(float(fps) * KEYFRAME_SECONDS))
    cmd = [
        find_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", info.path,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", encoder, "-pix_fmt", "yuv420p", "-g", str(gop),
    ]
    if info.variable_frame_rate:   # seule une source à cadence variable est rééchantillonnée
        cmd += ["-fps_mode", "cfr", "-r", f"{fps.numerator}/{fps.denominator}"]
    else:                          # sinon chaque image source donne exactement une image
        cmd += ["-fps_mode", "passthrough"]
    if encoder == "libx264":
        cmd += ["-preset", "veryfast", "-crf", "20", "-bf", "0"]
    else:
        cmd += ["-b:v", "8M"]
    cmd += ["-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-progress", "pipe:1", str(output)]
    return cmd


def normalize(
    info: VideoInfo,
    output: str | Path,
    on_progress: Callable[[float], None] | None = None,
    encoder: str | None = None,
) -> VideoInfo:
    """Transcode `info` vers `output` et renvoie l'inspection du fichier produit."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = normalization_command(info, output, encoder or available_encoder())
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None and proc.stderr is not None
    for line in proc.stdout:
        if on_progress and line.startswith("out_time_us=") and info.duration > 0:
            value = line.split("=", 1)[1].strip()
            if value.isdigit():
                on_progress(min(1.0, int(value) / 1e6 / info.duration))
    err = proc.stderr.read()
    if proc.wait() != 0:
        output.unlink(missing_ok=True)
        raise VideoError(f"échec de la normalisation : {err.strip()[:300]}")
    if on_progress:
        on_progress(1.0)
    return probe(output)
