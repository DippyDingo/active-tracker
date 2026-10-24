"""Страница «Добавить приложение» — внутри главного окна.

Это НЕ модальное окно и НЕ отдельный HWND. Страница живёт в QStackedWidget
главного окна, поэтому появление/исчезновение физически не может создать
новое окно Windows (именно это и давало белую «кошку»).

Продумано из опыта прошлой версии:
  * нет QListWidget — список на QScrollArea с обычными строками-виджетами;
  * нет QFileDialog — выбор exe встроен прямо в страницу;
  * нет QInputDialog — имя вводится в самой строке/панели;
  * скан и иконки — в фоновых сервисах, UI никогда не блокируется;
  * при уходе со страницы потоки отменяются, ссылки на виджеты не остаются.
"""

import os
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..installed_apps import InstalledApp
from ..services.application_scanner import ApplicationScanThread, invalidate_cache
from ..services.icon_loader import IconLoader
from . import theme
from .shell import Page
from .widgets import magnifier_icon, pixmap_from_png, rounded_pixmap, ui_icon


class _AppRow(QFrame):
    """Строка списка установленных программ."""

    add_clicked = Signal(object)

    def __init__(self, app: InstalledApp, parent=None):
        super().__init__(parent)
        self.app = app
        self._added = False
        self.setObjectName("addRow")
        self.setAttribute(Qt.WA_Hover, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(12)

        self._icon = QLabel()
        self._icon.setFixedSize(30, 30)
        layout.addWidget(self._icon)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        name = QLabel(app.name)
        name.setObjectName("addRowName")
        path = QLabel()
        path.setObjectName("pathLabel")
        fm = QFontMetrics(path.font())
        path.setText(fm.elidedText(app.exe_path, Qt.ElideMiddle, 520))
        path.setToolTip(app.exe_path)
        texts.addWidget(name)
        texts.addWidget(path)
        layout.addLayout(texts, 1)

        self._btn = QPushButton("Добавить")
        self._btn.setObjectName("rowAdd")
        self._btn.setFixedHeight(30)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.clicked.connect(self._on_add)
        layout.addWidget(self._btn)

    def set_icon(self, png: bytes) -> None:
        pm = pixmap_from_png(png)
        if pm is not None:
            self._icon.setPixmap(rounded_pixmap(pm, 30, 8))

    def matches(self, lowered: str) -> bool:
        if not lowered:
            return True
        return lowered in self.app.name.lower() or lowered in self.app.exe_path.lower()

    def mark_added(self) -> None:
        self._added = True
        self._btn.setText("✓ Добавлено")
        self._btn.setEnabled(False)
        self._btn.setObjectName("rowAddDone")
        self._btn.style().unpolish(self._btn)
        self._btn.style().polish(self._btn)

    def _on_add(self) -> None:
        if not self._added:
            self.add_clicked.emit(self.app)


class AddApplicationPage(Page):
    """Страница добавления приложения (внутри главного окна)."""

    application_added = Signal(object)  # InstalledApp

    def __init__(self, existing_paths: set[str], parent=None):
        super().__init__("Добавление приложения", parent)
        self._existing = {os.path.normcase(p) for p in existing_paths}
        self._rows: list[_AppRow] = []
        self._scan_thread: ApplicationScanThread | None = None
        self._icons = IconLoader(30, self)
        self._icons.ready.connect(self._on_icon_ready)
        self._scan_done = False

        body = self.body_layout()
        body.setSpacing(12)

        # ---- поиск
        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setObjectName("searchEdit")
        self._search.setPlaceholderText("Поиск по названию или пути")
        self._search.setClearButtonEnabled(True)
        self._search.addAction(magnifier_icon(), QLineEdit.LeadingPosition)
        self._search.setTextMargins(14, 0, 0, 0)
        self._search.textChanged.connect(self._apply_filter)
        search_row.addWidget(self._search, 1)

        self._refresh_btn = QPushButton("Обновить список")
        self._refresh_btn.setObjectName("ghost")
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._rescan)
        search_row.addWidget(self._refresh_btn)
        body.addLayout(search_row)

        self._hint = QLabel("Загрузка списка установленных программ…")
        self._hint.setObjectName("subtleLabel")
        body.addWidget(self._hint)

        # ---- список
        self._scroll = QScrollArea()
        self._scroll.setObjectName("addScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_host = QWidget()
        self._list_host.setObjectName("addHost")
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(6, 6, 6, 6)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._list_host)
        theme.paint_background(self._scroll)
        body.addWidget(self._scroll, 1)

        # ---- ручной путь (встроенная панель вместо QFileDialog)
        manual = QFrame()
        manual.setObjectName("manualBlock")
        manual_layout = QVBoxLayout(manual)
        manual_layout.setContentsMargins(16, 12, 16, 12)
        manual_layout.setSpacing(8)

        manual_title = QLabel("Добавить по пути вручную")
        manual_title.setObjectName("modalTitle")
        manual_layout.addWidget(manual_title)

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText(r"Например: C:\Program Files\App\app.exe")
        path_row.addWidget(self._path_edit, 1)

        browse = QPushButton("Обзор…")
        browse.setObjectName("ghost")
        browse.setCursor(Qt.PointingHandCursor)
        browse.setIcon(ui_icon("folder"))
        browse.clicked.connect(self._browse_file)
        path_row.addWidget(browse)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Название (необязательно)")
        path_row.addWidget(self._name_edit, 1)

        add_manual = QPushButton("Добавить")
        add_manual.setObjectName("primary")
        add_manual.setCursor(Qt.PointingHandCursor)
        add_manual.clicked.connect(self._add_manual)
        path_row.addWidget(add_manual)
        manual_layout.addLayout(path_row)

        self._manual_status = QLabel("")
        self._manual_status.setObjectName("subtleLabel")
        manual_layout.addWidget(self._manual_status)

        body.addWidget(manual)

        self._start_scan(use_cache=True)

    # ------------------------------------------------------------ сканирование
    def _start_scan(self, use_cache: bool) -> None:
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return
        self._hint.setText("Загрузка списка установленных программ…")
        self._scan_thread = ApplicationScanThread(use_cache, self)
        self._scan_thread.scanned.connect(self._on_scanned)
        self._scan_thread.start()

    def _rescan(self) -> None:
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return
        invalidate_cache()
        self._rebuild_rows([])
        self._scan_done = False
        self._start_scan(use_cache=False)

    def _on_scanned(self, apps: list) -> None:
        self._scan_done = True
        visible = [
            a for a in apps
            if os.path.normcase(a.exe_path) not in self._existing
        ]
        self._rebuild_rows(visible)

    def _rebuild_rows(self, apps: list) -> None:
        # Удаляем только строки (stretch остаётся последним).
        for row in self._rows:
            self._list_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        for app in apps:
            row = _AppRow(app)
            row.add_clicked.connect(self._on_row_add)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)
            self._rows.append(row)
            self._icons.request(app.icon_path or app.exe_path, app.icon_index)

        self._apply_filter(self._search.text())

    def _on_icon_ready(self, source_path: str, _key: str, png: bytes) -> None:
        target = os.path.normcase(source_path)
        for row in self._rows:
            if os.path.normcase(row.app.icon_path or row.app.exe_path) == target:
                row.set_icon(png)

    # ---------------------------------------------------------------- фильтр
    def _apply_filter(self, text: str) -> None:
        lowered = (text or "").strip().lower()
        shown = 0
        for row in self._rows:
            visible = row.matches(lowered)
            row.setVisible(visible)
            shown += 1 if visible else 0

        if not self._scan_done:
            self._hint.setText("Загрузка списка установленных программ…")
        elif lowered:
            self._hint.setText(f"Найдено: {shown}")
        elif not self._rows:
            self._hint.setText(
                "Новых программ не найдено — добавьте приложение по пути ниже."
            )
        else:
            self._hint.setText(f"Доступно приложений: {len(self._rows)}")

    # ------------------------------------------------------------ добавление
    def _on_row_add(self, app: InstalledApp) -> None:
        self.application_added.emit(app)
        self._existing.add(os.path.normcase(app.exe_path))
        for row in self._rows:
            if row.app is app:
                row.mark_added()

    def _browse_file(self) -> None:
        # Никакого QFileDialog/QDialog: выбор пути выполняется через строку
        # внутри страницы. Это исключает создание второго HWND Windows.
        self._path_edit.setFocus()
        self._manual_status.setText(
            "Введите или вставьте полный путь к .exe в поле слева."
        )

    def _on_file_selected(self, path: str) -> None:
        self._path_edit.setText(path)
        if not self._name_edit.text().strip():
            try:
                from ..win32_utils import get_file_description

                description = get_file_description(path)
            except Exception:
                description = ""
            self._name_edit.setText(
                description or os.path.splitext(os.path.basename(path))[0]
            )

    def _add_manual(self) -> None:
        path = self._path_edit.text().strip().strip('"')
        if not path:
            self._manual_status.setText("Укажите путь к exe-файлу.")
            return
        if not os.path.isfile(path):
            self._manual_status.setText("Файл не найден. Проверьте путь.")
            return
        if not path.lower().endswith(".exe"):
            self._manual_status.setText("Нужен exe-файл приложения.")
            return
        norm = os.path.normcase(os.path.normpath(path))
        if norm in self._existing:
            self._manual_status.setText("Это приложение уже добавлено.")
            return

        name = self._name_edit.text().strip()
        if not name:
            try:
                from ..win32_utils import get_file_description

                name = get_file_description(path) or ""
            except Exception:
                name = ""
            name = name or os.path.splitext(os.path.basename(path))[0]

        app = InstalledApp(
            name=name, exe_path=os.path.normpath(path),
            icon_path=path, icon_index=0,
        )
        self.application_added.emit(app)
        self._existing.add(norm)
        self._manual_status.setText(f"Добавлено: {name}")
        self._path_edit.clear()
        self._name_edit.clear()

    # ------------------------------------------------------------- жизненный
    def on_show(self) -> None:
        if not self._scan_done and self._scan_thread is None:
            self._start_scan(use_cache=True)

    def on_hide(self) -> None:
        # Отвязываем сигнал: поток может дожить свой скан сам, но уже без
        # доступа к виджетам страницы. Объект потока должен жить до финиша —
        # удалять QThread при работающем потоке нельзя (падение процесса).
        thread = self._scan_thread
        if thread is not None:
            self._scan_thread = None
            try:
                thread.scanned.disconnect(self._on_scanned)
            except (RuntimeError, TypeError):
                pass
            thread.finished.connect(thread.deleteLater)
        self._icons.cancel_all()

    def shutdown(self) -> None:
        # Полный останов перед удалением страницы: ждём завершения потока
        # сканирования и пула иконок, чтобы не было «QThread destroyed while
        # running» и порчи кучи при сборке мусора.
        thread = self._scan_thread
        self._scan_thread = None
        if thread is not None:
            try:
                thread.scanned.disconnect(self._on_scanned)
            except (RuntimeError, TypeError):
                pass
            thread.wait(5000)
        self._icons.shutdown()
