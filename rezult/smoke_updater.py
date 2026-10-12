"""Smoke-test подсистемы обновлений: без сети, чистая логика (не часть приложения)."""
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from app import config, updater  # noqa: E402

errors: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


# --- 1. Разбор и сравнение версий ---------------------------------------------
check(updater.parse_version("v1.2.0") == (1, 2, 0), "parse v1.2.0")
check(updater.parse_version("1.0") == (1, 0), "parse 1.0")
check(updater.parse_version("2.0.0.512") == (2, 0, 0, 512), "parse 2.0.0.512")
check(updater.parse_version("v2.0.0-beta") == (2, 0, 0), "parse префикс с хвостом")
check(updater.parse_version("abc") is None, "parse мусора")
check(updater.parse_version("") is None, "parse пустоты")

check(updater.is_newer("1.0.1", "1.0.0"), "1.0.1 > 1.0.0")
check(not updater.is_newer("1.0.0", "1.0.0"), "равные версии")
check(updater.is_newer("2.0.0.512", "2.0.0"), "2.0.0.512 > 2.0.0")
check(not updater.is_newer("2.0", "2.0.0"), "2.0 == 2.0.0")
check(not updater.is_newer("0.9", "1.0.0"), "0.9 < 1.0.0")
check(updater.is_newer("v10.0.0", "v9.9.9"), "числовое сравнение 10 > 9")

# --- 2. Размер файла ------------------------------------------------------------
check(updater.format_size(15 * 1024 * 1024) == "15.0 МБ", "размер в МБ")
check(updater.format_size(512 * 1024) == "512 КБ", "размер в КБ")
check(updater.format_size(None) == "", "пустой размер")

# --- 3. sha256 в тексте релиза --------------------------------------------------
sha = "a" * 64
check(updater.parse_sha256(f"sha256: {sha}") == sha, "sha256: hex")
check(updater.parse_sha256(f"Файл {sha} готов") == sha, "голый hex")
check(updater.parse_sha256("никаких сумм") is None, "нет суммы")
check(updater.parse_sha256("abc123") is None, "короткий не-hex")

# --- 4. Разбор релиза -----------------------------------------------------------
release_json = {
    "tag_name": "v1.2.0",
    "name": "Версия 1.2.0",
    "body": f"Что нового\nsha256: {sha}",
    "published_at": "2026-10-12T10:00:00Z",
    "html_url": "https://github.com/x/y/releases/tag/v1.2.0",
    "draft": False,
    "prerelease": False,
    "assets": [
        {"name": "checksums.txt", "browser_download_url": "u0", "size": 10},
        {"name": "Nodexy.exe", "browser_download_url": "u1", "size": 1234},
    ],
}
info = updater.parse_release(release_json)
check(info is not None and info.tag == "v1.2.0", "разбор релиза")
check(info.asset_name == "Nodexy.exe" and info.asset_url == "u1", "выбран exe")
check(info.asset_size == 1234, "размер ассета")
check(info.sha256 == sha, "sha256 из body")
check(info.published_at == "2026-10-12", "дата релиза")

check(updater.parse_release({**release_json, "draft": True}) is None, "черновик пропущен")
check(updater.parse_release({**release_json, "prerelease": True}) is None, "prerelease пропущен")
no_exe = updater.parse_release({**release_json, "assets": []})
check(no_exe is not None and no_exe.asset_url is None, "релиз без exe")

# --- 5. Выбор обновления и суммарные заметки ------------------------------------
def mk(tag: str, body: str, exe: bool = True, **kw):
    d = {
        "tag_name": tag,
        "name": tag,
        "body": body,
        "published_at": "2026-10-01T00:00:00Z",
        "html_url": f"page-{tag}",
        "draft": False,
        "prerelease": False,
        "assets": [{"name": "Nodexy.exe", "browser_download_url": f"u-{tag}", "size": 100}] if exe else [],
    }
    d.update(kw)
    return d

latest, notes = updater.select_update(
    [mk("v1.1.0", "первая"), mk("v1.2.0", "вторая"), mk("v1.3.0", "третья")],
    current="1.0.0",
)
check(latest is not None and latest.tag == "v1.3.0", "выбрана последняя версия")
check("v1.3.0" in notes and "v1.2.0" in notes and "v1.1.0" in notes, "заметки суммируются")

latest, notes = updater.select_update([mk("v2.0.0", "только она")], current="1.9.9")
check(latest.tag == "v2.0.0" and notes == "только она", "одна новая версия")

latest, _ = updater.select_update([mk("v1.0.0", "старая")], current="1.0.0")
check(latest is None, "обновлений нет")

latest, _ = updater.select_update([mk("v2.0.0", "x", draft=True), mk("v1.5.0", "y")], current="1.0.0")
check(latest is not None and latest.tag == "v1.5.0", "черновик не считается")

# --- 6. Целостность файла --------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    f = Path(tmp) / "file.bin"
    f.write_bytes(b"hello updater")
    import hashlib

    good_sha = hashlib.sha256(b"hello updater").hexdigest()
    ok, _ = updater.verify_file(f, len(b"hello updater"), good_sha)
    check(ok, "валидный файл принят")
    ok, reason = updater.verify_file(f, 999, good_sha)
    check(not ok and "размер" in reason, "неверный размер отклонён")
    ok, reason = updater.verify_file(f, None, "b" * 64)
    check(not ok and "sha256" in reason, "битая сумма отклонена")
    ok, _ = updater.verify_file(f, None, None)
    check(ok, "без эталона файл принят")
    ok, _ = updater.verify_file(Path(tmp) / "nope.bin", None, None)
    check(not ok, "отсутствующий файл отклонён")

