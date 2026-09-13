import os

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThread, QThreadPool, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from .. import installed_apps, win32_utils


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
    def __init__(self, key: str, icon_path: str, icon_index: int, size: int = 32):
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


class AddAppDialog(QDialog):
    def __init__(self, existing_exes: set[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить приложение")
        self.resize(680, 580)

        self._all_apps: list[installed_apps.InstalledApp] = []
        self._existing = {os.path.normcase(p) for p in existing_exes}
        self._icon_cache: dict[str, QIcon] = {}
        self._scheduled: set[str] = set()
        self._pool = QThreadPool.globalInstance()
        self._selected: list[installed_apps.InstalledApp] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self._search = QLineEdit()
        self._search.setObjectName("searchEdit")
        self._search.setPlaceholderText("Поиск по названию или пути...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        self._hint = QLabel("Загрузка списка установленных программ...")
        self._hint.setObjectName("subtleLabel")
        layout.addWidget(self._hint)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._list.setIconSize(QSize(28, 28))
        self._list.itemDoubleClicked.connect(lambda _: self.accept())
        layout.addWidget(self._list, 1)

        buttons = QHBoxLayout()
        path_btn = QPushButton("Добавить по пути...")
        path_btn.setToolTip("Выбрать exe-файл приложения вручную")
        path_btn.clicked.connect(self._pick_path)
        buttons.addWidget(path_btn)
        buttons.addStretch(1)
        self._cancel_btn = QPushButton("Отмена")
        self._cancel_btn.clicked.connect(self.reject)
        self._add_btn = QPushButton("Добавить")
        self._add_btn.setObjectName("primary")
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self.accept)
        buttons.addWidget(self._cancel_btn)
        buttons.addWidget(self._add_btn)
        layout.addLayout(buttons)

        self._list.itemSelectionChanged.connect(
            lambda: self._add_btn.setEnabled(bool(self._list.selectedItems()))
        )

        self._worker = _ScanWorker(self)
        self._worker.finished_scan.connect(self._on_scanned)
        self._worker.start()

    def _on_scanned(self, apps: list) -> None:
        self._all_apps = [
            a for a in apps if os.path.normcase(a.exe_path) not in self._existing
        ]
        self._apply_filter(self._search.text())

    def _apply_filter(self, text: str) -> None:
        lowered = (text or "").strip().lower()
        self._list.clear()
        shown = 0
        for app in self._all_apps:
            if lowered and lowered not in app.name.lower() and lowered not in app.exe_path.lower():
                continue
            item = QListWidgetItem(app.name)
            item.setData(Qt.UserRole, app)
            item.setToolTip(app.exe_path)
            self._list.addItem(item)
            key = os.path.normcase(app.exe_path)
            cached = self._icon_cache.get(key)
            if cached is not None:
                item.setIcon(cached)
            elif key not in self._scheduled:
                self._scheduled.add(key)
                task = _IconTask(key, app.icon_path, app.icon_index, 32)
                task.signals.ready.connect(self._on_icon_ready)
                self._pool.start(task)
            shown += 1
        if not self._all_apps and not self._worker.isFinished():
            self._hint.setText("Загрузка списка установленных программ...")
        elif lowered:
            self._hint.setText(f"Найдено: {shown}")
        else:
            self._hint.setText(f"Установленных приложений: {len(self._all_apps)}")

    def _on_icon_ready(self, key: str, png: bytes) -> None:
        pm = QPixmap()
        if not pm.loadFromData(png, "PNG"):
            return
        icon = QIcon(pm)
        self._icon_cache[key] = icon
        for i in range(self._list.count()):
            item = self._list.item(i)
            app = item.data(Qt.UserRole)
            if app is not None and os.path.normcase(app.exe_path) == key:
                item.setIcon(icon)

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
        self._selected = [
            installed_apps.InstalledApp(
                name=name.strip(), exe_path=path, icon_path=path, icon_index=0
            )
        ]
        self._shutdown_worker()
        QDialog.accept(self)

    def selected_apps(self) -> list[installed_apps.InstalledApp]:
        return self._selected

    def accept(self) -> None:
        self._selected = [
            item.data(Qt.UserRole) for item in self._list.selectedItems()
        ]
        self._shutdown_worker()
        super().accept()

    def reject(self) -> None:
        self._selected = []
        self._shutdown_worker()
        super().reject()

    def _shutdown_worker(self) -> None:
        if self._worker.isRunning():
            self._worker.wait(5000)
