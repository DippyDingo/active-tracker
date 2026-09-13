import ctypes
import sys

from PySide6.QtWidgets import QApplication, QDialog

from app import config
from app.db import Database
from app.tracker import Tracker
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.welcome_dialog import WelcomeDialog


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
    tracker = Tracker(db)
    window = MainWindow(db, tracker)
    window.show()
    tracker.start()
    qt.aboutToQuit.connect(tracker.stop)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
