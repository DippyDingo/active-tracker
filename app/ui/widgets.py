from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QRectF,
    Qt,
    QPropertyAnimation,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..utils import format_compact


def pixmap_from_png(data: bytes | None) -> QPixmap | None:
    if not data:
        return None
    pm = QPixmap()
    if pm.loadFromData(data, "PNG"):
        return pm
    return None


def rounded_pixmap(src: QPixmap, size: int, radius: int) -> QPixmap:
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0.5, 0.5, size - 1.0, size - 1.0, radius, radius)
    painter.setClipPath(path)
    scaled = src.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    dx = (scaled.width() - size) // 2
    dy = (scaled.height() - size) // 2
    painter.drawPixmap(-dx, -dy, scaled)
    painter.end()
    return out


def magnifier_icon(color: str = "#8fa3b8", size: int = 16) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.7, Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(1.5, 1.5, 9.0, 9.0))
    painter.drawLine(QPointF(9.8, 9.8), QPointF(14.2, 14.2))
    painter.end()
    return QIcon(pm)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


class MiniChart(QWidget):
    def __init__(self, height: int = 46, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setMinimumWidth(100)
        self.setMouseTracking(True)
        self._values: list[int] = []
        self._day_labels: list[str] = []
        self._hover = -1
        self._progress = 1.0
        self._pulse = 1.0

        self._draw_anim = QPropertyAnimation(self, b"progress")
        self._draw_anim.setDuration(900)
        self._draw_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._draw_anim.setStartValue(0.0)
        self._draw_anim.setEndValue(1.0)

        self._pulse_anim = QVariantAnimation(self)
        self._pulse_anim.setDuration(3200)
        self._pulse_anim.setKeyValueAt(0.0, 0.82)
        self._pulse_anim.setKeyValueAt(0.5, 1.0)
        self._pulse_anim.setKeyValueAt(1.0, 0.82)
        self._pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.valueChanged.connect(self._on_pulse)
        self._pulse_anim.start()

        self._draw_anim.finished.connect(self._on_draw_finished)
        self._drawn_at_least_once = False

    def _on_pulse(self, value) -> None:
        self._pulse = float(value)
        if self._drawn_at_least_once:
            self.update()

    def _on_draw_finished(self) -> None:
        self._drawn_at_least_once = True

    def _get_progress(self) -> float:
        return self._progress

    def _set_progress(self, value: float) -> None:
        self._progress = value
        self.update()

    progress = Property(float, _get_progress, _set_progress)

    def set_days(self, labels: list[str]) -> None:
        self._day_labels = labels

    def set_values(self, values: list[int], animate: bool = False) -> None:
        self._values = [max(0, int(v)) for v in values]
        self._hover = -1
        if animate and len(self._values) >= 2:
            self._drawn_at_least_once = False
            self._draw_anim.stop()
            self._draw_anim.start()
        else:
            self._progress = 1.0
            self._drawn_at_least_once = True
        self.update()

    def _points(self) -> list[QPointF]:
        w = max(self.width(), 10)
        h = max(self.height(), 10)
        n = len(self._values)
        if n < 2:
            return []
        vmax = max(max(self._values), 1)
        pad_l, pad_r, pad_t, pad_b = 3.0, 3.0, 5.0, 4.0
        pts = []
        for i, v in enumerate(self._values):
            x = pad_l + i * (w - pad_l - pad_r) / (n - 1)
            y = h - pad_b - (v / vmax) * (h - pad_t - pad_b)
            pts.append(QPointF(x, y))
        return pts

    def paintEvent(self, event) -> None:
        pts = self._points()
        if not pts:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()

        path = QPainterPath()
        path.moveTo(pts[0])
        for i in range(1, len(pts) - 1):
            mid = QPointF((pts[i].x() + pts[i + 1].x()) / 2, (pts[i].y() + pts[i + 1].y()) / 2)
            path.quadTo(pts[i], mid)
        path.lineTo(pts[-1])

        fill = QPainterPath(path)
        fill.lineTo(pts[-1].x(), h)
        fill.lineTo(pts[0].x(), h)
        fill.closeSubpath()

        painter.save()
        painter.setClipRect(QRectF(0, 0, w * self._progress + 0.5, h))
        grad = QLinearGradient(0, 0, 0, h)
        top_alpha = int(70 * self._pulse)
        grad.setColorAt(0.0, QColor(96, 165, 250, top_alpha))
        grad.setColorAt(1.0, QColor(96, 165, 250, 6))
        painter.fillPath(fill, QBrush(grad))
        painter.setPen(QPen(QColor("#60a5fa"), 2))
        painter.drawPath(path)
        painter.restore()

        if 0 <= self._hover < len(pts) and self._progress >= 0.99:
            p = pts[self._hover]
            painter.setPen(QPen(QColor(11, 18, 32), 1.5))
            painter.setBrush(QColor("#60a5fa"))
            painter.drawEllipse(p, 4.2, 4.2)

            value = self._values[self._hover]
            day = self._day_labels[self._hover] if self._hover < len(self._day_labels) else ""
            text = f"{day} — {format_compact(value)}" if day else format_compact(value)
            font = QFont(self.font())
            font.setPointSizeF(8.5)
            painter.setFont(font)
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(text) + 16
            th = 22.0
            bx = min(max(p.x() - tw / 2, 1.0), max(1.0, w - tw - 1))
            by = p.y() - th - 8
            if by < 1:
                by = p.y() + 10
            painter.setPen(QPen(QColor("#24344d"), 1))
            painter.setBrush(QColor(15, 27, 45, 240))
            painter.drawRoundedRect(QRectF(bx, by, tw, th), 6, 6)
            painter.setPen(QColor("#e5e7eb"))
            painter.drawText(QRectF(bx, by, tw, th), Qt.AlignCenter, text)
        painter.end()

    def mouseMoveEvent(self, event) -> None:
        pts = self._points()
        if not pts or self._progress < 0.99:
            return
        w = max(self.width(), 10)
        ratio = min(max(event.position().x() / w, 0.0), 1.0)
        idx = int(round(ratio * (len(pts) - 1)))
        idx = min(max(idx, 0), len(pts) - 1)
        if idx != self._hover:
            self._hover = idx
            self.update()

    def leaveEvent(self, event) -> None:
        if self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(event)


class AppCard(QFrame):
    clicked = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, app_id: int, name: str, exe_path: str, icon_bytes: bytes | None, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self.name = name
        self.exe_path = exe_path
        self.setObjectName("appCard")
        self.setProperty("selected", False)
        self.setMinimumHeight(206)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{name}\n{exe_path}")

        self._shown_period = -1
        self._shown_today = -1
        self._period_anim = None
        self._today_anim = None

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(2, 6, 23, 150))
        self.setGraphicsEffect(shadow)
        self._shadow = shadow

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 12, 12)
        layout.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(9)
        self._icon = QLabel()
        self._icon.setFixedSize(32, 32)
        pm = pixmap_from_png(icon_bytes)
        if pm is not None:
            self._icon.setPixmap(rounded_pixmap(pm, 32, 8))
        top.addWidget(self._icon)

        name_label = QLabel()
        name_label.setObjectName("cardName")
        fm = name_label.fontMetrics()
        name_label.setText(fm.elidedText(name, Qt.ElideRight, 148))
        top.addWidget(name_label)

        self._dot = QLabel()
        self._dot.setObjectName("runningDot")
        self._dot.setFixedSize(8, 8)
        self._dot.setVisible(False)
        self._dot.setToolTip("Приложение запущено")
        top.addWidget(self._dot)
        top.addStretch(1)

        delete_btn = QPushButton("✕")
        delete_btn.setObjectName("deleteBtn")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setToolTip("Удалить из списка")
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.app_id))
        top.addWidget(delete_btn)
        layout.addLayout(top)

        self._time = QLabel("0м")
        self._time.setObjectName("cardTime")
        layout.addWidget(self._time)

        self.chart = MiniChart(46)
        layout.addWidget(self.chart)

        days = QHBoxLayout()
        days.setSpacing(0)
        self._day_labels: list[QLabel] = []
        for _ in range(7):
            label = QLabel("")
            label.setObjectName("dayLabel")
            label.setAlignment(Qt.AlignCenter)
            self._day_labels.append(label)
            days.addWidget(label, 1)
        layout.addLayout(days)

        self._footer = QLabel("СЕГОДНЯ: 0м")
        self._footer.setObjectName("cardFooter")
        layout.addWidget(self._footer)
        layout.addStretch(1)

    def set_selected(self, selected: bool) -> None:
        if self.property("selected") == selected:
            return
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_running(self, running: bool) -> None:
        self._dot.setVisible(running)

    def set_day_names(self, names: list[str]) -> None:
        for label, text in zip(self._day_labels, names):
            label.setText(text)

    def _animate_number(self, attr_shown: str, attr_anim: str, label, value: int, prefix: str = "") -> None:
        current = getattr(self, attr_shown)
        if current < 0 or abs(value - current) <= 2:
            setattr(self, attr_shown, value)
            label.setText(prefix + format_compact(value))
            return
        old = getattr(self, attr_anim)
        if old is not None:
            old.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(current)
        anim.setEndValue(value)
        anim.setDuration(320)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def on_value(v, _label=label, _attr=attr_shown, _prefix=prefix):
            setattr(self, _attr, int(v))
            _label.setText(_prefix + format_compact(v))

        anim.valueChanged.connect(on_value)
        setattr(self, attr_anim, anim)
        anim.start()

    def set_period_seconds(self, seconds: int, animate: bool = False) -> None:
        if animate:
            self._animate_number("_shown_period", "_period_anim", self._time, seconds)
        else:
            self._shown_period = seconds
            self._time.setText(format_compact(seconds))

    def set_today_seconds(self, seconds: int, animate: bool = False) -> None:
        if animate:
            self._animate_number("_shown_today", "_today_anim", self._footer, seconds, "СЕГОДНЯ: ")
        else:
            self._shown_today = seconds
            self._footer.setText(f"СЕГОДНЯ: {format_compact(seconds)}")

    def set_chart(self, values: list[int], animate: bool = False) -> None:
        self.chart.set_values(values, animate)

    def set_day_tooltips(self, labels: list[str]) -> None:
        self.chart.set_days(labels)

    def enterEvent(self, event) -> None:
        self._animate_shadow(QColor(59, 130, 246, 110), 32)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate_shadow(QColor(2, 6, 23, 150), 22)
        super().leaveEvent(event)

    def _animate_shadow(self, color: QColor, blur: int) -> None:
        for attr in ("color", "blurRadius"):
            old = getattr(self, f"_shadow_{attr}_anim", None)
            if old is not None:
                old.stop()
        color_anim = QPropertyAnimation(self._shadow, b"color")
        color_anim.setDuration(180)
        color_anim.setStartValue(self._shadow.color())
        color_anim.setEndValue(color)
        blur_anim = QPropertyAnimation(self._shadow, b"blurRadius")
        blur_anim.setDuration(180)
        blur_anim.setStartValue(self._shadow.blurRadius())
        blur_anim.setEndValue(blur)
        self._shadow_color_anim = color_anim
        self._shadow_blur_anim = blur_anim
        color_anim.start()
        blur_anim.start()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.app_id)
        super().mousePressEvent(event)


