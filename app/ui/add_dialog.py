import os

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThread, QThreadPool, QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import installed_apps, win32_utils
from ..installed_apps import InstalledApp
from .widgets import magnifier_icon, pixmap_from_png, rounded_pixmap, ui_icon


class _ScanWorker(QThread):
    finished_scan = Signal(list)

    def run(self):
        try:
            apps = installed_apps.get_installed_apps()
        except Exception:
            apps = []
        self.finished_scan.emit(apps)


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
        self._items: list[QListWidgetItem] = []
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
        self._search.setAttribute(Qt.WA_InputMethodEnabled, False)
        self._search.setInputMethodHints(Qt.ImhNoAutoUppercase)
        self._search.addAction(magnifier_icon(), QLineEdit.LeadingPosition)
        self._search.setTextMargins(14, 0, 0, 0)
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        self._hint = QLabel("Загрузка списка установленных программ...")
        self._hint.setObjectName("subtleLabel")
        layout.addWidget(self._hint)

        self._list = QListWidget()
        self._list.setObjectName("addList")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self._list, 1)

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

        self._worker = _ScanWorker(self)
        self._worker.finished_scan.connect(self._on_scanned)
        self._worker.start()

    def _on_scanned(self, apps: list) -> None:
        apps = [a for a in apps if os.path.normcase(a.exe_path) not in self._existing]
        for app in apps:
            row = _Row(app)
            row.add_clicked.connect(self._on_row_add)
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 52))
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
            self._rows.append(row)
            self._items.append(item)
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
        for row, item in zip(self._rows, self._items):
            match = row.matches(lowered)
            item.setHidden(not match)
            shown += 1 if match else 0
        if self._worker.isRunning() and not self._rows:
            self._hint.setText("Загрузка списка установленных программ...")
        elif lowered:
            self._hint.setText(f"Найдено: {shown}")
        else:
            self._hint.setText(f"Доступно приложений: {len(self._rows)}")

    def _pick_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите приложение", "", "Программы (*.exe);;Все файлы (*.*)"
        )
        if not path:
            return
        path = os.path.normpath(path)
        suggestion = win32_utils.get_file_description(path) or os.path.splitext(os.path.basename(path))[0]
        name, ok = QInputDialog.getText(self, "Название приложения", "Название:", text=suggestion)
        if not ok or not name.strip():
            return
        app = InstalledApp(name=name.strip(), exe_path=path, icon_path=path, icon_index=0)
        self.add_requested.emit(app)
        self._existing.add(os.path.normcase(path))
        self._hint.setText(f"Добавлено: {app.name}")
        QTimer.singleShot(3000, self, lambda: self._apply_filter(self._search.text()))

    def shutdown(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(5000)
