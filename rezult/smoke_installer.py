"""Smoke-test установочной инфраструктуры (не часть приложения)."""
import importlib.util
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from app import updater  # noqa: E402

errors: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


# --- 1. Детектор ассета-установщика -------------------------------------------
for name in (
    "Nodexy-Setup-1.2.3.exe",
    "nodexy_setup_2.0.exe",
    "Setup-Nodexy.exe",
    "Nodexy-Installer.exe",
    "my_installer_x.exe",
):
    check(updater.is_installer_asset(name), f"должен быть установщиком: {name}")
for name in ("Nodexy.exe", "nodexy-portable.exe", "app.exe"):
    check(not updater.is_installer_asset(name), f"не должен быть установщиком: {name}")

# --- 2. Выбор ассета: голый exe и setup в обоих порядках ----------------------
def mk_asset(name: str) -> dict:
    return {"name": name, "browser_download_url": f"u/{name}", "size": 100}

both_orders = (
    [mk_asset("Nodexy.exe"), mk_asset("Nodexy-Setup-1.0.0.exe")],
    [mk_asset("Nodexy-Setup-1.0.0.exe"), mk_asset("Nodexy.exe")],
)
for assets in both_orders:
    name, url, size = updater._pick_asset(assets, prefer_installer=False)
    check(name == "Nodexy.exe", f"prefer_installer=False должен взять голый exe, а не {name}")
    name, url, size = updater._pick_asset(assets, prefer_installer=True)
    check(name == "Nodexy-Setup-1.0.0.exe", f"prefer_installer=True должен взять установщик, а не {name}")

# Только установщик — голый exe выбирает его как запасной вариант
name, _u, _s = updater._pick_asset([mk_asset("Nodexy-Setup-2.0.0.exe")], prefer_installer=False)
check(name == "Nodexy-Setup-2.0.0.exe", "нет голого exe — берём установщик")
# Только голый при предпочтении установщика: стратегия B строга — без
# установщика релиз непригоден (иначе апдейтер скачал бы голый exe).
name, _u, _s = updater._pick_asset([mk_asset("Nodexy.exe")], prefer_installer=True)
check(name is None, "нет установщика — голый exe НЕ берём (стратегия B)")
check(updater._pick_asset([], prefer_installer=False) == (None, None, None), "пустой список ассетов")

# .zip не считается ассетом для установки
name, _u, _s = updater._pick_asset([mk_asset("Nodexy-portable-1.0.0.zip")], prefer_installer=True)
check(name is None, "zip не должен выбираться")

# --- 3. Разбиение версии на 4 компонента ----------------------------------------
spec = importlib.util.spec_from_file_location(
    "make_version_info", ROOT / "tools" / "make_version_info.py"
)
mvi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mvi)
check(mvi.version_parts("1.2.3") == (1, 2, 3, 0), "1.2.3 -> (1,2,3,0)")
check(mvi.version_parts("1.2.3.4") == (1, 2, 3, 4), "1.2.3.4 -> как есть")
check(mvi.version_parts("2.0.0.512") == (2, 0, 0, 512), "2.0.0.512")
check(mvi.version_parts("v10.20") == (10, 20, 0, 0), "v10.20 -> нули дополнением")
version = mvi.read_app_version()
check(updater.parse_version(version) is not None, "APP_VERSION читается из файла")
mvi.main()
vi = (ROOT / "installer" / "version_info.txt").read_text(encoding="utf-8")
check("VSVersionInfo" in vi and "041904b0" in vi, "version_info.txt сгенерирован")

# --- 4. Обязательные директивы в installer/nodexy.iss ----------------------------
iss = (ROOT / "installer" / "nodexy.iss").read_text(encoding="utf-8")
iss_lines = [line.strip() for line in iss.splitlines()]
check("AppId={{4B8E2F7A" in iss, "AppId — фиксированный GUID")
check(any(l.startswith("PrivilegesRequired=lowest") for l in iss_lines), "только per-user")
check(not any(l.startswith("PrivilegesRequiredOverridesAllowed") for l in iss_lines),
      "нет опции «для всех пользователей»")
check(any(l.startswith("DisableDirPage=no") for l in iss_lines), "страница выбора каталога всегда")
check('AppMutex={#MyAppMutex}' in iss, "AppMutex задан")
check(sum(1 for l in iss_lines if l == "[Run]") == 1
      and "Check: RestartAfterSilentUpdate" in iss,
      "тихий [Run] с RestartAfterSilentUpdate")
check("postinstall skipifsilent" in iss, "ручной [Run] с postinstall")
check("*.old" in iss and "_internal" in iss, "[UninstallDelete] чистит .old и _internal")
check("Удалить также статистику и настройки?" in iss, "вопрос про данные при деинсталляции")
check("MB_DEFBUTTON2" in iss, "по умолчанию — НЕТ")
check("function NextButtonClick" in iss and "{commonpf}" in iss,
      "защита от установки в Program Files")
check("uninsdeletevalue" in iss, "Run-ключ удаляется при деинсталляции")
check("Russian.isl" in iss, "русская локализация")

# --- 5. Имя мьютекса совпадает в приложении и в установщике -----------------------
from app import win32_utils  # noqa: E402

check(f'#define MyAppMutex "{win32_utils.INSTANCE_MUTEX_NAME}"' in iss,
      "имя мьютекса совпадает в коде и в .iss")

if errors:
    print("FAIL")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("OK: all installer smoke checks passed")
