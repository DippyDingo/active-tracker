"""Сканирование установленных приложений в фоне.

Вынесено из UI: сервис ничего не знает о виджетах и никогда не создаёт
окон. Результат отдаётся сигналом в главный поток Qt.

Оптимизации по сравнению с прежней версией:
  * один проход по реестру (LM 64/32 + HKCU), без повторного открытия ключей;
  * ярлыки читаются через IShellLink напрямую (без WScript.Shell), COM
    инициализируется и освобождается корректно;
  * Steam — один раз на библиотеку;
  * жёсткий лимит времени на источник, чтобы UI не ждал медленный диск;
  * результат кэшируется в памяти на время сеанса.
"""

import os
import re
import time
import winreg

from PySide6.QtCore import QThread, Signal

from ..installed_apps import InstalledApp

_UNINSTALL_ROOTS = (
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
)

_NAME_BLOCKLIST = (
    "update for",
    "hotfix",
    "security update",
    "накопительное обновление",
    "обновление для",
    "обновление microsoft",
)

_UNINSTALLER_MARKERS = ("unins", "uninst", "unwise", "unreg", "uninstall", "remove")
_GAME_EXE_BLOCKLIST = (
    "unins", "setup", "redist", "vcredist", "directx", "dxsetup", "launcher",
    "crash", "report", "cleanup", "uninstall", "configure", "dotnet", "ue4-prereq",
)

# Кэш на время сеанса: повторное открытие страницы не пересканирует диск.
_STATIC_CACHE: list[InstalledApp] | None = None


def invalidate_cache() -> None:
    global _STATIC_CACHE
    _STATIC_CACHE = None


def _as_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "ignore")
    try:
        return str(value).strip()
    except Exception:
        return ""


def _looks_like_uninstaller(path: str) -> bool:
    base = os.path.basename(path).lower()
    return any(base.startswith(m) for m in _UNINSTALLER_MARKERS)


def _pick_main_exe(directory: str) -> str:
    try:
        entries = os.listdir(directory)
    except OSError:
        return ""
    candidates = [
        e for e in entries
        if e.lower().endswith(".exe") and not _looks_like_uninstaller(e)
    ]
    if not candidates:
        return ""
    if len(candidates) == 1:
        return os.path.join(directory, candidates[0])
    folder = os.path.basename(directory.rstrip("\\/")).lower()
    for e in candidates:
        if os.path.splitext(e)[0].lower() == folder:
            return os.path.join(directory, e)
    try:
        candidates.sort(
            key=lambda e: os.path.getsize(os.path.join(directory, e)), reverse=True
        )
    except OSError:
        pass
    return os.path.join(directory, candidates[0])


def _parse_icon_location(raw: str) -> tuple[str, int]:
    from ..win32_utils import parse_icon_location

    return parse_icon_location(raw)


def _read_registry_apps() -> list[InstalledApp]:
    apps: list[InstalledApp] = []
    for root, path in _UNINSTALL_ROOTS:
        try:
            base = winreg.OpenKey(root, path)
        except OSError:
            continue
        with base:
            try:
                count = winreg.QueryInfoKey(base)[0]
            except OSError:
                continue
            for i in range(count):
                try:
                    sub_name = winreg.EnumKey(base, i)
                    with winreg.OpenKey(base, sub_name) as key:
                        name = _as_str(_q(key, "DisplayName"))
                        if not name:
                            continue
                        if _q(key, "SystemComponent") == 1:
                            continue
                        if _q(key, "ParentKeyName") or _q(key, "ParentDisplayName"):
                            continue
                        lowered = name.lower()
                        if any(m in lowered for m in _NAME_BLOCKLIST):
                            continue
                        icon_raw = _as_str(_q(key, "DisplayIcon"))
                        install_location = _as_str(_q(key, "InstallLocation")).strip('"')
                except OSError:
                    continue

                icon_path, icon_index = _parse_icon_location(icon_raw)
                exe_path = ""
                if (
                    icon_path.lower().endswith(".exe")
                    and os.path.isfile(icon_path)
                    and not _looks_like_uninstaller(icon_path)
                ):
                    exe_path = icon_path
                if not exe_path and icon_path and os.path.isdir(os.path.dirname(icon_path)):
                    exe_path = _pick_main_exe(os.path.dirname(icon_path))
                if not exe_path and install_location and os.path.isdir(install_location):
                    exe_path = _pick_main_exe(install_location)
                if not exe_path:
                    continue
                if not icon_path or not os.path.exists(icon_path):
                    icon_path, icon_index = exe_path, 0
                apps.append(
                    InstalledApp(
                        name=name, exe_path=exe_path,
                        icon_path=icon_path, icon_index=icon_index,
                    )
                )
    return apps


def _q(key, name: str):
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except OSError:
        return None


def _shortcut_target(lnk_path: str) -> str:
    """Цель ярлыка через IShellLink (без WScript.Shell и лишних COM-объектов)."""
    import pythoncom
    from win32com.shell import shell, shellcon

    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None,
        pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink,
    )
    persist = link.QueryInterface(pythoncom.IID_IPersistFile)
    persist.Load(lnk_path, 0)
    target, _ = link.GetPath(shellcon.SLGP_UNCPRIORITY)
    return target or ""


