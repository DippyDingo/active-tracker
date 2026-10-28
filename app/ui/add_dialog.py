"""Окно добавления приложения — переписано с нуля.

Что было не так в прежней версии:
  * список на QListWidget: его viewport() — системный, светлый; при показе
    панели он на кадр вспыхивал белым;
  * строки с иконками создавались ПОСЛЕ открытия панели (асинхронный скан),
    поэтому сначала была видна пустая светлая область;
  * QInputDialog/QFileDialog — нативные светлые диалоги.

Как сделано теперь:
  * прокрутка на QScrollArea с явно заданным фоном темы (viewport красится
    вместе с панелью);
  * строки — обычные QWidget в QVBoxLayout, без QListWidget и его вьюпорта;
  * имя приложения спрашивается собственным тёмным диалогом вместо
    QInputDialog;
  * скан установленных программ стартует сразу при создании панели, а
    показывается панель только когда есть что показать (или сразу, если
    список пуст).
"""

import os
import sys
import time

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThread, QThreadPool, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import installed_apps, win32_utils
from ..installed_apps import InstalledApp
from . import theme
from .widgets import magnifier_icon, pixmap_from_png, rounded_pixmap, ui_icon


class _ScanWorker(QThread):
    finished_scan = Signal(list)

    def run(self):
        try:
            apps = installed_apps.get_installed_apps()
        except Exception:
            apps = []
        self.finished_scan.emit(apps)


# Живые потоки сканирования: панель может закрыться, поток доживёт сам.
_active_workers: set = set()


