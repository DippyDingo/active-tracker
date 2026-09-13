import os
from collections import defaultdict
from datetime import date, timedelta

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath

from .. import config, win32_utils
from ..db import Database
from ..tracker import GRACE_SECONDS, Tracker
from ..utils import WEEKDAYS, format_compact, format_seconds, ru_date
from . import theme
from .add_dialog import AddPanel
from .modal import ModalOverlay
from .settings_dialog import SettingsPanel
from .stats_panel import StatsPanel
from .widgets import AppCard, CardHost, SidebarItem, magnifier_icon, menu_icon

PERIODS = [
    ("День", 0, "СЕГОДНЯ"),
    ("Неделя", 6, "НЕДЕЛЮ"),
    ("Месяц", 29, "МЕСЯЦ"),
    ("Всё время", None, "ВСЁ ВРЕМЯ"),
]


class SearchEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("searchEdit")
        self.setPlaceholderText("  Поиск")
        self.setClearButtonEnabled(True)
        self.setFixedWidth(220)
        self.setAttribute(Qt.WA_InputMethodEnabled, False)
        self.setInputMethodHints(Qt.ImhNoAutoUppercase)
        self.addAction(magnifier_icon(), QLineEdit.LeadingPosition)
        self.setTextMargins(14, 0, 0, 0)


class AppMenuPopup(QFrame):
    settings_requested = Signal()
    export_requested = Signal()
    load_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("profilePopup")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(286)
        self._anim = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        for text, signal in (
            ("⚙  Настройки", self.settings_requested),
            ("⇪  Экспорт базы данных", self.export_requested),
            ("⇧  Загрузить базу данных", self.load_requested),
        ):
            btn = QPushButton(text)
            btn.setObjectName("popupItem")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(signal.emit)
            layout.addWidget(btn)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #1e293b; border: none;")
        layout.addWidget(sep)

        quit_btn = QPushButton("⏻  Выход")
        quit_btn.setObjectName("popupItem")
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.clicked.connect(self.quit_requested)
        layout.addWidget(quit_btn)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1.0, self.height() - 1.0, 12, 12)
        painter.fillPath(path, QColor("#101a2c"))
        painter.setPen(QColor("#24344d"))
        painter.drawPath(path)
        painter.end()

    def popup_at(self, global_bottom_right: QPoint) -> None:
        self.adjustSize()
        x = global_bottom_right.x() - self.width()
        y = global_bottom_right.y() + 8
        target = QPoint(x, y)
        self.move(x, y - 10)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        if self._anim is not None:
            self._anim.stop()
        group = QParallelAnimationGroup(self)
        move = QPropertyAnimation(self, b"pos")
        move.setDuration(170)
        move.setStartValue(self.pos())
        move.setEndValue(target)
        move.setEasingCurve(QEasingCurve.OutCubic)
        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setDuration(170)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        group.addAnimation(move)
        group.addAnimation(fade)
        self._anim = group
        group.start()


