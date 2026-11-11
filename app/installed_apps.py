import os
import re
import winreg
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from time import monotonic

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
_TECHNICAL_MARKERS = (
    "update", "updater", "helper", "service", "crash", "report", "repair",
    "runtime", "redist", "vcredist", "redistributable", "driver", "setup",
    "installer", "launcher", "bootstrap", "uninstall", "mainten", "telemetry",
    "webview", "cef", "elevat", "background", "broker", "browser", "repl",
)
_TECHNICAL_FOLDERS = ("drivers", "driverstore", "system32", "syswow64", "redist")
_APP_CACHE_TTL = 45.0
_app_cache: tuple[float, list["InstalledApp"]] | None = None
_app_cache_lock = Lock()


@dataclass(frozen=True)
class InstalledApp:
    name: str
    exe_path: str
    icon_path: str
    icon_index: int
    category: str = "installed"
    primary: bool = True
    source: str = ""


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


def _looks_technical(app: InstalledApp) -> bool:
    path = os.path.normcase(app.exe_path).replace("/", "\\")
    base = os.path.splitext(os.path.basename(path))[0].lower()
    name = app.name.lower()
    return (
        any(marker in base or marker in name for marker in _TECHNICAL_MARKERS)
        or any(f"\\{folder}\\" in path for folder in _TECHNICAL_FOLDERS)
    )


_SOURCE_SCORE = {"registry": 50, "start_menu": 42, "steam": 40, "running": 10}
_TECHNICAL_SUFFIXES = (
    "code mode host", "command runner", "computer use swift", "computer use",
    "browser", "helper", "launcher", "service", "updater", "update",
    "runtime", "host", "broker", "worker", "crash handler", "reporter",
)
_VERSION_RE = re.compile(r"\s+v?\d+(?:[._-]\d+)*", re.I)
_ARCH_RE = re.compile(r"\s*\([^)]*(?:x?64|x86|32|64|bit)[^)]*\)\s*$", re.I)


def _normalized_product_name(name: str) -> str:
    """Return a stable product key, removing versions and executable roles."""
    value = re.sub(r"[._-]+", " ", (name or "").lower())
    value = re.sub(r"\s+", " ", value).strip()
    value = _ARCH_RE.sub("", value).strip()
    value = re.sub(r"\s*\([^)]*\)\s*$", "", value).strip()
    value = _VERSION_RE.sub("", value).strip()
    changed = True
    while changed:
        changed = False
        for suffix in _TECHNICAL_SUFFIXES:
            if value.endswith(" " + suffix):
                value = value[: -len(suffix) - 1].strip()
                changed = True
                break
    return value or "unknown"


def _group_key(app: InstalledApp) -> str:
    name_key = _normalized_product_name(app.name)
    # DisplayName/FileDescription is the strongest identity. Installed versions
    # commonly live in different versioned directories, so the directory must
    # not split otherwise identical products into separate visible entries.
    if name_key != "unknown":
        return "name:" + name_key

    # Nameless process-derived candidates still need a little path context to
    # avoid merging every generic executable into one application.
    parent = os.path.normcase(os.path.dirname(app.exe_path)).replace("/", "\\")
    while True:
        reduced = re.sub(r"\\(?:app|bin|x64|x86|win32|win64|v?\d+(?:\.\d+)*)$", "", parent, flags=re.I)
        if reduced == parent:
            break
        parent = reduced
    return "name:" + name_key + "|root:" + parent


def _main_score(app: InstalledApp) -> tuple[int, int, int, int, int]:
    base = os.path.splitext(os.path.basename(app.exe_path))[0].lower()
    name = _normalized_product_name(app.name)
    technical = _looks_technical(app)
    exact = int(base.replace("_", " ").replace("-", " ") == name)
    name_match = int(name and (base in name or name in base))
    try:
        size = min(os.path.getsize(app.exe_path), 2_000_000_000)
    except OSError:
        size = 0
    return (
        int(not technical),
        _SOURCE_SCORE.get(app.source, 0),
        exact * 2 + name_match,
        int(app.category == "game"),
        size,
    )


def _deduplicate_and_rank(apps: list[InstalledApp]) -> list[InstalledApp]:
    by_path: dict[str, InstalledApp] = {}
    for app in apps:
        key = os.path.normcase(os.path.normpath(app.exe_path))
        previous = by_path.get(key)
        if previous is None or _SOURCE_SCORE.get(app.source, 0) > _SOURCE_SCORE.get(previous.source, 0):
            by_path[key] = app

    groups: dict[str, list[InstalledApp]] = {}
    for app in by_path.values():
        groups.setdefault(_group_key(app), []).append(app)

    result: list[InstalledApp] = []
    for candidates in groups.values():
        leader = max(candidates, key=_main_score)
        for app in candidates:
            category = "system" if app.category == "system" else app.category
            primary = app is leader and not _looks_technical(app) and category != "system"
            result.append(InstalledApp(
                app.name, app.exe_path, app.icon_path, app.icon_index,
                category, primary, app.source,
            ))
    return result


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
    return InstalledApp(name=name, exe_path=exe_path, icon_path=icon_path, icon_index=icon_index,
                        category="installed", source="registry")


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
    "easyanticheat", "start_protected_game", "unitycrashhandler", "ue4crash",
)


