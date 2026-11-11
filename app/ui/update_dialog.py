from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, Signal, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
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
from ..version import GITHUB_REPO
from . import theme
from .widgets import ui_icon


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
        dest = str(updater.updates_dir() / (self._release.asset_name or f"Nodexy-{self._release.tag}.exe"))
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
        self._status.setText(
            "Установщик проверен. После нажатия приложение закроется, "
            "установщик обновит файлы и откроет окно заново."
        )
        self._set_state("ready")

    def _on_download_error(self, message: str) -> None:
        self._task = None
        if message == "cancelled":
            self._status.setText("Скачивание отменено.")
            self._set_state("idle")
        elif message == "already-downloading":
            self._status.setText("Загрузка уже идёт — подождите завершения.")
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
        self.setObjectName("whatsnewPanel")
        self.setFixedSize(674, 770)
        self._closing = False
        p = theme.pal()
        btn_top, btn_bottom, btn_hover_top, btn_hover_bottom = theme.button_colors()
        self.setStyleSheet(f"""
            QFrame#whatsnewPanel {{ background: {p.popup}; border: 1px solid {p.border}; border-radius: 22px; }}
            QLabel#wnTitle {{ color: {p.text}; font-size: 28px; font-weight: 800; }}
            QLabel#wnBrand {{ color: {p.accent}; font-size: 28px; font-weight: 800; }}
            QLabel#wnSubtitle {{ color: {p.text2}; font-size: 15px; }}
            QLabel#wnMeta {{ color: {p.text}; font-size: 13px; }}
            QLabel#wnCardTitle {{ color: {p.text}; font-size: 15px; font-weight: 800; }}
            QLabel#wnBody {{ color: {p.text2}; font-size: 14px; }}
            QFrame#wnFeature {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 15px; }}
            QFrame#wnIcon {{ background: {p.card_hover}; border: 1px solid {p.accent}; border-radius: 12px; }}
            QPushButton#wnClose {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {btn_top},stop:1 {btn_bottom}); border: none; border-radius: 12px; color: #ffffff; font-size: 15px; font-weight: 800; padding: 12px 30px; }}
            QPushButton#wnClose:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {btn_hover_top},stop:1 {btn_hover_bottom}); }}
            QPushButton#wnClose:pressed {{ padding-top: 14px; padding-bottom: 10px; }}
            QPushButton#wnSecondary {{ background: transparent; border: 1px solid {p.border}; border-radius: 12px; color: {p.text2}; font-size: 14px; padding: 12px 22px; }}
            QPushButton#wnSecondary:hover {{ color: {p.text}; border-color: {p.accent}; background: rgba(128,128,128,20%); }}
            QPushButton#wnExit {{ background: transparent; border: none; color: {p.text2}; font-size: 25px; font-weight: 400; padding: 0; }}
            QPushButton#wnExit:hover {{ color: {p.text}; background: rgba(128,128,128,15%); border-radius: 8px; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 26)
        root.setSpacing(14)

        top = QHBoxLayout()
        month_names = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь")
        release_version = version if version.startswith("v") else f"v{version}"
        badge = QLabel(f"●  {release_version}  •  {month_names[datetime.now().month - 1]} {datetime.now().year}")
        badge.setObjectName("wnMeta")
        badge.setStyleSheet("background:#312657; border:1px solid #7248b5; border-radius:16px; padding:7px 14px; color:#e7d8ff;")
        top.addWidget(badge, 0, Qt.AlignLeft)
        top.addStretch(1)
        close = QPushButton("×")
        close.setObjectName("wnExit")
        close.setFixedSize(42, 42)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self._animate_close)
        top.addWidget(close)
        root.addLayout(top)

        heading = QHBoxLayout()
        heading.setSpacing(0)
        title = QLabel("Что нового в ")
        title.setObjectName("wnTitle")
        brand = QLabel("REDIS")
        brand.setObjectName("wnBrand")
        heading.addWidget(title)
        heading.addWidget(brand)
        heading.addStretch(1)
        root.addLayout(heading)
        sub = QLabel("Новая версия установлена — вот основные изменения.")
        sub.setObjectName("wnSubtitle")
        root.addWidget(sub)

        features = [
            ("rocket", "Быстрый запуск", "Открывайте приложения прямо из карточек."),
            ("pause", "Пауза учёта", "Ставьте учёт на паузу, не закрывая приложение."),
            ("stats", "Обновлённый интерфейс", "Чётче графики, яснее статусы, единый стиль."),
        ]
        for icon_kind, card_title, body in features:
            card = QFrame(); card.setObjectName("wnFeature")
            row = QHBoxLayout(card); row.setContentsMargins(15, 12, 15, 12); row.setSpacing(14)
            icon_box = QFrame(); icon_box.setObjectName("wnIcon"); icon_box.setFixedSize(40, 40)
            icon_layout = QVBoxLayout(icon_box); icon_layout.setContentsMargins(0,0,0,0)
            icon_label = QLabel(); icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setPixmap(ui_icon(icon_kind, None, 24).pixmap(QSize(24, 24)))
            icon_layout.addWidget(icon_label)
            row.addWidget(icon_box)
            text = QVBoxLayout(); text.setSpacing(3)
            h = QLabel(card_title); h.setObjectName("wnCardTitle"); text.addWidget(h)
            b = QLabel(body); b.setObjectName("wnBody"); b.setWordWrap(True); text.addWidget(b)
            row.addLayout(text, 1)
            root.addWidget(card)

        divider = QFrame(); divider.setFixedHeight(1); divider.setStyleSheet(f"background:{p.border}; border:none;"); root.addWidget(divider)
        summary = QHBoxLayout()
        check_icon = QLabel(); check_icon.setPixmap(ui_icon("info", None, 18).pixmap(QSize(18, 18))); summary.addWidget(check_icon)
        summary_text = QLabel("Улучшения производительности и исправления мелких ошибок."); summary_text.setObjectName("wnSubtitle"); summary.addWidget(summary_text); summary.addStretch(1)
        root.addLayout(summary)
        root.addStretch(1)

        footer = QHBoxLayout()
        footer_label = QLabel("REDIS Desktop  •  стабильная сборка"); footer_label.setObjectName("wnSubtitle"); footer.addWidget(footer_label); footer.addStretch(1)
        release_url = f"https://github.com/{GITHUB_REPO}/releases/tag/{release_version}"
        secondary = QPushButton("Все изменения ↗"); secondary.setObjectName("wnSecondary"); secondary.setCursor(Qt.PointingHandCursor); secondary.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(release_url))); footer.addWidget(secondary)
        ok = QPushButton("Понятно"); ok.setObjectName("wnClose"); ok.setCursor(Qt.PointingHandCursor); ok.clicked.connect(self._animate_close); footer.addWidget(ok)
        root.addLayout(footer)

    def _animate_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.setEnabled(False)
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(180)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(self.close_requested)
        animation.finished.connect(animation.deleteLater)
        self._close_animation = animation
        animation.start()
