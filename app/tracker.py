import os
import time
from datetime import date, datetime, timedelta

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
        self._buffer: dict[tuple[int, str, int], float] = {}
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
        self.last_save_error: str | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def set_tracked(self, mapping: dict[str, int]) -> None:
        self._tracked = {os.path.normcase(k): v for k, v in mapping.items()}

    def forget_app(self, app_id: int) -> None:
        for key in [k for k in self._buffer if k[0] == app_id]:
            del self._buffer[key]
        for path in [p for p, aid in self._tracked.items() if aid == app_id]:
            del self._tracked[path]
        self._idle_apps.discard(app_id)
        self.current_ids.discard(app_id)
        if self.current_app_id == app_id:
            self.current_app_id = None

    def switch_db(self, db: Database) -> None:
        self.flush()
        self._buffer.clear()
        self.db = db
        self._tracked = {}
        self._threshold_sec = max(1, db.get_int("idle_threshold_minutes", 30)) * 60
        self._bg = bool(db.get_int("background_counting", 0))
        self._running_cache = (0.0, set())
        self._idle = False
        self._idle_apps = set()
        self._idle_since = 0.0
        self.current_app_id = None
        self.current_ids = set()
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
        today = date.today().isoformat()
        total = 0.0
        for (aid, day, _hour), secs in self._buffer.items():
            if aid == app_id and day == today:
                total += secs
        return int(total)

    @property
    def is_idle(self) -> bool:
        return self.last_idle_seconds > GRACE_SECONDS

    def start(self) -> None:
        self._last_active_at = time.monotonic()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.flush()

    def _credit_interval(self, app_id: int, start_epoch: float, end_epoch: float) -> None:
        if end_epoch <= start_epoch:
            return
        t = start_epoch
        guard = 0
        while t < end_epoch and guard < 10000:
            guard += 1
            dt_local = datetime.fromtimestamp(t)
            day = dt_local.date().isoformat()
            hour = dt_local.hour
            next_hour = (
                dt_local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            ).timestamp()
            seg_end = min(end_epoch, next_hour)
            secs = seg_end - t
            if secs > 0:
                key = (app_id, day, hour)
                self._buffer[key] = self._buffer.get(key, 0.0) + secs
            t = seg_end

    def flush(self) -> None:
        if not self._buffer:
            self._last_flush = time.monotonic()
            return
        entries: list[tuple[int, str, int, int]] = []
        for (app_id, day, hour), secs in self._buffer.items():
            whole = int(secs)
            if whole > 0:
                entries.append((app_id, day, hour, whole))
        if entries:
            try:
                self.db.add_activity_batch(entries)
                self.last_save_error = None
                for (app_id, day, hour), secs in list(self._buffer.items()):
                    whole = int(secs)
                    if whole > 0:
                        rem = secs - whole
                        if rem > 0.001:
                            self._buffer[(app_id, day, hour)] = rem
                        else:
                            del self._buffer[(app_id, day, hour)]
            except Exception:
                from . import config

                self.last_save_error = "flush"
                config.log_error("Tracker.flush (данные сохранены в буфере, повтор при следующем сбросе)")
        self._last_flush = time.monotonic()

    def _on_tick(self) -> None:
        try:
            self._tick_impl()
        except Exception:
            from . import config

            config.log_error("Tracker._on_tick")

    def _tick_impl(self) -> None:
        now = time.monotonic()
        now_wall = time.time()
        today = date.today()
        if today != self._day:
            self.flush()
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
                        self._credit_interval(app_id, now_wall - gap, now_wall)
                self._idle = False
                self._idle_apps = set()
                self._last_active_at = now
            else:
                dt = min(now - self._last_active_at, GRACE_SECONDS + 2.0)
                fg_id, ids = self._resolve_apps()
                for app_id in ids:
                    self._credit_interval(app_id, now_wall - dt, now_wall)
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
