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
_UPDATER_VBS = r"""On Error Resume Next
Set args = WScript.Arguments
If args.Count < 5 Then WScript.Quit 1
pid = CLng(args(0))
oldExe = args(1)
newExe = args(2)
mode = args(3)
logPath = args(4)
Set fso = CreateObject("Scripting.FileSystemObject")
Set oShell = CreateObject("WScript.Shell")
elapsed = 0
Do While elapsed < 60
    If Not ProcessExists(pid) Then Exit Do
    WScript.Sleep 1000
    elapsed = elapsed + 1
Loop
If ProcessExists(pid) Then
    Log "timeout waiting for pid " & pid & "; aborted, nothing changed"
    WScript.Quit 0
End If
bak = oldExe & ".old"
ok = False
For attempt = 1 To 8
    Err.Clear
    If fso.FileExists(bak) Then fso.DeleteFile bak, True
    If Err.Number = 0 Then
        fso.MoveFile oldExe, bak
        If Err.Number = 0 Then
            fso.MoveFile newExe, oldExe
            If Err.Number = 0 Then
                ok = True
                Exit For
            Else
                Log "move new->old failed: " & Err.Description
                fso.MoveFile bak, oldExe
            End If
        Else
            Log "move old->backup failed: " & Err.Description
        End If
    Else
        Log "remove old backup failed: " & Err.Description
    End If
    WScript.Sleep 1000
Next
If Not ok Then
    Log "swap failed after retries; aborted"
    WScript.Quit 1
End If
If LCase(mode) = "restart" Then
    oShell.Run Chr(34) & oldExe & Chr(34), 1, False
End If
Log "update applied: " & oldExe
WScript.Quit 0
Function ProcessExists(p)
    On Error Resume Next
    ProcessExists = False
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If
    Set procs = wmi.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE ProcessId=" & p)
    ProcessExists = (procs.Count > 0)
End Function
Sub Log(msg)
    On Error Resume Next
    Dim lf
    Set lf = CreateObject("Scripting.FileSystemObject").OpenTextFile(logPath, 8, True)
    If Err.Number = 0 Then
        lf.WriteLine Now & " | " & msg
        lf.Close
    End If
    Err.Clear
End Sub
"""

_ROLLBACK_VBS = r"""On Error Resume Next
Set args = WScript.Arguments
If args.Count < 3 Then WScript.Quit 1
pid = CLng(args(0))
exe = args(1)
logPath = args(2)
bak = exe & ".old"
Set fso = CreateObject("Scripting.FileSystemObject")
Set oShell = CreateObject("WScript.Shell")
elapsed = 0
Do While elapsed < 60
    If Not ProcessExists(pid) Then Exit Do
    WScript.Sleep 1000
    elapsed = elapsed + 1
Loop
If ProcessExists(pid) Then WScript.Quit 0
If Not fso.FileExists(bak) Then
    Log "rollback: no backup found"
    WScript.Quit 1
End If
ok = False
For attempt = 1 To 8
    Err.Clear
    fso.DeleteFile exe, True
    fso.MoveFile bak, exe
    If Err.Number = 0 Then
        ok = True
        Exit For
    End If
    Log "rollback attempt failed: " & Err.Description
    WScript.Sleep 1000
Next
If Not ok Then
    Log "rollback failed after retries"
    WScript.Quit 1
End If
oShell.Run Chr(34) & exe & Chr(34), 1, False
Log "rollback applied: " & exe
WScript.Quit 0
Function ProcessExists(p)
    On Error Resume Next
    ProcessExists = False
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If
    Set procs = wmi.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE ProcessId=" & p)
    ProcessExists = (procs.Count > 0)
End Function
Sub Log(msg)
    On Error Resume Next
    Dim lf
    Set lf = CreateObject("Scripting.FileSystemObject").OpenTextFile(logPath, 8, True)
    If Err.Number = 0 Then
        lf.WriteLine Now & " | " & msg
        lf.Close
    End If
    Err.Clear
End Sub
"""


def write_updater_script() -> Path:
    """VBS-помощник: WScript — GUI-подсистема, консольных окон не бывает."""
    script = config.app_dir() / "nodexy_update.vbs"
    script.write_text(_UPDATER_VBS, encoding="ascii")
    return script


