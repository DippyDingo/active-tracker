import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import config
from .version import APP_VERSION, RELEASES_URL

CHECK_DELAY_MS = 20_000
CHECK_INTERVAL_MS = 12 * 3600 * 1000
SNOOZE_DAYS = 3
MAX_REPLACE_ATTEMPTS = 3
BOOT_FAIL_LIMIT = 3
HTTP_TIMEOUT = 25


# ---------------------------------------------------------------- versions
def parse_version(text) -> tuple[int, ...] | None:
    if not text:
        return None
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", str(text), re.I)
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split("."))


def _norm(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[tuple, tuple]:
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)), b + (0,) * (n - len(b))


def is_newer(candidate: str, current: str = APP_VERSION) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    if not a or not b:
        return False
    a, b = _norm(a, b)
    return a > b


def format_size(size: int | None) -> str:
    if not size or size <= 0:
        return ""
    mb = size / (1024 * 1024)
    return f"{mb:.1f} МБ" if mb >= 1 else f"{size // 1024} КБ"


# ---------------------------------------------------------------- releases
@dataclass
class ReleaseInfo:
    tag: str
    name: str
    body: str
    published_at: str
    html_url: str
    asset_name: str | None = None
    asset_url: str | None = None
    asset_size: int | None = None
    sha256: str | None = None


def parse_sha256(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"(?:sha\s*256|sha256)[^\w]{0,3}([0-9a-fA-F]{64})", text, re.I)
    if m:
        return m.group(1).lower()
    m = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    return m.group(1).lower() if m else None


def parse_release(data: dict) -> ReleaseInfo | None:
    if not isinstance(data, dict):
        return None
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name") or ""
    if parse_version(tag) is None:
        return None
    asset_name = asset_url = None
    asset_size = None
    for asset in data.get("assets") or []:
        name = asset.get("name") or ""
        if name.lower().endswith(".exe"):
            asset_name = name
            asset_url = asset.get("browser_download_url")
            asset_size = asset.get("size")
            break
    body = data.get("body") or ""
    return ReleaseInfo(
        tag=tag,
        name=data.get("name") or tag,
        body=body,
        published_at=(data.get("published_at") or "")[:10],
        html_url=data.get("html_url") or "",
        asset_name=asset_name,
        asset_url=asset_url,
        asset_size=int(asset_size) if asset_size else None,
        sha256=parse_sha256(body),
    )


def select_update(releases: list[dict], current: str = APP_VERSION) -> tuple[ReleaseInfo | None, str]:
    """Последний опубликованный релиз с exe + суммарные заметки всех версий новее текущей."""
    parsed: list[ReleaseInfo] = []
    for data in releases or []:
        info = parse_release(data)
        if info is not None:
            parsed.append(info)
    if not parsed:
        return None, ""
    parsed.sort(key=lambda r: parse_version(r.tag) or (0,), reverse=True)
    latest = parsed[0]
    if not is_newer(latest.tag, current):
        return None, ""
    newer = [r for r in parsed if is_newer(r.tag, current)]
    if len(newer) == 1:
        notes = newer[0].body.strip()
    else:
        parts = []
        for r in newer:
            title = r.body.strip() or r.name
            parts.append(f"{r.tag}\n{title}" if not title.startswith(r.tag) else title)
        notes = "\n\n".join(parts)
    return latest, notes


