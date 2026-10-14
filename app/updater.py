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
from .version import APP_VERSION, GITHUB_REPO, RELEASES_URL

RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases"

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


def same_version(a: str, b: str) -> bool:
    """Версии равны с учётом префикса 'v' и разной длины ('v1.2' == '1.2.0')."""
    pa, pb = parse_version(a), parse_version(b)
    if not pa or not pb:
        return False
    pa, pb = _norm(pa, pb)
    return pa == pb


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


def is_installer_asset(name: str) -> bool:
    """Признаки ассета-установщика (в отличие от «голого» exe приложения)."""
    n = (name or "").lower()
    return any(
        marker in n for marker in ("-setup", "_setup", "setup-", "-installer", "installer")
    )


# Какую .exe-ассетку предпочитать при выборе из релиза.
# Стратегия B: скачиваем установщик и ставим его тихо; голый exe больше
# не скачивается (если установщика в релизе нет — обновления нет).
PREFER_INSTALLER_ASSET = True


def _pick_asset(assets: list[dict], prefer_installer: bool):
    """Выбирает ассет по признакам имени (порядок ассетов в API не гарантирован).

    При prefer_installer=True запасного варианта НЕТ: без установщика релиз
    считается непригодным для автообновления (иначе апдейтер скачал бы голый
    exe и попытался «обновиться» им поверх установленной копии).
    При prefer_installer=False (устаревший механизм) голый exe в приоритете,
    установщик — только если exe нет.
    """
    exes = [a for a in (assets or []) if (a.get("name") or "").lower().endswith(".exe")]
    if not exes:
        return None, None, None
    installers = [a for a in exes if is_installer_asset(a.get("name") or "")]
    plain = [a for a in exes if not is_installer_asset(a.get("name") or "")]
    if prefer_installer:
        candidates = installers
    else:
        candidates = plain or installers
    if not candidates:
        return None, None, None
    chosen = candidates[0]
    return (
        chosen.get("name"),
        chosen.get("browser_download_url"),
        chosen.get("size"),
    )


def parse_release(data: dict, prefer_installer: bool | None = None) -> ReleaseInfo | None:
    if not isinstance(data, dict):
        return None
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name") or ""
    if parse_version(tag) is None:
        return None
    if prefer_installer is None:
        prefer_installer = PREFER_INSTALLER_ASSET
    asset_name, asset_url, asset_size = _pick_asset(
        data.get("assets") or [], prefer_installer
    )
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
    """Последний опубликованный релиз с пригодным ассетом + суммарные заметки."""
    parsed: list[ReleaseInfo] = []
    for data in releases or []:
        info = parse_release(data)
        # Стратегия B: релиз без установщика не предлагает ничего — голый exe
        # больше не скачивается.
        if info is not None and info.asset_url is not None:
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


def set_last_update(version: str, notes: str, file: str | None = None) -> None:
    cfg = config.read_config()
    data = {"version": version, "notes": notes}
    if file:
        data["file"] = str(file)
    cfg["last_update"] = data
    config.write_config(cfg)


def clear_last_update() -> None:
    cfg = config.read_config()
    cfg.pop("last_update", None)
    config.write_config(cfg)


# ---------------------------------------------------------------- prev cache (откат)
def prev_dir() -> Path:
    d = updates_dir() / "prev"
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_prev_installer(src: Path | str, version: str) -> Path | None:
    """Кладёт установщик успешно применённой версии в кэш отката."""
    import shutil

    try:
        src = Path(src)
        if not src.is_file():
            return None
        dest = prev_dir() / f"Nodexy-Setup-{version}.exe"
        for old in prev_dir().glob("*.exe"):
            _remove_quiet(old)
        shutil.move(str(src), str(dest))
        return dest
    except Exception:
        config.log_error("updater.store_prev_installer")
        return None


def prev_installer() -> Path | None:
    """Кэш предыдущего установщика (точка отката) или None."""
    try:
        candidates = sorted(updates_dir().joinpath("prev").glob("*.exe"))
        return candidates[-1] if candidates else None
    except Exception:
        return None


