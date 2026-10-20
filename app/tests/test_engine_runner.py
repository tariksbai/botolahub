"""La normalisation à l'import passe par le moteur, lancé dans un processus séparé."""

import os
from pathlib import Path

from bph_app.engine_runner import EngineJob
from bph_engine.video import probe


def test_normalize_through_engine_process(qtbot, vfr_avi: Path, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    os.environ["PYTHONPATH"] = os.pathsep.join([str(Path(__file__).parent.parent / "src"),
                                                os.environ.get("PYTHONPATH", "")])
    out = tmp_path / "norm.mp4"
    job = EngineJob("normalize", str(vfr_avi), str(out))
    progress: list[float] = []
    job.progress.connect(progress.append)
    with qtbot.waitSignal(job.finished, timeout=60000) as blocker:
        job.start()
    ok, message = blocker.args
    assert ok, message
    assert progress and progress[-1] == 1.0
    assert not probe(out).needs_normalization()


def test_engine_failure_is_reported(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    bad = tmp_path / "rien.mp4"
    bad.write_bytes(b"x")
    job = EngineJob("normalize", str(bad), str(tmp_path / "out.mp4"))
    with qtbot.waitSignal(job.finished, timeout=30000) as blocker:
        job.start()
    ok, message = blocker.args
    assert not ok and "rien.mp4" in message


def test_packaged_app_runs_engine_from_its_own_executable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import sys

    from bph_app.engine_runner import engine_command

    monkeypatch.delenv("BPH_ENGINE", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert engine_command("probe", "x.mp4") == (sys.executable, ["--engine", "probe", "x.mp4"])


def test_engine_mode_of_the_app_entry_point(counter_video: Path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    import json
    import sys

    from bph_app.launch import main

    monkeypatch.setattr(sys, "argv", ["BottolaAnalyse", "--engine", "probe", str(counter_video)])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["frame_count"] == 1000
