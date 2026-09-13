import os
import re
import winreg
from dataclasses import dataclass

import psutil

from .win32_utils import get_file_description, parse_icon_location

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


@dataclass(frozen=True)
class InstalledApp:
    name: str
    exe_path: str
    icon_path: str
    icon_index: int


def _reg_value(root: int, path: str, name: str):
    try:
        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None


def _as_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "ignore")
    return str(value).strip()


def _looks_like_uninstaller(path: str) -> bool:
    base = os.path.basename(path).lower()
    return any(base.startswith(m) for m in _UNINSTALLER_MARKERS)


def _pick_main_exe(directory: str) -> str:
    try:
        entries = os.listdir(directory)
    except OSError:
        return ""
    exes = [e for e in entries if e.lower().endswith(".exe")]
    candidates = [e for e in exes if not _looks_like_uninstaller(e)]
    if not candidates:
        return ""
    if len(candidates) == 1:
        return os.path.join(directory, candidates[0])
    folder = os.path.basename(directory.rstrip("\\/")).lower()
    for e in candidates:
        if os.path.splitext(e)[0].lower() == folder:
            return os.path.join(directory, e)
    try:
        candidates.sort(key=lambda e: os.path.getsize(os.path.join(directory, e)), reverse=True)
    except OSError:
        pass
    return os.path.join(directory, candidates[0])


def _read_entry(key) -> InstalledApp | None:
    name = _as_str(_raw_value(key, "DisplayName"))
    if not name:
        return None
    if _raw_value(key, "SystemComponent") == 1:
        return None
    if _raw_value(key, "ParentKeyName") or _raw_value(key, "ParentDisplayName"):
        return None
    lowered = name.lower()
    if any(marker in lowered for marker in _NAME_BLOCKLIST):
        return None

    icon_raw = _as_str(_raw_value(key, "DisplayIcon"))
    install_location = _as_str(_raw_value(key, "InstallLocation")).strip('"')

    icon_path, icon_index = parse_icon_location(icon_raw)
    exe_path = ""
    if icon_path.lower().endswith(".exe") and os.path.isfile(icon_path) and not _looks_like_uninstaller(icon_path):
        exe_path = icon_path
    if not exe_path and icon_path and os.path.isdir(os.path.dirname(icon_path)):
        exe_path = _pick_main_exe(os.path.dirname(icon_path))
    if not exe_path and install_location and os.path.isdir(install_location):
        exe_path = _pick_main_exe(install_location)
    if not exe_path:
        return None
    if not icon_path or not os.path.exists(icon_path):
        icon_path, icon_index = exe_path, 0
    return InstalledApp(name=name, exe_path=exe_path, icon_path=icon_path, icon_index=icon_index)


def _raw_value(key, name: str):
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except OSError:
        return None


def _registry_apps() -> list[InstalledApp]:
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
                    with winreg.OpenKey(base, sub_name) as sub:
                        app = _read_entry(sub)
                except OSError:
                    continue
                if app is not None:
                    apps.append(app)
    return apps


_GAME_EXE_BLOCKLIST = (
    "unins", "setup", "redist", "vcredist", "directx", "dxsetup", "launcher",
    "crash", "report", "cleanup", "uninstall", "configure", "dotnet", "ue4-prereq",
)


def _pick_game_exe(directory: str, game_name: str) -> str:
    if not os.path.isdir(directory):
        return ""
    try:
        entries = os.listdir(directory)
    except OSError:
        return ""
    exes = [e for e in entries if e.lower().endswith(".exe")]
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
    steam_path = _as_str(_reg_value(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam", "SteamPath"))
    if not steam_path:
        return []
    steam_path = steam_path.replace("/", os.sep)
    libraries: list[str] = []
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf_path, encoding="utf-8", errors="ignore") as f:
            libraries = re.findall(r'"path"\s+"([^"]+)"', f.read())
    except OSError:
        libraries = []
    if not libraries and os.path.isdir(steam_path):
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
            game_dir = os.path.join(steamapps, "common", dir_m.group(1))
            exe = _pick_game_exe(game_dir, game_name)
            if not exe:
                continue
            key = os.path.normcase(exe)
            if key in seen:
                continue
            seen.add(key)
            games.append(InstalledApp(name=game_name, exe_path=exe, icon_path=exe, icon_index=0))
    return games


def _start_menu_apps() -> list[InstalledApp]:
    try:
        import pythoncom
        from win32com.client import Dispatch

        pythoncom.CoInitialize()
    except Exception:
        return []
    try:
        shell = Dispatch("WScript.Shell")
        roots = [
            os.path.join(os.getenv("PROGRAMDATA", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.getenv("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        ]
        apps: list[InstalledApp] = []
        for root in roots:
            for dirpath, _dirnames, filenames in os.walk(root):
                for fn in filenames:
                    if not fn.lower().endswith(".lnk"):
                        continue
                    try:
                        shortcut = shell.CreateShortCut(os.path.join(dirpath, fn))
                        target = (shortcut.TargetPath or "").strip()
                        del shortcut
                    except Exception:
                        continue
                    if not target.lower().endswith(".exe") or not os.path.isfile(target):
                        continue
                    if _looks_like_uninstaller(target):
                        continue
                    apps.append(
                        InstalledApp(
                            name=os.path.splitext(fn)[0],
                            exe_path=target,
                            icon_path=target,
                            icon_index=0,
                        )
                    )
        del shell
        return apps
    except Exception:
        return []
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _running_apps() -> list[InstalledApp]:
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
            name = get_file_description(exe) or os.path.splitext(base)[0]
            apps.append(InstalledApp(name=name, exe_path=exe, icon_path=exe, icon_index=0))
    except Exception:
        pass
    return apps


def get_installed_apps() -> list[InstalledApp]:
    found: dict[str, InstalledApp] = {}
    sources = _registry_apps() + _start_menu_apps() + _steam_games() + _running_apps()
    for app in sources:
        found.setdefault(os.path.normcase(app.exe_path), app)
    return sorted(found.values(), key=lambda a: a.name.lower())
