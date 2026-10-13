from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import updater
from ..updater import ReleaseInfo


class UpdatePanel(QFrame):
    close_requested = Signal()
    install_requested = Signal()
    later_requested = Signal()

    def __init__(
        self,
        release: ReleaseInfo,
        notes: str,
        install_possible: bool,
        reason: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("modalPanel")
        self.setFixedWidth(480)
        self._release = release
        self._task = None
        self._downloaded_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Доступно обновление")
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

        meta = QVBoxLayout()
        meta.setSpacing(2)
        version_label = QLabel(f"Версия {release.tag}")
        version_label.setObjectName("statValue")
        meta.addWidget(version_label)
        details = []
        if release.published_at:
            details.append(f"от {release.published_at}")
        size_text = updater.format_size(release.asset_size)
        if size_text:
            details.append(size_text)
        if details:
            details_label = QLabel(" · ".join(details))
            details_label.setObjectName("subtleLabel")
            meta.addWidget(details_label)
        layout.addLayout(meta)

        notes_area = QScrollArea()
        notes_area.setWidgetResizable(True)
        notes_area.setFixedHeight(160)
        notes_host = QWidget()
        notes_text = QLabel(notes or release.body or "Без описания изменений.")
        notes_text.setObjectName("subtleLabel")
        notes_text.setWordWrap(True)
        notes_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        notes_layout = QVBoxLayout(notes_host)
        notes_layout.setContentsMargins(10, 8, 10, 8)
        notes_layout.addWidget(notes_text)
        notes_layout.addStretch(1)
        notes_area.setWidget(notes_host)
        layout.addWidget(notes_area)

        if not install_possible and reason:
            reason_label = QLabel(reason)
            reason_label.setObjectName("mutedLabel")
            reason_label.setWordWrap(True)
            layout.addWidget(reason_label)

        self._status = QLabel("")
        self._status.setObjectName("mutedLabel")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(12)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._actions = QHBoxLayout()
        layout.addLayout(self._actions)

        self._install_possible = install_possible and bool(release.asset_url)
        if not release.asset_url:
            self._status.setText("В релизе нет установочного файла — доступна только страница релиза.")
        self._set_state("idle")

    # ------------------------------------------------------------- states
    def _clear_actions(self) -> None:
        while self._actions.count():
            item = self._actions.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _btn(self, text: str, object_name: str | None = None) -> QPushButton:
        btn = QPushButton(text)
        if object_name:
            btn.setObjectName(object_name)
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    def _set_state(self, state: str) -> None:
        self._clear_actions()
        self._progress.setVisible(state == "downloading")
        self._actions.addStretch(1)
        if state == "idle":
            if self._release.asset_url and self._install_possible:
                download_btn = self._btn("Скачать и установить", "primary")
                download_btn.clicked.connect(self._start_download)
                self._actions.addWidget(download_btn)
            later_btn = self._btn("Позже")
            later_btn.clicked.connect(self.later_requested)
            self._actions.addWidget(later_btn)
            page_btn = self._btn("Страница релиза")
            page_btn.clicked.connect(self._open_page)
            self._actions.addWidget(page_btn)
        elif state == "downloading":
            cancel_btn = self._btn("Отмена")
            cancel_btn.clicked.connect(self._cancel_download)
            self._actions.addWidget(cancel_btn)
        elif state == "ready":
            install_btn = self._btn("Установить и перезапустить", "primary")
            install_btn.clicked.connect(self.install_requested)
            self._actions.addWidget(install_btn)
            page_btn = self._btn("Страница релиза")
            page_btn.clicked.connect(self._open_page)
            self._actions.addWidget(page_btn)
        elif state == "error":
            retry_btn = self._btn("Повторить")
            retry_btn.clicked.connect(self._start_download)
            self._actions.addWidget(retry_btn)
            page_btn = self._btn("Страница релиза")
            page_btn.clicked.connect(self._open_page)
            self._actions.addWidget(page_btn)

    # ----------------------------------------------------------- download
    def _start_download(self) -> None:
        if self._task is not None or not self._release.asset_url:
            return
        dest = str(updater.updates_dir() / f"Nodexy-{self._release.tag}.exe")
        self._status.setText("Скачивание…")
        self._progress.setValue(0)
        self._set_state("downloading")
        task = updater.DownloadTask(self._release.asset_url, dest, self)
        task.progress.connect(self._on_progress)
        task.ok.connect(self._on_downloaded)
        task.error.connect(self._on_download_error)
        self._task = task
        task.start()

    def _cancel_download(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def _on_progress(self, got: int, total: int) -> None:
        if total > 0:
            self._progress.setValue(min(100, int(got * 100 / total)))

    def _on_downloaded(self, path: str) -> None:
        self._task = None
        ok, reason = updater.verify_file(
            path, self._release.asset_size, self._release.sha256
        )
        if not ok:
            updater._remove_quiet(path)
            self._status.setText(f"Файл повреждён ({reason}) — установка отменена.")
            self._set_state("error")
            return
        # Ожидание установки не фиксируем до клика «Установить»: в режиме
        # с подтверждением выход из приложения не должен ставить обновление.
        self._downloaded_path = path
        self._status.setText("Файл проверен и готов к установке.")
        self._set_state("ready")

    def _on_download_error(self, message: str) -> None:
        self._task = None
        if message == "cancelled":
            self._status.setText("Скачивание отменено.")
            self._set_state("idle")
        else:
            self._status.setText(f"Не удалось скачать: {message}")
            self._set_state("error")

    def _open_page(self) -> None:
        url = self._release.html_url
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task.wait(1500)
            self._task = None


class WhatsNewPanel(QFrame):
    close_requested = Signal()

    def __init__(self, version: str, notes: str, parent=None):
        super().__init__(parent)
        self.setObjectName("modalPanel")
        self.setFixedWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel(f"Что нового в {version}")
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

        notes_area = QScrollArea()
        notes_area.setWidgetResizable(True)
        notes_area.setFixedHeight(240)
        notes_host = QWidget()
        notes_text = QLabel(notes or "Без описания изменений.")
        notes_text.setObjectName("subtleLabel")
        notes_text.setWordWrap(True)
        notes_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        notes_layout = QVBoxLayout(notes_host)
        notes_layout.setContentsMargins(10, 8, 10, 8)
        notes_layout.addWidget(notes_text)
        notes_layout.addStretch(1)
        notes_area.setWidget(notes_host)
        layout.addWidget(notes_area)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        ok_btn = QPushButton("Закрыть")
        ok_btn.setObjectName("primary")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.clicked.connect(self.close_requested)
        bottom.addWidget(ok_btn)
        layout.addLayout(bottom)
