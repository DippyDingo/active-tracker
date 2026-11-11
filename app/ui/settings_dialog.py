from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme
from ..version import APP_VERSION
from .widgets import ToggleSwitch, ui_icon


class _NavRow(QPushButton):
    """Пункт левого меню настроек."""

    def __init__(self, icon_name: str, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("settingsNavBtn")
        self.setIcon(ui_icon(icon_name, size=18))
        self.setIconSize(QSize(18, 18))
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)


class _SectionCard(QFrame):
    """Карточка-строка настройки: заголовок, подпись, элемент справа."""

    def __init__(self, title: str, note: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("settingsCard")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("settingsCardTitle")
        texts.addWidget(t)
        if note:
            n = QLabel(note)
            n.setObjectName("subtleLabel")
            n.setWordWrap(True)
            texts.addWidget(n)
        lay.addLayout(texts, 1)
        self.texts = texts


class SettingsPanel(QFrame):
    saved = Signal(int, bool, bool, bool, bool, str)
    theme_changed = Signal(str)
    check_now = Signal()
    export_requested = Signal()
    load_requested = Signal()
    quit_requested = Signal()
    close_requested = Signal()

    def __init__(
        self,
        threshold_minutes: int,
        background_enabled: bool,
        show_chart_help: bool = True,
        autostart_enabled: bool = False,
        theme_key: str = theme.DEFAULT_THEME,
        autoupdate_enabled: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("modalPanel")
        self.setFixedSize(640, 520)
        self._theme_choice = theme_key if theme_key in theme.PALETTES else theme.DEFAULT_THEME
        self._theme_initial = self._theme_choice
        self._committed = False
        self.close_requested.connect(self._revert_if_cancelled)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ------------------------------------------------- левое меню
        sidebar = QFrame()
        sidebar.setObjectName("settingsNav")
        sidebar.setFixedWidth(176)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(12, 18, 8, 18)
        nav.setSpacing(4)

        brand = QLabel("Настройки")
        brand.setObjectName("modalTitle")
        nav.addWidget(brand)
        nav.addSpacing(10)

        self._nav_buttons: dict[str, _NavRow] = {}
        for key, icon_name, label in (
            ("general", "time", "Учёт времени"),
            ("appearance", "palette", "Интерфейс"),
            ("data", "database", "Данные"),
            ("system", "monitor", "Система"),
            ("updates", "update_cw", "Обновления"),
        ):
            button = _NavRow(icon_name, label)
            button.clicked.connect(lambda _c=False, k=key: self._switch(k))
            nav.addWidget(button)
            self._nav_buttons[key] = button

        nav.addStretch(1)
        # Выход из приложения — внизу левого меню настроек (перенесён из
        # бургер-меню; дубликат в бургере оставлен до подтверждения).
        quit_btn = _NavRow("power_exit", "Выход")
        quit_btn.setObjectName("settingsQuitBtn")
        quit_btn.setCheckable(False)
        quit_btn.clicked.connect(self.quit_requested.emit)
        nav.addWidget(quit_btn)
        self._quit_btn = quit_btn
        version_label = QLabel(f"REDIS v{APP_VERSION}")
        version_label.setObjectName("mutedLabel")
        nav.addWidget(version_label)
        root.addWidget(sidebar)

        # ------------------------------------------------- правая часть
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(4, 16, 18, 10)
        self._section_title = QLabel("Общие")
        self._section_title.setObjectName("modalTitle")
        head.addWidget(self._section_title)
        head.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("deleteBtn")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close_requested)
        head.addWidget(close_btn)
        right.addLayout(head)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._make_general_page(threshold_minutes, background_enabled))
        self._pages.addWidget(self._make_appearance_page(show_chart_help))
        self._pages.addWidget(self._make_data_page())
        self._pages.addWidget(self._make_system_page(autostart_enabled))
        self._pages.addWidget(self._make_updates_page(autoupdate_enabled))
        right.addWidget(self._pages, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(4, 8, 18, 14)
        footer.setSpacing(10)
        self._update_status = QLabel("")
        self._update_status.setObjectName("subtleLabel")
        self._update_status.setWordWrap(True)
        footer.addWidget(self._update_status, 1)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.close_requested)
        save_btn = QPushButton("Сохранить")
        save_btn.setObjectName("primary")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        footer.addWidget(cancel_btn)
        footer.addSpacing(10)
        footer.addWidget(save_btn)
        right.addLayout(footer)
        root.addLayout(right, 1)

        self._switch("general")
        self._mark_theme_active()

    # ------------------------------------------------- страницы
    def _make_general_page(self, threshold, background) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(10)

        card = _SectionCard("Порог простоя", "Если активности нет дольше порога — простой не засчитывается")
        spin_row = QHBoxLayout()
        self._spin = QSpinBox()
        self._spin.setRange(1, 240)
        self._spin.setValue(int(threshold))
        self._spin.setSuffix(" мин")
        self._spin.setFixedWidth(110)
        spin_row.addStretch(1)
        spin_row.addWidget(self._spin)
        card.texts.addLayout(spin_row)
        lay.addWidget(card)

        card2 = _SectionCard("Фоновый учёт", "Засчитывать время запущенных приложений даже вне фокуса")
        self._toggle = ToggleSwitch(background)
        card2.layout().addWidget(self._toggle, 0, Qt.AlignVCenter)
        lay.addWidget(card2)

        lay.addStretch(1)
        return page

    def _make_data_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(10)

        card = _SectionCard("Выгрузить базу данных", "Сохранить копию данных в файл")
        self._export_btn = QPushButton("Выгрузить базу")
        self._export_btn.setObjectName("dataAction")
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.setIcon(ui_icon("export_database"))
        self._export_btn.setIconSize(QSize(20, 20))
        self._export_btn.clicked.connect(self.export_requested.emit)
        card.layout().addWidget(self._export_btn, 0, Qt.AlignRight)
        lay.addWidget(card)

        card2 = _SectionCard("Загрузить базу данных", "Восстановить данные из файла")
        self._import_btn = QPushButton("Загрузить базу")
        self._import_btn.setObjectName("dataAction")
        self._import_btn.setCursor(Qt.PointingHandCursor)
        self._import_btn.setIcon(ui_icon("import_database"))
        self._import_btn.setIconSize(QSize(20, 20))
        self._import_btn.clicked.connect(self.load_requested.emit)
        card2.layout().addWidget(self._import_btn, 0, Qt.AlignRight)
        lay.addWidget(card2)

        lay.addStretch(1)
        return page

    def _make_appearance_page(self, show_help: bool) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(10)

        card = _SectionCard("Тема", "Применяется сразу во всём приложении")
        samples_wrap = QVBoxLayout()
        samples_wrap.setSpacing(6)
        self._theme_samples: dict[str, QFrame] = {}
        for key, p in theme.PALETTES.items():
            samples_wrap.addWidget(self._theme_sample(key, p))
        card.texts.addLayout(samples_wrap)
        lay.addWidget(card)

        help_card = _SectionCard(
            "Подсказка по графику",
            "Показывать пункты «Как пользоваться графиком» в статистике",
        )
        self._help_toggle = ToggleSwitch(show_help)
        help_card.layout().addWidget(self._help_toggle, 0, Qt.AlignVCenter)
        lay.addWidget(help_card)
        lay.addStretch(1)
        return page

    def _make_system_page(self, autostart: bool) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(10)
        card = _SectionCard(
            "Запуск при входе в Windows",
            "Приложение стартует автоматически при входе в систему",
        )
        self._autostart_toggle = ToggleSwitch(autostart)
        card.layout().addWidget(self._autostart_toggle, 0, Qt.AlignVCenter)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _make_updates_page(self, autoupdate) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(10)

        card = _SectionCard("Автообновление", "Новые версии скачиваются и устанавливаются автоматически")
        self._autoupdate_toggle = ToggleSwitch(autoupdate)
        card.layout().addWidget(self._autoupdate_toggle, 0, Qt.AlignVCenter)
        lay.addWidget(card)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._update_btn = QPushButton("Обновить…")
        self._update_btn.setObjectName("primary")
        self._update_btn.setCursor(Qt.PointingHandCursor)
        self._update_btn.setVisible(False)
        row.addWidget(self._update_btn)
        check_btn = QPushButton("Проверить сейчас")
        check_btn.setCursor(Qt.PointingHandCursor)
        check_btn.clicked.connect(self.check_now)
        row.addWidget(check_btn)
        row.addStretch(1)
        lay.addLayout(row)

        note = QLabel(
            "Если автообновление выключено, будет предложено подтвердить установку.\n"
            "Установка выполняется при выходе из приложения."
        )
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        self._autoupdate_note = note
        lay.addWidget(note)
        lay.addStretch(1)
        return page

    # ------------------------------------------------- навигация
    _SECTION_TITLES = {
        "general": "Учёт времени",
        "appearance": "Интерфейс",
        "data": "Данные",
        "system": "Система",
        "updates": "Обновления",
    }

    def _switch(self, key: str) -> None:
        index = {
            "general": 0,
            "appearance": 1,
            "data": 2,
            "system": 3,
            "updates": 4,
        }.get(key, 0)
        self._pages.setCurrentIndex(index)
        self._section_title.setText(self._SECTION_TITLES[key])
        for k, button in self._nav_buttons.items():
            button.setChecked(k == key)

    # ------------------------------------------------- темы
    def _theme_sample(self, key: str, p: "theme.Palette") -> QFrame:
        sample = QFrame()
        sample.setObjectName("themeSample")
        sample.setProperty("active", False)
        sample.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(sample)
        lay.setContentsMargins(8, 6, 10, 6)
        lay.setSpacing(6)
        dot = QLabel()
        dot.setFixedSize(16, 16)
        dot.setStyleSheet(
            f"background: {p.bg}; border: 3px solid {p.accent}; border-radius: 8px;"
        )
        lay.addWidget(dot, 0, Qt.AlignVCenter)
        name = QLabel(p.title)
        name.setObjectName("themeName")
        lay.addWidget(name, 0, Qt.AlignVCenter)
        lay.addStretch(1)
        sample.mouseReleaseEvent = lambda _e, k=key: self._pick_theme(k)
        self._theme_samples[key] = sample
        return sample

    def _mark_theme_active(self) -> None:
        for key, sample in self._theme_samples.items():
            active = key == self._theme_choice
            if sample.property("active") != active:
                sample.setProperty("active", active)
                sample.style().unpolish(sample)
                sample.style().polish(sample)
                sample.update()

    def _pick_theme(self, key: str) -> None:
        if key == self._theme_choice:
            return
        self._theme_choice = key
        self._mark_theme_active()
        self.theme_changed.emit(key)

    def _revert_if_cancelled(self) -> None:
        if self._committed or self._theme_choice == self._theme_initial:
            return
        self.theme_changed.emit(self._theme_initial)

    def _save(self) -> None:
        self._committed = True
        self.saved.emit(
            self._spin.value(),
            self._toggle.isChecked(),
            self._help_toggle.isChecked(),
            self._autostart_toggle.isChecked(),
            self._autoupdate_toggle.isChecked(),
            self._theme_choice,
        )
        self.close_requested.emit()

    def set_update_status(self, text: str) -> None:
        self._update_status.setText(text)

    def set_update_action(self, callback) -> None:
        """Показывает кнопку «Обновить…» (есть доступное обновление)."""
        try:
            self._update_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._update_btn.clicked.connect(callback)
        self._update_btn.setVisible(True)
        self._switch("updates")

    def set_autoupdate_note(self, text: str) -> None:
        # Заметка теперь показывается на странице «Обновления» под заголовком
        # раздела: причина отключения (нет прав SelfUpdate) должна быть видна.
        self._autoupdate_note.setText(text)
        self._autoupdate_note.setWordWrap(True)

    def value(self) -> int:
        return self._spin.value()

    def background_enabled(self) -> bool:
        return self._toggle.isChecked()
