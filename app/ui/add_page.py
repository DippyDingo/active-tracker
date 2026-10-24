"""Страница «Добавить приложение» — внутри главного окна.

Это НЕ модальное окно и НЕ отдельный HWND: страница живёт в QStackedWidget
главного окна, поэтому её открытие/закрытие физически не может создать
второе окно Windows.

Интерфейс повторяет прежнюю панель добавления:
  * верхняя строка: поиск + «Обзор» (в одной строке);
  * список найденных программ строками (иконка, имя, путь, «Добавить»);
  * внизу только «Готово»;
  * «Обзор» переключает страницу в режим выбора файла прямо внутри неё
    (никаких системных диалогов).
"""

import os

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
    """Строка списка установленных программ (как в прежней панели)."""

    add_clicked = Signal(object)

    def __init__(self, app: InstalledApp, parent=None):
        super().__init__(parent)
        self.app = app
        self._added = False
        self.setObjectName("addRow")
        self.setAttribute(Qt.WA_Hover, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(11)

        self._icon = QLabel()
        self._icon.setFixedSize(28, 28)
        layout.addWidget(self._icon)

        texts = QVBoxLayout()
        texts.setSpacing(1)
        name = QLabel(app.name)
        name.setObjectName("sideName")
        path = QLabel()
        path.setObjectName("pathLabel")
        fm = QFontMetrics(path.font())
        path.setText(fm.elidedText(app.exe_path, Qt.ElideMiddle, 420))
        path.setToolTip(app.exe_path)
        texts.addWidget(name)
        texts.addWidget(path)
        layout.addLayout(texts)
        layout.addStretch(1)

        self._btn = QPushButton("＋ Добавить")
        self._btn.setObjectName("rowAdd")
        self._btn.setFixedHeight(28)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.clicked.connect(self._on_add)
        layout.addWidget(self._btn)

    def set_icon(self, png: bytes) -> None:
        pm = pixmap_from_png(png)
        if pm is not None:
            self._icon.setPixmap(rounded_pixmap(pm, 28, 7))

    def matches(self, lowered: str) -> bool:
        if not lowered:
            return True
        return lowered in self.app.name.lower() or lowered in self.app.exe_path.lower()

    def mark_added(self) -> None:
        self._added = True
        self._btn.setText("✓ Добавлено")
        self._btn.setObjectName("rowAddDone")
        self._btn.setEnabled(False)
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
        self._icons = IconLoader(28, self)
        self._icons.ready.connect(self._on_icon_ready)
        self._scan_done = False
        self._browsing = False

        # Центрированная колонка фиксированной ширины — вид как у прежней
        # панели добавления, а не растянутая на всё окно страница.
        body = self.body_layout()
        body.setContentsMargins(0, 0, 0, 0)
        wrap = QWidget()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 4, 10, 4)
        wrap_layout.addStretch(1)
        holder = QHBoxLayout()
        holder.addStretch(1)
        column = QWidget()
        column.setFixedWidth(700)
        self._col = QVBoxLayout(column)
        self._col.setContentsMargins(0, 0, 0, 0)
        self._col.setSpacing(12)
        holder.addWidget(column)
        holder.addStretch(1)
        wrap_layout.addLayout(holder)
        wrap_layout.addStretch(2)
        body.addWidget(wrap, 1)

        # -------- верхняя строка: поиск + обзор (в одной строке)
        top = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setObjectName("searchEdit")
        self._search.setPlaceholderText("Поиск по названию или пути")
        self._search.setClearButtonEnabled(True)
        self._search.addAction(magnifier_icon(), QLineEdit.LeadingPosition)
        self._search.setTextMargins(14, 0, 0, 0)
        self._search.textChanged.connect(self._apply_filter)
        top.addWidget(self._search, 1)

        browse_btn = QPushButton("Обзор…")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setToolTip("Выбрать exe-файл вручную")
        browse_btn.setIcon(ui_icon("folder"))
        browse_btn.clicked.connect(self._open_browse)
        top.addWidget(browse_btn)
        self._col.addLayout(top)

        self._hint = QLabel("Загрузка списка установленных программ…")
        self._hint.setObjectName("subtleLabel")
        self._col.addWidget(self._hint)

        # -------- список
        self._scroll = QScrollArea()
        self._scroll.setObjectName("addScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_host = QWidget()
        self._list_host.setObjectName("addHost")
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(4, 4, 4, 4)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._list_host)
        theme.paint_background(self._scroll)
        self._col.addWidget(self._scroll, 1)

        # -------- режим обзора файлов (внутри страницы)
        self._browse_box = QWidget()
        browse_layout = QVBoxLayout(self._browse_box)
        browse_layout.setContentsMargins(0, 0, 0, 0)
        browse_layout.setSpacing(8)
        nav = QHBoxLayout()
        self._up_btn = QPushButton("↑")
        self._up_btn.setFixedSize(30, 30)
        self._up_btn.setCursor(Qt.PointingHandCursor)
        self._up_btn.setToolTip("На уровень выше")
        self._up_btn.clicked.connect(self._go_up)
        nav.addWidget(self._up_btn)
        self._dir_label = QLineEdit()
        self._dir_label.setReadOnly(True)
        nav.addWidget(self._dir_label, 1)
        back_btn = QPushButton("Назад к списку")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self._close_browse)
        nav.addWidget(back_btn)
        browse_layout.addLayout(nav)

        self._browse_scroll = QScrollArea()
        self._browse_scroll.setObjectName("addScroll")
        self._browse_scroll.setWidgetResizable(True)
        self._browse_scroll.setFrameShape(QFrame.NoFrame)
        self._browse_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._browse_host = QWidget()
        self._browse_host.setObjectName("addHost")
        self._browse_layout = QVBoxLayout(self._browse_host)
        self._browse_layout.setContentsMargins(4, 4, 4, 4)
        self._browse_layout.setSpacing(2)
        self._browse_layout.addStretch(1)
        self._browse_scroll.setWidget(self._browse_host)
        theme.paint_background(self._browse_scroll)
        browse_layout.addWidget(self._browse_scroll, 1)
        self._browse_box.setVisible(False)
        self._col.addWidget(self._browse_box, 1)
        self._browse_dir = os.path.expanduser("~")

        # -------- низ: только «Готово» (как в прежней панели)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        done_btn = QPushButton("Готово")
        done_btn.setObjectName("primary")
        done_btn.setCursor(Qt.PointingHandCursor)
        done_btn.clicked.connect(self.close_requested)
        bottom.addWidget(done_btn)
        self._col.addLayout(bottom)

        self._start_scan(use_cache=True)

    # ------------------------------------------------------------ сканирование
    def _start_scan(self, use_cache: bool) -> None:
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return
        self._hint.setText("Загрузка списка установленных программ…")
        self._scan_thread = ApplicationScanThread(use_cache, self)
        self._scan_thread.scanned.connect(self._on_scanned)
        self._scan_thread.start()

    def _on_scanned(self, apps: list) -> None:
        self._scan_done = True
        visible = [
            a for a in apps
            if os.path.normcase(a.exe_path) not in self._existing
        ]
        self._rebuild_rows(visible)

    def _rebuild_rows(self, apps: list) -> None:
        for row in self._rows:
            row.hide()
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
            self._hint.setText("Новых программ не найдено — добавьте через «Обзор».")
        else:
            self._hint.setText(f"Доступно приложений: {len(self._rows)}")

    # ------------------------------------------------------------ добавление
    def _on_row_add(self, app: InstalledApp) -> None:
        self.application_added.emit(app)
        self._existing.add(os.path.normcase(app.exe_path))
        for row in self._rows:
            if row.app is app:
                row.mark_added()

    # ------------------------------------------------- обзор файлов (внутри)
    def _open_browse(self) -> None:
        self._browsing = True
        self._scroll.setVisible(False)
        self._browse_box.setVisible(True)
        self._fill_browse(self._browse_dir)

    def _close_browse(self) -> None:
        self._browsing = False
        self._browse_box.setVisible(False)
        self._scroll.setVisible(True)

    def _go_up(self) -> None:
        parent = os.path.dirname(self._browse_dir)
        if parent and parent != self._browse_dir:
            self._fill_browse(parent)

    def _fill_browse(self, directory: str) -> None:
        self._browse_dir = directory
        self._dir_label.setText(directory)
        self._up_btn.setEnabled(os.path.dirname(directory) != directory)

        while self._browse_layout.count() > 1:
            item = self._browse_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        entries: list[tuple[str, bool]] = []
        try:
            for name in sorted(os.listdir(directory), key=str.lower):
                full = os.path.join(directory, name)
                try:
                    is_dir = os.path.isdir(full)
                except OSError:
                    continue
                if is_dir or name.lower().endswith(".exe"):
                    entries.append((name, is_dir))
        except OSError:
            entries = []

        if not entries:
            empty = QLabel("Здесь нет папок и exe-файлов")
            empty.setObjectName("subtleLabel")
            self._browse_layout.insertWidget(0, empty)

        for name, is_dir in entries[:3000]:
            self._browse_layout.insertWidget(
                self._browse_layout.count() - 1,
                self._browse_row(name, is_dir, os.path.join(directory, name)),
            )

    def _browse_row(self, name: str, is_dir: bool, full: str) -> QWidget:
        row = QFrame()
        row.setObjectName("addRow")
        row.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(10)
        icon = QLabel("📁" if is_dir else "▸")
        icon.setFixedSize(20, 20)
        lay.addWidget(icon)
        label = QLabel()
        label.setObjectName("sideName")
        fm = QFontMetrics(label.font())
        label.setText(fm.elidedText(name, Qt.ElideMiddle, 560))
        lay.addWidget(label, 1)

        def on_click(_e, path=full, directory=is_dir):
            if directory:
                self._fill_browse(path)
            else:
                self._add_by_path(path)

        row.mouseReleaseEvent = on_click
        return row

    def _add_by_path(self, path: str) -> None:
        path = os.path.normpath(path)
        norm = os.path.normcase(path)
        if norm in self._existing:
            self._close_browse()
            return
        try:
            from ..win32_utils import get_file_description

            name = get_file_description(path) or ""
        except Exception:
            name = ""
        name = name or os.path.splitext(os.path.basename(path))[0]
        app = InstalledApp(name=name, exe_path=path, icon_path=path, icon_index=0)
        self.application_added.emit(app)
        self._existing.add(norm)
        self._close_browse()

    # ------------------------------------------------------------- жизненный
    def on_show(self) -> None:
        if not self._scan_done and self._scan_thread is None:
            self._start_scan(use_cache=True)

    def on_hide(self) -> None:
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
        thread = self._scan_thread
        self._scan_thread = None
        if thread is not None:
            try:
                thread.scanned.disconnect(self._on_scanned)
            except (RuntimeError, TypeError):
                pass
            thread.wait(5000)
        self._icons.shutdown()