class CardHost(QWidget):
    clicked = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, card: AppCard, parent=None):
        super().__init__(parent)
        self.card = card
        card.setParent(self)
        card.clicked.connect(self.clicked)
        card.delete_requested.connect(self.delete_requested)
        self.setMinimumHeight(card.minimumHeight() + 14)
        self._lift = 0.0
        self._lift_anim = None
        card.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.card:
            if event.type() == event.Type.Enter:
                self._animate_lift(6.0)
            elif event.type() == event.Type.Leave:
                self._animate_lift(0.0)
        return super().eventFilter(obj, event)

    def _animate_lift(self, target: float) -> None:
        if self._lift_anim is not None:
            self._lift_anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(self._lift)
        anim.setEndValue(target)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(self._on_lift)
        self._lift_anim = anim
        anim.start()

    def _on_lift(self, value) -> None:
        self._lift = float(value)
        self._relayout()

    def resizeEvent(self, event) -> None:
        self._relayout()
        super().resizeEvent(event)

    def _relayout(self) -> None:
        self.card.setGeometry(
            5,
            int(9 - self._lift),
            max(10, self.width() - 10),
            max(10, self.height() - 13),
        )


class ToggleSwitch(QAbstractButton):
    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)
        self._t = 1.0 if checked else 0.0
        self._anim = None
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        if self._anim is not None:
            self._anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(self._t)
        anim.setEndValue(1.0 if checked else 0.0)
        anim.setDuration(150)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(self._on_t)
        self._anim = anim
        anim.start()

    def _on_t(self, value) -> None:
        self._t = float(value)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = _mix(QColor("#2b3a52"), QColor("#3b82f6"), self._t)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0.5, 0.5, 45, 25), 12.5, 12.5)
        knob_x = 3.0 + self._t * 20.0
        painter.setBrush(QColor("#e8eef6"))
        painter.drawEllipse(QRectF(knob_x, 3.0, 20, 20))
        painter.end()