class MainWindow(QMainWindow):
    def __init__(self, db: Database, tracker: Tracker):
        super().__init__()
        self.db = db
        self.tracker = tracker

        self._cards: dict[int, AppCard] = {}
        self._hosts: dict[int, CardHost] = {}
        self._side_items: dict[int, tuple] = {}
        self._rows_meta: dict[int, object] = {}
        self._order: list[int] = []
        self._names: dict[int, str] = {}
        self._base: dict[int, int] = {}
        self._series: dict[int, list[int]] = {}
        self._day_names: list[str] = []
        self._day_dates: list[str] = []
        self._today = date.today()
        self._period_idx = 1
        self._selected_id: int | None = None
        self._filter = ""
        self._cols = 3
        self._overlay = None
        self._pending_modal: tuple | None = None
        self._running: set[str] = set()
        self._header_value = 0
        self._header_anim = None
        self._tray = None
        self._tray_hint_shown = False

        self.setWindowTitle("Трекер активности")
        self.setWindowIcon(theme.load_app_icon())
        self.resize(1210, 780)
        self.setMinimumSize(1020, 680)

        root = QWidget()
        root.setObjectName("mainRoot")
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._build_sidebar(root_layout)
        self._build_content(root_layout)

        self._status = QLabel()
        self.statusBar().addWidget(self._status, 1)
        self._status_right = QLabel()
        self.statusBar().addPermanentWidget(self._status_right)

        self._build_tray()
        self.tracker.tick.connect(self._on_tick)
        self.refresh_apps()
        self._on_tick()

    def _build_sidebar(self, root_layout) -> None:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(264)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 18, 0, 12)
        layout.setSpacing(10)

        title_wrap = QHBoxLayout()
        title_wrap.setContentsMargins(22, 0, 16, 0)
        title = QLabel("МОИ ПРИЛОЖЕНИЯ")
        title.setObjectName("sectionTitle")
        title_wrap.addWidget(title)
        title_wrap.addStretch(1)
        layout.addLayout(title_wrap)

        self._sidebar_list = QListWidget()
        self._sidebar_list.setObjectName("sidebarList")
        self._sidebar_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._sidebar_list.currentItemChanged.connect(self._on_sidebar_changed)
        layout.addWidget(self._sidebar_list, 1)

        buttons = QVBoxLayout()
        buttons.setContentsMargins(14, 4, 14, 0)
        buttons.setSpacing(8)
        add_btn = QPushButton("＋  Добавить приложение")
        add_btn.setObjectName("primary")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._open_add)
        buttons.addWidget(add_btn)
        layout.addLayout(buttons)

        root_layout.addWidget(sidebar)

    def _build_content(self, root_layout) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(26, 18, 26, 8)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        page_title = QLabel("ACTIVITY")
        page_title.setObjectName("pageTitle")
        self._header_sub = QLabel("")
        self._header_sub.setObjectName("pageSub")
        titles.addWidget(page_title)
        titles.addWidget(self._header_sub)
        header.addLayout(titles)
        header.addStretch(1)

        self._period_group = QButtonGroup(self)
        self._period_group.setExclusive(True)
        periods_wrap = QHBoxLayout()
        periods_wrap.setSpacing(2)
        for idx, (label, _days, _gen) in enumerate(PERIODS):
            btn = QPushButton(label)
            btn.setObjectName("periodBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            if idx == self._period_idx:
                btn.setChecked(True)
            self._period_group.addButton(btn, idx)
            periods_wrap.addWidget(btn)
        self._period_group.idClicked.connect(self._on_period_changed)
        header.addLayout(periods_wrap)

        self._search = SearchEdit()
        self._search.textChanged.connect(self._on_filter_changed)
        header.addWidget(self._search)

        self._profile_btn = QPushButton()
        self._profile_btn.setObjectName("profileBtn")
        self._profile_btn.setCursor(Qt.PointingHandCursor)
        self._profile_btn.setFixedSize(36, 36)
        self._profile_btn.setIcon(menu_icon())
        self._profile_btn.setIconSize(QSize(18, 18))
        self._profile_btn.setToolTip("Меню")
        self._profile_btn.clicked.connect(self._show_app_menu)
        header.addWidget(self._profile_btn)

        layout.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        container = QWidget()
        container.setObjectName("cardsContainer")
        self._grid = QGridLayout(container)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(18)
        self._empty_label = QLabel(
            "Здесь пока пусто.\nДобавьте приложение — и увидите честную статистику активности."
        )
        self._empty_label.setObjectName("emptyLabel")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._scroll.setWidget(container)
        layout.addWidget(self._scroll, 1)

        self._popup = AppMenuPopup()
        self._popup.settings_requested.connect(self._open_settings)
        self._popup.export_requested.connect(self._export_database)
        self._popup.load_requested.connect(self._load_database)
        self._popup.quit_requested.connect(QApplication.quit)

        root_layout.addWidget(content, 1)

    def _show_app_menu(self) -> None:
        corner = self._profile_btn.mapToGlobal(
            QPoint(self._profile_btn.width(), self._profile_btn.height())
        )
        self._popup.popup_at(corner)

    def refresh_apps(self) -> None:
        self.tracker.flush()
        apps = self.db.list_apps()

        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._empty_label:
                widget.deleteLater()
        self._sidebar_list.blockSignals(True)
        self._sidebar_list.clear()
        self._sidebar_list.blockSignals(False)
        self._cards.clear()
        self._hosts.clear()
        self._side_items.clear()
        self._rows_meta.clear()
        self._order.clear()
        self._names.clear()

        for row in apps:
            self._rows_meta[row.id] = row
            self._names[row.id] = row.name
            self._order.append(row.id)

            card = AppCard(row.id, row.name, row.exe_path, row.icon)
            card.clicked.connect(self._on_card_clicked)
            card.delete_requested.connect(self._confirm_delete)
            host = CardHost(card)
            self._cards[row.id] = card
            self._hosts[row.id] = host

            item = QListWidgetItem()
            widget = SidebarItem(row.name, row.icon)
            item.setSizeHint(QSize(0, 46))
            item.setData(Qt.UserRole, row.id)
            self._sidebar_list.addItem(item)
            self._sidebar_list.setItemWidget(item, widget)
            self._side_items[row.id] = (item, widget)

        self._recompute_base()
        self._relayout_grid()
        self._apply_filter(self._filter)

        if self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(True)
            item = self._side_items[self._selected_id][0]
            self._sidebar_list.blockSignals(True)
            self._sidebar_list.setCurrentItem(item)
            self._sidebar_list.blockSignals(False)

        self.tracker.set_tracked({row.exe_path: row.id for row in apps})
        self._update_status_right()

    def _recompute_base(self) -> None:
        today = date.today()
        self._today = today
        yesterday = (today - timedelta(days=1)).isoformat()
        days = PERIODS[self._period_idx][1]
        start = None if days is None else (today - timedelta(days=days)).isoformat()

        base = defaultdict(int)
        if start is None or start <= yesterday:
            for app_id, _day, secs in self.db.query_stats(start, yesterday):
                base[app_id] += secs
        self._base = dict(base)

        series = {app_id: [0] * 6 for app_id in self._order}
        for app_id, day, secs in self.db.query_stats(
            (today - timedelta(days=6)).isoformat(), yesterday
        ):
            delta = (today - date.fromisoformat(day)).days
            if app_id in series and 1 <= delta <= 6:
                series[app_id][6 - delta] += secs
        self._series = series

        self._day_names = [WEEKDAYS[(today - timedelta(days=6 - i)).weekday()] for i in range(7)]
        self._day_dates = [ru_date(today - timedelta(days=6 - i)) for i in range(7)]
        for app_id, card in self._cards.items():
            card.set_day_names(self._day_names)
            card.set_day_tooltips(self._day_dates)

    def _current_cols(self) -> int:
        width = self.width()
        if width >= 1210:
            return 3
        if width >= 940:
            return 2
        return 1

    def _relayout_grid(self) -> None:
        self._cols = self._current_cols()
        for c in range(self._cols):
            self._grid.setColumnStretch(c, 1)
        visible_order = [i for i in self._order if i in self._hosts]
        for idx, app_id in enumerate(visible_order):
            self._grid.addWidget(self._hosts[app_id], idx // self._cols, idx % self._cols)
        if not visible_order:
            self._grid.addWidget(self._empty_label, 0, 0, 1, max(self._cols, 1), Qt.AlignCenter)
            self._empty_label.setVisible(True)
        else:
            self._grid.removeWidget(self._empty_label)
        self._grid.setRowStretch((max(len(visible_order), 1) - 1) // self._cols + 1, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_grid") and self._current_cols() != self._cols:
            self._relayout_grid()

    def _apply_filter(self, text: str) -> None:
        self._filter = (text or "").strip().lower()
        for app_id in self._order:
            match = (
                not self._filter
                or self._filter in self._names.get(app_id, "").lower()
                or self._filter in self._rows_meta[app_id].exe_path.lower()
            )
            if app_id in self._hosts:
                self._hosts[app_id].setVisible(match)
            if app_id in self._side_items:
                self._side_items[app_id][0].setHidden(not match)

    def _on_filter_changed(self, text: str) -> None:
        self._apply_filter(text)

    def _on_period_changed(self, idx: int) -> None:
        if idx == self._period_idx:
            return
        self._period_idx = idx
        self._recompute_base()
        day_str = date.today().isoformat()
        today_db = self.db.get_day_stats(day_str)
        for app_id, card in self._cards.items():
            today_live = today_db.get(app_id, 0) + self.tracker.pending_seconds(app_id)
            card.set_period_seconds(self._base.get(app_id, 0) + today_live, animate=True)
            card.set_chart(self._series.get(app_id, [0] * 6) + [today_live], animate=True)
        self._update_values(animate_header=True)

    def _on_sidebar_changed(self, current, _previous) -> None:
        if current is None:
            return
        app_id = current.data(Qt.UserRole)
        self._selected_id = app_id
        for aid, card in self._cards.items():
            card.set_selected(aid == app_id)
        host = self._hosts.get(app_id)
        if host is not None:
            self._scroll.ensureWidgetVisible(host, 30, 60)

    def _on_card_clicked(self, app_id: int) -> None:
        self._selected_id = app_id
        for aid, card in self._cards.items():
            card.set_selected(aid == app_id)
        if app_id in self._side_items:
            item = self._side_items[app_id][0]
            self._sidebar_list.blockSignals(True)
            self._sidebar_list.setCurrentItem(item)
            self._sidebar_list.blockSignals(False)
        self._open_stats(app_id)

    def _show_modal(self, panel, start_rect: QRect | None = None, on_closed=None) -> ModalOverlay | None:
        if self._overlay is not None:
            self._pending_modal = (panel, start_rect, on_closed)
            if not self._overlay._closing:
                self._overlay.close_modal()
            return None
        overlay = ModalOverlay(self, panel, start_rect)
        self._overlay = overlay
        overlay.closed.connect(self._on_modal_closed)
        if on_closed is not None:
            overlay.closed.connect(on_closed)
        return overlay

    def _on_modal_closed(self) -> None:
        self._overlay = None
        if self._pending_modal is not None:
            panel, start_rect, on_closed = self._pending_modal
            self._pending_modal = None
            self._show_modal(panel, start_rect, on_closed)

    def _open_add(self) -> None:
        existing = {row.exe_path for row in self.db.list_apps()}
        panel = AddPanel(existing, self)
        panel.add_requested.connect(self._on_add_request)
        self._show_modal(panel, on_closed=lambda: (panel.shutdown(), self.refresh_apps()))

    def _on_add_request(self, app) -> None:
        icon_bytes = win32_utils.extract_icon_png(app.icon_path, app.icon_index, 64)
        self.db.add_app(app.name, app.exe_path, icon_bytes)
        self.refresh_apps()

    def _open_settings(self) -> None:
        self._popup.hide()
        panel = SettingsPanel(
            self.tracker.threshold_minutes(), self.tracker.background_counting(), self
        )
        panel.saved.connect(self._apply_settings)
        self._show_modal(panel)

    def _apply_settings(self, threshold: int, background: bool) -> None:
        self.tracker.set_threshold_minutes(threshold)
        self.tracker.set_background_counting(background)
        self._update_status_right()

    def _export_database(self) -> None:
        self._popup.hide()
        self.tracker.flush()
        default_name = f"tracker_{date.today().isoformat()}.db"
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт базы данных", default_name, "База данных (*.db)"
        )
        if not path:
            return
        if not path.lower().endswith(".db"):
            path += ".db"
        if self.db.export_to(path):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("Экспорт базы данных")
            box.setText("База данных успешно экспортирована.")
            box.setInformativeText(path)
            box.setStandardButtons(QMessageBox.Ok)
            box.exec()
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось экспортировать базу данных.")

    def _load_database(self) -> None:
        self._popup.hide()
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузка базы данных", "", "База данных (*.db);;Все файлы (*.*)"
        )
        if not path:
            return
        if not Database.validate(path):
            QMessageBox.warning(
                self,
                "Неподходящий файл",
                "Выбранный файл не является корректной базой данных трекера.",
            )
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Загрузка базы данных")
        box.setText("Переключиться на выбранную базу?")
        box.setInformativeText("Текущая база останется на диске без изменений.")
        yes_btn = box.addButton("Переключиться", QMessageBox.AcceptRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes_btn:
            self._switch_db(path)

    def _switch_db(self, path: str) -> None:
        new_db = Database(path)
        self.tracker.switch_db(new_db)
        self.db.close()
        self.db = new_db
        config.set_db_path(path)
        self._selected_id = None
        self.refresh_apps()
        self._update_values()
        self._update_status()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("Загрузка базы данных")
        box.setText("База данных загружена.")
        box.setInformativeText(path)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()

    def _open_stats(self, app_id: int) -> None:
        row = self._rows_meta.get(app_id)
        card = self._cards.get(app_id)
        if row is None or card is None:
            return
        start_rect = None
        host = self._hosts.get(app_id)
        if host is not None and not host.isHidden():
            pos = card.mapTo(self, QPoint(0, 0))
            rect = QRect(pos, card.size()).intersected(self.rect())
            if not rect.isEmpty() and rect.width() > 40:
                start_rect = rect
        panel = StatsPanel(
            self.db,
            self.tracker,
            row.id,
            row.name,
            row.exe_path,
            row.icon,
            PERIODS[self._period_idx][2],
            card._shown_period if card._shown_period >= 0 else 0,
        )
        panel.delete_requested.connect(
            lambda aid: (
                self._overlay.close_modal() if self._overlay else None,
                self._confirm_delete(aid),
            )
        )
        self._show_modal(panel, start_rect)

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
            if self._selected_id == app_id:
                self._selected_id = None
            self.db.remove_app(app_id)
            self.refresh_apps()

    def _update_status_right(self) -> None:
        suffix = " · фон ✦" if self.tracker.background_counting() else ""
        self._status_right.setText(
            f"Порог простоя: {self.tracker.threshold_minutes()} мин{suffix}"
        )

    def _update_values(self, animate_header: bool = False) -> None:
        day_str = date.today().isoformat()
        today_db = self.db.get_day_stats(day_str)
        self._running = self.tracker.running_paths()
        header_total = 0
        for app_id, card in self._cards.items():
            today_live = today_db.get(app_id, 0) + self.tracker.pending_seconds(app_id)
            period_total = self._base.get(app_id, 0) + today_live
            header_total += period_total
            card.set_period_seconds(period_total)
            card.set_today_seconds(today_live)
            card.set_chart(self._series.get(app_id, [0] * 6) + [today_live])
            card.set_running(os.path.normcase(card.exe_path) in self._running)
        self._set_header_total(header_total, animate_header)

    def _set_header_total(self, value: int, animate: bool) -> None:
        gen = PERIODS[self._period_idx][2]
        if not animate or abs(value - self._header_value) <= 2:
            self._header_value = value
            self._header_sub.setText(f"АКТИВНОСТЬ ЗА {gen}: {format_compact(value)}")
            return
        if self._header_anim is not None:
            self._header_anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(self._header_value)
        anim.setEndValue(value)
        anim.setDuration(350)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(
            lambda v: self._header_sub.setText(f"АКТИВНОСТЬ ЗА {gen}: {format_compact(v)}")
        )
        anim.finished.connect(lambda: setattr(self, "_header_value", value))
        self._header_anim = anim
        anim.start()

    def _on_tick(self) -> None:
        if date.today() != self._today:
            self.refresh_apps()
        self._update_values()
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

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(theme.load_app_icon())
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
