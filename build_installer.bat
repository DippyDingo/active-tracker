@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_installer.ps1 %*
if errorlevel 1 exit /b 1
if not defined CI pause