class SidebarItem(QWidget):
    def __init__(self, name: str, icon_bytes: bytes | None, parent=None):
        super().__init__(parent)
        self._slide = 0.0
        self._anim = None

        self._inner = QWidget(self)
        layout = QHBoxLayout(self._inner)
        layout.setContentsMargins(6, 5, 8, 5)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setFixedSize(32, 32)
        pm = pixmap_from_png(icon_bytes)
        if pm is not None:
            icon.setPixmap(rounded_pixmap(pm, 32, 8))
        layout.addWidget(icon)

        texts = QVBoxLayout()
        texts.setSpacing(1)
        name_label = QLabel()
        name_label.setObjectName("sideName")
        fm = QFontMetrics(name_label.font())
        name_label.setText(fm.elidedText(name, Qt.ElideRight, 152))
        name_label.setToolTip(name)
        texts.addWidget(name_label)
        layout.addLayout(texts)
        layout.addStretch(1)

    def resizeEvent(self, event) -> None:
        self._inner.setGeometry(int(self._slide), 0, int(self.width() - self._slide), self.height())
        super().resizeEvent(event)

    def enterEvent(self, event) -> None:
        self._animate_slide(4.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate_slide(0.0)
        super().leaveEvent(event)

    def _animate_slide(self, target: float) -> None:
        if self._anim is not None:
            self._anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(self._slide)
        anim.setEndValue(target)
        anim.setDuration(130)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(self._on_slide)
        self._anim = anim
        anim.start()

    def _on_slide(self, value) -> None:
        self._slide = float(value)
        self._inner.setGeometry(
            int(self._slide), 0, int(self.width() - self._slide), self.height()
        )
