import ctypes
import io
import os
from ctypes import wintypes

import psutil

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
version_dll = ctypes.windll.version

kernel32.GetTickCount.restype = wintypes.DWORD
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
shell32.SHDefExtractIconW.restype = ctypes.c_long
shell32.SHDefExtractIconW.argtypes = [
    wintypes.LPCWSTR, ctypes.c_int, wintypes.UINT,
    ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON), wintypes.UINT,
]

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

version_dll.GetFileVersionInfoSizeW.restype = wintypes.DWORD
version_dll.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
version_dll.GetFileVersionInfoW.restype = wintypes.BOOL
version_dll.GetFileVersionInfoW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
]
version_dll.VerQueryValueW.restype = wintypes.BOOL
version_dll.VerQueryValueW.argtypes = [
    ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT),
]


class _LANGANDCODEPAGE(ctypes.Structure):
    _fields_ = [("wLanguage", wintypes.WORD), ("wCodePage", wintypes.WORD)]


def get_file_description(path: str) -> str:
    try:
        if not path or not os.path.isfile(path):
            return ""
        handle = wintypes.DWORD(0)
        size = version_dll.GetFileVersionInfoSizeW(path, ctypes.byref(handle))
        if not size:
            return ""
        buffer = ctypes.create_string_buffer(size)
        if not version_dll.GetFileVersionInfoW(path, handle.value, size, buffer):
            return ""
        ptr = ctypes.c_void_p(0)
        length = wintypes.UINT(0)
        pairs: list[tuple[int, int]] = []
        if version_dll.VerQueryValueW(buffer, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(length)):
            count = length.value // ctypes.sizeof(_LANGANDCODEPAGE)
            if count:
                table = (_LANGANDCODEPAGE * count).from_address(ptr.value)
                pairs = [(p.wLanguage, p.wCodePage) for p in table]
        if not pairs:
            pairs = [(0x0409, 0x04B0), (0x0419, 0x04E3), (0x0419, 0x04B0)]
        for lang, codepage in pairs:
            subkey = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileDescription"
            if version_dll.VerQueryValueW(buffer, subkey, ctypes.byref(ptr), ctypes.byref(length)) and length.value > 0:
                nchars = min(length.value, size)
                text = ctypes.wstring_at(ptr.value, nchars).split("\x00")[0].strip()
                if text:
                    return text
        return ""
    except Exception:
        return ""


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def get_idle_seconds() -> float:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    delta = (kernel32.GetTickCount() - info.dwTime) % 2**32
    return delta / 1000.0


def get_foreground_pid() -> int | None:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value) if pid.value else None


def get_process_exe(pid: int) -> str:
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(32768)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value
        finally:
            kernel32.CloseHandle(handle)
    try:
        return psutil.Process(pid).exe() or ""
    except Exception:
        return ""


def get_foreground_exe() -> str:
    pid = get_foreground_pid()
    if not pid:
        return ""
    return get_process_exe(pid)


def running_exe_set() -> set[str]:
    result: set[str] = set()
    try:
        for proc in psutil.process_iter(["exe"]):
            try:
                exe = proc.info.get("exe")
            except Exception:
                continue
            if exe:
                result.add(os.path.normcase(exe))
    except Exception:
        pass
    return result


def parse_icon_location(raw: str) -> tuple[str, int]:
    raw = (raw or "").strip()
    if not raw:
        return "", 0
    if "," in raw:
        path, _, suffix = raw.rpartition(",")
        suffix = suffix.strip()
        if suffix.lstrip("-").isdigit() and path.strip():
            return path.strip().strip('"'), int(suffix)
    if raw.startswith('"') and raw.count('"') >= 2:
        return raw[1:raw.index('"', 1)], 0
    return raw.strip('"'), 0


def extract_icon_png(source_path: str, icon_index: int = 0, size: int = 64) -> bytes | None:
    if not source_path or not os.path.exists(source_path):
        return None
    hicon = 0
    extras: list[int] = []
    try:
        large = wintypes.HICON()
        small = wintypes.HICON()
        res = shell32.SHDefExtractIconW(
            source_path, icon_index, 0,
            ctypes.byref(large), ctypes.byref(small), size | (16 << 16),
        )
        if res == 0:
            hicon = large.value or 0
            if small.value:
                extras.append(small.value)
        if not hicon:
            import win32gui

            larges, smalls = win32gui.ExtractIconEx(source_path, 0)
            if larges:
                hicon = larges[0]
                extras.extend(larges[1:])
            extras.extend(smalls)
        if not hicon:
            return None
        return _hicon_to_png(hicon, size)
    except Exception:
        return None
    finally:
        import win32gui

        for h in ([hicon] if hicon else []) + extras:
            try:
                win32gui.DestroyIcon(h)
            except Exception:
                pass


def _hicon_to_png(hicon: int, size: int) -> bytes | None:
    import win32con
    import win32gui
    import win32ui
    from PIL import Image

    hdc_screen = win32gui.GetDC(0)
    srcdc = None
    memdc = None
    hbmp = None
    try:
        srcdc = win32ui.CreateDCFromHandle(hdc_screen)
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(srcdc, size, size)
        memdc = srcdc.CreateCompatibleDC()
        memdc.SelectObject(hbmp)
        win32gui.DrawIconEx(memdc.GetHandleOutput(), 0, 0, hicon, size, size, 0, 0, win32con.DI_NORMAL)
        bits = hbmp.GetBitmapBits(True)
        img = Image.frombuffer("RGBA", (size, size), bits, "raw", "BGRA", 0, 0)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None
    finally:
        try:
            if memdc is not None:
                memdc.DeleteDC()
            if srcdc is not None:
                srcdc.DeleteDC()
            if hbmp is not None:
                win32gui.DeleteObject(hbmp.GetHandle())
            win32gui.ReleaseDC(0, hdc_screen)
        except Exception:
            pass


