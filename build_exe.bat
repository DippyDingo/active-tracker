@echo off
cd /d "%~dp0"

rem Ресурс версии exe генерируется из app/version.py; если генерация не
rem удалась — собираем без него, сборка не должна из-за этого падать.
set "VERSION_ARGS="
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe tools\make_version_info.py >nul
  if exist installer\version_info.txt set "VERSION_ARGS=--version-file installer\version_info.txt"
)
if "%VERSION_ARGS%"=="" echo Предупреждение: version_info.txt не создан, сборка без ресурса версии.

call .venv\Scripts\pyinstaller.exe --noconfirm --onedir --noconsole ^
  --name Nodexy ^
  %VERSION_ARGS% ^
  --icon assets\app_icon.ico ^
  --add-data "assets;assets" ^
  --hidden-import win32com.client ^
  --hidden-import pythoncom ^
  --hidden-import win32ui ^
  --hidden-import win32gui ^
  --hidden-import win32api ^
  --hidden-import win32con ^
  main.py
if errorlevel 1 (
  echo.
  echo ОШИБКА СБОРКИ: dist\Nodexy.exe не создан.
  if not defined CI pause
  exit /b 1
)
echo.
echo Готово: dist\Nodexy\Nodexy.exe
rem В CI (определена переменная CI) не ждём нажатия клавиши.
if not defined CI pause
