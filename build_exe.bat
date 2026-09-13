@echo off
cd /d "%~dp0"
call .venv\Scripts\pyinstaller.exe --noconfirm --onefile --noconsole ^
  --name ActiveTracker ^
  --icon assets\app_icon.ico ^
  --add-data "assets;assets" ^
  --hidden-import win32com.client ^
  --hidden-import pythoncom ^
  --hidden-import win32ui ^
  --hidden-import win32gui ^
  --hidden-import win32api ^
  --hidden-import win32con ^
  main.py
echo.
echo Готово: dist\ActiveTracker.exe
pause
