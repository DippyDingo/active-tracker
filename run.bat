@echo off
rem Запуск актуальной исходной версии REDIS (без установленной копии).
rem Если приложение уже работает — останавливаем его, чтобы не осталось
rem старого окна: запущенная копия молча закрывалась бы по мьютексу.
setlocal
set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
  echo ОШИБКА: не найден %PYTHONW%
  echo Сначала создайте виртуальное окружение: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

rem Завершаем только наши процессы (pythonw.exe c main.py из этой папки).
for /f "tokens=2 delims=," %%P in ('
  wmic process where "name='pythonw.exe' and CommandLine like '%%active-tracker%%main.py%%'" get ProcessId /format:csv 2^>nul ^| findstr /r "[0-9]"
') do taskkill /PID %%P /F >nul 2>&1

start "" "%PYTHONW%" "%~dp0main.py"
endlocal
