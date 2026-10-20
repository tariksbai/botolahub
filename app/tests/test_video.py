from pathlib import Path

import pytest

from bph_engine.video import VideoError, normalize, probe


def test_probe_counter_video(counter_video: Path) -> None:
    info = probe(counter_video)
    assert (info.width, info.height, info.frame_count, info.fps_float) == (640, 360, 1000, 25.0)
    assert not info.needs_normalization()


def test_probe_rejects_missing_and_invalid(tmp_path: Path) -> None:
    with pytest.raises(VideoError):
        probe(tmp_path / "absent.mp4")
    bad = tmp_path / "bad.mov"
    bad.write_text("pas une vidéo")
    with pytest.raises(VideoError):
        probe(bad)


def test_normalize_non_compliant_video(vfr_avi: Path, tmp_path: Path) -> None:
    info = probe(vfr_avi)
    assert info.needs_normalization()
    seen: list[float] = []
    out = normalize(info, tmp_path / "norm.mp4", on_progress=seen.append)
    assert out.codec == "h264" and out.pix_fmt == "yuv420p" and out.has_audio
    assert not out.needs_normalization()
    assert out.frame_count == info.frame_count == 90
    assert seen and seen[-1] == 1.0


def test_variable_frame_rate_is_detected_and_fixed(tmp_path: Path) -> None:
    import subprocess

    src = tmp_path / "telephone.mkv"   # images à intervalles irréguliers, comme un téléphone
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
                    "-t", "20", "-vf", "setpts='PTS+0.3*sin(N/7)/TB'", "-fps_mode", "vfr", "-c:v", "libx264",
                    str(src)], check=True)
    info = probe(src)
    out = normalize(info, tmp_path / "norm.mp4")
    assert not out.variable_frame_rate and not out.needs_normalization()
