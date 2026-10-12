from datetime import date, timedelta
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

from ..utils import SHORT_MONTHS, WEEKDAYS, format_compact, ru_date
from . import theme


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


def magnifier_icon(color: str | None = None, size: int = 18) -> QIcon:
    if color is None:
        color = theme.pal().text2
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


def menu_icon(color: str | None = None, size: int = 18) -> QIcon:
    if color is None:
        color = theme.pal().text2
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


def smooth_path(pts: list[QPointF]) -> QPainterPath:
    """Гладкая монотонная кривая, проходящая ТОЧНО через все точки.

    Использует монотонную кубическую интерполяцию с ограничением касательных
    для предотвращения overshoot (искусственных впадин/выбросов перед пиками).
    """
    path = QPainterPath()
    n = len(pts)
    if n == 0:
        return path
    path.moveTo(pts[0])
    if n == 1:
        return path
    if n == 2:
        path.lineTo(pts[1])
        return path
    
    # Вычисляем наклоны между соседними точками
    slopes = []
    for i in range(n - 1):
        dx = pts[i + 1].x() - pts[i].x()
        dy = pts[i + 1].y() - pts[i].y()
        slopes.append(dy / dx if dx != 0 else 0)
    
    # Вычисляем монотонные касательные для каждой точки
    tangents = [0.0] * n
    tangents[0] = slopes[0]
    tangents[n - 1] = slopes[n - 2]
    
    for i in range(1, n - 1):
        # Если наклоны по обе стороны имеют разные знаки или один равен нулю,
        # устанавливаем касательную в ноль (локальный экстремум)
        if slopes[i - 1] * slopes[i] <= 0:
            tangents[i] = 0
        else:
            # Используем среднее гармоническое для предотвращения overshoot
            tangents[i] = 2.0 / (1.0 / slopes[i - 1] + 1.0 / slopes[i])
    
    # Строим кубические кривые Безье с монотонными касательными
    for i in range(n - 1):
        p1 = pts[i]
        p2 = pts[i + 1]
        dx = (p2.x() - p1.x()) / 3.0
        
        # Контрольные точки на основе монотонных касательных
        c1 = QPointF(p1.x() + dx, p1.y() + dx * tangents[i])
        c2 = QPointF(p2.x() - dx, p2.y() - dx * tangents[i + 1])
        
        path.cubicTo(c1, c2, p2)
    
    return path


