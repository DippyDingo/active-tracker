"""Загрузка иконок приложений в фоне с кэшем.

Иконки извлекаются из exe/dll (Win32) — операция недешёвая, её нельзя делать
в UI-потоке. Сервис отдаёт готовые PNG-байты сигналом.

Кэш двухуровневый:
  * в памяти (нормализованный путь + индекс + размер) — на время сеанса;
  * на диске в %APPDATA%\\ActiveTracker\\icon_cache — между запусками.

Это позволяет открывать страницу добавления мгновенно: иконки уже есть.
"""

import hashlib
import os

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from .. import config

_MEM_CACHE: dict[str, bytes] = {}
_DISK_CACHE_READY = False


def _cache_dir() -> str:
    path = config.app_dir() / "icon_cache"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return str(path)


def _key(source_path: str, icon_index: int, size: int) -> str:
    raw = f"{os.path.normcase(source_path)}|{icon_index}|{size}"
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()


def _disk_path(key: str) -> str:
    return os.path.join(_cache_dir(), key + ".png")


def get_cached(source_path: str, icon_index: int, size: int) -> bytes | None:
    key = _key(source_path, icon_index, size)
    cached = _MEM_CACHE.get(key)
    if cached is not None:
        return cached
    path = _disk_path(key)
    try:
        if os.path.isfile(path):
            with open(path, "rb") as f:
                data = f.read()
            if data:
                _MEM_CACHE[key] = data
                return data
    except OSError:
        pass
    return None


def _store(source_path: str, icon_index: int, size: int, data: bytes) -> None:
    key = _key(source_path, icon_index, size)
    _MEM_CACHE[key] = data
    try:
        with open(_disk_path(key), "wb") as f:
            f.write(data)
    except OSError:
        pass


class _Signals(QObject):
    ready = Signal(str, str, bytes)  # source_path, cache_key, png
    failed = Signal(str, str)


class _IconJob(QRunnable):
    def __init__(self, source_path: str, icon_index: int, size: int):
        super().__init__()
        self.source_path = source_path
        self.icon_index = icon_index
        self.size = size
        self.key = _key(source_path, icon_index, size)
        self.signals = _Signals()
        self.setAutoDelete(True)

    def run(self) -> None:
        cached = get_cached(self.source_path, self.icon_index, self.size)
        if cached is not None:
            self.signals.ready.emit(self.source_path, self.key, cached)
            return
        try:
            import pythoncom

            pythoncom.CoInitialize()
        except Exception:
            pass
        try:
            from ..win32_utils import extract_icon_png

            data = extract_icon_png(self.source_path, self.icon_index, self.size)
            if data:
                _store(self.source_path, self.icon_index, self.size, data)
                self.signals.ready.emit(self.source_path, self.key, data)
            else:
                self.signals.failed.emit(self.source_path, self.key)
        except Exception:
            self.signals.failed.emit(self.source_path, self.key)


class IconLoader(QObject):
    """Заказывает иконки пачкой; готовые приходят сигналом ready."""

    ready = Signal(str, str, bytes)

    def __init__(self, size: int = 28, parent=None):
        super().__init__(parent)
        self._size = size
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(2, min(6, os.cpu_count() or 4)))
        self._requested: set[str] = set()
        self._jobs: list[_IconJob] = []

    def request(self, source_path: str, icon_index: int = 0) -> None:
        if not source_path:
            return
        key = _key(source_path, icon_index, self._size)
        if key in self._requested:
            return
        self._requested.add(key)

        cached = get_cached(source_path, icon_index, self._size)
        if cached is not None:
            self.ready.emit(source_path, key, cached)
            return

        job = _IconJob(source_path, icon_index, self._size)
        job.signals.ready.connect(self.ready)
        self._jobs.append(job)
        self._pool.start(job)

    def cancel_all(self) -> None:
        self._pool.clear()
        self._requested.clear()
        self._jobs.clear()

    def shutdown(self) -> None:
        self.cancel_all()
        self._pool.waitForDone(2000)