def _pick_game_exe(directory: str, game_name: str) -> str:
    if not os.path.isdir(directory):
        return ""
    try:
        entries = os.listdir(directory)
    except OSError:
        return ""
    exes = [e for e in entries if e.lower().endswith(".exe")]
    candidates = [(directory, e) for e in exes]
    # Many Steam games keep the real binary in Game/, Base/Binaries/Win64,
    # or a similar subdirectory. Keep this bounded so a game cannot cause a
    # scan of arbitrary user data through a junction or nested runtime folder.
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            relative_depth = os.path.relpath(dirpath, directory).count(os.sep) + 1
            if relative_depth > 4:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d.lower() not in {
                "redist", "redistributables", "directx", "_commonredist",
                "easyanticheat", "crashpad", "cef", "node_modules",
            }]
            for entry in filenames:
                if entry.lower().endswith(".exe"):
                    candidates.append((dirpath, entry))
    except OSError:
        pass
    if not candidates:
        return ""

    game_key = re.sub(r"[^a-z0-9]+", "", game_name.lower())
    def score(item: tuple[str, str]) -> tuple[int, int, int, int]:
        folder, entry = item
        base = os.path.splitext(entry)[0].lower()
        compact = re.sub(r"[^a-z0-9]+", "", base)
        blocked = any(marker in base for marker in _GAME_EXE_BLOCKLIST)
        exact = int(compact == game_key or game_key in compact or compact in game_key)
        depth = folder.count(os.sep) - directory.count(os.sep)
        try:
            size = min(os.path.getsize(os.path.join(folder, entry)), 2_000_000_000)
        except OSError:
            size = 0
        return (int(not blocked), exact, -depth, size)

    folder, entry = max(candidates, key=score)
    return os.path.join(folder, entry)


def _steam_games() -> list[InstalledApp]:
    steam_paths = [
        _as_str(_reg_value(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam", "SteamPath")),
        _as_str(_reg_value(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")),
        _as_str(_reg_value(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")),
    ]
    steam_path = next((path for path in steam_paths if path), "")
    if not steam_path:
        return []
    steam_path = steam_path.replace("/", os.sep)
    libraries: list[str] = [steam_path]
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf_path, encoding="utf-8", errors="ignore") as f:
            libraries.extend(re.findall(r'"path"\s+"([^"]+)"', f.read()))
    except OSError:
        pass

    normalized_libraries: list[str] = []
    seen_libraries: set[str] = set()
    for library in libraries:
        library = library.replace("\\\\", "\\").replace("/", "\\")
        key = os.path.normcase(os.path.normpath(library))
        if key not in seen_libraries and os.path.isdir(library):
            seen_libraries.add(key)
            normalized_libraries.append(library)
    libraries = normalized_libraries

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
            games.append(InstalledApp(name=game_name, exe_path=exe, icon_path=exe, icon_index=0,
                                      category="game", source="steam"))
    return games


def _start_menu_apps() -> list[InstalledApp]:
    com_ready = False
    try:
        import pythoncom
        from win32com.client import Dispatch

        pythoncom.CoInitialize()
        com_ready = True
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
                            category="installed",
                            source="start_menu",
                        )
                    )
        del shell
        return apps
    except Exception:
        return []
    finally:
        if com_ready:
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
            is_system = os.path.normcase(exe).startswith(windows_dir + os.sep)
            if _looks_like_uninstaller(exe) and not is_system:
                continue
            base = os.path.basename(exe)
            if base.lower() in ("explorer.exe", "searchhost.exe", "applicationframehost.exe"):
                continue
            name = get_file_description(exe) or os.path.splitext(base)[0]
            apps.append(InstalledApp(name=name, exe_path=exe, icon_path=exe, icon_index=0,
                                     category="system" if is_system else "installed", source="running"))
    except Exception:
        pass
    return apps


def get_installed_apps() -> list[InstalledApp]:
    global _app_cache
    now = monotonic()
    with _app_cache_lock:
        if _app_cache is not None and now - _app_cache[0] < _APP_CACHE_TTL:
            return list(_app_cache[1])

    # Registry, Start Menu, Steam and running processes are independent. Steam
    # is the slowest source, so running them concurrently removes its latency
    # from the critical path of the other three sources.
    source_functions = (_registry_apps, _start_menu_apps, _steam_games, _running_apps)
    with ThreadPoolExecutor(max_workers=len(source_functions), thread_name_prefix="app-scan") as pool:
        futures = [pool.submit(function) for function in source_functions]
        sources = [app for future in futures for app in future.result()]
    apps = _deduplicate_and_rank(sources)
    result = sorted(
        apps,
        key=lambda a: (
            a.category == "system",
            not a.primary,
            a.name.lower(),
            a.exe_path.lower(),
        ),
    )
    with _app_cache_lock:
        _app_cache = (monotonic(), result)
    return list(result)


def clear_installed_apps_cache() -> None:
    """Force the next add-apps dialog to rescan installed software."""
    global _app_cache
    with _app_cache_lock:
        _app_cache = None