def wait_workers(timeout_ms: int = 8000) -> None:
    """Ждёт завершения всех фоновых потоков сканирования.

    Вызывается при выходе из приложения. Если закрыть программу, пока поток ещё
    сканирует установленные программы, QThread будет уничтожен на ходу
    («QThread: Destroyed while thread is still running»), что портит память при
    завершении процесса. Короткое ожидание это исключает.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    for worker in list(_active_workers):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            worker.wait(int(remaining * 1000))
        except Exception:
            continue


class _IconSignals(QObject):
    ready = Signal(str, bytes)


class _IconTask(QRunnable):
    def __init__(self, key: str, icon_path: str, icon_index: int, size: int = 28):
        super().__init__()
        self.key = key
        self.icon_path = icon_path
        self.icon_index = icon_index
        self.size = size
        self.signals = _IconSignals()
        self.setAutoDelete(True)

    def run(self):
        try:
            import pythoncom

            pythoncom.CoInitialize()
        except Exception:
            pass
        try:
            png = win32_utils.extract_icon_png(self.icon_path, self.icon_index, self.size)
        except Exception:
            png = None
        if png:
            self.signals.ready.emit(self.key, png)


class _NameDialog(QFrame):
    """Собственный тёмный диалог ввода имени (замена нативного QInputDialog)."""

    def __init__(self, title: str, suggestion: str, on_done, parent=None):
        super().__init__(parent)
        self.setObjectName("modalPanel")
        self.setFixedWidth(420)
        self._on_done = on_done

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        head = QLabel(title)
        head.setObjectName("modalTitle")
        layout.addWidget(head)

        self._edit = QLineEdit(suggestion)
        self._edit.selectAll()
        self._edit.returnPressed.connect(self._accept)
        layout.addWidget(self._edit)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self._cancel)
        row.addWidget(cancel)
        ok = QPushButton("Добавить")
        ok.setObjectName("primary")
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self._accept)
        row.addWidget(ok)
        layout.addLayout(row)

        self._edit.setFocus()

    def _accept(self) -> None:
        self._on_done(self._edit.text().strip())

    def _cancel(self) -> None:
        self._on_done("")


class _Row(QFrame):
    add_clicked = Signal(object)

    def __init__(self, app: InstalledApp, parent=None):
        super().__init__(parent)
        self.app = app
        self.added = False
        self.setObjectName("addRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(11)

        self.icon = QLabel()
        self.icon.setFixedSize(28, 28)
        layout.addWidget(self.icon)

        texts = QVBoxLayout()
        texts.setSpacing(1)
        name = QLabel(app.name)
        name.setObjectName("sideName")
        path = QLabel()
        path.setObjectName("pathLabel")
        fm = QFontMetrics(path.font())
        path.setText(fm.elidedText(app.exe_path, Qt.ElideMiddle, 360))
        path.setToolTip(app.exe_path)
        texts.addWidget(name)
        texts.addWidget(path)
        layout.addLayout(texts)
        layout.addStretch(1)

        self.btn = QPushButton("＋ Добавить")
        self.btn.setObjectName("rowAdd")
        self.btn.setFixedHeight(28)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setVisible(False)
        self.btn.clicked.connect(self._on_add)
        layout.addWidget(self.btn)

    def _on_add(self) -> None:
        if not self.added:
            self.add_clicked.emit(self.app)

    def set_icon(self, pm) -> None:
        self.icon.setPixmap(rounded_pixmap(pm, 28, 7))

    def mark_added(self) -> None:
        self.added = True
        self.btn.setText("✓ Добавлено")
        self.btn.setObjectName("rowAddDone")
        self.btn.setEnabled(False)
        self.btn.setVisible(True)
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)

    def matches(self, lowered: str) -> bool:
        return (
            not lowered
            or lowered in self.app.name.lower()
            or lowered in self.app.exe_path.lower()
        )

    def enterEvent(self, event) -> None:
        if not self.added:
            self.btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self.added:
            self.btn.setVisible(False)
        super().leaveEvent(event)


class AddPanel(QFrame):
    add_requested = Signal(object)
    close_requested = Signal()

    def __init__(self, existing_exes: set[str], parent=None):
        super().__init__(parent)
        self.setObjectName("modalPanel")
        self.setFixedSize(680, 620)

        self._existing = {os.path.normcase(p) for p in existing_exes}
        self._rows: list[_Row] = []
        self._scheduled: set[str] = set()
        self._pool = QThreadPool.globalInstance()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Добавление приложения")
        title.setObjectName("modalTitle")
        top.addWidget(title)
        top.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("deleteBtn")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close_requested)
        top.addWidget(close_btn)
        layout.addLayout(top)

        self._search = QLineEdit()
        self._search.setObjectName("searchEdit")
        self._search.setPlaceholderText("  Поиск по названию или пути")
        self._search.setClearButtonEnabled(True)
        self._search.addAction(magnifier_icon(), QLineEdit.LeadingPosition)
        self._search.setTextMargins(14, 0, 0, 0)
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        self._hint = QLabel("Загрузка списка установленных программ...")
        self._hint.setObjectName("subtleLabel")
        layout.addWidget(self._hint)

        # Прокрутка на QScrollArea с фоном темы вместо QListWidget: вьюпорт
        # QScrollArea мы красим явно, поэтому белой вспышки при показе нет.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setObjectName("addScroll")
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._host.setObjectName("addHost")
        self._list_layout = QVBoxLayout(self._host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._host)
        layout.addWidget(self._scroll, 1)

        bottom = QHBoxLayout()
        path_btn = QPushButton("Добавить по пути...")
        path_btn.setCursor(Qt.PointingHandCursor)
        path_btn.setToolTip("Выбрать exe-файл приложения вручную")
        path_btn.setIcon(ui_icon("folder"))
        path_btn.setIconSize(QSize(16, 16))
        path_btn.clicked.connect(self._pick_path)
        bottom.addWidget(path_btn)
        bottom.addStretch(1)
        done_btn = QPushButton("Готово")
        done_btn.setObjectName("primary")
        done_btn.setCursor(Qt.PointingHandCursor)
        done_btn.clicked.connect(self.close_requested)
        bottom.addWidget(done_btn)
        layout.addLayout(bottom)

        self._paint_bg()

        self._worker = _ScanWorker()
        self._worker.finished_scan.connect(self._on_scanned)
        self._worker.finished.connect(lambda: _active_workers.discard(self._worker))
        _active_workers.add(self._worker)
        self._worker.start()

    # ------------------------------------------------------------- фон
    def _paint_bg(self) -> None:
        theme.paint_background(self._scroll)
        pal = self._host.palette()
        bg = theme.color("popup")
        pal.setColor(QPalette.Window, bg)
        pal.setColor(QPalette.Base, bg)
        self._host.setPalette(pal)
        self._host.setAutoFillBackground(True)

    def _on_scanned(self, apps: list) -> None:
        # Показываем весь найденный список при каждом открытии панели. Раньше
        # уже добавленные приложения отфильтровывались здесь и «исчезали» при
        # повторном открытии. Теперь они остаются в списке и помечаются как
        # добавленные, чтобы пользователь видел полный каталог.
        seen: set[str] = set()
        for app in apps:
            key = os.path.normcase(app.exe_path)
            if key in seen:
                continue
            seen.add(key)
            row = _Row(app)
            row.add_clicked.connect(self._on_row_add)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)
            self._rows.append(row)
            if key in self._existing:
                row.mark_added()
            self._schedule_icon(app, row)
        self._apply_filter(self._search.text())

    def _schedule_icon(self, app: InstalledApp, row: _Row) -> None:
        key = os.path.normcase(app.exe_path)
        if key in self._scheduled:
            return
        self._scheduled.add(key)
        task = _IconTask(key, app.icon_path, app.icon_index, 28)
        task.signals.ready.connect(self._on_icon_ready)
        self._pool.start(task)

    def _on_icon_ready(self, key: str, png: bytes) -> None:
        pm = pixmap_from_png(png)
        if pm is None:
            return
        for row in self._rows:
            if os.path.normcase(row.app.exe_path) == key:
                row.set_icon(pm)

    def _on_row_add(self, app: InstalledApp) -> None:
        self.add_requested.emit(app)
        for row in self._rows:
            if row.app is app:
                row.mark_added()
                self._existing.add(os.path.normcase(app.exe_path))

    def _apply_filter(self, text: str) -> None:
        lowered = (text or "").strip().lower()
        shown = 0
        for row in self._rows:
            match = row.matches(lowered)
            row.setVisible(match)
            shown += 1 if match else 0
        added = sum(1 for row in self._rows if row.added)
        if self._worker.isRunning() and not self._rows:
            self._hint.setText("Загрузка списка установленных программ...")
        elif lowered:
            self._hint.setText(f"Найдено: {shown}  ·  уже добавлено: {added}")
        else:
            self._hint.setText(
                f"Доступно приложений: {len(self._rows)}  ·  уже добавлено: {added}"
            )

    def _pick_path(self) -> None:
        # Свой тёмный выбор файла вместо QFileDialog: системный диалог
        # открывается отдельным светлым окном Windows.
        from .file_picker import FilePickerPanel

        start = os.path.dirname(os.path.abspath(sys.argv[0])) if hasattr(sys, "argv") else ""
        picker = FilePickerPanel(start, "Выберите приложение", self)
        picker.close_requested.connect(picker.deleteLater)
        picker.picked.connect(self._on_file_picked)
        picker.move(
            (self.width() - picker.width()) // 2,
            (self.height() - picker.height()) // 2,
        )
        picker.show()
        picker.raise_()
        self._picker = picker

    def _on_file_picked(self, path: str) -> None:
        picker = getattr(self, "_picker", None)
        if picker is not None:
            picker.deleteLater()
            self._picker = None
        path = os.path.normpath(path)
        suggestion = (
            win32_utils.get_file_description(path)
            or os.path.splitext(os.path.basename(path))[0]
        )
        self._ask_name(suggestion, path)

    def _ask_name(self, suggestion: str, path: str) -> None:
        dialog = _NameDialog("Название приложения", suggestion, self._on_name, self)
        dialog.move(
            (self.width() - dialog.width()) // 2, (self.height() - dialog.height()) // 2
        )
        dialog.show()
        dialog.raise_()
        self._name_dialog = dialog
        self._pending_path = path

    def _on_name(self, name: str) -> None:
        dialog = getattr(self, "_name_dialog", None)
        if dialog is not None:
            dialog.deleteLater()
            self._name_dialog = None
        path = getattr(self, "_pending_path", "")
        if not name or not path:
            return
        app = InstalledApp(name=name, exe_path=path, icon_path=path, icon_index=0)
        self.add_requested.emit(app)
        self._existing.add(os.path.normcase(path))
        self._hint.setText(f"Добавлено: {app.name}")
        QTimer.singleShot(3000, self, lambda: self._apply_filter(self._search.text()))

    def shutdown(self) -> None:
        if self._worker is not None:
            try:
                self._worker.finished_scan.disconnect(self._on_scanned)
            except (RuntimeError, TypeError):
                pass
