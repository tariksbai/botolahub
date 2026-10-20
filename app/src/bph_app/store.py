"""Bibliothèque locale : matchs, codes, tags et playlists dans SQLite (tâches P02, P06, P07).

Aucune dépendance à Qt : ce module se teste seul. Toutes les positions sont des numéros
d'image, jamais des secondes — c'est ce qui rend le tagging reproductible.

Le schéma évolue par migrations numérotées (MIGRATIONS) ; `PRAGMA user_version` garde
le numéro de la dernière migration appliquée.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

MIGRATIONS: list[str] = [
    # 1 — schéma initial
    """
    CREATE TABLE clients (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE matches (
        id INTEGER PRIMARY KEY,
        client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
        season TEXT NOT NULL DEFAULT '',
        competition TEXT NOT NULL DEFAULT '',
        match_date TEXT NOT NULL DEFAULT '',
        home_team TEXT NOT NULL DEFAULT '',
        away_team TEXT NOT NULL DEFAULT '',
        home_score INTEGER,
        away_score INTEGER,
        video_path TEXT NOT NULL,
        source_path TEXT NOT NULL,
        fps_num INTEGER NOT NULL,
        fps_den INTEGER NOT NULL,
        frame_count INTEGER NOT NULL,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE INDEX matches_by_season ON matches(season, competition);
    CREATE TABLE codes (
        id INTEGER PRIMARY KEY,
        label TEXT NOT NULL,
        shortcut TEXT NOT NULL DEFAULT '',
        color TEXT NOT NULL DEFAULT '#1f6feb',
        lead_seconds REAL NOT NULL DEFAULT 5,
        lag_seconds REAL NOT NULL DEFAULT 5,
        position INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE tags (
        id INTEGER PRIMARY KEY,
        match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
        code_id INTEGER REFERENCES codes(id) ON DELETE SET NULL,
        label TEXT NOT NULL,
        frame INTEGER NOT NULL,
        frame_in INTEGER NOT NULL,
        frame_out INTEGER NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        CHECK (frame_in <= frame AND frame <= frame_out)
    );
    CREATE INDEX tags_by_match ON tags(match_id, frame);
    CREATE TABLE playlists (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE TABLE playlist_items (
        playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
        tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        PRIMARY KEY (playlist_id, tag_id)
    );
    """,
]

DEFAULT_CODES = [
    ("Tir", "1", "#d1242f"),
    ("But", "2", "#8250df"),
    ("Passe clé", "3", "#1f6feb"),
    ("Récupération", "4", "#1a7f37"),
    ("Perte de balle", "5", "#bc4c00"),
    ("Faute", "6", "#9a6700"),
    ("Corner", "7", "#0969da"),
    ("Coup franc", "8", "#6e7781"),
    ("Hors-jeu", "9", "#cf222e"),
    ("Pressing", "0", "#2da44e"),
]


@dataclass(frozen=True)
class Match:
    id: int
    client: str
    season: str
    competition: str
    match_date: str
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    video_path: str
    source_path: str
    fps_num: int
    fps_den: int
    frame_count: int
    width: int
    height: int

    @property
    def fps(self) -> float:
        return self.fps_num / self.fps_den

    @property
    def title(self) -> str:
        score = ""
        if self.home_score is not None and self.away_score is not None:
            score = f" {self.home_score}-{self.away_score}"
        teams = f"{self.home_team or '?'} – {self.away_team or '?'}"
        return f"{teams}{score}"


@dataclass(frozen=True)
class Code:
    id: int
    label: str
    shortcut: str
    color: str
    lead_seconds: float
    lag_seconds: float
    position: int


@dataclass(frozen=True)
class Tag:
    id: int
    match_id: int
    code_id: int | None
    label: str
    frame: int
    frame_in: int
    frame_out: int
    note: str
    color: str


@dataclass(frozen=True)
class Playlist:
    id: int
    name: str
    count: int


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self.db:
            yield self.db

    @property
    def schema_version(self) -> int:
        return int(self.db.execute("PRAGMA user_version").fetchone()[0])

    def _migrate(self) -> None:
        current = self.schema_version
        if current > len(MIGRATIONS):
            raise RuntimeError(
                f"bibliothèque créée par une version plus récente (schéma {current}) : mettre à jour l'application"
            )
        for number, script in enumerate(MIGRATIONS[current:], start=current + 1):
            with self._tx() as db:
                db.executescript("BEGIN;" + script + f"PRAGMA user_version = {number};")
        if current == 0:
            self.reset_codes()

    # --- clients ----------------------------------------------------------------
    def client_id(self, name: str) -> int | None:
        name = name.strip()
        if not name:
            return None
        with self._tx() as db:
            db.execute("INSERT OR IGNORE INTO clients(name) VALUES (?)", (name,))
            return int(db.execute("SELECT id FROM clients WHERE name = ?", (name,)).fetchone()[0])

    def clients(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT name FROM clients ORDER BY name")]

    # --- matchs -----------------------------------------------------------------
    def add_match(self, *, video_path: str, source_path: str, fps_num: int, fps_den: int, frame_count: int,
                  width: int, height: int, client: str = "", season: str = "", competition: str = "",
                  match_date: str = "", home_team: str = "", away_team: str = "",
                  home_score: int | None = None, away_score: int | None = None) -> int:
        cid = self.client_id(client)
        with self._tx() as db:
            cur = db.execute(
                """INSERT INTO matches(client_id, season, competition, match_date, home_team, away_team,
                   home_score, away_score, video_path, source_path, fps_num, fps_den, frame_count, width,
                   height, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (cid, season, competition, match_date, home_team, away_team, home_score, away_score,
                 video_path, source_path, fps_num, fps_den, frame_count, width, height, time.time()),
            )
            return int(cur.lastrowid or 0)

    def update_match(self, match_id: int, **fields: object) -> None:
        allowed = {"season", "competition", "match_date", "home_team", "away_team", "home_score", "away_score"}
        if "client" in fields:
            fields["client_id"] = self.client_id(str(fields.pop("client")))
            allowed.add("client_id")
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"champs non modifiables : {sorted(bad)}")
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._tx() as db:
            db.execute(f"UPDATE matches SET {cols} WHERE id = ?", (*fields.values(), match_id))

    def delete_match(self, match_id: int) -> None:
        with self._tx() as db:
            db.execute("DELETE FROM matches WHERE id = ?", (match_id,))

    _MATCH_SELECT = """SELECT m.*, COALESCE(c.name, '') AS client FROM matches m
                       LEFT JOIN clients c ON c.id = m.client_id"""

    @staticmethod
    def _match(row: sqlite3.Row) -> Match:
        return Match(**{k: row[k] for k in Match.__dataclass_fields__})

    def match(self, match_id: int) -> Match:
        row = self.db.execute(self._MATCH_SELECT + " WHERE m.id = ?", (match_id,)).fetchone()
        if row is None:
            raise KeyError(match_id)
        return self._match(row)

    def matches(self, search: str = "", client: str = "", season: str = "") -> list[Match]:
        where, args = [], []
        if search:
            where.append("(m.home_team LIKE ? OR m.away_team LIKE ? OR m.competition LIKE ?)")
            args += [f"%{search}%"] * 3
        if client:
            where.append("c.name = ?")
            args.append(client)
        if season:
            where.append("m.season = ?")
            args.append(season)
        sql = self._MATCH_SELECT + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY m.match_date DESC, m.id DESC"
        return [self._match(r) for r in self.db.execute(sql, args)]

    def seasons(self) -> list[str]:
        return [r[0] for r in self.db.execute(
            "SELECT DISTINCT season FROM matches WHERE season != '' ORDER BY season DESC")]

    # --- grille de codes ----------------------------------------------------------
    def codes(self) -> list[Code]:
        return [Code(**dict(r)) for r in self.db.execute("SELECT * FROM codes ORDER BY position, id")]

    def save_codes(self, codes: list[tuple[int | None, str, str, str, float, float]]) -> None:
        """Remplace la grille : (id ou None, libellé, raccourci, couleur, avant s, après s)."""
        keys = [c[2].upper() for c in codes if c[2]]
        if len(keys) != len(set(keys)):
            raise ValueError("deux codes utilisent le même raccourci")
        with self._tx() as db:
            keep = [c[0] for c in codes if c[0] is not None]
            db.execute(f"DELETE FROM codes WHERE id NOT IN ({','.join('?' * len(keep)) or 'NULL'})", keep)
            for pos, (cid, label, key, color, lead, lag) in enumerate(codes):
                if cid is None:
                    db.execute("INSERT INTO codes(label, shortcut, color, lead_seconds, lag_seconds, position)"
                               " VALUES (?,?,?,?,?,?)", (label, key.upper(), color, lead, lag, pos))
                else:
                    db.execute("UPDATE codes SET label=?, shortcut=?, color=?, lead_seconds=?, lag_seconds=?,"
                               " position=? WHERE id=?", (label, key.upper(), color, lead, lag, pos, cid))

    def reset_codes(self) -> None:
        with self._tx() as db:
            db.execute("DELETE FROM codes")
            for pos, (label, key, color) in enumerate(DEFAULT_CODES):
                db.execute("INSERT INTO codes(label, shortcut, color, position) VALUES (?,?,?,?)",
                           (label, key, color, pos))

    # --- tags -------------------------------------------------------------------
    def add_tag(self, match: Match, code: Code, frame: int, note: str = "") -> int:
        frame = max(0, min(frame, match.frame_count - 1))
        frame_in = max(0, frame - round(code.lead_seconds * match.fps))
        frame_out = min(match.frame_count - 1, frame + round(code.lag_seconds * match.fps))
        return self.add_raw_tag(match.id, code.id, code.label, frame, frame_in, frame_out, note)

    def add_raw_tag(self, match_id: int, code_id: int | None, label: str, frame: int, frame_in: int,
                    frame_out: int, note: str = "") -> int:
        with self._tx() as db:
            cur = db.execute(
                "INSERT INTO tags(match_id, code_id, label, frame, frame_in, frame_out, note, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (match_id, code_id, label, frame, frame_in, frame_out, note, time.time()),
            )
            return int(cur.lastrowid or 0)

    def update_tag(self, tag_id: int, *, frame_in: int | None = None, frame_out: int | None = None,
                   note: str | None = None) -> None:
        sets, args = [], []
        for col, val in (("frame_in", frame_in), ("frame_out", frame_out), ("note", note)):
            if val is not None:
                sets.append(f"{col} = ?")
                args.append(val)
        if sets:
            with self._tx() as db:
                db.execute(f"UPDATE tags SET {', '.join(sets)} WHERE id = ?", (*args, tag_id))

    def delete_tag(self, tag_id: int) -> None:
        with self._tx() as db:
            db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

    def tags(self, match_id: int) -> list[Tag]:
        rows = self.db.execute(
            """SELECT t.*, COALESCE(c.color, '#6e7781') AS color FROM tags t
               LEFT JOIN codes c ON c.id = t.code_id WHERE t.match_id = ? ORDER BY t.frame, t.id""",
            (match_id,),
        )
        return [Tag(**{k: r[k] for k in Tag.__dataclass_fields__}) for r in rows]

    # --- playlists ----------------------------------------------------------------
    def create_playlist(self, name: str, tag_ids: list[int] | None = None) -> int:
        with self._tx() as db:
            pid = int(db.execute("INSERT INTO playlists(name, created_at) VALUES (?, ?)",
                                 (name, time.time())).lastrowid or 0)
        if tag_ids:
            self.set_playlist_items(pid, tag_ids)
        return pid

    def playlists(self) -> list[Playlist]:
        rows = self.db.execute(
            """SELECT p.id, p.name, COUNT(i.tag_id) AS count FROM playlists p
               LEFT JOIN playlist_items i ON i.playlist_id = p.id GROUP BY p.id ORDER BY p.created_at""")
        return [Playlist(r["id"], r["name"], r["count"]) for r in rows]

    def set_playlist_items(self, playlist_id: int, tag_ids: list[int]) -> None:
        with self._tx() as db:
            db.execute("DELETE FROM playlist_items WHERE playlist_id = ?", (playlist_id,))
            for pos, tid in enumerate(dict.fromkeys(tag_ids)):  # sans doublon, ordre conservé
                db.execute("INSERT INTO playlist_items VALUES (?, ?, ?)", (playlist_id, tid, pos))

    def playlist_tags(self, playlist_id: int) -> list[Tag]:
        rows = self.db.execute(
            """SELECT t.*, COALESCE(c.color, '#6e7781') AS color FROM playlist_items i
               JOIN tags t ON t.id = i.tag_id LEFT JOIN codes c ON c.id = t.code_id
               WHERE i.playlist_id = ? ORDER BY i.position""",
            (playlist_id,),
        )
        return [Tag(**{k: r[k] for k in Tag.__dataclass_fields__}) for r in rows]

    def rename_playlist(self, playlist_id: int, name: str) -> None:
        with self._tx() as db:
            db.execute("UPDATE playlists SET name = ? WHERE id = ?", (name, playlist_id))

    def delete_playlist(self, playlist_id: int) -> None:
        with self._tx() as db:
            db.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))

    def merge_playlists(self, name: str, playlist_ids: list[int]) -> int:
        tag_ids = [t.id for pid in playlist_ids for t in self.playlist_tags(pid)]
        return self.create_playlist(name, tag_ids)


def timecode(frame: int, fps: float) -> str:
    """HH:MM:SS:FF à partir d'un numéro d'image."""
    fps_int = max(1, round(fps))
    seconds, ff = divmod(max(0, frame), fps_int)
    hh, rem = divmod(seconds, 3600)
    mm, ss = divmod(rem, 60)
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"