# --- 7. Отсрочка «Позже» ----------------------------------------------------------
today = date(2026, 10, 12)
snooze = updater.make_snooze("v1.2.0", today)
check(updater.snooze_active(snooze, "v1.2.0", today), "отсрочка активна в день нажатия")
check(updater.snooze_active(snooze, "v1.2.0", today + timedelta(days=2)), "активна 2 дня")
check(not updater.snooze_active(snooze, "v1.2.0", today + timedelta(days=3)), "истекает через 3 дня")
check(not updater.snooze_active(snooze, "v1.3.0", today), "новая версия снимает отсрочку")
check(not updater.snooze_active(None, "v1.2.0", today), "пустая отсрочка")
check(not updater.snooze_active("мусор", "v1.2.0", today), "битая отсрочка")

# --- 8. Счётчик запусков (откат) ---------------------------------------------------
boot, rollback = updater.boot_step(None, "1.0.0")
check(boot == {"version": "1.0.0", "fails": 1} and not rollback, "первый запуск")
boot, rollback = updater.boot_step(boot, "1.0.0")
check(boot["fails"] == 2 and not rollback, "второй запуск")
boot, rollback = updater.boot_step(boot, "1.0.0")
check(rollback, "третий неудачный запуск — откат")
boot, rollback = updater.boot_step({"version": "0.9.0", "fails": 9}, "1.0.0")
check(boot["fails"] == 1 and not rollback, "смена версии сбрасывает счётчик")

# --- 9. Состояние обновления в config.json -----------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    config.APP_DIR = Path(tmp)
    old_version = updater.APP_VERSION
    try:
        updater.APP_VERSION = "1.0.0"

        # Успех: ожидающая версия совпала с запущенной
        updater.set_pending({"version": "1.0.0", "notes": "заметки", "file": "x", "page": "p", "attempts": 1})
        res = updater.startup_processing()
        check(res["plate"] == "1.0.0", "плашка после успешного обновления")
        check(updater.get_pending() is None, "pending очищен после успеха")
        check(updater.get_last_update()["notes"] == "заметки", "заметки сохранены для «Что нового»")

        # Провал: версия новее, счётчик попыток растёт
        updater.set_pending({"version": "2.0.0", "notes": "", "file": "нет-файла", "page": "url", "attempts": 0})
        res = updater.startup_processing()
        check(updater.get_pending()["attempts"] == 1, "попытка №1 учтена")
        updater.startup_processing()
        res = updater.startup_processing()
        check(res["failed_url"] == "url", "исчерпаны попытки — страница релиза")
        check(updater.get_pending() is None, "pending очищен после исчерпания")

        # Стоп-кран
        updater.set_pending({"version": "3.0.0", "notes": "", "file": "f", "page": "", "attempts": 0})
        updater.startup_processing(skip_update=True)
        check(updater.get_pending() is None, "--skip-update сбрасывает ожидание")

        updater.clear_last_update()
        check(updater.get_last_update() is None, "очистка «Что нового»")
    finally:
        updater.APP_VERSION = old_version

# --- 10. Скрипт апдейтера -------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    config.APP_DIR = Path(tmp)
    old_exe = Path(tmp) / "Nodexy.exe"
    new_exe = Path(tmp) / "new" / "Nodexy.exe"
    new_exe.parent.mkdir()
    old_exe.write_text("old")
    new_exe.write_text("new")
    script = updater.write_updater_script(old_exe, new_exe, 1234, restart=False)
    text = script.read_text(encoding="ascii")
    check('set "PID=1234"' in text, "pid в скрипте")
    check(str(old_exe) in text and str(new_exe) in text, "пути в скрипте")
    check("%OLD%.old" in text, "резервная копия .old")
    check("restart" not in text.split("MODE")[1].split("\n")[0] or "once" in text, "режим без перезапуска")
    script2 = updater.write_updater_script(old_exe, new_exe, 1234, restart=True)
    check("restart" in script2.read_text(encoding="ascii").split("MODE=")[1].split("\n")[0], "режим с перезапуском")

# --- 11. Режим запуска из исходников -----------------------------------------------------
can, reason = updater.can_self_update()
check(not can, "из исходников самообновление недоступно")
check(reason != "", "указана причина деградации")
check(not updater.schedule_apply(restart=False), "без frozen апдейтер не запускается")

# --- 12. Панели обновлений (offscreen) ------------------------------------------------------
from app.ui.update_dialog import UpdatePanel, WhatsNewPanel  # noqa: E402

rel = updater.ReleaseInfo(
    tag="v1.2.0", name="1.2.0", body="заметки", published_at="2026-10-12",
    html_url="https://example.com", asset_name="Nodexy.exe",
    asset_url="https://example.com/f.exe", asset_size=1000, sha256=None,
)
panel = UpdatePanel(rel, "заметки", install_possible=False, reason="тест")
panel.set_status("статус")
panel.shutdown()
no_asset = updater.ReleaseInfo(
    tag="v1.3.0", name="1.3.0", body="", published_at="", html_url="h",
)
panel2 = UpdatePanel(no_asset, "", install_possible=True)
check("установочного файла" in panel2._status.text(), "релиз без exe — только страница")
panel2.shutdown()
wn = WhatsNewPanel("v1.2.0", "список изменений")
wn.deleteLater()

if errors:
    print("FAIL")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("OK: all updater smoke checks passed")