def ui_icon(kind: str, color: str | None = None, size: int = 16) -> QIcon:
    if color is None:
        color = theme.pal().text2
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
    elif kind == "chevron_left":
        painter.drawLine(pt(9.8, 3.6), pt(5.6, 8.0))
        painter.drawLine(pt(5.6, 8.0), pt(9.8, 12.4))
    elif kind == "chevron_right":
        painter.drawLine(pt(6.2, 3.6), pt(10.4, 8.0))
        painter.drawLine(pt(10.4, 8.0), pt(6.2, 12.4))
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
    clicked = Signal()

    AXIS_H = 14.0  # высота полосы подписей под графиком (рисуются самим виджетом)
    PAD_L = 6.0
    PAD_R = 6.0
    PAD_T = 5.0
    PAD_B = 6.0

    def __init__(self, height: int = 46, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height + int(self.AXIS_H))
        self.setMinimumWidth(100)
        self.setMouseTracking(True)
        self._values: list[int] = []
        self._values_start: list[int] = []  # Значения в начале анимации
        self._day_labels: list[str] = []
        self._axis: list[tuple[int, str]] = []  # (индекс точки, подпись) — полный набор
        self._hover = -1
        self._hover_x: float | None = None
        self._progress = 1.0
        self._pulse = 1.0
        self._visible: int | None = None
        self._offset = 0
        self._drag_x: float | None = None
        self._drag_offset = 0
        self._press_x: float | None = None
        self._press_pan = False
        self._moved = False

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
        if labels != self._day_labels:
            self._day_labels = list(labels)
            if self._hover >= 0:
                self.update()

    def set_axis(self, indices: list[int], labels: list[str]) -> None:
        """Полный набор подписей (индекс точки → текст). Виджет сам прореживает
        их равномерным шагом под ширину видимого окна и прижимает крайние внутрь."""
        axis = [(int(i), str(t)) for i, t in zip(indices, labels)]
        if axis != self._axis:
            self._axis = axis
            self.update()

    def set_values(self, values: list[int], animate: bool = False) -> None:
        new_vals = [max(0, int(v)) for v in values]
        same_len = len(new_vals) == len(self._values)
        if same_len and new_vals == self._values and not animate:
            return  # ничего не изменилось — не трогаем ни hover, ни перерисовку
        
        # Запоминаем старые значения для плавной интерполяции.
        if animate:
            self._values_start = list(self._values) if self._values else []
            # Если длины разные, дополняем нулями
            if len(self._values_start) < len(new_vals):
                self._values_start.extend([0] * (len(new_vals) - len(self._values_start)))
            elif len(self._values_start) > len(new_vals):
                self._values_start = self._values_start[:len(new_vals)]
        
        self._values = new_vals
        n = len(self._values)
        if self._visible is not None:
            self._visible = max(2, min(self._visible, max(n, 2)))
            # На тике (та же длина) сохраняем позицию прокрутки; иначе — к концу.
            if same_len:
                self._offset = self._clamp_offset(self._offset)
            else:
                self._offset = max(0, n - self._visible)
        if not same_len:
            self._hover = -1
        if animate and n >= 2:
            self._drawn_at_least_once = False
            self._draw_anim.stop()
            self._draw_anim.start()
        else:
            self._progress = 1.0
            self._drawn_at_least_once = True
        self.update()

    def set_view(self, visible: int | None) -> None:
        # Не зажимаем к текущему числу точек (могут ещё не быть загружены);
        # фактическое окно вычисляется в _window() по актуальным данным.
        self._visible = None if visible is None else max(2, int(visible))
        n = len(self._values)
        self._offset = max(0, n - (self._visible or n))
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

    def _plot_h(self) -> float:
        return max(self.height() - self.AXIS_H, 10.0)

    def _x_at(self, i: int, n: int) -> float:
        """X точки с индексом i (в видимом окне) при n точках: первая у левого края, последняя у правого."""
        w = max(self.width(), 10)
        if n <= 1:
            return w / 2.0
        return self.PAD_L + i * (w - self.PAD_L - self.PAD_R) / (n - 1)

    def _points(self) -> list[QPointF]:
        off, vis = self._window()
        vals = self._values[off : off + vis]
        h = self._plot_h()
        n = len(vals)
        if n < 2:
            return []
        
        # Интерполируем значения во время анимации для плавного перехода.
        if self._progress < 1.0 and self._values_start:
            vals_start = self._values_start[off : off + vis]
            # Дополняем нулями если нужно
            if len(vals_start) < len(vals):
                vals_start = vals_start + [0] * (len(vals) - len(vals_start))
            elif len(vals_start) > len(vals):
                vals_start = vals_start[:len(vals)]
            # Интерполируем каждое значение
            vals = [int(v_start + (v_end - v_start) * self._progress) 
                    for v_start, v_end in zip(vals_start, vals)]
        
        vmax = max(max(vals), 1)
        pts = []
        for i, v in enumerate(vals):
            x = self._x_at(i, n)
            y = h - self.PAD_B - (v / vmax) * (h - self.PAD_T - self.PAD_B)
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
        h = self._plot_h()
        anchor = None
        anchor_idx = -1


        if not pts:
            if vis != 1:
                painter.end()
                return
            v = self._values[off]
            # Интерполируем значение для одной точки тоже
            if self._progress < 1.0 and self._values_start and off < len(self._values_start):
                v_start = self._values_start[off]
                v = int(v_start + (v - v_start) * self._progress)
            
            pad_t, pad_b = 5.0, 6.0
            bw = min(46.0, w * 0.25)
            x = (w - bw) / 2
            bh = (h - pad_t - pad_b) if v > 0 else 3.0
            y = h - pad_b - bh
            painter.save()
            painter.setClipRect(QRectF(0, 0, w * self._progress + 0.5, h))
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, theme.accent_alpha(int(min(255, theme.pal().chart_fill_top + 15) * self._pulse)))
            grad.setColorAt(1.0, theme.color("chart_fill_bottom"))
            painter.setPen(QPen(theme.color("chart_line"), 2))
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(QRectF(x, y, bw, bh), 6, 6)
            painter.restore()
            anchor = QPointF(x + bw / 2, y)
            anchor_idx = off
        else:
            path = smooth_path(pts)

            fill = QPainterPath(path)
            fill.lineTo(pts[-1].x(), h)
            fill.lineTo(pts[0].x(), h)
            fill.closeSubpath()

            painter.save()
            painter.setClipRect(QRectF(0, 0, w * self._progress + 0.5, h))
            grad = QLinearGradient(0, 0, 0, h)
            top_alpha = int(theme.pal().chart_fill_top * self._pulse)
            grad.setColorAt(0.0, theme.accent_alpha(top_alpha))
            grad.setColorAt(1.0, theme.color("chart_fill_bottom"))
            painter.fillPath(fill, QBrush(grad))
            painter.setPen(QPen(theme.color("chart_line"), 2))
            painter.drawPath(path)
            painter.restore()
            if 0 <= self._hover < len(pts):
                anchor = pts[self._hover]
                anchor_idx = off + self._hover

        n_total = len(self._values)
        # Убрали ползунок (scrollbar) — на мини-графиках карточек он сливается с графиком
        # и не нужен, т.к. перетаскивание работает и без визуального индикатора.

        # Подписи оси — прореживаем равномерным шагом под ширину окна,
        # крайние прижимаем внутрь, чтобы текст не срезался у границы.
        if self._axis and vis > 0:
            font = QFont(self.font())
            font.setPointSizeF(7.5)
            painter.setFont(font)
            painter.setPen(theme.color("chart_dim"))
            fm = QFontMetrics(font)
            visible_axis = [(idx, text) for idx, text in self._axis if 0 <= idx - off < vis and text]
            if visible_axis:
                slot_w = (w - self.PAD_L - self.PAD_R) / max(vis, 1)
                label_w = max((fm.horizontalAdvance(t) for _i, t in visible_axis), default=20) + 8
                step = max(1, int(ceil(label_w / max(slot_w, 1.0))))
                # Собираем индексы видимых подписей с учётом прореживания
                visible_indices = list(range(0, len(visible_axis), step))
                for enum_k, k in enumerate(visible_indices):
                    idx, text = visible_axis[k]
                    local = idx - off
                    x = self._x_at(local, vis) if vis > 1 else w / 2.0
                    # Используем RangeChart._axis_label_rect для правильного размещения
                    rect, align = RangeChart._axis_label_rect(
                        enum_k, len(visible_indices), x, w,
                        self.PAD_L, self.PAD_R, 60.0, self.AXIS_H, h
                    )
                    painter.drawText(rect, align, text)

        if anchor is not None and self._progress >= 0.99 and anchor_idx >= 0:
            p = anchor
            painter.setPen(QPen(theme.color("point_ring"), 1.5))
            painter.setBrush(theme.color("chart_line"))
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
            painter.setPen(QPen(theme.color("tooltip_border"), 1))
            painter.setBrush(theme.color("tooltip_bg"))
            painter.drawRoundedRect(QRectF(bx, by, tw, th), 6, 6)
            painter.setPen(theme.color("tooltip_text"))
            painter.drawText(QRectF(bx, by, tw, th), Qt.AlignCenter, text)
        painter.end()

    def _index_at_x(self, x: float) -> int:
        """Ближайшая точка к x (в координатах видимого окна)."""
        _off, vis = self._window()
        if vis <= 1:
            return 0 if vis == 1 else -1
        span = max(self.width(), 10) - self.PAD_L - self.PAD_R
        ratio = min(max((x - self.PAD_L) / max(span, 1.0), 0.0), 1.0)
        return min(max(int(round(ratio * (vis - 1))), 0), vis - 1)

    def mouseMoveEvent(self, event) -> None:
        off, vis = self._window()
        n = len(self._values)
        x = event.position().x()
        if self._drag_x is not None and n > vis:
            if abs(x - self._drag_x) > 3:
                self._moved = True
            ppp = max(self.width(), 10) / vis
            delta = int(round((self._drag_x - x) / ppp))
            new_off = self._clamp_offset(self._drag_offset + delta)
            if new_off != self._offset:
                self._offset = new_off
                self._hover = -1
                self._emit_view()
                self.update()
            return
        if self._press_x is not None and abs(x - self._press_x) > 3:
            self._moved = True
        self._hover_x = x
        if self._progress < 0.99:
            return
        idx = self._index_at_x(x)
        if idx != self._hover:
            self._hover = idx
            self.update()

    def mousePressEvent(self, event) -> None:
        off, vis = self._window()
        if event.button() == Qt.LeftButton:
            self._press_x = event.position().x()
            self._moved = False
            self._press_pan = len(self._values) > vis
            if self._press_pan:
                self._drag_x = event.position().x()
                self._drag_offset = self._offset
                self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        was_click = (
            event.button() == Qt.LeftButton
            and self._press_x is not None
            and not self._moved
        )
        self._drag_x = None
        self._press_x = None
        self._press_pan = False
        self.setCursor(Qt.ArrowCursor)
        if was_click:
            self.clicked.emit()
            event.accept()
            return
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
        self._hover_x = None
        if self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(event)


