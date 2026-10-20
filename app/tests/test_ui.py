"""Parcours clavier de l'espace de travail (sans souris), sur la vraie fenêtre."""

from pathlib import Path

from PySide6.QtCore import Qt

from bph_app.main_window import MainWindow
from bph_app.store import Store
from bph_engine.video import probe


def test_keyboard_tagging_flow(qtbot, tmp_path: Path, counter_video: Path) -> None:  # type: ignore[no-untyped-def]
    store = Store(tmp_path / "lib.sqlite")
    info = probe(counter_video)
    mid = store.add_match(video_path=str(counter_video), source_path=str(counter_video), fps_num=25, fps_den=1,
                          frame_count=info.frame_count, width=info.width, height=info.height,
                          home_team="Raja CA", away_team="Wydad AC")
    win = MainWindow(store, tmp_path / "videos")
    qtbot.addWidget(win)
    win.show()
    ws = win.workspace
    with qtbot.waitSignal(ws.player.loaded, timeout=10000):
        win.open_match(mid)
    assert win.pages.currentWidget() is ws

    ws.player.seek(500)
    qtbot.waitUntil(lambda: ws.player.frame == 500 and not ws.player.busy, timeout=5000)
    qtbot.keyClick(ws, Qt.Key.Key_Right)
    qtbot.waitUntil(lambda: ws.player.frame == 501 and not ws.player.busy, timeout=5000)
    qtbot.keyClick(ws, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
    qtbot.waitUntil(lambda: ws.player.frame == 476 and not ws.player.busy, timeout=5000)

    qtbot.keyClick(ws.tag_table, Qt.Key.Key_1)   # code « Tir », même si le focus est sur la liste
    tags = store.tags(mid)
    assert [(t.label, t.frame) for t in tags] == [("Tir", 476)]
    assert ws.tag_table.rowCount() == 1

    ws.player.seek(480)
    qtbot.waitUntil(lambda: ws.player.frame == 480 and not ws.player.busy, timeout=5000)
    qtbot.keyClick(ws, Qt.Key.Key_I)          # début du tag sélectionné
    assert store.tags(mid)[0].frame_in == 476  # jamais après l'instant du tag
    qtbot.keyClick(ws, Qt.Key.Key_Delete)
    assert store.tags(mid) == []
    win.show_library()
    qtbot.keyClick(win.library.table, Qt.Key.Key_1)  # sur la bibliothèque, les touches ne taguent rien
    assert store.tags(mid) == []
    store.close()
