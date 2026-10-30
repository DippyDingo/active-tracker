import os
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPixmap

from .. import config, updater, win32_utils
from ..db import Database
from ..tracker import GRACE_SECONDS, Tracker
from ..version import APP_VERSION
from ..utils import (
    MONTHS_NOM,
    PERIOD_KEYS,
    PERIOD_TITLES,
    SHORT_MONTHS,
    WEEKDAYS,
    add_months,
    format_compact,
    format_seconds,
    month_days,
    ru_date,
    week_start,
)
from . import theme
from .add_dialog import AddPanel
from .modal import ModalOverlay
from .settings_dialog import SettingsPanel
from .stats_panel import StatsPanel
from .update_dialog import UpdatePanel, WhatsNewPanel
from .widgets import (
    AddAppButton,
    AppCard,
    CardHost,
    CategoryHeader,
    InlineEdit,
    SidebarItem,
    magnifier_icon,
    menu_icon,
    ui_icon,
)

# Подпись «АКТИВНОСТЬ ЗА …» в шапке для каждого периода (индексы = PERIOD_KEYS).
PERIOD_GENITIVE = ["СЕГОДНЯ", "НЕДЕЛЮ", "МЕСЯЦ", "ГОД", "ВСЁ ВРЕМЯ"]


class SearchEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("searchEdit")
        self.setPlaceholderText("  Поиск")
        self.setClearButtonEnabled(True)
        self.setFixedWidth(220)
        self.setAttribute(Qt.WA_InputMethodEnabled, False)
        self.setInputMethodHints(Qt.ImhNoAutoUppercase)
        self._icon_action = self.addAction(magnifier_icon(), QLineEdit.LeadingPosition)
        self.setTextMargins(14, 0, 0, 0)

    def retheme(self) -> None:
        self._icon_action.setIcon(magnifier_icon())


