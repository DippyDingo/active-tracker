import ctypes
import datetime
import faulthandler
import sys
import traceback
from datetime import date

from PySide6.QtCore import QLockFile, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app import config, updater
from app.runtime import InstanceGuard, create_application
from app.db import Database
from app.tracker import Tracker
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.welcome_dialog import WelcomeDialog

# Ротация логов до открытия crash.log: файл не должен расти бесконечно.
try:
    config.rotate_logs()
except Exception:
    pass

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
    """Одноразовая миграция: размазать «сегодня» по часам, если почасовые данные
    отсутствуют (наследие версий до почасового учёта).

    Выполняется только когда в настройках нет маркера `hours_backfilled`.
    Раньше это выполнялось при КАЖДОМ запуске: пока приложение было закрыто,
    секунды копились в `stats`, а при следующем старте равномерно
    размазывались по уже прошедшим часам — почасовой график «сегодня»
    выглядел неестественно ровным.
    """
    if db.has("hours_backfilled"):
        return
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
    db.set_int("hours_backfilled", 1)


def _daily_backup(db: Database) -> None:
    """Раз в сутки снимает консистентную копию базы в updates\\..\\backup.

    Раньше резервных копий не было вовсе: повреждение файла или неудачная
    миграция означали безвозвратную потерю всей статистики.
    """
    try:
        today = date.today().isoformat()
        if db.get_text("last_backup") == today:
            return
        dest = config.app_dir() / "backup" / f"tracker_{today}.db"
        if not db.backup_to(dest):
            return
        db.set_text("last_backup", today)
        # Храним только три последних копии.
        backup_dir = config.app_dir() / "backup"
        copies = sorted(backup_dir.glob("tracker_*.db"))
        for old in copies[:-3]:
            try:
                old.unlink()
            except OSError:
                pass
    except Exception:
        config.log_error("main._daily_backup")


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


def _make_splash():
    """Тёмный сплэш в цветах текущей палитры (лёгкий, без анимаций)."""
    try:
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QFont, QPixmap
        from PySide6.QtWidgets import QSplashScreen

        p = theme.pal()
        w, h = 300, 180
        pm = QPixmap(w, h)
        pm.fill(QColor(p.bg))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        icon = theme.make_clock_icon().pixmap(QSize(72, 72))
        painter.drawPixmap((w - 72) // 2, 26, icon)
        font = QFont("Segoe UI", 14, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(p.text))
        painter.drawText(
            QRectF(0, 106, w, 26), Qt.AlignCenter, "Nodexy"
        )
        small = QFont("Segoe UI", 9)
        painter.setFont(small)
        painter.setPen(QColor(p.text2))
        painter.drawText(QRectF(0, 132, w, 20), Qt.AlignCenter, "загрузка…")
        painter.end()
        splash = QSplashScreen(pm)
        splash.show()
        return splash
    except Exception:
        return None


def main() -> int:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "DippyDingo.Nodexy"
            )
        except Exception:
            pass

    # QApplication создаётся ровно один раз и ДО любых проверок/диалогов.
    # Тема и палитра применяются здесь же, поэтому первое же окно рождается
    # уже в цветах темы (никакого белого кадра).
    qt = create_application(sys.argv)

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

    guard = InstanceGuard()
    if not guard.acquire():
        # Второй экземпляр ничего не рисует и не создаёт окон: просит уже
        # запущенное приложение показать окно и тихо завершается.
        try:
            from app import win32_utils
            win32_utils.activate_existing_window("Nodexy")
        except Exception:
            pass
        return 0

    # Бут-контроль и применение ожидающего обновления — до появления окна.
    boot = updater.startup_processing(skip_update)
    if boot.get("rollback"):
        # Внешний апдейтер вернёт старую версию и перезапустит её.
        return 0

    # Отдельный QSplashScreen намеренно не используем: это самостоятельный
    # top-level HWND, который Windows успевал показать белым до первого кадра
    # главного окна. С onedir загрузка достаточно быстрая, а первое окно сразу
    # создаётся с уже установленной палитрой.
    _splash = None
    db_path = _resolve_db_path()
    if not db_path:
        return 0
    if not config.set_db_path(db_path):
        config.log_error("Не удалось сохранить путь к базе данных в config.json")

    db = Database(db_path)
    theme.apply_theme(qt, db.get_text("theme", theme.DEFAULT_THEME))
    _ensure_first_launch(db)
    _backfill_today_hours(db)
    # Ежедневная резервная копия БД (не чаще раза в сутки; храним 3 шт.).
    _daily_backup(db)
    
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
    # Штатный выход помечаем: счётчик неудачных запусков (откат версии) должен
    # расти только на реальных падениях, а не на обычном закрытии окна.
    qt.aboutToQuit.connect(updater.mark_clean_exit)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
