@echo off
cd /d "%~dp0"

REM Проверяем чистоту рабочей копии: незакоммиченное не публикуем молча.
git diff-index --quiet HEAD -- 2>nul
if errorlevel 1 (
  echo Рабочая копия не чистая. Сначала закоммить изменения:
  echo   git add -A ^&^& git commit -m "..."
  pause
  exit /b 1
)

REM Версия берётся из app/version.py и должна совпадать с тегом v<версия>.
for /f "tokens=2 delims=" %%V in ('.venv\Scripts\python.exe -c "import re;print(re.search(r'APP_VERSION = \"([^\"]+)\"',open('app/version.py',encoding='utf-8').read()).group(1))"') do set "VERSION=%%V"
if "%VERSION%"=="" (
  echo Не удалось прочитать APP_VERSION из app/version.py
  pause
  exit /b 1
)

echo Публикация v%VERSION%: коммит и пуш main, затем тег v%VERSION%.
git push origin main
if errorlevel 1 goto :fail

git tag v%VERSION%
if errorlevel 1 (
  echo Тег v%VERSION% уже существует? Проверь: git tag -l v%VERSION%
  goto :fail
)
git push origin v%VERSION%
if errorlevel 1 goto :fail

echo.
echo Готово: GitHub Actions соберёт и опубликует релиз v%VERSION%.
echo Прогресс: gh run watch или вкладка Actions в репозитории.
pause
exit /b 0

:fail
echo.
echo Ошибка публикации. Проверь интернет и доступ к репозиторию.
pause
exit /b 1