class _PopupItem(QFrame):
    clicked = Signal()

    def __init__(self, icon, text, parent=None):
        super().__init__(parent)
        self.setObjectName("popupItem")
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(0)
        # Иконка в фиксированном квадратном контейнере: у всех пунктов одна колонка.
        icon_box = QLabel()
        icon_box.setFixedSize(20, 20)
        icon_box.setAlignment(Qt.AlignCenter)
        icon_box.setPixmap(icon.pixmap(QSize(18, 18)))
        lay.addWidget(icon_box, 0, Qt.AlignVCenter)
        lay.addSpacing(10)
        lb = QLabel(text)
        lb.setObjectName("popupItemText")
        lay.addWidget(lb, 1, Qt.AlignVCenter)
        self._icon_box = icon_box
        self._text_label = lb

    def set_icon(self, icon) -> None:
        self._icon_box.setPixmap(icon.pixmap(QSize(18, 18)))

    def set_text(self, text: str) -> None:
        self._text_label.setText(text)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class AppMenuPopup(QFrame):
    settings_requested = Signal()
    export_requested = Signal()
    load_requested = Signal()
    quit_requested = Signal()
    update_requested = Signal()
    whatsnew_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("profilePopup")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(286)
        self._anim = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        self._version_label = QLabel(f"Nodexy v{APP_VERSION}")
        self._version_label.setObjectName("popupVersion")
        layout.addWidget(self._version_label)

        for text, signal, icon_kind in (
            ("Настройки", self.settings_requested, "settings"),
            ("Экспорт базы данных", self.export_requested, "upload"),
            ("Загрузить базу данных", self.load_requested, "download"),
        ):
            item = _PopupItem(ui_icon(icon_kind), text)
            item.clicked.connect(signal.emit)
            layout.addWidget(item)

        self._update_item = _PopupItem(ui_icon("update"), "Доступно обновление")
        self._update_item.clicked.connect(self.update_requested)
        self._update_item.setVisible(False)
        layout.addWidget(self._update_item)

        self._whatsnew_item = _PopupItem(ui_icon("info"), "Что нового")
        self._whatsnew_item.clicked.connect(self.whatsnew_requested)
        self._whatsnew_item.setVisible(False)
        layout.addWidget(self._whatsnew_item)

        sep = QFrame()
        sep.setFixedHeight(1)
        self._sep = sep
        layout.addWidget(sep)

        self._quit_item = _PopupItem(ui_icon("power", theme.pal().danger), "Выход")
        self._quit_item.clicked.connect(self.quit_requested)
        layout.addWidget(self._quit_item)
        self.retheme()

    def retheme(self) -> None:
        self._sep.setStyleSheet(f"background: {theme.pal().card}; border: none;")
        self._quit_item.set_icon(ui_icon("power", theme.pal().danger))
        self._update_item.set_icon(ui_icon("update"))
        self._whatsnew_item.set_icon(ui_icon("info"))
        self.update()

    def set_update_available(self, version: str | None) -> None:
        if version:
            self._update_item.set_text(f"Доступно обновление {version}")
            self._update_item.setVisible(True)
        else:
            self._update_item.setVisible(False)

    def set_whatsnew(self, visible: bool) -> None:
        self._whatsnew_item.setVisible(visible)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1.0, self.height() - 1.0, 12, 12)
        painter.fillPath(path, theme.color("popup_bg"))
        painter.setPen(theme.color("popup_border"))
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
    def __init__(self, db: Database, tracker: Tracker, boot: dict | None = None):
        super().__init__()
        self.db = db
        self.tracker = tracker

        self._cards: dict[int, AppCard] = {}
        self._hosts: dict[int, CardHost] = {}
        self._side_items: dict[int, SidebarItem] = {}
        self._cat_rows: dict[int, list[SidebarItem]] = {}
        self._cat_headers: dict[int, CategoryHeader] = {}
        self._uncat_header: QLabel | None = None
        self._collapsed: set[int] = set()
        self._inline: InlineEdit | None = None
        self._editing_header: CategoryHeader | None = None
        self._side_drag: dict | None = None
        self._side_ghost: QLabel | None = None
        self._drop_hint = None
        self._rows_meta: dict[int, object] = {}
        self._order: list[int] = []
        self._names: dict[int, str] = {}
        self._base: dict[int, int] = {}
        self._series: dict[int, list[int]] = {}
        self._live_slot = -1
        self._axis_idx: list[int] = []
        self._axis_labels: list[str] = []
        self._axis_tips: list[str] = []
        self._today = date.today()
        self._period_idx = 1
        self._selected_id: int | None = None
        self._filter = ""
        self._cols = 3
        self._overlay = None
        self._pending_modal: tuple | None = None
        self._drag: dict | None = None
        self._drag_ghost: QLabel | None = None
        self._drag_dim = None
        self._drop_anim = None
        self._running: set[str] = set()
        self._header_value = 0
        self._header_anim = None
        self._tray = None
        self._tray_hint_shown = False
        self._force_quit = False

        self._boot = boot or {}
        self._pending_plate = None
        if self._boot.get("plate"):
            self._pending_plate = (self._boot["plate"], self._boot.get("notes") or "")
        self._update_available = None
        self._update_notes = ""
        self._checking = False
        self._check_task = None
        self._silent_task = None
        self._updater_launched = False
        self._banner_session_hidden = False
        self._tray_update_hint_shown = False
        self._tray_progress_cache: dict[int, QIcon] = {}

        self.setWindowTitle("Nodexy")
        self.setWindowIcon(theme.load_app_icon())
        self.resize(1210, 780)
        self.setMinimumSize(1020, 680)
        # Нативный фон окна под цвет темы: без этого при первом показе и при
        # перестроении карточек мелькает белый HWND/QAbstractScrollArea.
        self._apply_window_palette()

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

        self._popup.update_requested.connect(self._open_update_panel)
        self._popup.whatsnew_requested.connect(self._open_whats_new)
        if updater.get_last_update():
            self._popup.set_whatsnew(True)
        if self._boot.get("failed_url"):
            self._update_failed_url = self._boot["failed_url"]
        QApplication.instance().aboutToQuit.connect(self._apply_pending_on_exit)
        self._apply_rollback_safe_mode()
        QTimer.singleShot(updater.CHECK_DELAY_MS, self._auto_check)
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(updater.CHECK_INTERVAL_MS)
        self._update_timer.timeout.connect(self._auto_check)
        self._update_timer.start()

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

        self._side_scroll = QScrollArea()
        self._side_scroll.setObjectName("sidebarScroll")
        # Полоса прокрутки сайдбара не нужна визуально и создавала заметную
        # вертикальную линию на границе панели во всех темах. Прокрутка колёсиком
        # продолжает работать, но сам системный скроллбар не занимает место.
        self._side_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._side_scroll.setFrameShape(QFrame.NoFrame)
        self._side_scroll.setStyleSheet("QScrollBar { width: 0px; height: 0px; }")
        self._side_scroll.setWidgetResizable(True)
        side_container = QWidget()
        side_container.setObjectName("sidebarContainer")
        side_container.setContextMenuPolicy(Qt.CustomContextMenu)
        side_container.customContextMenuRequested.connect(self._sidebar_context_menu)
        self._side_container = side_container
        self._side_layout = QVBoxLayout(side_container)
        self._side_layout.setContentsMargins(8, 0, 8, 0)
        self._side_layout.setSpacing(3)
        self._side_scroll.setWidget(side_container)
        layout.addWidget(self._side_scroll, 1)

        # Кнопка добавления — в подвале панели, по центру её ширины: список
        # приложений должен начинаться сразу под заголовком, а кружок «+»
        # стоит ровно посередине между краями панели.
        self._add_app_btn = AddAppButton()
        # clicked передаёт checked(bool) — без лямбды это значение попадало в
        # cat_id и добавление падало на внешнем ключе (cat_id=False → 0).
        self._add_app_btn.clicked.connect(lambda: self._open_add())
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 2, 0, 0)
        footer.setSpacing(0)
        footer.addStretch(1)
        footer.addWidget(self._add_app_btn, 0, Qt.AlignHCenter)
        footer.addStretch(1)
        layout.addLayout(footer)

        root_layout.addWidget(sidebar)

    def _build_content(self, root_layout) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(26, 18, 26, 8)
        layout.setSpacing(16)
        self._content_layout = layout

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
        for idx, label in enumerate(PERIOD_TITLES):
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

        self._badge = QLabel(self._profile_btn)
        self._badge.setFixedSize(9, 9)
        self._badge.setStyleSheet(
            f"background: {theme.pal().accent}; border-radius: 4px;"
        )
        self._badge.move(25, 3)
        self._badge.hide()

        layout.addLayout(header)

        self._banner = QFrame()
        self._banner.setObjectName("updateBanner")
        self._banner.setVisible(False)
        banner_layout = QHBoxLayout(self._banner)
        banner_layout.setContentsMargins(14, 8, 10, 8)
        banner_layout.setSpacing(10)
        self._banner_text = QLabel()
        self._banner_text.setObjectName("updateBannerTitle")
        self._banner_text.setCursor(Qt.PointingHandCursor)
        self._banner_text.mouseReleaseEvent = lambda _e: self._open_update_panel()
        banner_layout.addWidget(self._banner_text, 1)
        banner_update = QPushButton("Обновить")
        banner_update.setObjectName("primary")
        banner_update.setCursor(Qt.PointingHandCursor)
        banner_update.clicked.connect(self._open_update_panel)
        banner_layout.addWidget(banner_update)
        banner_later = QPushButton("Позже")
        banner_later.setCursor(Qt.PointingHandCursor)
        banner_later.clicked.connect(self._snooze_update)
        banner_layout.addWidget(banner_later)
        banner_close = QPushButton("✕")
        banner_close.setObjectName("deleteBtn")
        banner_close.setFixedSize(22, 22)
        banner_close.setCursor(Qt.PointingHandCursor)
        banner_close.clicked.connect(self._hide_banner_session)
        banner_layout.addWidget(banner_close)
        layout.addWidget(self._banner)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("cardsScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        container = QWidget()
        container.setObjectName("cardsContainer")
        self._cards_container = container
        self._grid = QGridLayout(container)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(18)
        self._empty_text = (
            "Здесь пока пусто.\nДобавьте приложение — и увидите честную статистику активности."
        )
        self._empty_label = QLabel(self._empty_text)
        self._empty_label.setObjectName("emptyLabel")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._scroll.setWidget(container)
        layout.addWidget(self._scroll, 1)
        # Вьюпорт прокрутки создан — закрасить его нативный фон под тему.
        self._apply_window_palette()

        self._popup = AppMenuPopup()
        self._popup.settings_requested.connect(self._open_settings)
        self._popup.export_requested.connect(self._export_database)
        self._popup.load_requested.connect(self._load_database)
        self._popup.quit_requested.connect(self._quit_app)

        root_layout.addWidget(content, 1)

    def _show_app_menu(self) -> None:
        corner = self._profile_btn.mapToGlobal(
            QPoint(self._profile_btn.width(), self._profile_btn.height())
        )
        self._popup.popup_at(corner)

    def refresh_apps(self) -> None:
        self.tracker.flush()
        apps = self.db.list_apps()

        # Сохраняем позицию прокрутки: полное перестроение не должно сбрасывать
        # то место, где пользователь читал список.
        cur = self._scroll.verticalScrollBar().value() if self._scroll else 0

        # На время перестроения запрещаем отрисовку: иначе между удалением
        # старых виджетов и добавлением новых проскакивает кадр с пустым
        # контентом — то самое «белое окно». Старые виджеты прячем сразу,
        # чтобы они не рисовались поверх новых до своего фактического удаления.
        self.setUpdatesEnabled(False)

        self._discard_inline()
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._empty_label:
                widget.hide()
                widget.deleteLater()
        while self._side_layout.count():
            item = self._side_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._cards.clear()
        self._hosts.clear()
        self._side_items.clear()
        self._cat_rows.clear()
        self._cat_headers.clear()
        self._uncat_header = None
        self._inline = None
        self._editing_header = None
        self._side_drag = None
        self._destroy_side_ghost()
        self._drop_hint = None
        self._rows_meta.clear()
        self._order.clear()
        self._names.clear()

        for row in apps:
            self._rows_meta[row.id] = row
            self._names[row.id] = row.name
            self._order.append(row.id)

            card = AppCard(row.id, row.name, row.exe_path, row.icon)
            card.delete_requested.connect(self._confirm_delete)
            card.clicked.connect(self._on_card_clicked)
            card.installEventFilter(self)
            # Родитель сразу при создании: без него QGridLayout::addWidget
            # показывал карточку отдельным top-level окном (белый прямоугольник
            # 640×480 на секунду при добавлении приложения).
            host = CardHost(card, self._cards_container)
            self._cards[row.id] = card
            self._hosts[row.id] = host

        self._build_side_sections(apps)
        self._recompute_base()
        self._apply_filter(self._filter)

        if self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(True)
            item = self._side_items.get(self._selected_id)
            if item is not None:
                item.set_selected(True)

        self.tracker.set_tracked({row.exe_path: row.id for row in apps})
        self._update_status_right()
        self._update_values()

        self.setUpdatesEnabled(True)
        self.update()
        if self._scroll is not None:
            self._scroll.verticalScrollBar().setValue(cur)

    @staticmethod
    def _pick_indices(n: int, k: int = 7) -> list[int]:
        """Равномерная выборка k индексов из n (первый и последний включены)."""
        if n <= 0:
            return []
        if n <= k:
            return list(range(n))
        return [round(i * (n - 1) / (k - 1)) for i in range(k)]

    def _recompute_base(self) -> None:
        """Строит бакеты текущего календарного периода для всех приложений.

        self._series[app_id] — значения бакетов без «живого» сегодня;
        self._live_slot     — индекс бакета, куда добавляется today_live;
        self._axis_labels / self._axis_tips — подписи под мини-графиком.
        """
        today = date.today()
        self._today = today
        yesterday = (today - timedelta(days=1)).isoformat()
        key = PERIOD_KEYS[self._period_idx]

        # Границы бакетов по дням: список пар (start_date, end_date) включительно.
        bounds: list[tuple[date, date]] = []
        axis_full: list[str] = []
        tips_full: list[str] = []

        if key == "day":
            # Часы: значения строятся отдельно в _card_series из db.get_hours.
            self._series = {app_id: [0] * 24 for app_id in self._order}
            self._live_slot = -1
            self._base = {}
            self._axis_idx = list(range(24))
            # Короткие подписи позволяют показать каждый час 0–23 даже на
            # компактной карточке без наложения цифр.
            self._axis_labels = [str(h) for h in range(24)]
            self._axis_tips = [f"{h:02d}:00–{(h + 1) % 24:02d}:00" for h in range(24)]
            win = self._card_window(24)
            for card in self._cards.values():
                card.set_chart_window(win)
                card.set_axis(self._axis_idx, self._axis_labels)
                card.set_day_tooltips(self._axis_tips)
            return

        if key == "week":
            start = week_start(today)
            for i in range(7):
                d = start + timedelta(days=i)
                bounds.append((d, d))
                axis_full.append(WEEKDAYS[d.weekday()])
                tips_full.append(f"{WEEKDAYS[d.weekday()]}, {ru_date(d)}")
        elif key == "month":
            n = month_days(today.year, today.month)
            for i in range(n):
                d = date(today.year, today.month, i + 1)
                bounds.append((d, d))
                axis_full.append(str(d.day))
                tips_full.append(f"{WEEKDAYS[d.weekday()]}, {ru_date(d)}")
        elif key == "year":
            for m in range(1, 13):
                s = date(today.year, m, 1)
                e = date(today.year, m, month_days(today.year, m))
                bounds.append((s, e))
                axis_full.append(SHORT_MONTHS[m - 1])
                tips_full.append(f"{MONTHS_NOM[m - 1]} {today.year}")
        else:  # all — от первой записи до сегодня; шаг бакета по длине истории
            first_str = self.db.get_min_day()
            try:
                first = date.fromisoformat(first_str) if first_str else today
            except ValueError:
                first = today
            first = min(first, today)
            span = (today - first).days + 1
            if span <= 90:
                d = first
                while d <= today:
                    bounds.append((d, d))
                    axis_full.append(f"{d.day} {SHORT_MONTHS[d.month - 1]}")
                    tips_full.append(f"{WEEKDAYS[d.weekday()]}, {ru_date(d)}")
                    d += timedelta(days=1)
            elif span <= 730:
                s = first
                while s <= today:
                    e = min(s + timedelta(days=6), today)
                    bounds.append((s, e))
                    axis_full.append(f"{s.day} {SHORT_MONTHS[s.month - 1]}")
                    if s.month == e.month:
                        tips_full.append(f"{s.day}–{e.day} {SHORT_MONTHS[s.month - 1]}")
                    else:
                        tips_full.append(
                            f"{s.day} {SHORT_MONTHS[s.month - 1]}–{e.day} {SHORT_MONTHS[e.month - 1]}"
                        )
                    s = e + timedelta(days=1)
            else:
                y, m = first.year, first.month
                while (y, m) <= (today.year, today.month):
                    s = date(y, m, 1)
                    e = date(y, m, month_days(y, m))
                    bounds.append((s, e))
                    axis_full.append(SHORT_MONTHS[m - 1])
                    tips_full.append(f"{MONTHS_NOM[m - 1]} {y}")
                    y, m = add_months(y, m, 1)

        n = len(bounds)
        # Индекс бакета, содержащего сегодня.
        live_slot = -1
        for i, (s, e) in enumerate(bounds):
            if s <= today <= e:
                live_slot = i
                break
        self._live_slot = live_slot

        range_start = bounds[0][0].isoformat() if bounds else today.isoformat()
        series = {app_id: [0] * n for app_id in self._order}
        base = defaultdict(int)
        if bounds and range_start <= yesterday:
            for app_id, day, secs in self.db.query_stats(range_start, yesterday):
                if app_id not in series:
                    continue
                d = date.fromisoformat(day)
                for i, (s, e) in enumerate(bounds):
                    if s <= d <= e:
                        series[app_id][i] += secs
                        base[app_id] += secs
                        break
        self._series = series
        self._base = dict(base)

        self._axis_idx = list(range(n))
        self._axis_labels = list(axis_full)
        self._axis_tips = tips_full
        win = self._card_window(n)
        for card in self._cards.values():
            card.set_chart_window(win)
            card.set_axis(self._axis_idx, self._axis_labels)
            card.set_day_tooltips(self._axis_tips)

    def _card_window(self, n: int) -> int | None:
        """Размер окна мини-графика по текущему периоду.

        Если точек больше ~14-20, показываем окно и позволяем листать
        перетаскиванием; для коротких рядов помещаем весь ряд.
        """
        key = PERIOD_KEYS[self._period_idx]
        if key == "day":
            # В карточке помещаем 12 часов: 00–11 или 12–23. Вторую
            # половину можно пролистать мышью так же, как длинный график.
            return 12
        elif key == "week":
            # Для недели — показываем все 7 дней
            return None
        elif key == "month":
            # Для месяца (до 31 дня) — если больше 20, окно 20
            if n > 20:
                return 20
            return None
        elif key == "year":
            # В маленькой карточке показываем по шесть месяцев: январь–июнь,
            # затем июль–декабрь листаются колёсиком.
            return 6 if n > 6 else None
        elif key == "all":
            # Для «Всё время» показываем окно 14-20 точек в зависимости от длины
            if n > 60:
                return 20
            elif n > 14:
                return 14
            return None
        return None

    def _card_series(self, app_id: int, today_live: int) -> list[int]:
        """Значения мини-графика карточки с учётом «живого» сегодня."""
        key = PERIOD_KEYS[self._period_idx]
        if key == "day":
            hours = list(self.db.get_hours(app_id, self._today.isoformat()))
            pending = max(0, today_live - sum(hours))
            if pending:
                from datetime import datetime

                hours[datetime.now().hour] += pending
            return hours
        values = list(self._series.get(app_id, []))
        if 0 <= self._live_slot < len(values):
            values[self._live_slot] += today_live
        return values

    def _current_cols(self) -> int:
        width = self.width()
        if width >= 1210:
            return 3
        if width >= 940:
            return 2
        return 1

    def _match_rank(self, app_id: int, q: str) -> int | None:
        """Ранг совпадения (чем меньше, тем лучше) или None."""
        name = self._names.get(app_id, "").lower()
        if name == q:
            return 0
        if name.startswith(q):
            return 1
        if any(word.startswith(q) for word in name.split()):
            return 2
        if q in name:
            return 3
        if q in self._rows_meta[app_id].exe_path.lower():
            return 4
        return None

    def _current_grid_order(self) -> list[int]:
        """Порядок карточек в сетке: при поиске — совпавшие по релевантности."""
        base = [i for i in self._order if i in self._hosts]
        if not self._filter:
            return base
        ranked = []
        for pos, app_id in enumerate(base):
            rank = self._match_rank(app_id, self._filter)
            if rank is not None:
                ranked.append((rank, pos, app_id))
        ranked.sort(key=lambda t: (t[0], t[1]))
        return [app_id for _rank, _pos, app_id in ranked]

    def _relayout_grid(self) -> None:
        order = self._current_grid_order()
        self._cols = self._current_cols()
        for c in range(self._cols):
            self._grid.setColumnStretch(c, 1)
        for host in self._hosts.values():
            self._grid.removeWidget(host)
        self._grid.removeWidget(self._empty_label)
        matched = set(order)
        for app_id, host in self._hosts.items():
            host.setVisible(app_id in matched)
        for idx, app_id in enumerate(order):
            self._grid.addWidget(self._hosts[app_id], idx // self._cols, idx % self._cols)
        if not order:
            if self._filter:
                self._empty_label.setText(f"Ничего не найдено по запросу «{self._filter}»")
            else:
                self._empty_label.setText(self._empty_text)
            self._grid.addWidget(self._empty_label, 0, 0, 1, max(self._cols, 1), Qt.AlignCenter)
            self._empty_label.setVisible(True)
        else:
            self._empty_label.setVisible(False)
        self._grid.setRowStretch((max(len(order), 1) - 1) // self._cols + 1, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_grid") and self._current_cols() != self._cols:
            self._relayout_grid()

    def _apply_filter(self, text: str) -> None:
        self._filter = (text or "").strip().lower()
        visible_per_cat: dict[int, int] = defaultdict(int)
        uncat_visible = 0
        for app_id in self._order:
            match = (
                True
                if not self._filter
                else self._match_rank(app_id, self._filter) is not None
            )
            cat_id = self._rows_meta[app_id].category_id
            collapsed = (cat_id in self._collapsed) if cat_id is not None else False
            row_visible = match and ((not collapsed) or bool(self._filter))
            item = self._side_items.get(app_id)
            if item is not None:
                item.setVisible(row_visible)
            if match:
                if cat_id is None:
                    uncat_visible += 1
                else:
                    visible_per_cat[cat_id] += 1
        if self._filter:
            for cat_id, header in self._cat_headers.items():
                header.setVisible(visible_per_cat.get(cat_id, 0) > 0)
            if self._uncat_header is not None:
                self._uncat_header.setVisible(uncat_visible > 0)
        else:
            for header in self._cat_headers.values():
                header.setVisible(True)
            if self._uncat_header is not None:
                self._uncat_header.setVisible(True)
        self._relayout_grid()

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
            card.set_chart(self._card_series(app_id, today_live), animate=True)
        self._update_values(animate_header=True)

    def _on_side_row_clicked(self, app_id: int) -> None:
        self._selected_id = app_id
        for aid, card in self._cards.items():
            card.set_selected(aid == app_id)
        for aid, item in self._side_items.items():
            item.set_selected(aid == app_id)
        host = self._hosts.get(app_id)
        if host is not None:
            self._scroll.ensureWidgetVisible(host, 30, 60)

    def _on_card_clicked(self, app_id: int) -> None:
        self._selected_id = app_id
        for aid, card in self._cards.items():
            card.set_selected(aid == app_id)
        for aid, item in self._side_items.items():
            item.set_selected(aid == app_id)
        self._open_stats(app_id)

    def _build_side_sections(self, apps) -> None:
        cats = self.db.list_categories()
        by_cat: dict[int | None, list] = defaultdict(list)
        for row in apps:
            by_cat[row.category_id].append(row)

        if not cats:
            for row in apps:
                self._side_layout.addWidget(self._make_side_item(row))
            self._side_layout.addStretch(1)
            return

        for cat_id, cat_name in cats:
            rows = by_cat.get(cat_id, [])
            collapsed = cat_id in self._collapsed
            header = CategoryHeader(cat_name, len(rows), collapsed)
            header.toggle_requested.connect(
                lambda _checked=False, cid=cat_id: self._toggle_category(cid)
            )
            header.set_context_menu(self._category_menu(cat_id, cat_name))
            self._side_layout.addWidget(header)
            self._cat_headers[cat_id] = header
            self._cat_rows[cat_id] = []
            for row in rows:
                item = self._make_side_item(row)
                self._side_layout.addWidget(item)
                if collapsed:
                    item.setVisible(False)
                self._cat_rows[cat_id].append(item)

        uncat = by_cat.get(None, [])
        if uncat:
            uncat_label = QLabel("БЕЗ КАТЕГОРИИ")
            uncat_label.setObjectName("catName")
            wrap = QHBoxLayout()
            wrap.setContentsMargins(10, 6, 10, 2)
            wrap.addWidget(uncat_label)
            wrap.addStretch(1)
            holder = QWidget()
            holder.setLayout(wrap)
            self._side_layout.addWidget(holder)
            self._uncat_header = holder
            for row in uncat:
                self._side_layout.addWidget(self._make_side_item(row))

        self._side_layout.addStretch(1)

    def _make_side_item(self, row) -> SidebarItem:
        item = SidebarItem(row.name, row.icon)
        item.clicked.connect(lambda app_id=row.id: self._on_side_row_clicked(app_id))
        item.set_context_menu(self._app_menu(row.id))
        item.installEventFilter(self)
        self._side_items[row.id] = item
        return item

    def _toggle_category(self, cat_id: int) -> None:
        header = self._cat_headers.get(cat_id)
        if header is None:
            return
        if cat_id in self._collapsed:
            self._collapsed.discard(cat_id)
            collapsed = False
        else:
            self._collapsed.add(cat_id)
            collapsed = True
        header.set_arrow(collapsed)
        self._apply_filter(self._filter)

    def _refresh_after_category_move(self, app_id: int, new_cat: int | None) -> None:
        """Обновляет категории без пересоздания окна и всех виджетов.

        Перенос меняет только category_id. Полный refresh_apps уничтожает
        сотни Qt-виджетов и вызывает белый кадр в некоторых конфигурациях
        Windows; здесь перестраиваем только левую панель, а карточки и графики
        оставляем на месте.
        """
        current = self._rows_meta.get(app_id)
        if current is None:
            return
        self._rows_meta[app_id] = replace(current, category_id=new_cat)
        self._rebuild_sidebar_only()
        self._apply_filter(self._filter)
        self._flash_move_result(app_id, new_cat)

    def _rebuild_sidebar_only(self) -> None:
        self._discard_inline()
        side_scroll_value = self._side_scroll.verticalScrollBar().value()
        self._side_scroll.setUpdatesEnabled(False)
        try:
            while self._side_layout.count():
                item = self._side_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.hide()
                    widget.deleteLater()
            rows = list(self._rows_meta.values())
            self._side_items.clear()
            self._cat_rows.clear()
            self._cat_headers.clear()
            self._uncat_header = None
            self._build_side_sections(rows)
        finally:
            self._side_scroll.setUpdatesEnabled(True)
            self._side_scroll.verticalScrollBar().setValue(side_scroll_value)
            self._side_scroll.viewport().update()

    def _move_app(self, app_id: int, cat_id: int | None) -> None:
        current = self._rows_meta.get(app_id)
        if current is None or current.category_id == cat_id:
            return
        self.db.set_app_category(app_id, cat_id)
        self._refresh_after_category_move(app_id, cat_id)

    def _flash_move_result(self, app_id: int, cat_id: int | None) -> None:
        if cat_id is not None:
            self._flash_widget(self._cat_headers.get(cat_id))
        self._flash_widget(self._side_items.get(app_id))

    def _flash_widget(self, widget) -> None:
        if widget is None:
            return
        widget.setProperty("flash", True)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        QTimer.singleShot(1300, lambda: self._unflash_widget(widget))

    def _unflash_widget(self, widget) -> None:
        try:
            widget.setProperty("flash", False)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        except RuntimeError:
            pass

    def _delete_category(self, cat_id: int, cat_name: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Удаление категории")
        box.setText(f"Удалить категорию «{cat_name}»?")
        box.setInformativeText("Приложения из неё останутся в списке без категории.")
        yes_btn = box.addButton("Удалить", QMessageBox.AcceptRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes_btn:
            self._collapsed.discard(cat_id)
            self.db.delete_category(cat_id)
            self.refresh_apps()

    def _sidebar_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        add_action = menu.addAction(ui_icon("plus"), "Добавить приложение")
        add_action.triggered.connect(lambda: self._open_add())
        cat_action = menu.addAction(ui_icon("folder"), "Создать категорию")
        cat_action.triggered.connect(lambda: self._start_inline_create(None))
        menu.exec(self._side_container.mapToGlobal(pos))

    def _app_menu(self, app_id: int) -> QMenu:
        menu = QMenu(self)
        new_action = menu.addAction(ui_icon("folder"), "Новая категория…")
        new_action.triggered.connect(lambda: self._start_inline_create(app_id))
        cats = self.db.list_categories()
        if cats:
            menu.addSeparator()
            move_menu = menu.addMenu("Добавить в категорию")
            move_menu.setIcon(ui_icon("folder"))
            current = self._rows_meta.get(app_id)
            current_cat = current.category_id if current is not None else None
            for cat_id, cat_name in cats:
                mark = "✓  " if cat_id == current_cat else ""
                action = move_menu.addAction(f"{mark}{cat_name}")
                action.triggered.connect(
                    lambda _checked=False, cid=cat_id: self._move_app(app_id, cid)
                )
            if current_cat is not None:
                menu.addSeparator()
                none_action = menu.addAction(ui_icon("minus"), "Убрать из категории")
                none_action.triggered.connect(lambda: self._move_app(app_id, None))
        # Удаление прямо из левой панели: искать приложение в ACTIVITY, чтобы
        # убрать его из отслеживания, не нужно.
        menu.addSeparator()
        delete_action = menu.addAction(
            ui_icon("trash", theme.pal().danger), "Удалить из отслеживания"
        )
        delete_action.triggered.connect(lambda: self._confirm_delete(app_id))
        return menu

    def _category_menu(self, cat_id: int, cat_name: str) -> QMenu:
        menu = QMenu(self)
        add_here_action = menu.addAction(ui_icon("plus"), "Добавить приложение сюда")
        add_here_action.triggered.connect(lambda: self._open_add(cat_id))
        rename_action = menu.addAction(ui_icon("pen"), "Переименовать")
        delete_action = menu.addAction(ui_icon("trash", theme.pal().danger), "Удалить")
        rename_action.triggered.connect(lambda: self._start_inline_rename(cat_id, cat_name))
        delete_action.triggered.connect(lambda: self._delete_category(cat_id, cat_name))
        return menu

    def _remove_inline(self) -> None:
        widget = self._inline
        header = self._editing_header
        self._inline = None
        self._editing_header = None
        if widget is None:
            return
        if header is not None:
            # Вернуть заголовок на место редактора, не трогая остальной список.
            self._side_layout.replaceWidget(widget, header)
            header.setVisible(True)
        self._side_layout.removeWidget(widget)
        widget.deleteLater()

    def _discard_inline(self) -> None:
        # Тихо убрать редактор без срабатывания сигналов (используется при
        # перестроении списка, чтобы отложенный FocusOut не трогал удалённые виджеты).
        edit = self._inline
        header = self._editing_header
        self._inline = None
        self._editing_header = None
        if edit is None:
            return
        edit._done = True
        try:
            edit.accepted.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            edit.cancelled.disconnect()
        except (RuntimeError, TypeError):
            pass
        if header is not None:
            # Вернуть заголовок в список, чтобы перестроение его корректно удалило.
            self._side_layout.replaceWidget(edit, header)
            header.setVisible(True)
        self._side_layout.removeWidget(edit)
        edit.deleteLater()

    def _cancel_active_inline(self) -> None:
        # Отменить текущее редактирование без сохранения (восстанавливает заголовок).
        edit = self._inline
        if edit is not None:
            edit.cancel()

    def _start_inline_create(self, for_app_id: int | None = None) -> None:
        self._cancel_active_inline()
        edit = InlineEdit(placeholder="Имя категории, затем Enter")
        edit.accepted.connect(lambda text: self._finish_create(text, for_app_id))
        edit.cancelled.connect(self._remove_inline)
        self._inline = edit
        self._editing_header = None
        self._side_layout.insertWidget(max(0, self._side_layout.count() - 1), edit)
        QTimer.singleShot(30, self._focus_inline)

    def _focus_inline(self) -> None:
        if self._inline is None:
            return
        self._side_scroll.ensureWidgetVisible(self._inline, 10, 10)
        self.activateWindow()
        self._inline.focus_edit()

    def _finish_create(self, text: str, for_app_id: int | None) -> None:
        self._remove_inline()
        if not text:
            return
        cat_id = self.db.create_category(text)
        if for_app_id is not None:
            self.db.set_app_category(for_app_id, cat_id)
        # Категории живут только в левой панели: карточки и графики при этом
        # не меняются, поэтому полное перестроение здесь не нужно.
        if for_app_id is not None:
            self._refresh_after_category_move(for_app_id, cat_id)
        else:
            self._rebuild_sidebar_only()
            self._apply_filter(self._filter)
            self._flash_widget(self._cat_headers.get(cat_id))

    def _start_inline_rename(self, cat_id: int, current_name: str) -> None:
        header = self._cat_headers.get(cat_id)
        if header is None:
            return
        self._cancel_active_inline()
        edit = InlineEdit(initial=current_name)
        edit.setFixedHeight(header.height())
        edit.accepted.connect(lambda text: self._finish_rename(cat_id, text))
        edit.cancelled.connect(lambda: (self._remove_inline(), self._apply_filter(self._filter)))
        self._inline = edit
        self._editing_header = header
        header.setVisible(False)
        edit.setVisible(True)
        if self._side_layout.replaceWidget(header, edit) is None:
            idx = self._side_layout.indexOf(header)
            if idx >= 0:
                self._side_layout.insertWidget(idx, edit)
            else:
                self._side_layout.addWidget(edit)
        QTimer.singleShot(30, self._focus_inline)

    def _finish_rename(self, cat_id: int, text: str) -> None:
        header = self._editing_header
        if text:
            self.db.rename_category(cat_id, text)
            if header is not None:
                # Меняем только имя этой категории, без полного перестроения.
                header.set_name(text)
        self._remove_inline()
        self._apply_filter(self._filter)

    def eventFilter(self, obj, event) -> bool:
        if isinstance(obj, SidebarItem):
            if self._side_item_event(obj, event):
                return True
            return super().eventFilter(obj, event)
        if isinstance(obj, AppCard) and obj.app_id in self._cards:
            etype = event.type()
            if etype == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                grab = event.position().toPoint() + obj.pos()
                self._drag = {
                    "app_id": obj.app_id,
                    "start": event.globalPosition().toPoint(),
                    "grab": grab,
                    "dragging": False,
                }
            elif etype == QEvent.MouseMove and self._drag is not None:
                if (
                    self._drag["app_id"] == obj.app_id
                    and event.buttons() & Qt.LeftButton
                ):
                    pos = event.globalPosition().toPoint()
                    if not self._drag["dragging"]:
                        # Во время поиска порядок карточек диктует релевантность —
                        # перетаскивание отключено, чтобы не конфликтовать с выдачей.
                        if (
                            not self._filter
                            and (pos - self._drag["start"]).manhattanLength() > 14
                        ):
                            self._drag["dragging"] = True
                            self.setCursor(Qt.ClosedHandCursor)
                            obj.grabMouse()
                            self._start_drag(self._drag["app_id"], pos, self._drag["grab"])
                    if self._drag["dragging"]:
                        self._move_ghost(pos)
                        self._drag_over(pos)
                    return True
            elif etype == QEvent.MouseButtonRelease and self._drag is not None:
                if self._drag["app_id"] == obj.app_id:
                    was_dragging = self._drag["dragging"]
                    app_id = self._drag["app_id"]
                    self._drag = None
                    self.setCursor(Qt.ArrowCursor)
                    if was_dragging:
                        obj.releaseMouse()
                        self._end_drag(app_id)
                        self._persist_order()
                    else:
                        self._on_card_clicked(app_id)
                    return True
        return super().eventFilter(obj, event)

    def _start_drag(self, app_id: int, global_pos: QPoint, grab: QPoint) -> None:
        host = self._hosts.get(app_id)
        if host is None:
            return
        pm = host.grab()
        dpr = pm.devicePixelRatioF() or 1.0
        pm = pm.scaled(
            int(host.width() * dpr), int(host.height() * dpr),
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
        )
        pm.setDevicePixelRatio(dpr)
        ghost = QLabel(self)
        ghost.setPixmap(pm)
        ghost.setFixedSize(host.size())
        ghost.setAttribute(Qt.WA_TransparentForMouseEvents)
        opacity = QGraphicsOpacityEffect(ghost)
        opacity.setOpacity(0.8)
        ghost.setGraphicsEffect(opacity)
        ghost.show()
        ghost.raise_()
        self._drag_ghost = ghost

        dim = QGraphicsOpacityEffect(host)
        dim.setOpacity(0.35)
        host.setGraphicsEffect(dim)
        self._drag_dim = dim

        self._move_ghost(global_pos)

    def _move_ghost(self, global_pos: QPoint) -> None:
        if self._drag_ghost is None or self._drag is None:
            return
        local = self.mapFromGlobal(global_pos - self._drag["grab"])
        x = min(max(local.x(), 0), max(0, self.width() - self._drag_ghost.width()))
        y = min(max(local.y(), 0), max(0, self.height() - self._drag_ghost.height()))
        self._drag_ghost.move(x, y)

    def _end_drag(self, app_id: int) -> None:
        host = self._hosts.get(app_id)
        ghost = self._drag_ghost
        self._drag_ghost = None
        if host is not None:
            host.setGraphicsEffect(None)
        self._drag_dim = None
        if ghost is None or host is None:
            if ghost is not None:
                ghost.deleteLater()
            return
        target = self.mapFromGlobal(host.mapToGlobal(QPoint(0, 0)))
        anim = QPropertyAnimation(ghost, b"pos")
        anim.setDuration(160)
        anim.setStartValue(ghost.pos())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(ghost.deleteLater)
        self._drop_anim = anim
        anim.start()

    def _drag_over(self, global_pos: QPoint) -> None:
        container = self._scroll.widget()
        local = container.mapFromGlobal(global_pos)
        target = None
        for app_id in self._order:
            host = self._hosts.get(app_id)
            if host is not None and not host.isHidden() and host.geometry().contains(local):
                target = app_id
                break
        drag_id = self._drag["app_id"]
        if target is None or target == drag_id:
            return
        i = self._order.index(drag_id)
        j = self._order.index(target)
        self._order[i], self._order[j] = self._order[j], self._order[i]
        self._relayout_grid()

    def _persist_order(self) -> None:
        try:
            self.db.set_apps_order(self._order)
        except Exception:
            config.log_error("MainWindow._persist_order")

    def _app_id_for_item(self, item: SidebarItem) -> int | None:
        for app_id, widget in self._side_items.items():
            if widget is item:
                return app_id
        return None

    def _side_item_event(self, item: SidebarItem, event) -> bool:
        etype = event.type()
        if etype == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            app_id = self._app_id_for_item(item)
            if app_id is not None:
                self._side_drag = {
                    "app_id": app_id,
                    "item": item,
                    "start": event.globalPosition().toPoint(),
                    "grab": event.position().toPoint(),
                    "dragging": False,
                }
        elif etype == QEvent.MouseMove and self._side_drag is not None:
            if self._side_drag["item"] is item and event.buttons() & Qt.LeftButton:
                pos = event.globalPosition().toPoint()
                if not self._side_drag["dragging"]:
                    if (pos - self._side_drag["start"]).manhattanLength() > 12:
                        self._side_drag["dragging"] = True
                        item.grabMouse()
                        self.setCursor(Qt.ClosedHandCursor)
                        self._start_side_ghost(item, pos)
                if self._side_drag["dragging"]:
                    self._move_side_ghost(pos)
                    self._set_drop_hint(self._side_drop_target_at(pos))
                return True
        elif etype == QEvent.MouseButtonRelease and self._side_drag is not None:
            if self._side_drag["item"] is item:
                state = self._side_drag
                self._side_drag = None
                self.setCursor(Qt.ArrowCursor)
                if state["dragging"]:
                    item.releaseMouse()
                    self._destroy_side_ghost()
                    target = self._side_drop_target_at(event.globalPosition().toPoint())
                    self._set_drop_hint(None)
                    self._apply_side_drop(state["app_id"], target)
                    return True
        return False

    def _start_side_ghost(self, item: SidebarItem, global_pos: QPoint) -> None:
        pm = item.grab()
        dpr = pm.devicePixelRatioF() or 1.0
        pm = pm.scaled(
            int(item.width() * dpr), int(item.height() * dpr),
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
        )
        pm.setDevicePixelRatio(dpr)
        ghost = QLabel(self)
        ghost.setPixmap(pm)
        ghost.setFixedSize(item.size())
        ghost.setAttribute(Qt.WA_TransparentForMouseEvents)
        opacity = QGraphicsOpacityEffect(ghost)
        opacity.setOpacity(0.75)
        ghost.setGraphicsEffect(opacity)
        ghost.show()
        ghost.raise_()
        self._side_ghost = ghost
        self._move_side_ghost(global_pos)

    def _move_side_ghost(self, global_pos: QPoint) -> None:
        ghost = self._side_ghost
        if ghost is None or self._side_drag is None:
            return
        local = self.mapFromGlobal(global_pos - self._side_drag["grab"])
        x = min(max(local.x(), 0), max(0, self.width() - ghost.width()))
        y = min(max(local.y(), 0), max(0, self.height() - ghost.height()))
        ghost.move(x, y)

    def _destroy_side_ghost(self) -> None:
        if self._side_ghost is not None:
            self._side_ghost.deleteLater()
            self._side_ghost = None

    def _side_drop_target_at(self, global_pos: QPoint):
        container = self._side_container
        local = container.mapFromGlobal(global_pos)
        if not container.rect().contains(local):
            return None
        for cat_id, header in self._cat_headers.items():
            if header.isVisible() and header.geometry().contains(local):
                return ("cat", cat_id)
            for row in self._cat_rows.get(cat_id, []):
                if row.isVisible() and row.geometry().contains(local):
                    return ("cat", cat_id)
        if self._uncat_header is not None and self._uncat_header.isVisible():
            if self._uncat_header.geometry().contains(local):
                return ("uncat", None)
            for app_id, item in self._side_items.items():
                meta = self._rows_meta.get(app_id)
                if (
                    meta is not None
                    and meta.category_id is None
                    and item.isVisible()
                    and item.geometry().contains(local)
                ):
                    return ("uncat", None)
        return None

    def _apply_side_drop(self, app_id: int, target) -> None:
        if target is None:
            return
        meta = self._rows_meta.get(app_id)
        if meta is None:
            return
        kind, cat_id = target
        new_cat = cat_id if kind == "cat" else None
        if meta.category_id == new_cat:
            return
        self.db.set_app_category(app_id, new_cat)
        self._refresh_after_category_move(app_id, new_cat)

    def _set_drop_hint(self, target) -> None:
        widget = None
        if target is not None:
            kind, cat_id = target
            widget = self._cat_headers.get(cat_id) if kind == "cat" else self._uncat_header
        if self._drop_hint is widget:
            return
        old = self._drop_hint
        self._drop_hint = widget
        if isinstance(old, CategoryHeader):
            old.setProperty("droptarget", False)
            old.style().unpolish(old)
            old.style().polish(old)
        elif old is not None:
            old.setStyleSheet("")
        if isinstance(widget, CategoryHeader):
            widget.setProperty("droptarget", True)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        elif widget is not None:
            widget.setStyleSheet(
                f"background: rgba({theme._rgb_str(theme.pal().accent)}, 10%); border-radius: 8px;"
            )

    def _show_modal(self, panel, on_closed=None) -> ModalOverlay | None:
        # Перед показом красим нативные вьюпорты панели под тему — иначе
        # QListWidget/скроллы внутри модалки мигнут системным белым фоном.
        try:
            theme.paint_background(panel)
            for child in panel.findChildren(QAbstractScrollArea):
                theme.paint_background(child)
        except Exception:
            pass
        if self._overlay is not None:
            self._pending_modal = (panel, on_closed)
            if not self._overlay._closing:
                self._overlay.close_modal()
            return None
        overlay = ModalOverlay(self, panel)
        self._overlay = overlay
        overlay.closed.connect(self._on_modal_closed)
        if on_closed is not None:
            overlay.closed.connect(on_closed)
        return overlay

    def _on_modal_closed(self) -> None:
        self._overlay = None
        if self._pending_modal is not None:
            panel, on_closed = self._pending_modal
            self._pending_modal = None
            self._show_modal(panel, on_closed)

    def _open_add(self, cat_id: int | None = None) -> None:
        existing = {row.exe_path for row in self.db.list_apps()}
        panel = AddPanel(existing, self)
        panel.add_requested.connect(lambda app: self._on_add_request(app, cat_id))
        # При закрытии ничего не перестраиваем — список уже обновился в момент
        # добавления (_on_add_request). Раньше здесь был refresh_apps(), и его
        # полное перестроение показывало белое окно. Теперь закрытие работает
        # так же чисто, как закрытие статистики карточки.
        self._show_modal(panel, on_closed=panel.shutdown)

    def _on_add_request(self, app, cat_id: int | None = None) -> None:
        # Извлечение иконки — в фоне: сетевые/медленные пути не должны
        # подвешивать интерфейс при добавлении приложения.
        try:
            icon_bytes = win32_utils.extract_icon_png(app.icon_path, app.icon_index, 64)
        except Exception:
            icon_bytes = None
        new_id = self.db.add_app(app.name, app.exe_path, icon_bytes)
        if new_id is None:
            # Путь уже есть в базе — не создаём ещё одну карточку.
            self.refresh_apps()
            return
        if cat_id is not None:
            # Панель добавления может оставаться открытой после удаления или
            # переноса категории. Не отправляем устаревший category_id в FK.
            valid_categories = {category_id for category_id, _name in self.db.list_categories()}
            if cat_id in valid_categories:
                self.db.set_app_category(new_id, cat_id)
        self.refresh_apps()

    def _open_settings(self) -> None:
        self._popup.hide()
        panel = SettingsPanel(
            self.tracker.threshold_minutes(),
            self.tracker.background_counting(),
            bool(self.db.get_int("show_chart_help", 1)),
            bool(self.db.get_int("autostart", 0)),
            self.db.get_text("theme", theme.DEFAULT_THEME),
            self._autoupdate_on(),
            self,
        )
        panel.saved.connect(self._apply_settings)
        panel.theme_changed.connect(self._preview_theme)
        panel.check_now.connect(lambda: self._check_updates(manual=True))
        panel.set_update_status(self._settings_status_text())
        if self._update_available is not None:
            panel.set_update_action(self._open_update_panel)
        can, reason = updater.can_self_update()
        if not can:
            panel.set_autoupdate_note(
                f"{reason}. Обновления будут предлагаться с подтверждением."
            )
        self._show_modal(panel)

    def _apply_settings(
        self,
        threshold: int,
        background: bool,
        show_help: bool = True,
        autostart: bool = False,
        autoupdate: bool = True,
        theme_key: str = theme.DEFAULT_THEME,
    ) -> None:
        from app import win32_utils
        from app import config

        self.tracker.set_threshold_minutes(threshold)
        self.tracker.set_background_counting(background)
        self.db.set_int("show_chart_help", 1 if show_help else 0)
        self.db.set_text("theme", theme_key)

        old_autoupdate = self._autoupdate_on()
        self.db.set_int("auto_update", 1 if autoupdate else 0)
        if old_autoupdate and not autoupdate:
            # Тумблер выключили при скачанном/ожидающем обновлении — ожидание отменяется.
            updater.cancel_pending()
            self._banner.setVisible(False)
        elif not old_autoupdate and autoupdate and self._update_available is not None:
            self._apply_update_state()
        
        # Обработка автозапуска
        old_autostart = bool(self.db.get_int("autostart", 0))
        if autostart != old_autostart:
            if win32_utils.set_autostart(autostart):
                self.db.set_int("autostart", 1 if autostart else 0)
            else:
                # Ошибка записи в реестр
                config.log_error(f"Не удалось {'включить' if autostart else 'выключить'} автозапуск")
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    f"Не удалось {'включить' if autostart else 'выключить'} автозапуск.\nПроверьте права доступа к реестру Windows."
                )
        
        self._update_status_right()

    def _preview_theme(self, key: str) -> None:
        theme.apply_theme(QApplication.instance(), key)
        self._retheme()

    def _retheme(self) -> None:
        self._search.retheme()
        self._add_app_btn.retheme()
        self._profile_btn.setIcon(menu_icon())
        self._badge.setStyleSheet(
            f"background: {theme.pal().accent}; border-radius: 4px;"
        )
        self._popup.retheme()
        for card in self._cards.values():
            card.update()
            card.chart.update()
        if self._overlay is not None:
            panel = getattr(self._overlay, "_panel", None)
            if panel is not None and hasattr(panel, "retheme"):
                panel.retheme()
            self._overlay.update()
        self._apply_window_palette()
        self.update()

    def _apply_window_palette(self) -> None:
        """Красит нативные фоны в цвет темы до первой отрисовки QSS.

        Убирает белые вспышки: при первом показе окна и при массовом
        перестроении карточек (перенос между категориями, обновление списка).
        """
        bg = QColor(theme.pal().bg)
        pal = self.palette()
        pal.setColor(QPalette.Window, bg)
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        # Основные области должны оставаться прозрачными, чтобы под ними был
        # единый градиент mainRoot. Если залить viewport сплошным цветом,
        # после смены темы появляется вертикальная полоса на его границе.
        for scroll in (getattr(self, "_scroll", None), getattr(self, "_side_scroll", None)):
            if scroll is None:
                continue
            scroll.setAutoFillBackground(False)
            viewport = scroll.viewport()
            viewport.setAutoFillBackground(False)
            for widget in (scroll, viewport):
                palette = widget.palette()
                palette.setColor(QPalette.Window, bg)
                palette.setColor(QPalette.Base, bg)
                widget.setPalette(palette)
            scroll.update()
            viewport.update()

    # ------------------------------------------------------------- updates
    def _autoupdate_on(self) -> bool:
        return bool(self.db.get_int("auto_update", 1))

    def _apply_rollback_safe_mode(self) -> None:
        cfg = config.read_config()
        if cfg.get("rollback_safe_mode"):
            cfg.pop("rollback_safe_mode", None)
            config.write_config(cfg)
            self.db.set_int("auto_update", 0)

    def _auto_check(self) -> None:
        self._check_updates(manual=False)

    def _check_updates(self, manual: bool) -> None:
        if self._checking:
            if manual:
                self._settings_status("Проверка уже выполняется…")
            return
        self._checking = True
        if manual:
            self._settings_status("Проверяем…")
        task = updater.CheckTask(self)
        task.ok.connect(lambda releases: self._on_check_ok(releases, manual))
        task.error.connect(lambda msg: self._on_check_error(msg, manual))
        self._check_task = task
        task.start()

    def _on_check_ok(self, releases, manual: bool) -> None:
        self._checking = False
        self.db.set_text(
            "update_last_check", datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        release, notes = updater.select_update(releases)
        if release is None:
            if manual:
                self._settings_status("Обновлений нет")
            return
        self._update_available = release
        self._update_notes = notes
        if manual:
            self._settings_status(f"Доступна {release.tag}")
            sp = self._settings_panel()
            if sp is not None:
                sp.set_update_action(self._open_update_panel)
        self._apply_update_state()

    def _on_check_error(self, _msg: str, manual: bool) -> None:
        self._checking = False
        # Автоцикл при ошибках молчит; показываем только ответ ручной проверки.
        if manual:
            self._settings_status("Ошибка сети — не удалось проверить обновления")

    def _apply_update_state(self) -> None:
        release = self._update_available
        if release is None:
            return
        self._popup.set_update_available(release.tag)
        can, _reason = updater.can_self_update()
        if self._autoupdate_on() and can:
            self._start_silent_download()
            return
        # Ручной режим или деградация тихого: бейдж + баннер.
        first_notice = not self._badge.isVisible()
        self._badge.show()
        if first_notice:
            self._pulse_badge()
        snoozed = updater.snooze_active(
            self.db.get_text("update_snooze"), release.tag
        )
        if not snoozed and not self._banner_session_hidden:
            self._banner_text.setText(f"Вышла версия {release.tag}")
            self._banner.setVisible(True)
        if self._tray is not None and not self._tray_update_hint_shown:
            self._tray.showMessage(
                "Nodexy",
                f"Доступно обновление {release.tag}. Подробности — в меню.",
                QSystemTrayIcon.Information,
                4000,
            )
            self._tray_update_hint_shown = True

    def _start_silent_download(self) -> None:
        release = self._update_available
        if release is None or not release.asset_url or self._silent_task is not None:
            return
        pending = updater.get_pending()
        if pending and pending.get("version") == release.tag:
            return
        # Имя файла — как у ассета в релизе (Nodexy-Setup-<версия>.exe).
        dest = str(updater.updates_dir() / (release.asset_name or f"Nodexy-{release.tag}.exe"))
        task = updater.DownloadTask(release.asset_url, dest, self)
        task.progress.connect(self._on_silent_progress)
        task.ok.connect(self._on_silent_downloaded)
        task.error.connect(self._on_silent_error)
        self._silent_task = task
        task.start()

    def _on_silent_progress(self, got: int, total: int) -> None:
        if total > 0:
            self._set_tray_progress(min(1.0, got / total))

    def _on_silent_downloaded(self, path: str) -> None:
        self._silent_task = None
        self._set_tray_progress(None)
        release = self._update_available
        if release is None:
            updater._remove_quiet(path)
            return
        ok, _reason = updater.verify_file(path, release.asset_size, release.sha256)
        if not ok:
            # Повреждённый файл не устанавливается; повтор — на следующей проверке.
            updater._remove_quiet(path)
            return
        updater.set_pending(
            {
                "version": release.tag,
                "notes": release.body,
                "file": path,
                "page": release.html_url,
                "attempts": 0,
                "kind": "installer",
            }
        )
        self._settings_status(f"Доступна {release.tag} — установится при выходе")

    def _on_silent_error(self, _msg: str) -> None:
        self._silent_task = None
        self._set_tray_progress(None)

    def _set_tray_progress(self, fraction: float | None) -> None:
        if self._tray is None:
            return
        if fraction is None:
            self._tray.setIcon(theme.load_app_icon())
            self._tray.setToolTip("Nodexy — учёт времени идёт")
            return
        step = max(0, min(10, int(fraction * 10)))
        icon = self._tray_progress_cache.get(step)
        if icon is None:
            icon = self._progress_icon(step / 10)
            self._tray_progress_cache[step] = icon
        self._tray.setIcon(icon)
        self._tray.setToolTip(f"Nodexy — скачивание обновления {int(fraction * 100)}%")

    def _progress_icon(self, fraction: float) -> QIcon:
        base = theme.load_app_icon().pixmap(QSize(64, 64))
        pm = QPixmap(base.toImage())
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(11, 18, 32, 170))
        painter.drawRoundedRect(6, 52, 52, 8, 4, 4)
        painter.setBrush(QColor(theme.pal().accent))
        painter.drawRoundedRect(6, 52, max(8.0, 52 * fraction), 8, 4, 4)
        painter.end()
        return QIcon(pm)

    def _hide_banner_session(self) -> None:
        self._banner_session_hidden = True
        self._banner.setVisible(False)

    def _pulse_badge(self) -> None:
        """Короткая пульсация бейджа: обновление заметно без звука и окон.

        БЕЗ QGraphicsOpacityEffect: он рендерит бейдж в прозрачный буфер и
        вызывал белую вспышку. Пульсируем размер/отступ — безопасно и видно.
        """
        try:
            if not self._badge.isVisible():
                return
            start = self._badge.geometry()
            end = QRect(start)
            end.adjust(-3, -3, 3, 3)
            anim = QVariantAnimation(self)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setDuration(240)
            anim.setEasingCurve(QEasingCurve.OutCubic)

            def on_tick(v):
                w = int(start.width() + (end.width() - start.width()) * v)
                h = int(start.height() + (end.height() - start.height()) * v)
                self._badge.setFixedSize(w, h)

            anim.valueChanged.connect(on_tick)
            anim.finished.connect(lambda: self._badge.setFixedSize(start.size()))
            anim.start(QVariantAnimation.DeleteWhenStopped)
        except Exception:
            pass

    def _snooze_update(self) -> None:
        if self._update_available is not None:
            self.db.set_text(
                "update_snooze", updater.make_snooze(self._update_available.tag)
            )
        self._banner.setVisible(False)

    def _open_update_panel(self) -> None:
        release = self._update_available
        if release is None:
            return
        self._popup.hide()
        can, reason = updater.can_self_update()
        panel = UpdatePanel(release, self._update_notes, can, reason, self)
        panel.install_requested.connect(lambda: self._install_and_restart(panel))
        panel.later_requested.connect(self._snooze_update)
        panel.later_requested.connect(panel.close_requested)
        self._show_modal(panel, on_closed=panel.shutdown)

    def _install_and_restart(self, panel: UpdatePanel) -> None:
        if self._updater_launched:
            return
        path = panel._downloaded_path
        if not path:
            panel.set_status("Файл не скачан — повторите загрузку.")
            return
        updater.set_pending(
            {
                "version": panel._release.tag,
                "notes": panel._release.body,
                "file": path,
                "page": panel._release.html_url,
                "attempts": 0,
                "kind": "installer",
            }
        )
        if updater.schedule_apply(restart=True):
            self._updater_launched = True
            self._quit_app()
        else:
            updater.set_pending(None)
            panel.set_status("Не удалось запустить установку. Откройте страницу релиза.")

    def _quit_app(self) -> None:
        # Полный выход (не в трей): обязателен для применения обновления
        # и чтобы в диспетчере не оставалось процесса.
        self._force_quit = True
        QApplication.quit()

    def _open_whats_new(self) -> None:
        self._popup.hide()
        info = updater.get_last_update()
        if not info:
            return
        panel = WhatsNewPanel(str(info.get("version", "")), str(info.get("notes", "")), self)
        self._show_modal(panel)

    def _apply_pending_on_exit(self) -> None:
        if self._updater_launched:
            return
        # Тихая установка при выходе — только в режиме автообновления.
        if not self._autoupdate_on():
            return
        if updater.get_pending() is None:
            return
        if updater.schedule_apply(restart=False):
            self._updater_launched = True

    def _settings_panel(self):
        if self._overlay is None:
            return None
        panel = getattr(self._overlay, "_panel", None)
        return panel if isinstance(panel, SettingsPanel) else None

    def _stats_panel(self):
        if self._overlay is None:
            return None
        panel = getattr(self._overlay, "_panel", None)
        return panel if isinstance(panel, StatsPanel) else None

    def _settings_status(self, text: str) -> None:
        panel = self._settings_panel()
        if panel is not None:
            panel.set_update_status(text)

    def _settings_status_text(self) -> str:
        last = self.db.get_text("update_last_check")
        text = f"Последняя проверка: {last}" if last else "Ещё не проверялось"
        if self._update_available is not None:
            text += f" · Доступна {self._update_available.tag}"
        elif getattr(self, "_update_failed_url", ""):
            text += " · Установка не удалась: исчерпаны попытки"
        return text

    def paintEvent(self, event) -> None:
        # Гарантия тёмного фона на самом первом кадре: до применения QSS и
        # палитры вьюпортов нативный фон HWND мог мелькнуть белым.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.pal().bg))
        painter.end()
        super().paintEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._pending_plate is not None:
            version, _notes = self._pending_plate
            self._pending_plate = None
            plate = QFrame(self)
            plate.setObjectName("updatePlate")
            lay = QHBoxLayout(plate)
            lay.setContentsMargins(14, 8, 14, 8)
            text = QLabel(f"Обновлено до {version}")
            text.setObjectName("updatePlateText")
            lay.addWidget(text)
            plate.setCursor(Qt.PointingHandCursor)
            plate.mouseReleaseEvent = lambda _e: self._open_whats_new()
            self._content_layout.insertWidget(1, plate)
            QTimer.singleShot(8000, plate.deleteLater)

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
        try:
            first_day = date.fromisoformat(config.read_config().get("first_launch", ""))
        except (TypeError, ValueError):
            first_day = None
        panel = StatsPanel(
            self.db,
            self.tracker,
            row.id,
            row.name,
            row.exe_path,
            row.icon,
            self._period_idx,
            first_day,
        )
        panel.delete_requested.connect(
            lambda aid: (
                self._overlay.close_modal() if self._overlay else None,
                self._confirm_delete(aid),
            )
        )
        panel.path_changed.connect(self._change_app_path)
        self._show_modal(panel)

    def _change_app_path(self, app_id: int, new_path: str) -> None:
        row = self._rows_meta.get(app_id)
        if row is None:
            return
        normalized = os.path.normpath(new_path)
        if normalized.lower().endswith(".lnk"):
            try:
                import pythoncom
                from win32com.client import Dispatch

                pythoncom.CoInitialize()
                shortcut = Dispatch("WScript.Shell").CreateShortCut(normalized)
                normalized = os.path.normpath((shortcut.TargetPath or "").strip())
                del shortcut
            except Exception:
                return
        if not normalized.lower().endswith(".exe") or not os.path.isfile(normalized):
            return
        if self.db.app_path_taken(normalized, except_id=app_id):
            return
        if not self.db.update_app_path(app_id, normalized):
            return
        self.tracker.flush()
        updated = replace(row, exe_path=normalized)
        self._rows_meta[app_id] = updated
        self._names[app_id] = updated.name
        card = self._cards.get(app_id)
        if card is not None:
            card.exe_path = normalized
        self.tracker.set_tracked({item.exe_path: item.id for item in self._rows_meta.values()})
        panel = self._stats_panel()
        if panel is not None:
            panel.set_path(normalized)
        self._update_values()

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
            self.tracker.forget_app(app_id)
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
            card.set_chart(self._card_series(app_id, today_live))
            card.set_running(os.path.normcase(card.exe_path) in self._running)
        self._set_header_total(header_total, animate_header)

    def _set_header_total(self, value: int, animate: bool) -> None:
        gen = PERIOD_GENITIVE[self._period_idx]
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
        try:
            if date.today() != self._today:
                self.refresh_apps()
            self._update_values()
            self._update_status()
        except Exception:
            config.log_error("MainWindow._on_tick")

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
        self._tray.setToolTip("Nodexy — учёт времени идёт")
        self._tray_menu = QMenu()
        show_action = self._tray_menu.addAction("Показать окно")
        show_action.triggered.connect(self._show_window)
        self._tray_menu.addSeparator()
        quit_action = self._tray_menu.addAction("Выход")
        quit_action.triggered.connect(self._quit_app)
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
        if self._force_quit:
            event.accept()
            return
        if self._tray is not None:
            self.hide()
            if not self._tray_hint_shown:
                self._tray.showMessage(
                    "Nodexy",
                    "Программа свёрнута в трей и продолжает учитывать время.",
                    QSystemTrayIcon.Information,
                    3000,
                )
                self._tray_hint_shown = True
            event.ignore()
        else:
            event.accept()
            QApplication.quit()
