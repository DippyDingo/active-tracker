from datetime import date
from math import ceil, floor

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QPointF,
    QRectF,
    QSize,
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
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..utils import SHORT_MONTHS, format_compact, ru_date


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


def magnifier_icon(color: str = "#9db2c7", size: int = 18) -> QIcon:
    scale = 3
    px = size * scale
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), 2.0 * scale, Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(2.0 * scale, 2.0 * scale, 9.5 * scale, 9.5 * scale))
    painter.drawLine(QPointF(10.6 * scale, 10.6 * scale), QPointF(15.5 * scale, 15.5 * scale))
    painter.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


def menu_icon(color: str = "#c3d0dd", size: int = 18) -> QIcon:
    scale = 3
    px = size * scale
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), 2.2 * scale, Qt.SolidLine, Qt.RoundCap))
    for y in (4.6, 9.0, 13.4):
        painter.drawLine(QPointF(2.8 * scale, y * scale), QPointF(15.2 * scale, y * scale))
    painter.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


def ui_icon(kind: str, color: str = "#9db2c7", size: int = 16) -> QIcon:
    scale = 3
    px = size * scale
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.8 * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    def pt(x: float, y: float) -> QPointF:
        return QPointF(x * scale, y * scale)

    if kind == "plus":
        painter.drawLine(pt(8, 3.2), pt(8, 12.8))
        painter.drawLine(pt(3.2, 8), pt(12.8, 8))
    elif kind == "minus":
        painter.drawLine(pt(3.2, 8), pt(12.8, 8))
    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(pt(2.4, 13.0))
        path.lineTo(pt(2.4, 3.8))
        path.lineTo(pt(6.6, 3.8))
        path.lineTo(pt(8.2, 5.6))
        path.lineTo(pt(13.6, 5.6))
        path.lineTo(pt(13.6, 13.0))
        path.closeSubpath()
        painter.drawPath(path)
    elif kind == "settings":
        for y, kx in ((4.2, 10.4), (8.0, 5.6), (11.8, 11.0)):
            painter.drawLine(pt(2.6, y), pt(13.4, y))
            painter.setBrush(QColor(color))
            painter.drawEllipse(pt(kx, y), 1.7 * scale, 1.7 * scale)
            painter.setBrush(Qt.NoBrush)
    elif kind == "upload":
        painter.drawLine(pt(8, 13.2), pt(8, 4.2))
        painter.drawLine(pt(4.6, 7.4), pt(8, 4.0))
        painter.drawLine(pt(11.4, 7.4), pt(8, 4.0))
    elif kind == "download":
        painter.drawLine(pt(8, 2.8), pt(8, 11.8))
        painter.drawLine(pt(4.6, 8.6), pt(8, 12.0))
        painter.drawLine(pt(11.4, 8.6), pt(8, 12.0))
    elif kind == "power":
        painter.setPen(QPen(QColor(color), 1.6 * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawArc(int(4.0 * scale), int(4.0 * scale), int(8.0 * scale), int(8.0 * scale), 150 * 16, 240 * 16)
        painter.drawLine(pt(8, 3.9), pt(8, 7.6))
    elif kind == "trash":
        painter.drawLine(pt(3.2, 4.6), pt(12.8, 4.6))
        painter.drawLine(pt(6.4, 2.8), pt(9.6, 2.8))
        painter.drawRoundedRect(QRectF(4.4 * scale, 4.6 * scale, 7.2 * scale, 8.6 * scale), 1.6 * scale, 1.6 * scale)
        painter.drawLine(pt(6.8, 7.0), pt(6.8, 11.0))
        painter.drawLine(pt(9.2, 7.0), pt(9.2, 11.0))
    elif kind == "pen":
        painter.drawLine(pt(3.0, 13.0), pt(12.0, 4.0))
        painter.drawLine(pt(12.0, 4.0), pt(13.2, 5.2))
        painter.drawLine(pt(13.2, 5.2), pt(4.2, 14.2))
        painter.drawLine(pt(3.0, 13.0), pt(4.2, 14.2))
    painter.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


class InlineEdit(QFrame):
    accepted = Signal(str)
    cancelled = Signal()

    def __init__(self, initial: str = "", placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("inlineEdit")
        self.setFixedHeight(34)
        self._done = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        self._edit = QLineEdit()
        self._edit.setText(initial)
        self._edit.setPlaceholderText(placeholder)
        self._edit.setAttribute(Qt.WA_InputMethodEnabled, False)
        self._edit.installEventFilter(self)
        layout.addWidget(self._edit)

    def focus_edit(self) -> None:
        self._edit.setFocus(Qt.OtherFocusReason)
        self._edit.selectAll()
        self._edit.activateWindow()

    def confirm(self) -> None:
        self._finish_accept(self._edit.text().strip())

    def cancel(self) -> None:
        self._finish_cancel()

    def _finish_accept(self, text: str) -> None:
        if self._done:
            return
        self._done = True
        self.accepted.emit(text)

    def _finish_cancel(self) -> None:
        if self._done:
            return
        self._done = True
        self.cancelled.emit()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._edit:
            t = event.type()
            if t == QEvent.KeyPress:
                if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    self._finish_accept(self._edit.text().strip())
                    return True
                if event.key() == Qt.Key_Escape:
                    self._finish_cancel()
                    return True
            elif t == QEvent.FocusOut:
                # Потеря фокуса (клик вне поля и т.п.) = отмена, не подтверждение.
                self._finish_cancel()
        return super().eventFilter(obj, event)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


class MiniChart(QWidget):
    view_changed = Signal(int, int)

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
        self._visible: int | None = None
        self._offset = 0
        self._drag_x: float | None = None
        self._drag_offset = 0

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
        n = len(self._values)
        if self._visible is not None:
            self._visible = max(2, min(self._visible, max(n, 2)))
            self._offset = max(0, n - self._visible)
        if animate and n >= 2:
            self._drawn_at_least_once = False
            self._draw_anim.stop()
            self._draw_anim.start()
        else:
            self._progress = 1.0
            self._drawn_at_least_once = True
        self.update()

    def set_view(self, visible: int | None) -> None:
        n = len(self._values)
        self._visible = None if visible is None else max(2, min(int(visible), max(n, 2)))
        self._offset = max(0, n - self._visible) if self._visible else 0
        self._hover = -1
        self._emit_view()
        self.update()

    def _window(self) -> tuple[int, int]:
        n = len(self._values)
        if self._visible is None or n <= self._visible:
            return 0, n
        return self._clamp_offset(self._offset), self._visible

    def _clamp_offset(self, off: int) -> int:
        n = len(self._values)
        vis = self._visible if self._visible and n > self._visible else n
        return min(max(int(off), 0), max(0, n - vis))

    def _emit_view(self) -> None:
        off, vis = self._window()
        self.view_changed.emit(off, vis)

    def _points(self) -> list[QPointF]:
        off, vis = self._window()
        vals = self._values[off : off + vis]
        w = max(self.width(), 10)
        h = max(self.height(), 10)
        n = len(vals)
        if n < 2:
            return []
        vmax = max(max(vals), 1)
        pad_l, pad_r, pad_t, pad_b = 3.0, 3.0, 5.0, 6.0
        pts = []
        for i, v in enumerate(vals):
            x = pad_l + i * (w - pad_l - pad_r) / (n - 1)
            y = h - pad_b - (v / vmax) * (h - pad_t - pad_b)
            pts.append(QPointF(x, y))
        return pts

    def paintEvent(self, event) -> None:
        try:
            self._paint(event)
        except Exception:
            from .. import config

            config.log_error("MiniChart.paintEvent")

    def _paint(self, event) -> None:
        off, vis = self._window()
        pts = self._points()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        anchor = None
        anchor_idx = -1

        if not pts:
            if vis != 1:
                painter.end()
                return
            v = self._values[off]
            pad_t, pad_b = 5.0, 6.0
            bw = min(46.0, w * 0.25)
            x = (w - bw) / 2
            bh = (h - pad_t - pad_b) if v > 0 else 3.0
            y = h - pad_b - bh
            painter.save()
            painter.setClipRect(QRectF(0, 0, w * self._progress + 0.5, h))
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(96, 165, 250, int(80 * self._pulse)))
            grad.setColorAt(1.0, QColor(96, 165, 250, 10))
            painter.setPen(QPen(QColor("#60a5fa"), 2))
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(QRectF(x, y, bw, bh), 6, 6)
            painter.restore()
            anchor = QPointF(x + bw / 2, y)
            anchor_idx = off
        else:
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
            if 0 <= self._hover < len(pts):
                anchor = pts[self._hover]
                anchor_idx = off + self._hover

        n_total = len(self._values)
        if self._visible is not None and n_total > self._visible:
            track = QRectF(2, h - 3.5, w - 4, 2.5)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 18))
            painter.drawRoundedRect(track, 1.5, 1.5)
            x0 = 2 + (w - 4) * off / n_total
            bw = max(14.0, (w - 4) * vis / n_total)
            painter.setBrush(QColor("#3b82f6"))
            painter.drawRoundedRect(QRectF(x0, h - 3.5, bw, 2.5), 1.5, 1.5)

        if anchor is not None and self._progress >= 0.99 and anchor_idx >= 0:
            p = anchor
            painter.setPen(QPen(QColor(11, 18, 32), 1.5))
            painter.setBrush(QColor("#60a5fa"))
            painter.drawEllipse(p, 4.2, 4.2)

            value = self._values[anchor_idx] if anchor_idx < len(self._values) else 0
            day = self._day_labels[anchor_idx] if anchor_idx < len(self._day_labels) else ""
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
        off, vis = self._window()
        n = len(self._values)
        if self._drag_x is not None and n > vis:
            ppp = max(self.width(), 10) / vis
            delta = int(round((self._drag_x - event.position().x()) / ppp))
            new_off = self._clamp_offset(self._drag_offset + delta)
            if new_off != self._offset:
                self._offset = new_off
                self._hover = -1
                self._emit_view()
                self.update()
            return
        if vis == 1:
            if self._hover != 0 and self._progress >= 0.99:
                self._hover = 0
                self.update()
            return
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

    def mousePressEvent(self, event) -> None:
        off, vis = self._window()
        if event.button() == Qt.LeftButton and len(self._values) > vis:
            self._drag_x = event.position().x()
            self._drag_offset = self._offset
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_x = None
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        off, vis = self._window()
        n = len(self._values)
        if self._visible is None or n <= vis:
            return
        if event.modifiers() & Qt.ControlModifier:
            factor = 0.8 if event.angleDelta().y() > 0 else 1.25
            new_vis = int(round(vis * factor))
            new_vis = min(max(new_vis, min(7, n)), n)
            if new_vis != vis:
                ratio = min(max(event.position().x() / max(self.width(), 10), 0.0), 1.0)
                anchor_idx = off + ratio * vis
                new_off = int(round(anchor_idx - ratio * new_vis))
                self._visible = new_vis
                self._offset = self._clamp_offset(new_off)
                self._hover = -1
                self._emit_view()
                self.update()
        else:
            step = max(1, vis // 8)
            d = -step if event.angleDelta().y() > 0 else step
            new_off = self._clamp_offset(off + d)
            if new_off != self._offset:
                self._offset = new_off
                self._hover = -1
                self._emit_view()
                self.update()

    def leaveEvent(self, event) -> None:
        if self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(event)


class RangeChart(QWidget):
    selection_changed = Signal(object)

    PAD_L = 6.0
    PAD_R = 6.0
    PAD_T = 8.0
    PAD_B = 24.0
    MIN_VISIBLE = 7.0

    def __init__(self, height: int = 150, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setMinimumWidth(200)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setCursor(Qt.CrossCursor)
        self._days: list[int] = []
        self._dates: list[date] = []
        self._buckets: list[tuple[int, int, str, str, int]] = []
        self._offset = 0.0
        self._visible = 7.0
        self._unit = "days"
        self._min_visible = 7.0
        self._sel: tuple[int, int] | None = None
        self._sel_float: tuple[float, float] | None = None
        self._hover = -1
        self._mode: str | None = None
        self._space = False
        self._press_x = 0.0
        self._pan_start_offset = 0.0
        self._sel_anchor_f = 0.0
        self._drag_moved = False
        self._vis_buckets: list[tuple[int, int, str, str, int]] = []
        self._vis_pts: list[QPointF] = []

    def set_data(self, values: list[int], dates: list[date]) -> None:
        self.set_days(values, dates)

    def set_days(self, values: list[int], dates: list[date]) -> None:
        self._unit = "days"
        self._min_visible = 7.0
        self._days = [max(0, int(v)) for v in values]
        self._dates = list(dates)
        self._sel = None
        self._sel_float = None
        self.set_window_days(None)

    def set_hours(self, values: list[int]) -> None:
        self._unit = "hours"
        self._min_visible = 4.0
        self._days = [max(0, int(v)) for v in values]
        self._dates = []
        self._sel = None
        self._sel_float = None
        self.set_window_days(None)

    def _n(self) -> int:
        return len(self._days)

    def selection(self) -> tuple[int, int] | None:
        return self._sel

    def clear_selection(self) -> None:
        if self._sel is not None or self._sel_float is not None:
            self._sel = None
            self._sel_float = None
            self.update()
            self.selection_changed.emit(None)

    def _float_band_to_days(self, left: float, right: float) -> tuple[int, int]:
        n = self._n()
        s = min(max(int(floor(left)), 0), n - 1)
        e = min(max(int(ceil(right)) - 1, 0), n - 1)
        if e < s:
            e = s
        return s, e

    def _sel_band_px(self) -> tuple[float, float] | None:
        if self._sel_float is not None:
            left, right = self._sel_float
        elif self._sel is not None:
            left, right = float(self._sel[0]), float(self._sel[1] + 1)
        else:
            return None
        return self._day_to_x(left), self._day_to_x(right)

    def set_window_days(self, days: int | None) -> None:
        n = self._n()
        if n == 0:
            return
        if days is None:
            vis = float(n)
        else:
            vis = min(max(float(days), self._min_visible), float(n))
        self._visible = vis
        self._offset = float(n) - vis
        self._clamp_view()
        self._rebuild_buckets()
        self.update()

    def _clamp_view(self) -> None:
        n = self._n()
        max_vis = max(float(n), self._min_visible)
        self._visible = min(max(self._visible, self._min_visible), max_vis)
        self._offset = min(max(self._offset, 0.0), max(0.0, n - self._visible))

    def _rebuild_buckets(self) -> None:
        n = self._n()
        if n == 0:
            self._buckets = []
            return
        buckets: list[tuple[int, int, str, str, int]] = []
        if self._unit == "hours":
            for i, v in enumerate(self._days):
                label = f"{i:02d}:00"
                buckets.append((i, i + 1, f"{i:02d}", label, v))
            self._buckets = buckets
            return
        vis = self._visible
        unit = "day" if vis <= 90 else ("week" if vis <= 730 else "month")
        buckets: list[tuple[int, int, str, str, int]] = []
        if unit == "day":
            for i, v in enumerate(self._days):
                d = self._dates[i]
                axis = f"{d.day} {SHORT_MONTHS[d.month - 1]}"
                buckets.append((i, i + 1, axis, ru_date(d), v))
        elif unit == "week":
            for i in range(0, n, 7):
                chunk = self._days[i : i + 7]
                d0 = self._dates[i]
                d1 = self._dates[min(i + 7, n) - 1]
                axis = f"{d0.day} {SHORT_MONTHS[d0.month - 1]}"
                if d0.month == d1.month:
                    tip = f"{d0.day}–{d1.day} {SHORT_MONTHS[d0.month - 1]}"
                else:
                    tip = f"{d0.day} {SHORT_MONTHS[d0.month - 1]}–{d1.day} {SHORT_MONTHS[d1.month - 1]}"
                buckets.append((i, i + 7, axis, tip, sum(chunk)))
        else:
            i = 0
            while i < n:
                year, month = self._dates[i].year, self._dates[i].month
                j = i
                while j < n and (self._dates[j].year, self._dates[j].month) == (year, month):
                    j += 1
                label = f"{SHORT_MONTHS[month - 1]} {year}"
                buckets.append((i, j, label, label, sum(self._days[i:j])))
                i = j
        self._buckets = buckets

    def _plot(self) -> tuple[float, float, float, float]:
        w = max(self.width(), 20)
        h = max(self.height(), 20)
        return self.PAD_L, self.PAD_T, w - self.PAD_L - self.PAD_R, h - self.PAD_T - self.PAD_B

    def _day_to_x(self, di: float) -> float:
        pad_l, _pad_t, inner_w, _inner_h = self._plot()
        return pad_l + (di - self._offset) / self._visible * inner_w

    def _x_to_day(self, x: float) -> float:
        pad_l, _pad_t, inner_w, _inner_h = self._plot()
        return self._offset + (x - pad_l) / max(inner_w, 1.0) * self._visible

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        pad_l, pad_t, inner_w, inner_h = self._plot()
        n = self._n()
        if n == 0:
            painter.end()
            return

        right = self._offset + self._visible
        vis_buckets = [b for b in self._buckets if b[1] > self._offset and b[0] < right]
        vmax = max((b[4] for b in vis_buckets), default=1) or 1

        pts: list[QPointF] = []
        for start, end, _axis, _tip, total in vis_buckets:
            center = (start + end) / 2.0
            x = self._day_to_x(center)
            y = pad_t + inner_h - (total / vmax) * inner_h
            pts.append(QPointF(x, y))
        self._vis_buckets = vis_buckets
        self._vis_pts = pts

        painter.save()
        painter.setClipRect(QRectF(pad_l, 0, inner_w, h))

        band = self._sel_band_px()
        if band is not None:
            xs = max(band[0], pad_l)
            xe = min(band[1], pad_l + inner_w)
            if xe > xs:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(96, 165, 250, 40))
                painter.drawRect(QRectF(xs, pad_t, xe - xs, inner_h))

        if len(pts) >= 2:
            path = QPainterPath()
            path.moveTo(pts[0])
            for i in range(1, len(pts) - 1):
                mid = QPointF((pts[i].x() + pts[i + 1].x()) / 2, (pts[i].y() + pts[i + 1].y()) / 2)
                path.quadTo(pts[i], mid)
            path.lineTo(pts[-1])
            fill = QPainterPath(path)
            fill.lineTo(pts[-1].x(), pad_t + inner_h)
            fill.lineTo(pts[0].x(), pad_t + inner_h)
            fill.closeSubpath()
            grad = QLinearGradient(0, pad_t, 0, pad_t + inner_h)
            grad.setColorAt(0.0, QColor(96, 165, 250, 70))
            grad.setColorAt(1.0, QColor(96, 165, 250, 6))
            painter.fillPath(fill, QBrush(grad))
            painter.setPen(QPen(QColor("#60a5fa"), 2))
            painter.drawPath(path)
        elif len(pts) == 1:
            painter.setPen(QPen(QColor("#60a5fa"), 2))
            painter.setBrush(QBrush(QColor(96, 165, 250, 70)))
            painter.drawEllipse(pts[0], 3.0, 3.0)

        if band is not None:
            xs = max(band[0], pad_l)
            xe = min(band[1], pad_l + inner_w)
            painter.setPen(QPen(QColor("#60a5fa"), 1.5))
            painter.drawLine(QPointF(xs, pad_t), QPointF(xs, pad_t + inner_h))
            painter.drawLine(QPointF(xe, pad_t), QPointF(xe, pad_t + inner_h))
            mid_y = pad_t + inner_h / 2
            painter.setPen(QPen(QColor(11, 18, 32), 1))
            painter.setBrush(QColor("#60a5fa"))
            painter.drawRoundedRect(QRectF(xs - 3, mid_y - 9, 6, 18), 3, 3)
            painter.drawRoundedRect(QRectF(xe - 3, mid_y - 9, 6, 18), 3, 3)
        painter.restore()

        if vis_buckets:
            font = QFont(self.font())
            font.setPointSizeF(7.5)
            painter.setFont(font)
            painter.setPen(QColor("#6b7280"))
            max_labels = max(2, int(inner_w // 90))
            step = max(1, ceil(len(vis_buckets) / max_labels))
            for k in range(0, len(vis_buckets), step):
                bucket = vis_buckets[k]
                x = self._day_to_x((bucket[0] + bucket[1]) / 2.0)
                if pad_l - 4 <= x <= pad_l + inner_w + 4:
                    painter.drawText(QRectF(x - 45, h - self.PAD_B + 4, 90, 16), Qt.AlignCenter, bucket[2])

        if 0 <= self._hover < len(vis_buckets):
            p = pts[self._hover]
            painter.setPen(QPen(QColor(11, 18, 32), 1.5))
            painter.setBrush(QColor("#60a5fa"))
            painter.drawEllipse(p, 4.2, 4.2)
            bucket = vis_buckets[self._hover]
            text = f"{bucket[3]} — {format_compact(bucket[4])}"
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

    def _handle_at(self, x: float) -> str | None:
        band = self._sel_band_px()
        if band is None:
            return None
        xs, xe = band
        if abs(x - xs) <= 6:
            return "handle_l"
        if abs(x - xe) <= 6:
            return "handle_r"
        return None

    def _update_cursor(self, x: float | None = None) -> None:
        if self._mode == "pan":
            self.setCursor(Qt.ClosedHandCursor)
        elif self._mode in ("handle_l", "handle_r"):
            self.setCursor(Qt.SizeHorCursor)
        elif self._space:
            self.setCursor(Qt.OpenHandCursor)
        elif x is not None and self._handle_at(x):
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    def wheelEvent(self, event) -> None:
        n = self._n()
        if n == 0:
            return
        delta = event.angleDelta()
        horizontal = abs(delta.x()) > abs(delta.y())
        if event.modifiers() & Qt.ShiftModifier or horizontal:
            notches = (delta.x() if horizontal else delta.y()) / 120.0
            self._offset += -notches * self._visible / 8.0
            self._clamp_view()
            self._rebuild_buckets()
            self.update()
            return
        factor = 0.8 if delta.y() > 0 else 1.25
        new_vis = min(max(self._visible * factor, self.MIN_VISIBLE), float(n))
        if new_vis == self._visible:
            return
        x = event.position().x()
        anchor = self._x_to_day(x)
        pad_l, _t, inner_w, _h = self._plot()
        ratio = min(max((x - pad_l) / max(inner_w, 1.0), 0.0), 1.0)
        self._visible = new_vis
        self._offset = anchor - ratio * new_vis
        self._clamp_view()
        self._rebuild_buckets()
        self.update()

    def mousePressEvent(self, event) -> None:
        n = self._n()
        if n == 0:
            return
        x = event.position().x()
        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and self._space):
            self._mode = "pan"
            self._press_x = x
            self._pan_start_offset = self._offset
            self.grabMouse()
            self._update_cursor()
            return
        if event.button() != Qt.LeftButton:
            return
        handle = self._handle_at(x)
        if handle is not None and self._sel is not None:
            self._mode = handle
            self._sel_float = (float(self._sel[0]), float(self._sel[1] + 1))
            self.grabMouse()
            self._update_cursor()
            return
        band = self._sel_band_px()
        if band is not None and band[0] < x < band[1]:
            self._mode = "keep"
            return
        self._mode = "sel"
        self._drag_moved = False
        f = min(max(self._x_to_day(x), 0.0), float(n))
        self._sel_anchor_f = f
        self._sel_float = (f, f)
        day = min(max(int(floor(f)), 0), n - 1)
        self._sel = (day, day)
        self.grabMouse()
        self.selection_changed.emit(self._sel)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        n = self._n()
        if n == 0:
            return
        x = event.position().x()
        if self._mode == "pan":
            _pad_l, _t, inner_w, _h = self._plot()
            dx_days = (self._press_x - x) / max(inner_w, 1.0) * self._visible
            self._offset = self._pan_start_offset + dx_days
            self._clamp_view()
            self._rebuild_buckets()
            self.update()
            return
        if self._mode in ("handle_l", "handle_r") and self._sel_float is not None:
            f = min(max(self._x_to_day(x), 0.0), float(n))
            left, right = self._sel_float
            if self._mode == "handle_l":
                left = min(f, right - 0.2)
            else:
                right = max(f, left + 0.2)
            self._sel_float = (left, right)
            self._sel = self._float_band_to_days(left, right)
            self.selection_changed.emit(self._sel)
            self.update()
            return
        if self._mode == "sel":
            self._drag_moved = True
            f = min(max(self._x_to_day(x), 0.0), float(n))
            anchor = self._sel_anchor_f
            left, right = (anchor, f) if anchor <= f else (f, anchor)
            self._sel_float = (left, right)
            self._sel = self._float_band_to_days(left, right)
            self.selection_changed.emit(self._sel)
            self.update()
            return
        self._hover = self._bucket_at(x)
        self._update_cursor(x)
        self.update()

    def _bucket_at(self, x: float) -> int:
        day = self._x_to_day(x)
        for k, bucket in enumerate(self._vis_buckets):
            if bucket[0] <= day < bucket[1]:
                return k
        return -1

    def mouseReleaseEvent(self, event) -> None:
        if self._mode == "sel":
            if not self._drag_moved:
                self._sel = None
                self._sel_float = None
                self.selection_changed.emit(None)
                self.update()
            elif self._sel is not None:
                self._sel = (min(self._sel[0], self._sel[1]), max(self._sel[0], self._sel[1]))
                self._sel_float = None
                self.selection_changed.emit(self._sel)
        self._mode = None
        self._drag_moved = False
        try:
            self.releaseMouse()
        except RuntimeError:
            pass
        self._update_cursor(event.position().x())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Space:
            self._space = True
            self._update_cursor()
            event.accept()
            return
        if event.key() == Qt.Key_Escape and self._sel is not None:
            self.clear_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key_Space:
            self._space = False
            self._update_cursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

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


class SidebarItem(QFrame):
    clicked = Signal()

    def __init__(self, name: str, icon_bytes: bytes | None, parent=None):
        super().__init__(parent)
        self.setObjectName("sideItem")
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(46)
        self._slide = 0.0
        self._anim = None
        self._menu = None

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

        name_label = QLabel()
        name_label.setObjectName("sideName")
        fm = QFontMetrics(name_label.font())
        name_label.setText(fm.elidedText(name, Qt.ElideRight, 152))
        name_label.setToolTip(name)
        layout.addWidget(name_label)
        layout.addStretch(1)

    def set_context_menu(self, menu) -> None:
        self._menu = menu

    def set_selected(self, selected: bool) -> None:
        if self.property("selected") == selected:
            return
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        if self._menu is not None:
            self._menu.exec(event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)

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


class CategoryHeader(QFrame):
    toggle_requested = Signal()

    def __init__(self, name: str, count: int, collapsed: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("catHeader")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)
        self._menu = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(7)

        self._arrow = QLabel("▸" if collapsed else "▾")
        self._arrow.setObjectName("catArrow")
        self._arrow.setFixedWidth(10)
        layout.addWidget(self._arrow)

        icon_label = QLabel()
        icon_label.setFixedSize(16, 16)
        icon_label.setPixmap(ui_icon("folder", "#8fa3b8", 16).pixmap(QSize(16, 16)))
        layout.addWidget(icon_label)

        name_label = QLabel()
        name_label.setObjectName("catName")
        fm = QFontMetrics(name_label.font())
        name_label.setText(fm.elidedText(name.upper(), Qt.ElideRight, 130))
        name_label.setToolTip(name)
        self._name_label = name_label
        self._name_fm = fm
        layout.addWidget(name_label)
        layout.addStretch(1)

        self._count = QLabel(str(count))
        self._count.setObjectName("catCount")
        self._count.setAlignment(Qt.AlignCenter)
        self._count.setFixedHeight(18)
        layout.addWidget(self._count)

    def set_arrow(self, collapsed: bool) -> None:
        self._arrow.setText("▸" if collapsed else "▾")

    def set_count(self, count: int) -> None:
        self._count.setText(str(count))

    def set_name(self, name: str) -> None:
        self._name_label.setText(self._name_fm.elidedText(name.upper(), Qt.ElideRight, 130))
        self._name_label.setToolTip(name)

    def set_context_menu(self, menu) -> None:
        self._menu = menu

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.toggle_requested.emit()
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        if self._menu is not None:
            self._menu.exec(event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)
