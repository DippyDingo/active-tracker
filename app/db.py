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
    category_id: int | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    exe_path TEXT NOT NULL UNIQUE COLLATE NOCASE,
    icon BLOB,
    sort_order INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS stats (
    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    day TEXT NOT NULL,
    seconds INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (app_id, day)
);
CREATE TABLE IF NOT EXISTS hours (
    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    day TEXT NOT NULL,
    hour INTEGER NOT NULL,
    seconds INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (app_id, day, hour)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);
"""


class Database:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(apps)")}
        if "sort_order" not in cols:
            self._conn.execute(
                "ALTER TABLE apps ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
            )
            self._conn.commit()
        if "category_id" not in cols:
            self._conn.execute(
                "ALTER TABLE apps ADD COLUMN category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL"
            )
            self._conn.commit()

    @staticmethod
    def validate(path) -> bool:
        try:
            p = Path(path)
            if not p.is_file():
                return False
            conn = sqlite3.connect(str(p))
            try:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                names = {r[0] for r in rows}
                return {"apps", "stats", "settings"} <= names
            finally:
                conn.close()
        except Exception:
            return False

    def export_to(self, path) -> bool:
        try:
            target = str(Path(path).resolve())
            self._conn.commit()
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if Path(target).exists():
                Path(target).unlink()
            self._conn.execute("VACUUM INTO ?", (target,))
            return True
        except Exception:
            return False

    def close(self) -> None:
        self._conn.close()

    def add_app(self, name: str, exe_path: str, icon: bytes | None = None) -> int | None:
        try:
            with self._conn:
                cur = self._conn.execute(
                    """INSERT INTO apps(name, exe_path, icon, sort_order)
                       VALUES(?,?,?, COALESCE((SELECT MAX(sort_order) FROM apps), 0) + 1)""",
                    (name, exe_path, sqlite3.Binary(icon) if icon else None),
                )
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def set_apps_order(self, app_ids: list[int]) -> None:
        with self._conn:
            for idx, app_id in enumerate(app_ids):
                self._conn.execute(
                    "UPDATE apps SET sort_order=? WHERE id=?", (idx + 1, app_id)
                )

    def remove_app(self, app_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM apps WHERE id=?", (app_id,))
            self._conn.execute("DELETE FROM stats WHERE app_id=?", (app_id,))

    def list_apps(self) -> list[AppRow]:
        rows = self._conn.execute(
            """SELECT id, name, exe_path, icon, category_id
               FROM apps ORDER BY sort_order, name COLLATE NOCASE"""
        ).fetchall()
        return [
            AppRow(
                r["id"],
                r["name"],
                r["exe_path"],
                bytes(r["icon"]) if r["icon"] else None,
                r["category_id"],
            )
            for r in rows
        ]

    def set_app_category(self, app_id: int, category_id: int | None) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE apps SET category_id=? WHERE id=?", (category_id, app_id)
            )

    def create_category(self, name: str) -> int:
        with self._conn:
            cur = self._conn.execute(
                """INSERT INTO categories(name, sort_order)
                   VALUES(?, COALESCE((SELECT MAX(sort_order) FROM categories), 0) + 1)""",
                (name,),
            )
        return int(cur.lastrowid)

    def list_categories(self) -> list[tuple[int, str]]:
        rows = self._conn.execute(
            "SELECT id, name FROM categories ORDER BY sort_order, name COLLATE NOCASE"
        )
        return [(r["id"], r["name"]) for r in rows]

    def rename_category(self, category_id: int, name: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE categories SET name=? WHERE id=?", (name, category_id)
            )

    def delete_category(self, category_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE apps SET category_id=NULL WHERE category_id=?", (category_id,)
            )
            self._conn.execute("DELETE FROM categories WHERE id=?", (category_id,))

    def add_time(self, app_id: int, day: str, seconds: int) -> None:
        if seconds <= 0:
            return
        with self._conn:
            self._conn.execute(
                """INSERT INTO stats(app_id, day, seconds) VALUES(?,?,?)
                   ON CONFLICT(app_id, day) DO UPDATE SET seconds = seconds + excluded.seconds""",
                (app_id, day, seconds),
            )

    def add_hour(self, app_id: int, day: str, hour: int, seconds: int) -> None:
        if seconds <= 0:
            return
        with self._conn:
            self._conn.execute(
                """INSERT INTO hours(app_id, day, hour, seconds) VALUES(?,?,?,?)
                   ON CONFLICT(app_id, day, hour) DO UPDATE SET seconds = seconds + excluded.seconds""",
                (app_id, day, hour, seconds),
            )

    def get_hours(self, app_id: int, day: str) -> list[int]:
        rows = self._conn.execute(
            "SELECT hour, seconds FROM hours WHERE app_id=? AND day=?", (app_id, day)
        )
        out = [0] * 24
        for r in rows:
            if 0 <= r["hour"] <= 23:
                out[r["hour"]] += r["seconds"]
        return out

    def get_day_stats(self, day: str) -> dict[int, int]:
        rows = self._conn.execute("SELECT app_id, seconds FROM stats WHERE day=?", (day,))
        return {r["app_id"]: r["seconds"] for r in rows}

    def query_app_stats(
        self, app_id: int, start_day: str | None = None, end_day: str | None = None
    ) -> list[tuple[str, int]]:
        sql = "SELECT day, seconds FROM stats WHERE app_id=?"
        args: list = [app_id]
        if start_day is not None:
            sql += " AND day >= ?"
            args.append(start_day)
        if end_day is not None:
            sql += " AND day <= ?"
            args.append(end_day)
        return [(r["day"], r["seconds"]) for r in self._conn.execute(sql, args)]

    def get_min_day(self) -> str | None:
        row = self._conn.execute("SELECT MIN(day) AS day FROM stats").fetchone()
        return row["day"] if row else None

    def query_stats(
        self, start_day: str | None = None, end_day: str | None = None
    ) -> list[tuple[int, str, int]]:
        sql = "SELECT app_id, day, seconds FROM stats"
        where = []
        args = []
        if start_day is not None:
            where.append("day >= ?")
            args.append(start_day)
        if end_day is not None:
            where.append("day <= ?")
            args.append(end_day)
        if where:
            sql += " WHERE " + " AND ".join(where)
        return [(r["app_id"], r["day"], r["seconds"]) for r in self._conn.execute(sql, args)]

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