def rollback_possible() -> tuple[bool, str]:
    """Чистое решение «откат возможен/нет» от текущего состояния файловой системы."""
    prev = prev_installer()
    if prev is not None and prev.is_file():
        return True, str(prev)
    return False, ""


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
    """Возможность тихого самообновления через установщик.

    Требует, чтобы приложение было установлено через setup (рядом лежит
    unins000.exe) — тогда Inno при апгрейде возьмёт путь установки из реестра
    и заменит файлы корректно. Для портативного запуска тихая установка
    поверх себя не делается: только предложение скачать установщик.
    """
    exe = current_exe()
    if exe is None:
        return False, "Запуск из исходников — обновление через установщик недоступно"
    if not (exe.parent / "unins000.exe").is_file():
        return False, "Портативная версия: скачайте установщик и установите вручную"
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
# Помощник (стратегия B): дожидается полного выхода приложения и запускает
# установщик Inno Setup тихо. Никакого переноса файлов — файлы заменяет сам
# установщик, он же правит версию в «Приложениях и компонентах» и (с
# /RESTARTAPP) перезапускает приложение. Тот же шаблон служит для отката:
# вместо нового пакета подставляется кэш предыдущего (updates\prev).
_SETUP_VBS = r"""On Error Resume Next
Set args = WScript.Arguments
If args.Count < 5 Then WScript.Quit 1
pid = CLng(args(0))
parentPid = CLng(args(1))
setupPath = args(2)
setupFlags = args(3)
logPath = args(4)
Set fso = CreateObject("Scripting.FileSystemObject")
Set oShell = CreateObject("WScript.Shell")
' Wait for BOTH the app process and its PyInstaller bootloader parent:
' while the parent is alive the files are locked and Inno (AppMutex)
' refuses to install.
elapsed = 0
Do While elapsed < 60
    If Not ProcessExists(pid) And Not ProcessExists(parentPid) Then Exit Do
    WScript.Sleep 500
    elapsed = elapsed + 1
Loop
If ProcessExists(pid) Or ProcessExists(parentPid) Then
    Log "timeout waiting for pid " & pid & " / parent " & parentPid & "; aborted, nothing changed"
    WScript.Quit 0
End If
' Grace pause: let file handles and the _MEI cleanup settle.
WScript.Sleep 2000
If Not fso.FileExists(setupPath) Then
    Log "setup missing: " & setupPath & "; aborted"
    WScript.Quit 1
End If
If Not WaitFileReadable(setupPath, 15000) Then
    Log "setup not readable in time; aborted"
    WScript.Quit 1
End If
WScript.Sleep 1000
' Run the installer hidden and wait for it to finish.
rc = oShell.Run(Chr(34) & setupPath & Chr(34) & " " & setupFlags, 0, True)
If rc = 0 Then
    Log "installer finished OK: " & setupPath
Else
    Log "installer FAILED rc=" & rc & ": " & setupPath
End If
WScript.Quit 0
Function ProcessExists(p)
    On Error Resume Next
    ProcessExists = False
    If p = 0 Then Exit Function
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If
    Set procs = wmi.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE ProcessId=" & p)
    ProcessExists = (procs.Count > 0)
End Function
Function WaitFileReadable(exePath, maxMs)
    On Error Resume Next
    Dim waited
    waited = 0
    Do While waited < maxMs
        Err.Clear
        Dim chk
        Set chk = CreateObject("Scripting.FileSystemObject").OpenTextFile(exePath, 1, False)
        If Err.Number = 0 Then
            chk.Close
            WaitFileReadable = True
            Exit Function
        End If
        Err.Clear
        WScript.Sleep 500
        waited = waited + 500
    Loop
    WaitFileReadable = False
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


def build_silent_setup_args(restart: bool, log_path: str | Path | None = None) -> list[str]:
    """Флаги тихой установки Inno Setup (чистая функция — тестируется отдельно).

    /DIR намеренно НЕ передаётся: при апгрейде Inno берёт прежний путь из
    реестра. /RESTARTAPP включает перезапуск приложения записью [Run]
    с Check: RestartAfterSilentUpdate.
    """
    flags = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
    if restart:
        flags.append("/RESTARTAPP")
    if log_path is not None:
        flags.append(f'/LOG="{log_path}"')
    return flags


def install_log_path() -> Path:
    return config.app_dir() / "nodexy_install.log"


def write_updater_script() -> Path:
    """VBS-помощник: WScript — GUI-подсистема, консольных окон не бывает."""
    script = config.app_dir() / "nodexy_update.vbs"
    script.write_text(_SETUP_VBS, encoding="ascii")
    return script


def write_rollback_script() -> Path:
    script = config.app_dir() / "nodexy_rollback.vbs"
    script.write_text(_SETUP_VBS, encoding="ascii")
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
    """Гасит осиротевшие процессы помощников старых версий (только свои).

    Щадим текущий процесс и помощник, который его только что запустил
    (создан незадолго до нас): его убийство оборвало финальный лог/ретраи.
    Убиваем только старые сироты (созданные заметно раньше нашего старта).
    """
    try:
        import psutil
    except Exception:
        return 0
    markers = ("nodexy_update", "nodexy_rollback")
    my_pid = os.getpid()
    try:
        my_create = psutil.Process(my_pid).create_time()
    except Exception:
        my_create = None
    killed = 0

    def _kill(proc) -> None:
        nonlocal killed
        try:
            proc.kill()
            killed += 1
        except Exception:
            pass

    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            pid = proc.info["pid"]
            if pid == my_pid:
                continue
            name = (proc.info["name"] or "").lower()
            cmdline_list = proc.info["cmdline"] or []
            cmdline = " ".join(cmdline_list).lower()
            # Осиротевший `find "<число>"` от старой связки tasklist|find.
            if name in ("find.exe", "find") and len(cmdline_list) == 2:
                if cmdline_list[1].strip().strip('"').isdigit():
                    _kill(proc)
                    continue
            # cmd/wscript, исполняющие наши скрипты.
            if cmdline and any(m in cmdline for m in markers):
                created = proc.info.get("create_time")
                # Помощник, созданный менее 120 с до нас, — наш лаунчер: не трогаем.
                if my_create is not None and created and created > my_create - 120:
                    continue
                _kill(proc)
        except Exception:
            continue

    # Старые скрипты больше не нужны (рабочий помощник уже загрузил свой в память).
    for name in ("nodexy_update.bat", "nodexy_rollback.bat",
                 "nodexy_update.vbs", "nodexy_rollback.vbs"):
        _remove_quiet(config.app_dir() / name)
    return killed


_APPLY_SCHEDULED = False


def _parent_pid() -> int:
    """PID PyInstaller-bootloader-родителя (onefile: процессов всегда два)."""
    try:
        import psutil

        return psutil.Process(os.getpid()).ppid()
    except Exception:
        return 0


def schedule_apply(restart: bool) -> bool:
    """Запускает скрытый помощник: дождётся выхода и тихо поставит установщик."""
    global _APPLY_SCHEDULED
    if _APPLY_SCHEDULED and not restart:
        return True
    pending = get_pending()
    if not pending or current_exe() is None:
        return False
    if pending.get("kind") != "installer":
        return False
    setup = Path(str(pending.get("file") or ""))
    if not setup.is_file():
        set_pending(None)
        return False
    try:
        script = write_updater_script()
    except Exception:
        config.log_error("updater.write_updater_script")
        return False
    flags = " ".join(build_silent_setup_args(restart, install_log_path()))
    ok = launch_script(
        script,
        [
            str(os.getpid()),
            str(_parent_pid()),
            str(setup),
            flags,
            str(update_log_path()),
        ],
    )
    if ok:
        _APPLY_SCHEDULED = True
    return ok


def schedule_rollback() -> bool:
    """Тихая установка кэша предыдущего установщика (понижение версии)."""
    prev = prev_installer()
    if prev is None or current_exe() is None:
        return False
    try:
        script = write_rollback_script()
    except Exception:
        config.log_error("updater.write_rollback_script")
        return False
    flags = " ".join(build_silent_setup_args(True, install_log_path()))
    return launch_script(
        script,
        [
            str(os.getpid()),
            str(_parent_pid()),
            str(prev),
            flags,
            str(update_log_path()),
        ],
    )


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
        if pending.get("kind") != "installer":
            # Записи старого механизма (замена exe на месте) больше не действуют.
            cancel_pending()
        elif same_version(str(pending.get("version") or ""), APP_VERSION):
            # Обновление применилось: запоминаем заметки И путь к установщику —
            # после стабильного старта он станет точкой отката в updates\prev.
            set_last_update(
                str(pending.get("version") or ""),
                str(pending.get("notes") or ""),
                str(pending.get("file") or ""),
            )
            set_pending(None)
            result["plate"] = pending.get("version")
            result["notes"] = pending.get("notes") or ""
        elif is_newer(str(pending.get("version") or "")):
            # Предыдущая попытка установки не удалась (версия не сменилась).
            # Считаем попытки; помощник запускается только при выходе.
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
        # Перечитываем конфиг: логика выше могла его изменить, а запись
        # устаревшего снимка воскресила бы update_pending (залипшее состояние).
        cfg = config.read_config()
        boot, need_rollback = boot_step(cfg.get("boot_check"), APP_VERSION)
        cfg["boot_check"] = boot
        config.write_config(cfg)
        if need_rollback:
            can_rollback, prev_path = rollback_possible()
            if can_rollback:
                try:
                    script = write_rollback_script()
                    flags = " ".join(build_silent_setup_args(True, install_log_path()))
                    if launch_script(
                        script,
                        [
                            str(os.getpid()),
                            str(_parent_pid()),
                            prev_path,
                            flags,
                            str(update_log_path()),
                        ],
                    ):
                        cfg = config.read_config()
                        cfg.pop("boot_check", None)
                        cfg["rollback_safe_mode"] = 1
                        config.write_config(cfg)
                        cancel_pending()
                        result["rollback"] = True
                except Exception:
                    config.log_error("updater.rollback")
            else:
                # Кэша предыдущего установщика нет (чистая установка, файл
                # удалён/повреждён): НЕ откатываемся, чтобы не зациклиться.
                # Сбрасываем счётчик, чистим ожидание — дальше обычная работа.
                cfg = config.read_config()
                cfg.pop("boot_check", None)
                config.write_config(cfg)
                cancel_pending()
                config.log_error("updater: откат невозможен — нет кэша установщика")
                result["failed_url"] = RELEASES_PAGE_URL
    return result


def boot_success() -> None:
    cfg = config.read_config()
    if "boot_check" in cfg:
        cfg.pop("boot_check", None)
        config.write_config(cfg)
    # Установщик успешно применённой версии переезжает из updates\ в кэш
    # отката: если СЛЕДУЮЩЕЕ обновление окажется битым, откатывать будет чем.
    info = get_last_update()
    if info and info.get("file"):
        store_prev_installer(Path(str(info["file"])), str(info.get("version") or ""))
    # Наследие старой схемы: резервные копии .old больше не создаются.
    bak = backup_path()
    if bak is not None:
        _remove_quiet(bak)
