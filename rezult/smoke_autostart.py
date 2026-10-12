"""Тесты для функций автозапуска."""
import sys
from pathlib import Path

# Исправляем кодировку для Windows консоли
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Добавляем корневую директорию в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.win32_utils import autostart_command


def test_autostart_command_frozen():
    """Тест формирования командной строки для собранного exe."""
    exe_path = r"C:\Program Files\Nodexy\Nodexy.exe"
    cmd = autostart_command(exe_path, None, minimized=True, frozen=True)
    assert cmd == r'"C:\Program Files\Nodexy\Nodexy.exe" --minimized', f"Got: {cmd}"
    print("✓ frozen with spaces")


def test_autostart_command_frozen_no_minimized():
    """Тест формирования командной строки без --minimized."""
    exe_path = r"C:\Apps\Nodexy.exe"
    cmd = autostart_command(exe_path, None, minimized=False, frozen=True)
    assert cmd == r'"C:\Apps\Nodexy.exe"', f"Got: {cmd}"
    print("✓ frozen without --minimized")


def test_autostart_command_dev():
    """Тест формирования командной строки для dev-окружения (pythonw.exe)."""
    exe_path = r"C:\Users\lex\Documents\active-tracker\.venv\Scripts\python.exe"
    script_path = r"C:\Users\lex\Documents\active-tracker\main.py"
    
    # Тестируем с frozen=False
    cmd = autostart_command(exe_path, script_path, minimized=True, frozen=False)
    # Ожидаем либо pythonw.exe, либо python.exe
    assert "main.py" in cmd, f"Got: {cmd}"
    assert "--minimized" in cmd, f"Got: {cmd}"
    assert '"' in cmd, f"Got: {cmd}"  # Кавычки должны быть
    print(f"✓ dev mode: {cmd}")


def test_autostart_command_spaces_in_path():
    """Тест с пробелами в путях."""
    exe_path = r"C:\Program Files (x86)\My Apps\Nodexy.exe"
    cmd = autostart_command(exe_path, None, minimized=True, frozen=True)
    assert cmd.startswith('"'), f"Got: {cmd}"
    assert cmd.count('"') >= 2, f"Got: {cmd}"
    print("✓ spaces in path")


if __name__ == "__main__":
    print("Запуск тестов автозапуска...")
    print()
    
    test_autostart_command_frozen()
    test_autostart_command_frozen_no_minimized()
    test_autostart_command_dev()
    test_autostart_command_spaces_in_path()
    
    print()
    print("Все тесты пройдены! ✓")
    print()
    print("Ручное тестирование:")
    print("1. Запустите приложение")
    print("2. Откройте настройки и включите 'Запускать при входе в Windows'")
    print("3. Проверьте реестр: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run")
    print("4. Перезагрузите систему и проверьте, что приложение запустилось в трее")
    print("5. Выключите автозапуск и проверьте, что значение удалено из реестра")