_INSTANCE_MUTEX_HANDLE = None

# Имя должно совпадать с AppMutex в installer/nodexy.iss — по нему Inno
# Setup определяет, что приложение запущено (закрытие перед установкой).
INSTANCE_MUTEX_NAME = "NodexySingleInstanceMutex"


def acquire_instance_mutex(name: str = INSTANCE_MUTEX_NAME) -> bool:
    """Создаёт именованный мьютекс одного экземпляра.

    Возвращает True, если мьютекс создан (экземпляр первый). Дескриптор
    намеренно НЕ закрывается: он должен жить до выхода процесса.
    """
    global _INSTANCE_MUTEX_HANDLE
    import sys

    if sys.platform != "win32":
        return False
    try:
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            return False
        # ERROR_ALREADY_EXISTS = 183: мьютекс уже создан другим процессом.
        if kernel32.GetLastError() == 183:
            kernel32.CloseHandle(handle)
            return False
        _INSTANCE_MUTEX_HANDLE = handle
        return True
    except Exception:
        return False


def autostart_command(exe_path: str, script_path: str | None, minimized: bool = True, frozen: bool | None = None) -> str:
    """
    Формирует командную строку для автозапуска.
    
    Args:
        exe_path: путь к исполняемому файлу (sys.executable или собранный .exe)
        script_path: путь к main.py (только для незамороженного приложения)
        minimized: добавить флаг --minimized
        frozen: явно указать, собранное ли это приложение (для тестирования)
    
    Returns:
        Командная строка для записи в реестр
    """
    import sys
    from pathlib import Path
    
    if frozen is None:
        frozen = getattr(sys, "frozen", False)
    
    if frozen:
        # Собранный exe
        cmd = f'"{exe_path}"'
    else:
        # Запуск из исходников
        if script_path is None:
            raise ValueError("script_path required for non-frozen application")
        
        # Проверить pythonw.exe
        exe_dir = Path(exe_path).parent
        pythonw = exe_dir / "pythonw.exe"
        if pythonw.exists():
            cmd = f'"{pythonw}" "{script_path}"'
        else:
            # Fallback на python.exe
            cmd = f'"{exe_path}" "{script_path}"'
    
    if minimized:
        cmd += " --minimized"
    
    return cmd


def set_autostart(enabled: bool) -> bool:
    """
    Включает или выключает автозапуск через реестр Windows.
    
    Args:
        enabled: True — включить, False — выключить
    
    Returns:
        True если операция успешна, False при ошибке
    """
    import sys
    from pathlib import Path
    
    if sys.platform != "win32":
        return False
    
    try:
        import winreg
    except ImportError:
        return False
    
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    value_name = "Nodexy"
    
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        )
        
        if enabled:
            # Формируем командную строку
            exe_path = sys.executable
            script_path = None
            if not getattr(sys, "frozen", False):
                # Запуск из исходников
                import __main__
                if hasattr(__main__, "__file__"):
                    script_path = Path(__main__.__file__).resolve()
            
            cmd = autostart_command(str(exe_path), str(script_path) if script_path else None, minimized=True)
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, cmd)
        else:
            # Удаляем значение
            try:
                winreg.DeleteValue(key, value_name)
            except FileNotFoundError:
                # Значения уже нет
                pass
        
        winreg.CloseKey(key)
        return True
    
    except Exception:
        return False


def autostart_enabled() -> bool:
    """
    Проверяет, включён ли автозапуск в реестре.
    
    Returns:
        True если значение "Nodexy" существует в реестре
    """
    import sys
    
    if sys.platform != "win32":
        return False
    
    try:
        import winreg
    except ImportError:
        return False
    
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    value_name = "Nodexy"
    
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path,
            0,
            winreg.KEY_QUERY_VALUE
        )
        
        try:
            winreg.QueryValueEx(key, value_name)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    
    except Exception:
        return False


def autostart_value() -> str | None:
    """Сырое значение "Nodexy" из HKCU\\...\\Run или None."""
    import sys

    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_QUERY_VALUE,
        )
        try:
            value, _type = winreg.QueryValueEx(key, "Nodexy")
            return str(value)
        except FileNotFoundError:
            return None
        finally:
            winreg.CloseKey(key)
    except Exception:
        return None


def autostart_points_to_current() -> bool:
    """Указывает ли значение автозапуска на ТЕКУЩИЙ исполняемый файл.

    Значение имеет вид '"<путь>" --minimized' — берём первый путь в кавычках
    и сравниваем с sys.executable. Нужно для «усыновления» автозапуска,
    созданного установщиком, и для безопасного удаления только СВОЕЙ записи.
    """
    import os
    import sys

    raw = autostart_value()
    if not raw:
        return False
    path, _index = parse_icon_location(raw)
    if not path:
        return False
    try:
        return os.path.normcase(os.path.normpath(path)) == os.path.normcase(
            os.path.normpath(sys.executable)
        )
    except Exception:
        return False