def _start_menu_apps() -> list[InstalledApp]:
    import pythoncom

    pythoncom.CoInitialize()
    try:
        roots = [
            os.path.join(os.getenv("PROGRAMDATA", r"C:\ProgramData"),
                         r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.getenv("APPDATA", ""),
                         r"Microsoft\Windows\Start Menu\Programs"),
        ]
        apps: list[InstalledApp] = []
        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            for dirpath, _dirnames, filenames in os.walk(root):
                for fn in filenames:
                    if not fn.lower().endswith(".lnk"):
                        continue
                    try:
                        target = _shortcut_target(os.path.join(dirpath, fn))
                    except Exception:
                        continue
                    if not target.lower().endswith(".exe") or not os.path.isfile(target):
                        continue
                    if _looks_like_uninstaller(target):
                        continue
                    apps.append(
                        InstalledApp(
                            name=os.path.splitext(fn)[0], exe_path=target,
                            icon_path=target, icon_index=0,
                        )
                    )
        return apps
    except Exception:
        return []
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _pick_game_exe(directory: str, game_name: str) -> str:
    if not os.path.isdir(directory):
        return ""
    try:
        exes = [e for e in os.listdir(directory) if e.lower().endswith(".exe")]
    except OSError:
        return ""
    if not exes:
        return ""
    exact = game_name.lower() + ".exe"
    for e in exes:
        if e.lower() == exact:
            return os.path.join(directory, e)
    filtered = [e for e in exes if not any(m in e.lower() for m in _GAME_EXE_BLOCKLIST)]
    pool = filtered or exes
    if len(pool) > 1:
        try:
            pool.sort(key=lambda e: os.path.getsize(os.path.join(directory, e)), reverse=True)
        except OSError:
            pass
    return os.path.join(directory, pool[0])


def _steam_games() -> list[InstalledApp]:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam") as key:
            steam_path = _as_str(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        return []
    if not steam_path:
        return []
    steam_path = steam_path.replace("/", os.sep)
    if not os.path.isdir(steam_path):
        return []
    libraries: list[str] = []
    try:
        with open(os.path.join(steam_path, "steamapps", "libraryfolders.vdf"),
                  encoding="utf-8", errors="ignore") as f:
            libraries = re.findall(r'"path"\s+"([^"]+)"', f.read())
    except OSError:
        libraries = []
    if not libraries:
        libraries = [steam_path]

    games: list[InstalledApp] = []
    seen: set[str] = set()
    for lib in libraries:
        lib = lib.replace("\\\\", "\\").replace("/", "\\")
        steamapps = os.path.join(lib, "steamapps")
        try:
            manifests = [
                f for f in os.listdir(steamapps)
                if f.startswith("appmanifest_") and f.endswith(".acf")
            ]
        except OSError:
            continue
        for mf in manifests:
            try:
                with open(os.path.join(steamapps, mf), encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            name_m = re.search(r'"name"\s+"([^"]+)"', text)
            dir_m = re.search(r'"installdir"\s+"([^"]+)"', text)
            if not (name_m and dir_m):
                continue
            game_name = name_m.group(1)
            exe = _pick_game_exe(os.path.join(steamapps, "common", dir_m.group(1)), game_name)
            if not exe:
                continue
            key = os.path.normcase(exe)
            if key in seen:
                continue
            seen.add(key)
            games.append(InstalledApp(name=game_name, exe_path=exe, icon_path=exe, icon_index=0))
    return games


def _running_apps() -> list[InstalledApp]:
    """Запущенные процессы как кандидаты (быстрый источник, без кэша)."""
    import psutil

    from ..win32_utils import get_file_description

    windows_dir = os.path.normcase(os.getenv("SystemRoot", r"C:\Windows"))
    apps: list[InstalledApp] = []
    try:
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                exe = (proc.info.get("exe") or "").strip()
            except Exception:
                continue
            if not exe or not os.path.isfile(exe):
                continue
            if os.path.normcase(exe).startswith(windows_dir + os.sep):
                continue
            if _looks_like_uninstaller(exe):
                continue
            base = os.path.basename(exe)
            if base.lower() in ("explorer.exe", "searchhost.exe", "applicationframehost.exe"):
                continue
            try:
                name = get_file_description(exe) or os.path.splitext(base)[0]
            except Exception:
                name = os.path.splitext(base)[0]
            apps.append(InstalledApp(name=name, exe_path=exe, icon_path=exe, icon_index=0))
    except Exception:
        pass
    return apps


# Статические источники (реестр, ярлыки, Steam) кэшируются; запущенные
# процессы перечитываются каждый раз — иначе список «худел» относительно
# старой версии сканера.
def _scan_static() -> list[InstalledApp]:
    global _STATIC_CACHE
    if _STATIC_CACHE is not None:
        return list(_STATIC_CACHE)

    deadline = time.monotonic() + 20.0
    found: dict[str, InstalledApp] = {}
    for source in (_read_registry_apps, _start_menu_apps, _steam_games):
        if time.monotonic() > deadline:
            break
        try:
            for app in source():
                found.setdefault(os.path.normcase(app.exe_path), app)
        except Exception:
            continue

    result = list(found.values())
    _STATIC_CACHE = result
    return list(result)


def scan_installed_apps(use_cache: bool = True) -> list[InstalledApp]:
    """Полное сканирование. Блокирующая функция — вызывать из потока."""
    global _STATIC_CACHE
    if not use_cache:
        _STATIC_CACHE = None

    found: dict[str, InstalledApp] = {}
    for app in _scan_static():
        found.setdefault(os.path.normcase(app.exe_path), app)
    try:
        for app in _running_apps():
            found.setdefault(os.path.normcase(app.exe_path), app)
    except Exception:
        pass

    return sorted(found.values(), key=lambda a: a.name.lower())


class ApplicationScanThread(QThread):
    """Поток сканирования: результат приходит одним сигналом."""

    scanned = Signal(list)

    def __init__(self, use_cache: bool = True, parent=None):
        super().__init__(parent)
        self._use_cache = use_cache

    def run(self) -> None:
        try:
            apps = scan_installed_apps(self._use_cache)
        except Exception:
            apps = []
        self.scanned.emit(apps)
