"""Модальный слой поверх главного окна.

Переписан с нуля БЕЗ QGraphicsOpacityEffect: этот эффект заставляет Qt
рендерить панель в промежуточный прозрачный буфер, из-за чего при открытии
и закрытии на кадр вспыхивало БЕЛОЕ окно. Теперь панель просто появляется
и исчезает без буферов (только лёгкий скролл-ин, полностью безопасный).
"""

import time

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from . import theme


class ModalOverlay(QWidget):
    closed = Signal()

    def __init__(self, host: QWidget, panel: QWidget):
        super().__init__(host)
        self._host = host
        self._panel = panel
        self._closing = False

        panel.setParent(self)
        hint = panel.sizeHint().expandedTo(panel.minimumSize())
        max_w = max(320, host.width() - 90)
        max_h = max(240, host.height() - 70)
        size = QSize(min(hint.width(), max_w), min(hint.height(), max_h))
        panel.setFixedSize(size)
        target = QRect(0, 0, size.width(), size.height())
        target.moveCenter(QPoint(host.width() // 2, host.height() // 2))
        self._target = target

        self.setGeometry(host.rect())
        panel.setGeometry(target)
        host.installEventFilter(self)

        if hasattr(panel, "close_requested"):
            panel.close_requested.connect(self.close_modal)

        self.setFocusPolicy(Qt.StrongFocus)
        self.show()
        self.raise_()
        self.setFocus(Qt.PopupFocusReason)

        self._open_time = time.monotonic()

        # Простое появление: панель видна сразу, без прозрачных буферов.
        panel.show()
        panel.raise_()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._host and event.type() == QEvent.Resize:
            self.setGeometry(self._host.rect())
            self.raise_()
            geom = self._panel.geometry()
            if geom.width() > self.width() or geom.height() > self.height():
                size = QSize(
                    min(geom.width(), max(320, self.width() - 90)),
                    min(geom.height(), max(240, self.height() - 70)),
                )
                self._panel.setFixedSize(size)
            target = QRect(self._panel.geometry())
            target.moveCenter(QPoint(self.width() // 2, self.height() // 2))
            self._panel.setGeometry(target)
            self._target = target
        return super().eventFilter(obj, event)

    def close_modal(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.closed.emit()
        self.deleteLater()

    def mousePressEvent(self, event) -> None:
        # Защита: клик, открывший модалку, не должен её сразу закрыть.
        if time.monotonic() - self._open_time < 0.2:
            return
        if not self._panel.geometry().contains(event.position().toPoint()):
            self.close_modal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close_modal()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.color("overlay"))
        painter.end()
