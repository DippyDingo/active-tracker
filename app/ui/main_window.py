import os
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import win32_utils
from ..db import Database
from ..tracker import GRACE_SECONDS, Tracker
from ..utils import format_seconds
from .add_dialog import AddAppDialog
from .settings_dialog import SettingsDialog


class AppCard(QFrame):
    delete_requested = Signal(int)

    def __init__(self, app_id: int, name: str, exe_path: str, icon_bytes: bytes | None, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self.exe_path = exe_path
        self.setObjectName("appCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignCenter)
        if icon_bytes:
            pm = QPixmap()
            if pm.loadFromData(icon_bytes, "PNG"):
                icon_label.setPixmap(
                    pm.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        layout.addWidget(icon_label)

        info = QVBoxLayout()
        info.setSpacing(2)
        name_row = QHBoxLayout()
        name_row.setSpacing(7)
        name_label = QLabel(name)
        name_label.setObjectName("appName")
        self._dot = QLabel()
        self._dot.setObjectName("runningDot")
        self._dot.setFixedSize(8, 8)
        self._dot.setVisible(False)
        self._dot.setToolTip("Приложение запущено")
        name_row.addWidget(name_label)
        name_row.addWidget(self._dot)
        name_row.addStretch(1)

        path_label = QLabel(exe_path)
        path_label.setObjectName("appPath")
        path_label.setToolTip(exe_path)
        metrics = path_label.fontMetrics()
        path_label.setFixedWidth(min(420, max(200, metrics.horizontalAdvance(exe_path) + 8)))
        path_label.setText(metrics.elidedText(exe_path, Qt.ElideMiddle, path_label.width()))

        info.addLayout(name_row)
        info.addWidget(path_label)
        layout.addLayout(info, 1)

        times = QVBoxLayout()
        times.setSpacing(2)
        self._today = QLabel()
        self._today.setObjectName("timeBig")
        self._today.setAlignment(Qt.AlignRight)
        self._total = QLabel()
        self._total.setObjectName("appPath")
        self._total.setAlignment(Qt.AlignRight)
        times.addWidget(self._today)
        times.addWidget(self._total)
        layout.addLayout(times)

        delete_btn = QPushButton("✕")
        delete_btn.setObjectName("deleteBtn")
        delete_btn.setFixedSize(26, 26)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setToolTip("Удалить из списка")
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.app_id))
        layout.addWidget(delete_btn, 0, Qt.AlignTop)

    def set_times(self, today_s: int, total_s: int) -> None:
        self._today.setText(f"Сегодня · {format_seconds(today_s)}")
        self._total.setText(f"Всего · {format_seconds(total_s)}")

    def set_running(self, running: bool) -> None:
        self._dot.setVisible(running)


class MainWindow(QMainWindow):
    def __init__(self, db: Database, tracker: Tracker):
        super().__init__()
        self.db = db
        self.tracker = tracker
        self._cards: dict[int, AppCard] = {}
        self._names: dict[int, str] = {}
        self._running: set[str] = set()
        self._tick_count = 0
        self._tray_hint_shown = False
        self._tray = None
        self._tray_menu = None

        self.setWindowTitle("Трекер активности")
        self.resize(940, 640)
        self.setMinimumSize(720, 480)

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 16, 22, 16)
        header_layout.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Активное время")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Честный учёт времени в выбранных приложениях")
        subtitle.setObjectName("subtleLabel")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header_layout.addLayout(titles)
        header_layout.addStretch(1)

        self._today_total = QLabel("—")
        self._today_total.setObjectName("todayTotal")
        header_layout.addWidget(self._today_total)

        settings_btn = QPushButton("Настройки")
        settings_btn.clicked.connect(self._open_settings)
        header_layout.addWidget(settings_btn)

        add_btn = QPushButton("＋  Добавить приложение")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._open_add)
        header_layout.addWidget(add_btn)

        root_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setObjectName("scrollContainer")
        self._list_layout = QVBoxLayout(container)
        self._list_layout.setContentsMargins(22, 18, 22, 18)
        self._list_layout.setSpacing(10)
        self._empty = QLabel(
            "Список пуст.\nДобавьте приложение, чтобы начать учёт активного времени."
        )
        self._empty.setObjectName("emptyLabel")
        self._empty.setAlignment(Qt.AlignCenter)
        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

        self._status = QLabel()
        self.statusBar().addWidget(self._status, 1)
        self._status_right = QLabel()
        self.statusBar().addPermanentWidget(self._status_right)

        self._build_tray()
        self.tracker.tick.connect(self._on_tick)
        self.refresh_apps()
        self._on_tick()

    def refresh_apps(self) -> None:
        self.tracker.flush()
        apps = self.db.list_apps()

        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._empty:
                widget.deleteLater()
        self._cards.clear()
        self._names.clear()

        self._empty.setVisible(not apps)
        self._list_layout.addWidget(self._empty)

        day = date.today().isoformat()
        stats = self.db.get_day_stats(day)
        totals = self.db.get_totals()
        self._running = self.tracker.running_paths()

        for row in apps:
            card = AppCard(row.id, row.name, row.exe_path, row.icon)
            card.delete_requested.connect(self._confirm_delete)
            pending = self.tracker.pending_seconds(row.id)
            card.set_times(stats.get(row.id, 0) + pending, totals.get(row.id, 0) + pending)
            card.set_running(os.path.normcase(row.exe_path) in self._running)
            self._cards[row.id] = card
            self._names[row.id] = row.name
            self._list_layout.addWidget(card)
        self._list_layout.addStretch(1)

        self.tracker.set_tracked({row.exe_path: row.id for row in apps})
        self._update_status_right()
        self._update_day_total(stats)

    def _update_status_right(self) -> None:
        suffix = " · фон ✦" if self.tracker.background_counting() else ""
        self._status_right.setText(f"Порог простоя: {self.tracker.threshold_minutes()} мин{suffix}")

    def _update_day_total(self, day_stats: dict[int, int]) -> None:
        total = sum(day_stats.values())
        total += sum(self.tracker.pending_seconds(i) for i in self._cards)
        self._today_total.setText(f"Активно сегодня: {format_seconds(total)}")

    def _on_tick(self) -> None:
        self._tick_count += 1
        self._running = self.tracker.running_paths()
        day = date.today().isoformat()
        stats = self.db.get_day_stats(day)
        totals = self.db.get_totals()
        for app_id, card in self._cards.items():
            pending = self.tracker.pending_seconds(app_id)
            card.set_times(stats.get(app_id, 0) + pending, totals.get(app_id, 0) + pending)
            card.set_running(os.path.normcase(card.exe_path) in self._running)
        self._update_day_total(stats)
        self._update_status()

    def _update_status(self) -> None:
        idle = self.tracker.last_idle_seconds
        threshold = self.tracker.threshold_minutes() * 60
        if idle >= threshold:
            text = f"Простой {format_seconds(idle)} — время не засчитывается"
        elif idle > GRACE_SECONDS:
            text = f"Нет активности {int(idle)} с"
        elif self.tracker.current_ids:
            names = [self._names.get(i, "") for i in self.tracker.current_ids]
            names = [n for n in names if n]
            text = "Учёт идёт: " + ", ".join(names[:3])
            if len(names) > 3:
                text += f" +{len(names) - 3}"
        else:
            text = "Активность есть, но текущее приложение не отслеживается"
        self._status.setText(text)

    def _open_add(self) -> None:
        existing = {row.exe_path for row in self.db.list_apps()}
        dialog = AddAppDialog(existing, self)
        if dialog.exec() == QDialog.Accepted:
            for app in dialog.selected_apps():
                icon_bytes = win32_utils.extract_icon_png(app.icon_path, app.icon_index, 64)
                self.db.add_app(app.name, app.exe_path, icon_bytes)
            self.refresh_apps()

    def _confirm_delete(self, app_id: int) -> None:
        name = self._names.get(app_id, "приложение")
        box = QMessageBox(self)
        box.setWindowTitle("Удаление приложения")
        box.setIcon(QMessageBox.Warning)
        box.setText(f"Удалить «{name}» из отслеживания?")
        box.setInformativeText("Накопленная статистика по нему будет удалена.")
        delete_btn = box.addButton("Удалить", QMessageBox.AcceptRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is delete_btn:
            self.db.remove_app(app_id)
            self.refresh_apps()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self.tracker.threshold_minutes(), self.tracker.background_counting(), self
        )
        if dialog.exec() == QDialog.Accepted:
            self.tracker.set_threshold_minutes(dialog.value())
            self.tracker.set_background_counting(dialog.background_enabled())
            self._update_status_right()

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(QApplication.windowIcon())
        self._tray.setToolTip("Трекер активности — учёт времени идёт")
        self._tray_menu = QMenu()
        show_action = self._tray_menu.addAction("Показать окно")
        show_action.triggered.connect(self._show_window)
        self._tray_menu.addSeparator()
        quit_action = self._tray_menu.addAction("Выход")
        quit_action.triggered.connect(QApplication.quit)
        self._tray.setContextMenu(self._tray_menu)
        self._tray.activated.connect(
            lambda reason: self._show_window()
            if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger)
            else None
        )
        self._tray.show()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        if self._tray is not None:
            self.hide()
            if not self._tray_hint_shown:
                self._tray.showMessage(
                    "Трекер активности",
                    "Программа свёрнута в трей и продолжает учитывать время.",
                    QSystemTrayIcon.Information,
                    3000,
                )
                self._tray_hint_shown = True
            event.ignore()
        else:
            event.accept()
