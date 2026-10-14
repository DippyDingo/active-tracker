# Сборка артефактов релиза Nodexy: exe → установщик Inno → portable-zip → SHA256.
# Запуск: powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_installer.ps1
# Параметр -SkipExe позволяет собрать только установщик, если exe уже готов.
param(
    [switch]$SkipExe
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Fail($msg) {
    Write-Error $msg
    exit 1
}

# 1) Версия из единого источника: печатает версию и создаёт
#    installer/version_info.txt для PyInstaller.
$version = & ".venv\Scripts\python.exe" "tools\make_version_info.py"
if ($LASTEXITCODE -ne 0 -or -not $version) {
    Fail "Не удалось определить версию из app/version.py"
}
$version = $version.Trim()
Write-Host "Версия: $version"

# 2) Сборка exe теми же параметрами, что и build_exe.bat (без pause).
if (-not $SkipExe) {
    & ".venv\Scripts\pyinstaller.exe" --noconfirm --onefile --noconsole `
        --name Nodexy `
        --version-file installer\version_info.txt `
        --icon assets\app_icon.ico `
        --add-data "assets;assets" `
        --hidden-import win32com.client `
        --hidden-import pythoncom `
        --hidden-import win32ui `
        --hidden-import win32gui `
        --hidden-import win32api `
        --hidden-import win32con `
        main.py
    if ($LASTEXITCODE -ne 0) { Fail "PyInstaller: сборка exe не удалась" }
}
if (-not (Test-Path "dist\Nodexy.exe")) { Fail "dist\Nodexy.exe не найден" }

# 3) Поиск ISCC: PATH → Program Files (x86) → Program Files.
$iscc = $null
$inPath = Get-Command iscc.exe -ErrorAction SilentlyContinue
if ($inPath) { $iscc = $inPath.Source }
foreach ($candidate in @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)) {
    if (-not $iscc -and $candidate -and (Test-Path $candidate)) { $iscc = $candidate }
}
if (-not $iscc) {
    Fail "Inno Setup 6 не найден. Установите: winget install JRSoftware.InnoSetup"
}

# 4) Компиляция установщика: версия передаётся одним параметром.
& $iscc "/DMyAppVersion=$version" "installer\nodexy.iss"
if ($LASTEXITCODE -ne 0) { Fail "ISCC: компиляция установщика не удалась" }

# 5) Портативный архив (понадобится, когда голый exe перестанет
#    публиковаться отдельным ассетом).
$distInstaller = Join-Path $root "dist-installer"
$zipPath = Join-Path $distInstaller "Nodexy-portable-$version.zip"
Compress-Archive -Path "dist\Nodexy.exe" -DestinationPath $zipPath -Force

# 6) Контрольные суммы всех артефактов.
$setup = Join-Path $distInstaller "Nodexy-Setup-$version.exe"
if (-not (Test-Path $setup)) { Fail "Установщик не создан: $setup" }
$shaSetup = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
$shaExe = (Get-FileHash "dist\Nodexy.exe" -Algorithm SHA256).Hash.ToLower()
$shaZip = (Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLower()
Set-Content -Path "$setup.sha256" -Value $shaSetup -Encoding ascii

# 7) Итоги с явными подписями: какая сумма куда идёт.
Write-Host ""
Write-Host "=== Артефакты ==="
Write-Host $setup
Write-Host "$setup.sha256"
Write-Host "dist\Nodexy.exe"
Write-Host $zipPath
Write-Host ""
Write-Host "=== Контрольные суммы ==="
Write-Host "Nodexy.exe:                 $shaExe"
Write-Host "Nodexy-Setup-$version.exe:  $shaSetup"
Write-Host "Nodexy-portable-$version.zip: $shaZip"
Write-Host ""
# ВАЖНО (стратегия B): апдейтер скачивает УСТАНОВЩИК и сверяет сумму из тела
# релиза, поэтому в тело релиза идёт сумма Nodexy-Setup-<версия>.exe.
Write-Host "В ТЕЛО РЕЛИЗА (одна строка):"
Write-Host "sha256: $shaSetup"
Write-Host "В ФАЙЛ $setup.sha256 (дубль для ручной проверки):"
Write-Host $shaSetup
