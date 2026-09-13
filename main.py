import ctypes
import datetime
import faulthandler
import sys
import traceback
from datetime import date

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app import config
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
    _ensure_first_launch(db)
    _backfill_today_hours(db)
    tracker = Tracker(db)
    window = MainWindow(db, tracker)
    window.show()
    tracker.start()
    qt.aboutToQuit.connect(tracker.stop)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