class RangeChart(QWidget):
    selection_changed = Signal(object)

    PAD_L = 12.0  # Половина самой широкой подписи оси (~22px) помещается в поле
    PAD_R = 12.0
    PAD_T = 16.0  # Увеличен отступ сверху, чтобы график не обрезался
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
        # Явные подписи (фиксированные периоды: часы/дни/месяцы) — без автобакетов.
        self._explicit: tuple[list[str], list[str]] | None = None
        # Timeline mode: работа с почасовыми данными и непрерывным зумом
        self._timeline = None  # TimelineData | None
        self._timeline_mode = False

    def set_data(self, values: list[int], dates: list[date]) -> None:
        self.set_days(values, dates)

    def set_days(self, values: list[int], dates: list[date]) -> None:
        self._leave_timeline()
        self._unit = "days"
        self._min_visible = 14.0  # Увеличен с 7 до 14, чтобы избежать "дёрганья" при глубоком зуме
        self._explicit = None
        self._days = [max(0, int(v)) for v in values]
        self._dates = list(dates)
        self._sel = None
        self._sel_float = None
        self.set_window_days(None)

    def set_hours(self, values: list[int]) -> None:
        labels = [f"{i:02d}" for i in range(24)]
        tips = [f"{i:02d}:00–{(i + 1) % 24:02d}:00" for i in range(24)]
        self.set_series(values, labels, tips, unit="hours", min_visible=4.0)

    def set_series(
        self,
        values: list[int],
        axis_labels: list[str],
        tip_labels: list[str],
        unit: str = "days",
        min_visible: float = 7.0,
    ) -> None:
        """Ряд с готовыми подписями: одна точка = один бакет (час/день/месяц)."""
        # Возврат из режима «Всё время»: иначе бакеты продолжают строиться
        # по timeline и фиксированный период рисует чужие данные.
        self._leave_timeline()
        self._unit = unit
        self._min_visible = float(min_visible)
        self._days = [max(0, int(v)) for v in values]
        self._dates = []
        n = len(self._days)
        axis = list(axis_labels)[:n] + [""] * max(0, n - len(axis_labels))
        tips = list(tip_labels)[:n] + [""] * max(0, n - len(tip_labels))
        self._explicit = (axis, tips)
        self._sel = None
        self._sel_float = None
        self.set_window_days(None)
    
    def _leave_timeline(self) -> None:
        """Выход из режима «Всё время» при переходе к фиксированному ряду."""
        self._timeline = None
        self._timeline_mode = False

    def set_timeline(self, timeline) -> None:
        """Устанавливает timeline mode для непрерывного зума от лет до часов.
        
        Args:
            timeline: экземпляр TimelineData с почасовыми данными
        """
        self._timeline = timeline
        self._timeline_mode = True
        self._unit = "timeline"
        self._min_visible = 1.0  # Минимум 1 день
        self._explicit = None
        self._hover = -1
        
        # В timeline mode работаем в координатах ДНЕЙ (для совместимости)
        # Почасовые данные загружаются динамически при зуме
        total_days = timeline.total_hours() / 24.0
        
        # Начальное окно: показываем всё
        self._offset = 0.0
        self._visible = total_days
        self._sel = None
        self._sel_float = None
        
        self._rebuild_buckets()
        self.update()

    def unit(self) -> str:
        return self._unit

    def bucket_tips(self) -> list[str]:
        """Подписи-тултипы всех бакетов (для итогов выделения)."""
        return [b[3] for b in self._buckets]

    def day_tip(self, i: int) -> str:
        """Подпись для элемента ряда с индексом i (час / день / месяц) — независимо от бакетов."""
        if self._explicit is not None:
            tips = self._explicit[1]
            return tips[i] if 0 <= i < len(tips) else ""
        if self._timeline_mode and self._timeline is not None:
            start = getattr(self._timeline, "_start", None)
            if start is not None:
                d = start + timedelta(days=int(i))
                return f"{WEEKDAYS[d.weekday()]}, {ru_date(d)}"
            return ""
        if self._unit == "hours":
            return f"{i:02d}:00–{(i + 1) % 24:02d}:00"
        if 0 <= i < len(self._dates):
            d = self._dates[i]
            text = f"{WEEKDAYS[d.weekday()]}, {ru_date(d)}"
            if self._dates and self._dates[0].year != self._dates[-1].year:
                text += f" {d.year}"
            return text
        return ""

    def _n(self) -> int:
        if self._timeline_mode and self._timeline is not None:
            # В timeline mode возвращаем количество дней (для совместимости)
            return self._timeline.total_hours() // 24
        return len(self._days)

    def selection(self) -> tuple[int, int] | None:
        return self._sel

    def series_value(self, i: int) -> int:
        """Значение ряда для индекса точки (час/день/месяц) в текущем режиме.

        В режиме «Всё время» значения берутся из timeline, а не из self._days
        (там их нет) — иначе итоги по выделению всегда равны нулю.
        """
        if self._timeline_mode and self._timeline is not None:
            start = getattr(self._timeline, "_start", None)
            if start is None:
                return 0
            return int(self._timeline.get_day_value(start + timedelta(days=int(i))))
        if 0 <= i < len(self._days):
            return int(self._days[i])
        return 0

    def series_total(self, start: int, end: int) -> int:
        """Сумма значений ряда по индексам [start, end] включительно."""
        if end < start:
            return 0
        return sum(self.series_value(i) for i in range(int(start), int(end) + 1))

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
            self._buckets = []
            self._vis_buckets = []
            self._vis_pts = []
            self.update()
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
        # Если данных меньше минимального окна — показываем все точки на всю ширину,
        # а не прижимаем их к левому краю.
        lo = min(self._min_visible, float(max(n, 1)))
        self._visible = min(max(self._visible, lo), float(max(n, 1)))
        self._offset = min(max(self._offset, 0.0), max(0.0, n - self._visible))

    def _rebuild_buckets(self) -> None:
        # Timeline mode: динамическая бакетизация час→день→неделя→месяц
        if self._timeline_mode and self._timeline is not None:
            self._rebuild_timeline_buckets()
            return
        
        n = self._n()
        if n == 0:
            self._buckets = []
            return
        buckets: list[tuple[int, int, str, str, int]] = []
        if self._explicit is not None:
            axis, tips = self._explicit
            for i, v in enumerate(self._days):
                buckets.append((i, i + 1, axis[i], tips[i], v))
            self._buckets = buckets
            return
        if self._unit == "hours":
            for i, v in enumerate(self._days):
                label = f"{i:02d}:00"
                buckets.append((i, i + 1, f"{i:02d}", label, v))
            self._buckets = buckets
            return
        vis = self._visible
        # Изменены пороги для более плавных переходов и меньшего "дёрганья"
        # день: до 60 дней (2 месяца)
        # неделя: 60-365 дней (2 месяца - 1 год)
        # месяц: больше года
        if vis <= 60:
            unit = "day"
        elif vis <= 365:
            unit = "week"
        else:
            unit = "month"
        
        buckets: list[tuple[int, int, str, str, int]] = []
        if unit == "day":
            for i, v in enumerate(self._days):
                d = self._dates[i]
                axis = f"{d.day} {SHORT_MONTHS[d.month - 1]}"
                buckets.append((i, i + 1, axis, ru_date(d), v))
        elif unit == "week":
            for i in range(0, n, 7):
                end = min(i + 7, n)
                chunk = self._days[i:end]
                d0 = self._dates[i]
                d1 = self._dates[end - 1]
                axis = f"{d0.day} {SHORT_MONTHS[d0.month - 1]}"
                if d0.month == d1.month:
                    tip = f"{d0.day}–{d1.day} {SHORT_MONTHS[d0.month - 1]}"
                else:
                    tip = f"{d0.day} {SHORT_MONTHS[d0.month - 1]}–{d1.day} {SHORT_MONTHS[d1.month - 1]}"
                buckets.append((i, end, axis, tip, sum(chunk)))
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
    
    def _rebuild_timeline_buckets(self) -> None:
        """Динамическая бакетизация для timeline mode: час→день→неделя→месяц.
        
        Вся логика в координатах ДНЕЙ для совместимости с отрисовкой.
        При глубоком зуме (<1 день) подгружаем почасовые данные.
        """
        from datetime import datetime, timedelta
        
        timeline = self._timeline
        if timeline is None:
            self._buckets = []
            return
        
        # Определяем уровень детализации по масштабу зума (visible в днях)
        vis_days = self._visible
        
        # Пороги для переключения уровней (в днях):
        # - час: до 2 дней (для плавного перехода)
        # - день: 2-60 дней
        # - неделя: 60-365 дней
        # - месяц: больше года
        
        if vis_days <= 2:
            level = "hour"
        elif vis_days <= 60:
            level = "day"
        elif vis_days <= 365:
            level = "week"
        else:
            level = "month"
        
        # Вычисляем видимый диапазон (не выходя за последний день данных:
        # прежний «+1» без ограничения добавлял лишний пустой бакет).
        total_days = timeline.total_hours() // 24
        start_day_idx = int(self._offset)
        end_day_idx = min(int(self._offset + self._visible) + 1, total_days)
        
        # Подгружаем почасовые данные для видимого диапазона (если нужны)
        if level == "hour":
            start_hour = int(self._offset * 24)
            end_hour = int((self._offset + self._visible) * 24)
            timeline.load_hours_range(start_hour, end_hour)
        
        buckets = []
        
        if level == "hour":
            # Почасовая разбивка - создаём по 24 бакета на каждый день
            # Координаты в ДОЛЯХ ДНЯ для плавной отрисовки
            for day_idx in range(start_day_idx, end_day_idx):
                day = timeline._start + timedelta(days=day_idx)
                
                for hour_of_day in range(24):
                    hour_idx = day_idx * 24 + hour_of_day
                    if hour_idx >= timeline.total_hours():
                        break
                    
                    value = timeline.get_value_at_hour(hour_idx)
                    axis_label = f"{hour_of_day:02d}"
                    tip_label = f"{ru_date(day)}, {hour_of_day:02d}:00"
                    
                    # Бакет в координатах дней: день.часть
                    bucket_start = day_idx + hour_of_day / 24.0
                    bucket_end = day_idx + (hour_of_day + 1) / 24.0
                    buckets.append((bucket_start, bucket_end, axis_label, tip_label, value))
        
        elif level == "day":
            # Дневная разбивка
            start_day_idx = int(self._offset)
            end_day_idx = min(int(self._offset + self._visible) + 1, total_days)
            
            for day_idx in range(start_day_idx, end_day_idx):
                day = timeline._start + timedelta(days=day_idx)
                value = timeline.get_day_value(day)
                
                axis_label = f"{day.day} {SHORT_MONTHS[day.month - 1]}"
                tip_label = ru_date(day)
                
                buckets.append((day_idx, day_idx + 1, axis_label, tip_label, value))
        
        elif level == "week":
            # Недельная разбивка
            start_day_idx = int(self._offset)
            end_day_idx = min(int(self._offset + self._visible) + 1, total_days)
            
            # Группируем по 7 дней
            for week_start_idx in range(start_day_idx, end_day_idx, 7):
                week_end_idx = min(week_start_idx + 7, total_days)
                
                # Суммируем дни недели
                week_sum = 0
                for day_idx in range(week_start_idx, week_end_idx):
                    day = timeline._start + timedelta(days=day_idx)
                    week_sum += timeline.get_day_value(day)
                
                d0 = timeline._start + timedelta(days=week_start_idx)
                d1 = timeline._start + timedelta(days=week_end_idx - 1)
                
                axis_label = f"{d0.day} {SHORT_MONTHS[d0.month - 1]}"
                if d0.month == d1.month:
                    tip_label = f"{d0.day}–{d1.day} {SHORT_MONTHS[d0.month - 1]}"
                else:
                    tip_label = f"{d0.day} {SHORT_MONTHS[d0.month - 1]}–{d1.day} {SHORT_MONTHS[d1.month - 1]}"
                
                buckets.append((week_start_idx, week_end_idx, axis_label, tip_label, week_sum))
        
        else:  # month
            # Месячная разбивка
            start_day_idx = int(self._offset)
            end_day_idx = min(int(self._offset + self._visible) + 1, total_days)
            
            # Группируем по месяцам
            current_day_idx = start_day_idx
            while current_day_idx < end_day_idx:
                current_date = timeline._start + timedelta(days=current_day_idx)
                year, month = current_date.year, current_date.month
                
                # Находим все дни этого месяца в видимом диапазоне
                month_start_idx = current_day_idx
                month_end_idx = current_day_idx
                month_sum = 0
                
                while month_end_idx < end_day_idx:
                    check_date = timeline._start + timedelta(days=month_end_idx)
                    if (check_date.year, check_date.month) != (year, month):
                        break
                    month_sum += timeline.get_day_value(check_date)
                    month_end_idx += 1
                
                label = f"{SHORT_MONTHS[month - 1]} {year}"
                buckets.append((month_start_idx, month_end_idx, label, label, month_sum))
                
                current_day_idx = month_end_idx
        
        self._buckets = buckets

    def _plot(self) -> tuple[float, float, float, float]:
        w = max(self.width(), 20)
        h = max(self.height(), 20)
        return self.PAD_L, self.PAD_T, w - self.PAD_L - self.PAD_R, h - self.PAD_T - self.PAD_B

    def _edge_halves(self) -> tuple[float, float]:
        """Половины ширин крайних видимых бакетов (в днях).

        Центр первого видимого бакета отображается на левый край плота, центр
        последнего — на правый: линия и выделение никогда не выходят за график.
        """
        if not self._buckets:
            return 0.5, 0.5
        lo = self._offset
        hi = self._offset + self._visible
        left = right = None
        for start, end, _a, _t, _v in self._buckets:
            if left is None and end > lo:
                left = (end - start) / 2.0
            if start < hi:
                right = (end - start) / 2.0
        return (left if left is not None else 0.5), (right if right is not None else 0.5)

    def _day_to_x(self, di: float) -> float:
        pad_l, _pad_t, inner_w, _inner_h = self._plot()
        lh, rh = self._edge_halves()
        span = self._visible - lh - rh
        if span <= 1e-6:
            return pad_l + inner_w / 2.0
        return pad_l + (di - self._offset - lh) / span * inner_w

    def _x_to_day(self, x: float) -> float:
        pad_l, _pad_t, inner_w, _inner_h = self._plot()
        lh, rh = self._edge_halves()
        span = self._visible - lh - rh
        if span <= 1e-6:
            return self._offset + self._visible / 2.0
        return self._offset + lh + (x - pad_l) / max(inner_w, 1.0) * span

    @staticmethod
    def _axis_label_rect(k: int, count: int, x: float, widget_w: float, 
                         pad_l: float, pad_r: float, label_w: float = 90.0, 
                         label_h: float = 16.0, y_offset: float = 0.0) -> tuple[QRectF, int]:
        """Вычисляет прямоугольник и alignment для подписи оси.
        
        Крайние подписи (первая и последняя видимые) прижимаются внутрь области графика,
        чтобы текст не обрезался у границы виджета. Средние подписи центрируются по своей
        x-координате.
        
        Args:
            k: индекс подписи в списке видимых подписей (0-based)
            count: общее количество видимых подписей
            x: x-координата центра точки данных
            widget_w: ширина виджета
            pad_l: левый отступ графика
            pad_r: правый отступ графика
            label_w: ширина прямоугольника подписи (по умолчанию 90)
            label_h: высота прямоугольника подписи (по умолчанию 16)
            y_offset: y-координата верхнего края подписи
            
        Returns:
            tuple[QRectF, Qt.Alignment]: прямоугольник и флаг выравнивания
        """
        if count == 0:
            return QRectF(0, y_offset, label_w, label_h), Qt.AlignCenter
        
        # Первая подпись: прижать к левому краю
        if k == 0:
            rect = QRectF(pad_l - 2, y_offset, label_w, label_h)
            align = Qt.AlignLeft | Qt.AlignVCenter
        # Последняя подпись: прижать к правому краю
        elif k == count - 1:
            rect = QRectF(widget_w - pad_r - label_w + 2, y_offset, label_w, label_h)
            align = Qt.AlignRight | Qt.AlignVCenter
        # Средние подписи: центрировать, но не выходить за границы виджета
        else:
            left = x - label_w / 2
            # Ограничиваем, чтобы не выйти за границы виджета
            left = max(0, min(left, widget_w - label_w))
            rect = QRectF(left, y_offset, label_w, label_h)
            align = Qt.AlignCenter
        
        return rect, align

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
        # Клип чуть шире плота, чтобы линия толщиной 2px у крайних точек не срезалась.
        painter.setClipRect(QRectF(pad_l - 3, 0, inner_w + 6, h))

        band = self._sel_band_px()

        if len(pts) >= 2:
            path = smooth_path(pts)
            fill = QPainterPath(path)
            fill.lineTo(pts[-1].x(), pad_t + inner_h)
            fill.lineTo(pts[0].x(), pad_t + inner_h)
            fill.closeSubpath()
            grad = QLinearGradient(0, pad_t, 0, pad_t + inner_h)
            grad.setColorAt(0.0, theme.color("chart_fill_top"))
            grad.setColorAt(1.0, theme.color("chart_fill_bottom"))
            painter.fillPath(fill, QBrush(grad))
            painter.setPen(QPen(theme.color("chart_line"), 2))
            painter.drawPath(path)
        elif len(pts) == 1:
            # Одна точка — рисуем её как столбик по центру, чтобы график не выглядел пустым.
            p = pts[0]
            bw = min(46.0, inner_w * 0.25)
            top = p.y() if vis_buckets[0][4] > 0 else pad_t + inner_h - 3.0
            grad = QLinearGradient(0, pad_t, 0, pad_t + inner_h)
            grad.setColorAt(0.0, theme.accent_alpha(min(255, theme.pal().chart_fill_top + 15)))
            grad.setColorAt(1.0, theme.color("chart_fill_bottom"))
            painter.setPen(QPen(theme.color("chart_line"), 2))
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(QRectF(p.x() - bw / 2, top, bw, pad_t + inner_h - top), 6, 6)

        if band is not None:
            xs = max(band[0], pad_l)
            xe = min(band[1], pad_l + inner_w)
            # Затемняем невыделенные области вместо подсветки выделенной
            dim_color = theme.color("dim")
            if xs > pad_l:
                painter.fillRect(QRectF(pad_l, pad_t, xs - pad_l, inner_h), dim_color)
            if xe < pad_l + inner_w:
                painter.fillRect(QRectF(xe, pad_t, pad_l + inner_w - xe, inner_h), dim_color)
            # Вертикальные линии и ручки выделения
            painter.setPen(QPen(theme.color("chart_line"), 1.5))
            painter.drawLine(QPointF(xs, pad_t), QPointF(xs, pad_t + inner_h))
            painter.drawLine(QPointF(xe, pad_t), QPointF(xe, pad_t + inner_h))
            mid_y = pad_t + inner_h / 2
            painter.setPen(QPen(theme.color("point_ring"), 1))
            painter.setBrush(theme.color("chart_line"))
            painter.drawRoundedRect(QRectF(xs - 3, mid_y - 9, 6, 18), 3, 3)
            painter.drawRoundedRect(QRectF(xe - 3, mid_y - 9, 6, 18), 3, 3)
        painter.restore()

        if vis_buckets:
            font = QFont(self.font())
            font.setPointSizeF(7.5)
            painter.setFont(font)
            painter.setPen(theme.color("chart_dim"))
            fm = QFontMetrics(font)
            label_gap = 2.0
            label_y = h - self.PAD_B + 4
            # Кандидаты: реальные прямоугольники подписей по центрам точек.
            cands: list[tuple[int, QRectF]] = []
            for k, bucket in enumerate(vis_buckets):
                text = bucket[2]
                if not text:
                    continue
                x = self._day_to_x((bucket[0] + bucket[1]) / 2.0)
                if not (pad_l - 4 <= x <= pad_l + inner_w + 4):
                    continue
                lw = float(fm.horizontalAdvance(text)) + 2.0
                left = max(0.0, min(x - lw / 2.0, w - lw))
                cands.append((k, QRectF(left, label_y, lw, 16.0)))
            if cands:
                n_c = len(cands)
                if n_c == 1:
                    sel = [0]
                else:
                    # Равномерный шаг по фактическому расстоянию между точками,
                    # первая и последняя подписи включаются всегда.
                    slot = (cands[-1][1].center().x() - cands[0][1].center().x()) / (n_c - 1)
                    max_w = max(r.width() for _, r in cands)
                    step = max(1, int(ceil((max_w + label_gap) / max(slot, 1.0))))
                    sel = sorted(set(list(range(0, n_c, step)) + [0, n_c - 1]))
                drawn: list[int] = []
                for i in sel:
                    rect = cands[i][1]
                    if drawn and rect.left() < cands[drawn[-1]][1].right() + label_gap:
                        # Последняя подпись важнее соседней средней: уступаем ей место.
                        if i == sel[-1] and len(drawn) > 1:
                            drawn.pop()
                        else:
                            continue
                    drawn.append(i)
                # Страховочный проход: гарантируем отсутствие пересечений.
                final: list[int] = []
                for i in drawn:
                    rect = cands[i][1]
                    if final and rect.left() < cands[final[-1]][1].right() + label_gap:
                        if i == drawn[-1] and len(final) > 1:
                            final.pop()
                        else:
                            continue
                    final.append(i)
                for i in final:
                    painter.drawText(cands[i][1], Qt.AlignCenter, vis_buckets[cands[i][0]][2])

        if 0 <= self._hover < len(vis_buckets):
            p = pts[self._hover]
            painter.setPen(QPen(theme.color("point_ring"), 1.5))
            painter.setBrush(theme.color("chart_line"))
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
            painter.setPen(QPen(theme.color("tooltip_border"), 1))
            painter.setBrush(theme.color("tooltip_bg"))
            painter.drawRoundedRect(QRectF(bx, by, tw, th), 6, 6)
            painter.setPen(theme.color("tooltip_text"))
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
        lo = min(self._min_visible, float(n))
        new_vis = min(max(self._visible * factor, lo), float(n))
        if new_vis == self._visible:
            return
        x = event.position().x()
        anchor = self._x_to_day(x)
        pad_l, _t, inner_w, _h = self._plot()
        ratio = min(max((x - pad_l) / max(inner_w, 1.0), 0.0), 1.0)
        self._visible = new_vis
        self._offset = anchor - ratio * new_vis
        self._clamp_view()
        
        # В timeline mode подгружаем данные при глубоком зуме
        if self._timeline_mode and self._timeline is not None and new_vis <= 3:
            # Подгружаем почасовые данные для видимого диапазона
            start_hour = int(self._offset * 24)
            end_hour = int((self._offset + self._visible) * 24)
            self._timeline.load_hours_range(start_hour, end_hour)
        
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
        shadow.setColor(theme.color("shadow"))
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
        self.chart.clicked.connect(lambda: self.clicked.emit(self.app_id))
        layout.addWidget(self.chart)

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

    def set_axis(self, indices: list[int], labels: list[str]) -> None:
        """Подписи под мини-графиком: labels[k] рисуется под точкой indices[k]."""
        self.chart.set_axis(indices, labels)

    def set_chart_window(self, visible: int | None) -> None:
        """Оконный режим мини-графика: показываем не больше visible точек,
        остальное листается перетаскиванием. None — показать всё."""
        self.chart.set_view(visible)

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
        """Подписи точек для всплывающей подсказки (по индексу точки)."""
        self.chart.set_days(labels)

    def enterEvent(self, event) -> None:
        self._animate_shadow(theme.color("shadow_hover"), 32)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate_shadow(theme.color("shadow"), 22)
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
        track = _mix(theme.color("toggle_off"), theme.color("accent"), self._t)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0.5, 0.5, 45, 25), 12.5, 12.5)
        knob_x = 3.0 + self._t * 20.0
        painter.setBrush(theme.color("knob"))
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
        icon_label.setPixmap(ui_icon("folder", None, 16).pixmap(QSize(16, 16)))
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
