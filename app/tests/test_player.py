"""Lecteur à l'image près : version courte du critère J1 (le test complet est marqué slow)."""

from pathlib import Path

import pytest

from tools.j1_seek_test import run


def test_seek_precision_short(qapp, counter_video: Path) -> None:  # type: ignore[no-untyped-def]
    report = run(counter_video, jumps=60, steps=20, seed=1, verbose=False)
    assert report.passed, report.summary()


@pytest.mark.slow
def test_seek_precision_j1_full(qapp, counter_video: Path) -> None:  # type: ignore[no-untyped-def]
    report = run(counter_video, jumps=500, steps=100, seed=2026, verbose=False)
    assert report.passed, report.summary()