def fetch_releases(timeout: int = HTTP_TIMEOUT) -> list[dict]:
    req = urllib.request.Request(
        RELEASES_URL,
        headers={
            "User-Agent": "Nodexy",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------- threads
class CheckTask(QThread):
    ok = Signal(object)
    error = Signal(str)

    def run(self) -> None:
        try:
            self.ok.emit(fetch_releases())
        except Exception as e:
            self.error.emit(str(e))


class DownloadTask(QThread):
    progress = Signal(int, int)
    ok = Signal(str)
    error = Signal(str)

    def __init__(self, url: str, dest: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.dest = dest
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        tmp = self.dest + ".part"
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": "Nodexy"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                got = 0
                Path(tmp).parent.mkdir(parents=True, exist_ok=True)
                with open(tmp, "wb") as f:
                    while True:
                        if self._cancel:
                            raise InterruptedError()
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        self.progress.emit(got, total)
            os.replace(tmp, self.dest)
            self.ok.emit(self.dest)
        except InterruptedError:
            _remove_quiet(tmp)
            self.error.emit("cancelled")
        except Exception as e:
            _remove_quiet(tmp)
            self.error.emit(str(e))


def _remove_quiet(path) -> None:
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------- integrity
def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_file(path, expected_size: int | None, expected_sha: str | None) -> tuple[bool, str]:
    try:
        p = Path(path)
        if not p.is_file():
            return False, "файл не найден"
        if expected_size and p.stat().st_size != int(expected_size):
            return False, "размер не совпадает"
        if expected_sha and sha256_file(p) != expected_sha.lower():
            return False, "sha256 не совпадает"
        return True, ""
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------- state (config.json)
def get_pending() -> dict | None:
    data = config.read_config().get("update_pending")
    return data if isinstance(data, dict) and data.get("version") else None


def set_pending(info: dict | None) -> None:
    cfg = config.read_config()
    if info is None:
        cfg.pop("update_pending", None)
    else:
        cfg["update_pending"] = info
    config.write_config(cfg)


def cancel_pending() -> None:
    pending = get_pending()
    if pending and pending.get("file"):
        _remove_quiet(pending["file"])
    set_pending(None)


def get_last_update() -> dict | None:
    data = config.read_config().get("last_update")
    return data if isinstance(data, dict) and data.get("version") else None


def set_last_update(version: str, notes: str) -> None:
    cfg = config.read_config()
    cfg["last_update"] = {"version": version, "notes": notes}
    config.write_config(cfg)


def clear_last_update() -> None:
    cfg = config.read_config()
    cfg.pop("last_update", None)
    config.write_config(cfg)


# ---------------------------------------------------------------- snooze (чистые функции)
def make_snooze(version: str, now: date | None = None) -> str:
    return f"{version}|{(now or date.today()).isoformat()}"


def snooze_active(snooze_value: str | None, version: str, now: date | None = None) -> bool:
    if not snooze_value or "|" not in snooze_value:
        return False
    snoozed_version, day = snooze_value.split("|", 1)
    if parse_version(snoozed_version) != parse_version(version):
        return False
    try:
        start = date.fromisoformat(day)
    except ValueError:
        return False
    return (now or date.today()) - start < timedelta(days=SNOOZE_DAYS)


# ---------------------------------------------------------------- capability
def current_exe() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable)


def can_self_update() -> tuple[bool, str]:
    exe = current_exe()
    if exe is None:
        return False, "Запуск из исходников — фоновая замена недоступна"
    folder = exe.parent
    probe = folder / ".nodexy_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except Exception:
        return False, "Нет прав на запись в папку программы"
    return True, ""


def updates_dir() -> Path:
    d = config.app_dir() / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def backup_path() -> Path | None:
    exe = current_exe()
    return exe.with_name(exe.name + ".old") if exe else None


# ---------------------------------------------------------------- updater script
_BAT_TEMPLATE = """@echo off
setlocal EnableExtensions
set "PID={pid}"
set "OLD={old}"
set "NEW={new}"
set "MODE={mode}"
set /a n=0
:wait
tasklist /FI "PID eq %PID%" | find "%PID%" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    set /a n+=1
    if %n% LSS 90 goto wait
)
set "BAK=%OLD%.old"
if exist "%BAK%" del /F /Q "%BAK%" >nul 2>nul
move /Y "%OLD%" "%BAK%" >nul 2>nul
if not exist "%BAK%" goto fail
move /Y "%NEW%" "%OLD%" >nul 2>nul
if not exist "%OLD%" goto restore
if /I "%MODE%"=="restart" start "" "%OLD%"
(goto) 2>nul & del "%~f0"
exit /b 0
:restore
move /Y "%BAK%" "%OLD%" >nul 2>nul
:fail
exit /b 1
"""

_ROLLBACK_BAT_TEMPLATE = """@echo off
setlocal EnableExtensions
set "PID={pid}"
set "EXE={old}"
set "BAK=%EXE%.old"
set /a n=0
:wait
tasklist /FI "PID eq %PID%" | find "%PID%" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    set /a n+=1
    if %n% LSS 90 goto wait
)
if not exist "%BAK%" exit /b 1
del /F /Q "%EXE%" >nul 2>nul
move /Y "%BAK%" "%EXE%" >nul 2>nul
if exist "%EXE%" start "" "%EXE%"
(goto) 2>nul & del "%~f0"
exit /b 1
"""


def write_updater_script(old_exe: Path, new_exe: Path, pid: int, restart: bool) -> Path:
    script = config.app_dir() / "nodexy_update.bat"
    script.write_text(
        _BAT_TEMPLATE.format(
            pid=pid, old=old_exe, new=new_exe, mode="restart" if restart else "once"
        ),
        encoding="ascii",
    )
    return script


def write_rollback_script(exe: Path, pid: int) -> Path:
    script = config.app_dir() / "nodexy_rollback.bat"
    script.write_text(_ROLLBACK_BAT_TEMPLATE.format(pid=pid, old=exe), encoding="ascii")
    return script


def launch_script(script: Path) -> bool:
    try:
        flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
        subprocess.Popen(
            ["cmd", "/c", str(script)],
            creationflags=flags,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        config.log_error("updater.launch_script")
        return False


_APPLY_SCHEDULED = False


def schedule_apply(restart: bool) -> bool:
    """Запускает внешний апдейтер: дождётся выхода процесса и заменит exe."""
    global _APPLY_SCHEDULED
    if _APPLY_SCHEDULED and not restart:
        return True
    pending = get_pending()
    exe = current_exe()
    if not pending or exe is None:
        return False
    new_exe = Path(str(pending.get("file") or ""))
    if not new_exe.is_file():
        set_pending(None)
        return False
    try:
        script = write_updater_script(exe, new_exe, os.getpid(), restart)
    except Exception:
        config.log_error("updater.write_updater_script")
        return False
    ok = launch_script(script)
    if ok:
        _APPLY_SCHEDULED = True
    return ok


# ---------------------------------------------------------------- boot control
def boot_step(boot: dict | None, version: str) -> tuple[dict, bool]:
    """Чистая логика счётчика запусков: (новое состояние, нужен ли откат)."""
    if isinstance(boot, dict) and boot.get("version") == version:
        fails = int(boot.get("fails", 0)) + 1
    else:
        fails = 1
    return {"version": version, "fails": fails}, fails >= BOOT_FAIL_LIMIT


def startup_processing(skip_update: bool = False) -> dict:
    """Вызывается до окна. Возвращает {"plate", "notes", "rollback", "failed_url"}."""
    result = {"plate": None, "notes": None, "rollback": False, "failed_url": None}
    cfg = config.read_config()

    if skip_update:
        cancel_pending()

    pending = get_pending()
    if pending and not skip_update:
        version = str(pending.get("version") or "")
        if version == APP_VERSION:
            set_last_update(version, str(pending.get("notes") or ""))
            set_pending(None)
            result["plate"] = version
            result["notes"] = pending.get("notes") or ""
        elif is_newer(version):
            attempts = int(pending.get("attempts", 0)) + 1
            if attempts >= MAX_REPLACE_ATTEMPTS:
                result["failed_url"] = str(pending.get("page") or "")
                cancel_pending()
            else:
                pending["attempts"] = attempts
                set_pending(pending)
                # Граничный случай (выключение ПК с ожидающим обновлением):
                # применить на этой границе запусков — апдейтер дождётся выхода.
                if Path(str(pending.get("file") or "")).is_file():
                    schedule_apply(restart=False)

    if getattr(sys, "frozen", False):
        boot, need_rollback = boot_step(cfg.get("boot_check"), APP_VERSION)
        cfg["boot_check"] = boot
        config.write_config(cfg)
        if need_rollback:
            exe = current_exe()
            bak = backup_path()
            if exe and bak and bak.is_file():
                try:
                    script = write_rollback_script(exe, os.getpid())
                    if launch_script(script):
                        cfg = config.read_config()
                        cfg.pop("boot_check", None)
                        cfg["rollback_safe_mode"] = 1
                        config.write_config(cfg)
                        cancel_pending()
                        result["rollback"] = True
                except Exception:
                    config.log_error("updater.rollback")
    return result


def boot_success() -> None:
    cfg = config.read_config()
    if "boot_check" in cfg:
        cfg.pop("boot_check", None)
        config.write_config(cfg)
    bak = backup_path()
    if bak is not None:
        _remove_quiet(bak)