def write_rollback_script() -> Path:
    script = config.app_dir() / "nodexy_rollback.vbs"
    script.write_text(_ROLLBACK_VBS, encoding="ascii")
    return script


def launch_script(script: Path, args: list[str]) -> bool:
    """Полностью скрытый запуск помощника.

    //B — батч-режим WScript: запрещены ЛЮБЫЕ окна (ошибки, запросы).
    //nologo — без баннера. Потоки заглушены. CREATE_NO_WINDOW на всякий случай.
    """
    try:
        subprocess.Popen(
            ["wscript.exe", "//B", "//nologo", str(script), *args],
            creationflags=0x08000000,  # CREATE_NO_WINDOW
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return True
    except Exception:
        config.log_error("updater.launch_script")
        return False


def update_log_path() -> Path:
    return config.app_dir() / "nodexy_update.log"


def cleanup_orphan_helpers() -> int:
    """Гасит осиротевшие процессы помощников старых версий (только свои)."""
    try:
        import psutil
    except Exception:
        return 0
    app_dir_str = str(config.app_dir()).lower()
    markers = ("nodexy_update", "nodexy_rollback")
    my_pid = os.getpid()
    killed = 0

    def _kill(proc) -> None:
        nonlocal killed
        try:
            proc.kill()
            killed += 1
        except Exception:
            pass

    roots = []
    finds = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] == my_pid:
                continue
            cmdline_list = proc.info["cmdline"] or []
            cmdline = " ".join(cmdline_list).lower()
            if cmdline and (app_dir_str in cmdline or any(m in cmdline for m in markers)):
                roots.append(proc)
                continue
            # Осиротевший `find "<pid>"` от старой связки tasklist|find:
            # имя совпадает, единственный аргумент — число.
            name = (proc.info["name"] or "").lower()
            if name in ("find.exe", "find") and len(cmdline_list) == 2:
                if cmdline_list[1].strip().strip('"').isdigit():
                    finds.append(proc)
        except Exception:
            continue

    for proc in roots:
        try:
            children = proc.children(recursive=True)
        except Exception:
            children = []
        _kill(proc)
        for child in children:
            _kill(child)
    for proc in finds:
        _kill(proc)

    # Старые скрипты больше не нужны.
    for name in ("nodexy_update.bat", "nodexy_rollback.bat",
                 "nodexy_update.vbs", "nodexy_rollback.vbs"):
        _remove_quiet(config.app_dir() / name)
    return killed


_APPLY_SCHEDULED = False


def schedule_apply(restart: bool) -> bool:
    """Запускает скрытый помощник: дождётся завершения процесса и заменит exe."""
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
        script = write_updater_script()
    except Exception:
        config.log_error("updater.write_updater_script")
        return False
    mode = "restart" if restart else "once"
    ok = launch_script(
        script, [str(os.getpid()), str(exe), str(new_exe), mode, str(update_log_path())]
    )
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

    # Самолечение: гасим осиротевшие процессы помощников старых версий.
    cleanup_orphan_helpers()

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
            # Предыдущая попытка применения не удалась. Считаем попытки;
            # помощник запускается только при выходе, при старте — никаких окон.
            attempts = int(pending.get("attempts", 0)) + 1
            if attempts >= MAX_REPLACE_ATTEMPTS:
                result["failed_url"] = str(pending.get("page") or "")
                cancel_pending()
            else:
                pending["attempts"] = attempts
                set_pending(pending)
        else:
            # Версия не новее текущей (ручная замена/откат) — ожидание устарело.
            cancel_pending()

    if getattr(sys, "frozen", False):
        boot, need_rollback = boot_step(cfg.get("boot_check"), APP_VERSION)
        cfg["boot_check"] = boot
        config.write_config(cfg)
        if need_rollback:
            exe = current_exe()
            bak = backup_path()
            if exe and bak and bak.is_file():
                try:
                    script = write_rollback_script()
                    if launch_script(script, [str(os.getpid()), str(exe), str(update_log_path())]):
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
