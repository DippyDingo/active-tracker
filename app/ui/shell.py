"""Новый UI-каркас Nodexy.

Главное отличие от прежней архитектуры: ВСЕ экраны (добавление приложения,
настройки, статистика, обновления, импорт/экспорт) — это страницы одного
QStackedWidget внутри единственного главного окна.

Почему так:
  * раньше модальные панели поднимались как самостоятельные окна поверх
    главного и на кадр показывались белыми (отдельный HWND с темой Windows);
  * QGraphicsOpacityEffect/QGraphicsDropShadowEffect рендерили панели в
    промежуточный буфер, давая белые вспышки;
  * QFileDialog/QInputDialog открывали нативные светлые окна;
  * полное пересоздание дерева виджетов на каждое действие давало мигание.

Здесь страницы — обычные дочерние виджеты. Ни один экран не может стать
самостоятельным окном, потому что это структурно невозможно.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme


class Page(QFrame):
    """Базовая страница приложения. Живёт только внутри QStackedWidget."""

    close_requested = Signal()

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("pageRoot")
        # Явно: страница не окно, не диалог, не popup.
        self.setWindowFlags(Qt.Widget)
        self.setAttribute(Qt.WA_DontShowOnScreen, False)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        self._header = QWidget()
        self._header.setObjectName("pageHeader")
        head_layout = QHBoxLayout(self._header)
        head_layout.setContentsMargins(28, 18, 20, 14)
        head_layout.setSpacing(12)

        self._title = QLabel(title)
        self._title.setObjectName("pageTitle")
        head_layout.addWidget(self._title)
        head_layout.addStretch(1)

        self._header_actions = QHBoxLayout()
        self._header_actions.setSpacing(8)
        head_layout.addLayout(self._header_actions)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("closePage")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Назад")
        close_btn.clicked.connect(self.close_requested)
        head_layout.addWidget(close_btn)

        self._outer.addWidget(self._header)

        self._body = QWidget()
        self._body.setObjectName("pageBody")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(28, 0, 28, 22)
        self._body_layout.setSpacing(12)
        self._outer.addWidget(self._body, 1)

    # ---------------------------------------------------------------- API
    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def add_header_action(self, button: QPushButton) -> None:
        button.setCursor(Qt.PointingHandCursor)
        self._header_actions.addWidget(button)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def retheme(self) -> None:
        self.update()

    def on_show(self) -> None:
        """Вызывается при активации страницы."""

    def on_hide(self) -> None:
        """Вызывается при уходе со страницы (остановить таймеры, потоки)."""


class PageStack(QStackedWidget):
    """Стек страниц внутри главного окна."""

    page_changed = Signal(QWidget)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pageStack")
        self._main: QWidget | None = None

    def set_main_page(self, page: QWidget) -> None:
        self._main = page
        self.addWidget(page)
        self.setCurrentWidget(page)

    def show_page(self, page: QWidget) -> None:
        previous = self.currentWidget()
        if previous is page:
            return
        if page not in (self.widget(i) for i in range(self.count())):
            self.addWidget(page)
        if previous is not None and hasattr(previous, "on_hide"):
            previous.on_hide()
        self.setCurrentWidget(page)
        if hasattr(page, "on_show"):
            page.on_show()
        self.page_changed.emit(page)

    def back_to_main(self) -> None:
        if self._main is not None:
            self.show_page(self._main)

    def discard_page(self, page: QWidget) -> None:
        if page is self._main or page is None:
            return
        if page is self.currentWidget():
            self.back_to_main()
        self.removeWidget(page)
        page.deleteLater()


class ScrollPage(Page):
    """Страница с прокручиваемым содержимым (стиль сохраняется)."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(title, parent)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("pageScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._inner = QWidget()
        self._inner.setObjectName("pageScrollInner")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 4, 0)
        self._inner_layout.setSpacing(12)
        self._inner_layout.addStretch(1)
        self._scroll.setWidget(self._inner)

        self.body_layout().addWidget(self._scroll, 1)
        theme.paint_background(self._scroll)

    def content_layout(self) -> QVBoxLayout:
        return self._inner_layout

    def add_content(self, widget: QWidget) -> None:
        self._inner_layout.insertWidget(self._inner_layout.count() - 1, widget)

    def clear_content(self) -> None:
        while self._inner_layout.count() > 1:
            item = self._inner_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def retheme(self) -> None:
        theme.paint_background(self._scroll)
        super().retheme()
