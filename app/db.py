import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


def default_db_path() -> Path:
    base = Path(os.getenv("APPDATA", str(Path.home()))) / "ActiveTracker"
    base.mkdir(parents=True, exist_ok=True)
    return base / "tracker.db"


@dataclass(frozen=True)
class AppRow:
    id: int
    name: str
    exe_path: str
    icon: bytes | None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    exe_path TEXT NOT NULL UNIQUE COLLATE NOCASE,
    icon BLOB,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS stats (
    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    day TEXT NOT NULL,
    seconds INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (app_id, day)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add_app(self, name: str, exe_path: str, icon: bytes | None = None) -> int | None:
        try:
            with self._conn:
                cur = self._conn.execute(
                    "INSERT INTO apps(name, exe_path, icon) VALUES(?,?,?)",
                    (name, exe_path, sqlite3.Binary(icon) if icon else None),
                )
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def remove_app(self, app_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM apps WHERE id=?", (app_id,))
            self._conn.execute("DELETE FROM stats WHERE app_id=?", (app_id,))

    def list_apps(self) -> list[AppRow]:
        rows = self._conn.execute(
            "SELECT id, name, exe_path, icon FROM apps ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [
            AppRow(r["id"], r["name"], r["exe_path"], bytes(r["icon"]) if r["icon"] else None)
            for r in rows
        ]

    def add_time(self, app_id: int, day: str, seconds: int) -> None:
        if seconds <= 0:
            return
        with self._conn:
            self._conn.execute(
                """INSERT INTO stats(app_id, day, seconds) VALUES(?,?,?)
                   ON CONFLICT(app_id, day) DO UPDATE SET seconds = seconds + excluded.seconds""",
                (app_id, day, seconds),
            )

    def get_day_stats(self, day: str) -> dict[int, int]:
        rows = self._conn.execute("SELECT app_id, seconds FROM stats WHERE day=?", (day,))
        return {r["app_id"]: r["seconds"] for r in rows}

    def get_totals(self) -> dict[int, int]:
        rows = self._conn.execute(
            "SELECT app_id, SUM(seconds) AS seconds FROM stats GROUP BY app_id"
        )
        return {r["app_id"]: r["seconds"] for r in rows}

    def get_int(self, key: str, default: int = 0) -> int:
        row = self._conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return default

    def set_int(self, key: str, value: int) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO settings(key, value) VALUES(?,?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (key, str(int(value))),
            )
