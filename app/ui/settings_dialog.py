from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QButtonGroup,
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
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(16)
        texts = QVBoxLayout()
        texts.setSpacing(5)
        t = QLabel(title)
        t.setObjectName("settingsCardTitle")
        t.setWordWrap(True)
        texts.addWidget(t)
        if note:
            n = QLabel(note)
            n.setObjectName("subtleLabel")
            n.setWordWrap(True)
            texts.addWidget(n)
        lay.addLayout(texts, 1)
        self.texts = texts


class _ThemeOption(QPushButton):
    """Theme option with a compact preview of the application palette."""

    def __init__(self, palette: "theme.Palette", parent=None):
        super().__init__(parent)
        self.setObjectName("themeOption")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 14, 8)
        row.setSpacing(14)
        row.addWidget(self._make_preview(palette), 0, Qt.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(palette.title)
        title.setObjectName("themeOptionTitle")
        subtitle = QLabel("Светлая тема" if palette.is_light else "Тёмная тема")
        subtitle.setObjectName("themeOptionNote")
        text.addWidget(title)
        text.addWidget(subtitle)
        row.addLayout(text, 1)

        self._check = QLabel("✓")
        self._check.setObjectName("themeOptionCheck")
        self._check.setAlignment(Qt.AlignCenter)
        self._check.setFixedSize(22, 22)
        row.addWidget(self._check)
        self.toggled.connect(self._sync_check)
        self._sync_check(self.isChecked())

    @staticmethod
    def _make_preview(palette: "theme.Palette") -> QFrame:
        preview = QFrame()
        preview.setObjectName("themePreview")
        preview.setFixedSize(82, 52)
        preview.setStyleSheet(
            f"QFrame#themePreview {{ background:{palette.bg}; border:1px solid {palette.border}; border-radius:7px; }}"
        )
        layout = QHBoxLayout(preview)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)
        sidebar = QFrame()
        sidebar.setFixedWidth(15)
        sidebar.setStyleSheet(f"background:{palette.sidebar}; border-radius:3px;")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(3, 5, 3, 5)
        side_layout.setSpacing(3)
        for index in range(3):
            mark = QFrame()
            mark.setFixedSize(8, 3)
            mark.setStyleSheet(
                f"background:{palette.accent if index == 0 else palette.text3}; border-radius:1px;"
            )
            side_layout.addWidget(mark)
        side_layout.addStretch(1)
        layout.addWidget(sidebar)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(4)
        for index in range(2):
            card = QFrame()
            card.setStyleSheet(f"background:{palette.card}; border-radius:3px;")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(5, 4, 5, 4)
            card_layout.setSpacing(3)
            bar = QFrame()
            bar.setFixedSize(18 if index == 0 else 13, 3)
            bar.setStyleSheet(f"background:{palette.text2}; border-radius:1px;")
            line = QFrame()
            line.setFixedSize(31 if index == 0 else 23, 2)
            line.setStyleSheet(f"background:{palette.accent}; border-radius:1px;")
            card_layout.addWidget(bar)
            card_layout.addWidget(line)
            content.addWidget(card, 1)
        layout.addLayout(content, 1)
        return preview

    def _sync_check(self, checked: bool) -> None:
        self._check.setVisible(checked)


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
        self.setFixedSize(700, 680)
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
        sidebar.setFixedWidth(190)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(16, 22, 12, 20)
        nav.setSpacing(6)

        brand = QLabel("Настройки")
        brand.setObjectName("modalTitle")
        nav.addWidget(brand)
        nav.addSpacing(12)

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
        quit_btn.setIcon(ui_icon("power_exit", theme.pal().text2, size=18))
        self._quit_btn = quit_btn
        quit_btn.installEventFilter(self)
        quit_btn.clicked.connect(self.quit_requested.emit)
        nav.addWidget(quit_btn)
        version_row = QHBoxLayout()
        version_row.setContentsMargins(2, 12, 2, 0)
        version_row.setSpacing(0)
        version_rule = QFrame()
        version_rule.setObjectName("settingsVersionRule")
        version_rule.setFixedWidth(3)
        version_rule.setFixedHeight(18)
        version_label = QLabel(f"REDIS  {APP_VERSION}")
        version_label.setObjectName("settingsVersion")
        version_row.addWidget(version_rule)
        version_row.addSpacing(9)
        version_row.addWidget(version_label)
        version_row.addStretch(1)
        nav.addLayout(version_row)
        root.addWidget(sidebar)

        # ------------------------------------------------- правая часть
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(28, 24, 26, 12)
        self._section_title = QLabel("Учёт времени")
        self._section_title.setObjectName("modalTitle")
        head.addWidget(self._section_title)
        head.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("deleteBtn")
        close_btn.setFixedSize(32, 32)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close_requested)
        head.addWidget(close_btn)
        right.addLayout(head)

        self._section_note = QLabel("Настройте правила учёта активности")
        self._section_note.setObjectName("subtleLabel")
        self._section_note.setContentsMargins(28, 0, 26, 16)
        right.addWidget(self._section_note)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._make_general_page(threshold_minutes, background_enabled))
        self._pages.addWidget(self._make_appearance_page(show_chart_help))
        self._pages.addWidget(self._make_data_page())
        self._pages.addWidget(self._make_system_page(autostart_enabled))
        self._pages.addWidget(self._make_updates_page(autoupdate_enabled))
        right.addWidget(self._pages, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(28, 14, 26, 22)
        footer.setSpacing(12)
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
        footer.addWidget(save_btn)
        right.addLayout(footer)
        root.addLayout(right, 1)

        self._switch("general")
        self._mark_theme_active()

    def eventFilter(self, watched, event):
        if watched is self._quit_btn:
            if event.type() == QEvent.Type.Enter:
                self._quit_btn.setIcon(ui_icon("power_exit", theme.pal().danger, size=18))
            elif event.type() == QEvent.Type.Leave:
                self._quit_btn.setIcon(ui_icon("power_exit", theme.pal().text2, size=18))
        return super().eventFilter(watched, event)

    # ------------------------------------------------- страницы
    def _make_general_page(self, threshold, background) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 0, 26, 0)
        lay.setSpacing(12)

        card = _SectionCard("Порог простоя", "Если активности нет дольше порога — простой не засчитывается")
        spin_row = QHBoxLayout()
        spin_row.setContentsMargins(0, 8, 0, 0)
        spin_row.setSpacing(12)
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
        lay.setContentsMargins(28, 0, 26, 0)
        lay.setSpacing(12)

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
        lay.setContentsMargins(28, 0, 26, 0)
        lay.setSpacing(12)

        card = _SectionCard("Тема", "Применяется сразу во всём приложении")
        samples_wrap = QVBoxLayout()
        samples_wrap.setContentsMargins(0, 2, 0, 2)
        samples_wrap.setSpacing(6)
        self._theme_samples: dict[str, _ThemeOption] = {}
        self._theme_group = QButtonGroup(self)
        self._theme_group.setExclusive(True)
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
        lay.setContentsMargins(28, 0, 26, 0)
        lay.setSpacing(12)
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
        lay.setContentsMargins(28, 0, 26, 0)
        lay.setSpacing(12)

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
    _SECTION_NOTES = {
        "general": "Настройте правила учёта активности",
        "appearance": "Выберите оформление и параметры графиков",
        "data": "Создавайте резервные копии и восстанавливайте данные",
        "system": "Управляйте запуском приложения в Windows",
        "updates": "Контролируйте получение обновлений REDIS",
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
        self._section_note.setText(self._SECTION_NOTES[key])
        for k, button in self._nav_buttons.items():
            button.setChecked(k == key)

    # ------------------------------------------------- темы
    def _theme_sample(self, key: str, p: "theme.Palette") -> _ThemeOption:
        option = _ThemeOption(p)
        self._theme_group.addButton(option)
        option.clicked.connect(lambda _checked=False, k=key: self._pick_theme(k))
        self._theme_samples[key] = option
        return option

    def _mark_theme_active(self) -> None:
        for key, option in self._theme_samples.items():
            option.setChecked(key == self._theme_choice)

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
