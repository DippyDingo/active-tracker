"""Генератор файла версии для PyInstaller (--version-file).

Читает APP_VERSION из app/version.py БЕЗ импорта приложения (без PySide6),
поэтому запускается «голым» python. Печатает версию в stdout — этим
пользуются сборочные скрипты и CI.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "installer" / "version_info.txt"

_TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={parts},
    prodvers={parts},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('041904b0', [
        StringStruct('CompanyName', 'DippyDingo'),
        StringStruct('FileDescription', 'Nodexy \\u2014 \\u0443\\u0447\\u0451\\u0442 \\u0432\\u0440\\u0435\\u043c\\u0435\\u043d\\u0438 \\u0432 \\u043f\\u0440\\u0438\\u043b\\u043e\\u0436\\u0435\\u043d\\u0438\\u044f\\u0445'),
        StringStruct('FileVersion', '{ver_str}'),
        StringStruct('InternalName', 'Nodexy'),
        StringStruct('OriginalFilename', 'Nodexy.exe'),
        StringStruct('ProductName', 'Nodexy'),
        StringStruct('ProductVersion', '{ver_str}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1049, 1200])])
  ]
)
"""


def read_app_version() -> str:
    text = (ROOT / "app" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    if not match:
        raise SystemExit("APP_VERSION не найден в app/version.py")
    return match.group(1)


def version_parts(version: str) -> tuple[int, int, int, int]:
    """Разбивает версию на 4 числовых компонента, недостающие — нули."""
    digits = [int(p) for p in re.findall(r"\d+", version)][:4]
    while len(digits) < 4:
        digits.append(0)
    return tuple(digits)


def main() -> None:
    version = read_app_version()
    parts = version_parts(version)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        _TEMPLATE.format(parts=parts, ver_str=version), encoding="utf-8"
    )
    # Версия в stdout — источник для build_installer.ps1 и CI.
    print(version)


if __name__ == "__main__":
    main()
