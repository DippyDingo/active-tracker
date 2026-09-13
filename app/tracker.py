import os
import time
from datetime import date

from PySide6.QtCore import QObject, QTimer, Signal

from . import win32_utils
from .db import Database

GRACE_SECONDS = 5.0
FLUSH_INTERVAL = 15.0


class Tracker(QObject):
    tick = Signal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._tracked: dict[str, int] = {}
        self._buffer: dict[int, float] = {}
        self._threshold_sec = max(1, db.get_int("idle_threshold_minutes", 30)) * 60
        self._bg = bool(db.get_int("background_counting", 0))
        self._running_cache: tuple[float, set[str]] = (0.0, set())
        self._idle = False
        self._idle_apps: set[int] = set()
        self._idle_since = 0.0
        self._last_active_at = time.monotonic()
        self._last_flush = self._last_active_at
        self._day = date.today()
        self.current_app_id: int | None = None
        self.current_ids: set[int] = set()
        self.last_idle_seconds = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def set_tracked(self, mapping: dict[str, int]) -> None:
        self._tracked = {os.path.normcase(k): v for k, v in mapping.items()}

    def switch_db(self, db: Database) -> None:
        self.flush()
        self._buffer.clear()
        self.db = db
        self._threshold_sec = max(1, db.get_int("idle_threshold_minutes", 30)) * 60
        self._bg = bool(db.get_int("background_counting", 0))
        self._running_cache = (0.0, set())
        self._day = date.today()

    def threshold_minutes(self) -> int:
        return int(round(self._threshold_sec / 60))

    def set_threshold_minutes(self, minutes: int) -> None:
        minutes = max(1, int(minutes))
        self._threshold_sec = minutes * 60
        self.db.set_int("idle_threshold_minutes", minutes)

    def background_counting(self) -> bool:
        return self._bg

    def set_background_counting(self, enabled: bool) -> None:
        self._bg = bool(enabled)
        self.db.set_int("background_counting", 1 if self._bg else 0)

    def running_paths(self) -> set[str]:
        now = time.monotonic()
        ts, cached = self._running_cache
        if now - ts > 2.0:
            cached = win32_utils.running_exe_set()
            self._running_cache = (now, cached)
        return cached

    def _resolve_apps(self) -> tuple[int | None, set[int]]:
        exe = win32_utils.get_foreground_exe()
        fg_id = self._tracked.get(os.path.normcase(exe)) if exe else None
        ids: set[int] = {fg_id} if fg_id is not None else set()
        if self._bg:
            running = self.running_paths()
            for path, app_id in self._tracked.items():
                if path in running:
                    ids.add(app_id)
        return fg_id, ids

    def pending_seconds(self, app_id: int) -> int:
        return int(self._buffer.get(app_id, 0.0))

    @property
    def is_idle(self) -> bool:
        return self.last_idle_seconds > GRACE_SECONDS

    def start(self) -> None:
        self._last_active_at = time.monotonic()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.flush()

    def _credit(self, app_id: int, seconds: float) -> None:
        if seconds > 0:
            self._buffer[app_id] = self._buffer.get(app_id, 0.0) + seconds

    def flush(self, day: date | None = None) -> None:
        day = day or self._day
        stamp = day.isoformat()
        for app_id, secs in list(self._buffer.items()):
            whole = int(secs)
            if whole > 0:
                self.db.add_time(app_id, stamp, whole)
                self._buffer[app_id] = secs - whole
        self._last_flush = time.monotonic()

    def _on_tick(self) -> None:
        now = time.monotonic()
        today = date.today()
        if today != self._day:
            self.flush(self._day)
            self._day = today

        idle_s = win32_utils.get_idle_seconds()
        self.last_idle_seconds = idle_s
        self.current_app_id = None
        self.current_ids = set()

        if idle_s <= GRACE_SECONDS:
            if self._idle:
                gap = now - self._idle_since
                if 0 < gap <= self._threshold_sec and self._idle_apps:
                    for app_id in self._idle_apps:
                        self._credit(app_id, gap)
                self._idle = False
                self._idle_apps = set()
                self._last_active_at = now
            else:
                dt = min(now - self._last_active_at, GRACE_SECONDS + 2.0)
                fg_id, ids = self._resolve_apps()
                for app_id in ids:
                    self._credit(app_id, dt)
                self.current_app_id = fg_id
                self.current_ids = ids
                self._last_active_at = now
        elif not self._idle:
            self._idle = True
            self._idle_since = max(now - idle_s, self._last_active_at)
            self._idle_apps = self._resolve_apps()[1]

        if now - self._last_flush >= FLUSH_INTERVAL:
            self.flush()
        self.tick.emit()
