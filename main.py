import ctypes
import datetime
import faulthandler
import sys
import traceback
from datetime import date

from PySide6.QtWidgets import QApplication, QDialog

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
    earliest = None
    for _app_id, day, _secs in db.query_stats():
        if earliest is None or day < earliest:
            earliest = day
    config.write_config(
        {**config.read_config(), "first_launch": earliest or date.today().isoformat()}
    )


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
                "DippyDingo.ActiveTracker"
            )
        except Exception:
            pass

    qt = QApplication(sys.argv)
    qt.setApplicationName("Active Tracker")
    qt.setOrganizationName("ActiveTracker")
    qt.setStyleSheet(theme.QSS)
    qt.setWindowIcon(theme.load_app_icon())
    qt.setQuitOnLastWindowClosed(False)

    db_path = _resolve_db_path()
    if not db_path:
        return 0
    config.set_db_path(db_path)

    db = Database(db_path)
    _ensure_first_launch(db)
    tracker = Tracker(db)
    window = MainWindow(db, tracker)
    window.show()
    tracker.start()
    qt.aboutToQuit.connect(tracker.stop)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
