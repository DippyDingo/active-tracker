from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


class ModalOverlay(QWidget):
    closed = Signal()

    def __init__(self, host: QWidget, panel: QWidget):
        super().__init__(host)
        self._host = host
        self._panel = panel
        self._closing = False
        self._group = None

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

        self._opacity = QGraphicsOpacityEffect(panel)
        self._opacity.setOpacity(0.0)
        panel.setGraphicsEffect(self._opacity)

        self.setFocusPolicy(Qt.StrongFocus)
        self.show()
        self.raise_()
        self.setFocus(Qt.PopupFocusReason)

        fade = QPropertyAnimation(self._opacity, b"opacity")
        fade.setDuration(160)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        fade.finished.connect(self._on_opened)
        self._group = fade
        fade.start()

    def _on_opened(self) -> None:
        self._panel.setGraphicsEffect(None)
        self._opacity = None

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
        if self._group is not None:
            self._group.stop()
        if self._opacity is None:
            effect = QGraphicsOpacityEffect(self._panel)
            effect.setOpacity(1.0)
            self._panel.setGraphicsEffect(effect)
            self._opacity = effect

        fade = QPropertyAnimation(self._opacity, b"opacity")
        fade.setDuration(130)
        fade.setStartValue(self._opacity.opacity())
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.InCubic)
        fade.finished.connect(self._on_closed)
        self._group = fade
        fade.start()

    def _on_closed(self) -> None:
        self.closed.emit()
        self.deleteLater()

    def mousePressEvent(self, event) -> None:
        if not self._panel.geometry().contains(event.position().toPoint()):
            self.close_modal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close_modal()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(4, 9, 20, 150))
        painter.end()
