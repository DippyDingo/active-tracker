import sys

from PySide6.QtWidgets import QApplication

from app.db import Database
from app.tracker import Tracker
from app.ui import theme
from app.ui.main_window import MainWindow


def main() -> int:
    qt = QApplication(sys.argv)
    qt.setApplicationName("Active Tracker")
    qt.setOrganizationName("ActiveTracker")
    qt.setStyleSheet(theme.QSS)
    qt.setWindowIcon(theme.make_clock_icon())
    qt.setQuitOnLastWindowClosed(False)

    db = Database()
    tracker = Tracker(db)
    window = MainWindow(db, tracker)
    window.show()
    tracker.start()
    qt.aboutToQuit.connect(tracker.stop)
    return qt.exec()


if __name__ == "__main__":
    sys.exit(main())
