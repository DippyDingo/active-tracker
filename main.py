import ctypes
import datetime
import faulthandler
import sys
import traceback
from datetime import date

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app import config, updater
from app.db import Database
from app.tracker import Tracker
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.welcome_dialog import WelcomeDialog

_CRASH_LOG = config.app_dir() / "crash.log"
_crash_file = open(_CRASH_LOG, "a", encoding="utf-8")
faulthandler.enable(file=_crash_file)


def _excepthook(exc_type, exc_value, exc_tb):
    try:
        _crash_file.write(f"\n=== {datetime.datetime.now().isoformat()} ===\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=_crash_file)
        _crash_file.flush()
    except Exception:
        pass


sys.excepthook = _excepthook


def _ensure_first_launch(db: Database) -> None:
    if config.read_config().get("first_launch"):
        return
    earliest = db.get_min_day()
    config.write_config(
        {**config.read_config(), "first_launch": earliest or date.today().isoformat()}
    )


def _backfill_today_hours(db: Database) -> None:
    import time

    today = date.today().isoformat()
    span = max(1, time.localtime().tm_hour + 1)
    for app_id, total in db.get_day_stats(today).items():
        diff = total - sum(db.get_hours(app_id, today))
        if diff <= 0:
            continue
        per = diff // span
        rem = diff - per * span
        for hour in range(span):
            add = per + (1 if hour < rem else 0)
            if add > 0:
                db.add_hour(app_id, today, hour, add)


def _resolve_db_path() -> str:
    db_path = config.get_db_path()
    if db_path and Database.validate(db_path):
        return db_path
    dialog = WelcomeDialog()
    dialog.setWindowIcon(theme.load_app_icon())
    if dialog.exec() != QDialog.Accepted:
        return ""
    if dialog.mode == "create":
        return str(config.default_db_path())
    return dialog.path


def main() -> int:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "DippyDingo.Nodexy"
            )
        except Exception:
            pass

    # Проверка флага --minimized
    start_minimized = "--minimized" in sys.argv
    # Стоп-кран: --skip-update пропускает ожидающее обновление (аварийный вход).
    skip_update = "--skip-update" in sys.argv

    # Прямо сейчас помощник ставит обновление (пользователь запустил приложение
    # во время установки): мгновенно выйти и оставить лёгкий вейтер — он
    # дождётся окончания установки и откроет уже новую версию. Ждать внутри
    # процесса нельзя: живой Nodexy блокирует установщик (AppMutex).
    # Проверка делается ДО мьютекса, чтобы не мешать установке.
    if getattr(sys, "frozen", False) and not skip_update:
        if updater.install_in_progress():
            updater.spawn_relaunch_waiter(
                [a for a in sys.argv[1:] if a != "--skip-update"]
            )
            return 0

    if sys.platform == "win32":
        # Именованный мьютекс нужен установщику Inno (AppMutex): по нему он
        # понимает, что приложение запущено. Держится до выхода процесса.
        # QLockFile ниже остаётся как внутренняя защита второго экземпляра.
        from app import win32_utils

        if not win32_utils.acquire_instance_mutex():
            app = QApplication(sys.argv)
            QMessageBox.information(None, "Nodexy", "Приложение уже запущено.")
            return 0

    # Бут-контроль и применение ожидающего обновления — до появления окна.
    boot = updater.startup_processing(skip_update)
    if boot.get("rollback"):
        # Внешний апдейтер вернёт старую версию и перезапустит её.
        return 0

    lock = QLockFile(str(config.app_dir() / "nodexy.lock"))
    if not lock.tryLock(100):
        app = QApplication(sys.argv)
        QMessageBox.information(None, "Nodexy", "Приложение уже запущено.")
        return 0

    qt = QApplication(sys.argv)
    qt.setApplicationName("Nodexy")
    qt.setOrganizationName("Nodexy")
    qt.setStyleSheet(theme.QSS)
    qt.setWindowIcon(theme.load_app_icon())
    qt.setQuitOnLastWindowClosed(False)

    db_path = _resolve_db_path()
    if not db_path:
        return 0
    if not config.set_db_path(db_path):
        config.log_error("Не удалось сохранить путь к базе данных в config.json")

    db = Database(db_path)
    theme.apply_theme(qt, db.get_text("theme", theme.DEFAULT_THEME))
    _ensure_first_launch(db)
    _backfill_today_hours(db)
    
    # Синхронизация автозапуска (HKCU\...\Run, значение "Nodexy") с настройкой в БД:
    # 1) в БД включён — путь в реестре всегда актуализируется;
    # 2) в БД выключен — удаляем запись, только если она указывает на ТЕКУЩИЙ
    #    exe (чужую запись, сделанную пользователем вручную, не трогаем);
    # 3) ключа в БД вообще нет — «усыновляем» автозапуск, оставленный
    #    установщиком: если запись в реестре указывает на текущий exe,
    #    фиксируем в БД 1, чтобы галочка в настройках отражала реальность.
    from app import win32_utils
    autostart_setting = db.get_int("autostart", 0)
    if autostart_setting == 1:
        win32_utils.set_autostart(True)
    elif db.has("autostart"):
        if win32_utils.autostart_points_to_current():
            win32_utils.set_autostart(False)
    else:
        if win32_utils.autostart_points_to_current():
            db.set_int("autostart", 1)
    
    tracker = Tracker(db)
    window = MainWindow(db, tracker, boot)

    if start_minimized:
        # Не показывать окно, только иконка в трее
        pass
    else:
        window.show()

    # Если окно стабильно работает ~10 секунд — старт успешен:
    # сбрасываем счётчик запусков и убираем резервную копию .old.
    QTimer.singleShot(10_000, updater.boot_success)

    tracker.start()
    qt.aboutToQuit.connect(tracker.stop)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
