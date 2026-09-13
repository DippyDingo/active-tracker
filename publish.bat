@echo off
echo Автоматическая публикация на GitHub
echo.

REM Добавляем удаленный репозиторий (замени URL на свой)
git remote add origin https://github.com/DippyDingo/active-tracker.git

REM Пушим изменения
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo Успешно опубликовано!
    echo Открой https://github.com/DippyDingo/active-tracker для просмотра
) else (
    echo.
    echo Ошибка публикации. Убедитесь, что:
    echo 1. У вас есть интернет
    echo 2. Репозиторий существует на GitHub
    echo 3. У вас есть права на запись
    echo 4. Учетные данные GitHub настроены
)

pause