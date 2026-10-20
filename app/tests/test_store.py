import sqlite3
from pathlib import Path

import pytest

from bph_app.store import MIGRATIONS, Store, timecode


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "lib.sqlite")


def add(store: Store, **kw: object) -> int:
    base = dict(video_path="/v.mp4", source_path="/v.mp4", fps_num=25, fps_den=1, frame_count=135000,
                width=1920, height=1080)
    base.update(kw)
    return store.add_match(**base)  # type: ignore[arg-type]


def test_new_library_has_default_grid(store: Store) -> None:
    assert store.schema_version == len(MIGRATIONS)
    codes = store.codes()
    assert codes[0].label == "Tir" and codes[0].shortcut == "1"


def test_matches_filter_by_client_and_season(store: Store) -> None:
    add(store, home_team="Raja CA", away_team="Wydad AC", client="Club A", season="2026-2027")
    add(store, home_team="AS FAR", away_team="RS Berkane", client="Club B", season="2025-2026")
    assert [m.home_team for m in store.matches(client="Club A")] == ["Raja CA"]
    assert [m.home_team for m in store.matches(season="2025-2026")] == ["AS FAR"]
    assert [m.home_team for m in store.matches("berkane")] == ["AS FAR"]
    assert store.clients() == ["Club A", "Club B"]


def test_tag_window_is_clamped_to_video(store: Store) -> None:
    mid = add(store, frame_count=300)
    match = store.match(mid)
    code = store.codes()[0]   # 5 s avant, 5 s après
    store.add_tag(match, code, 10)
    store.add_tag(match, code, 290)
    t1, t2 = store.tags(mid)
    assert (t1.frame_in, t1.frame, t1.frame_out) == (0, 10, 135)
    assert (t2.frame_in, t2.frame, t2.frame_out) == (165, 290, 299)


def test_deleting_match_removes_tags(store: Store) -> None:
    mid = add(store)
    store.add_tag(store.match(mid), store.codes()[0], 1000)
    store.delete_match(mid)
    assert store.db.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 0


def test_save_codes_rejects_duplicate_shortcut(store: Store) -> None:
    with pytest.raises(ValueError):
        store.save_codes([(None, "A", "q", "#000", 5, 5), (None, "B", "Q", "#000", 5, 5)])


def test_save_codes_keeps_ids_and_order(store: Store) -> None:
    first, second = store.codes()[:2]
    store.save_codes([(second.id, "But!", "2", second.color, 3, 4), (first.id, "Tir", "1", first.color, 5, 5),
                      (None, "Duel", "D", "#123456", 2, 2)])
    labels = [(c.id, c.label) for c in store.codes()]
    assert labels[:2] == [(second.id, "But!"), (first.id, "Tir")] and labels[2][1] == "Duel"


def test_playlists_keep_order_and_merge(store: Store) -> None:
    mid = add(store)
    m, c = store.match(mid), store.codes()[0]
    t = [store.add_tag(m, c, f) for f in (1000, 2000, 3000)]
    p1 = store.create_playlist("Attaque", [t[2], t[0]])
    p2 = store.create_playlist("Défense", [t[1], t[0]])
    assert [x.id for x in store.playlist_tags(p1)] == [t[2], t[0]]
    merged = store.merge_playlists("Causerie", [p1, p2])
    assert [x.id for x in store.playlist_tags(merged)] == [t[2], t[0], t[1]]


def test_library_from_newer_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "lib.sqlite"
    Store(path).close()
    db = sqlite3.connect(path)
    db.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")
    db.close()
    with pytest.raises(RuntimeError):
        Store(path)


def test_timecode() -> None:
    assert timecode(0, 25) == "00:00:00:00"
    assert timecode(25 * 3661 + 7, 25) == "01:01:01:07"
