from datetime import date, timedelta

from PySide6.QtCore import QEasingCurve, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..db import Database
from ..tracker import Tracker
from ..utils import format_compact, ru_date
from .widgets import MiniChart, pixmap_from_png, rounded_pixmap, ui_icon

PERIODS = [
    ("Сегодня", 1, "СЕГОДНЯ"),
    ("7 дней", 7, "7 ДНЕЙ"),
    ("30 дней", 30, "30 ДНЕЙ"),
    ("Всё время", 0, "ВСЁ ВРЕМЯ"),
]


class StatsPanel(QFrame):
    close_requested = Signal()
    delete_requested = Signal(int)

    def __init__(
        self,
        db: Database,
        tracker: Tracker,
        app_id: int,
        name: str,
        exe_path: str,
        icon_bytes: bytes | None,
        start_period_idx: int = 1,
        first_day: date | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("modalPanel")
        self.setFixedSize(620, 620)

        self._app_id = app_id
        self._today = date.today()
        self._big_value = 0
        self._big_anim = None
        self._period_idx = max(0, min(start_period_idx, len(PERIODS) - 1))
        self._cur_labels: list[str] = []

        today_str = self._today.isoformat()
        history: dict[str, int] = {}
        for _id, day, secs in db.query_stats():
            if _id == app_id and day != today_str:
                history[day] = history.get(day, 0) + secs
        self._history = history
        self._today_live = db.get_day_stats(today_str).get(app_id, 0) + tracker.pending_seconds(
            app_id
        )
        self._hours = db.get_hours(app_id, today_str)

        if first_day is None:
            past = [date.fromisoformat(d) for d in history]
            first_day = min(past) if past else self._today
        self._first_day = min(first_day, self._today)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(12)
        icon = QLabel()
        icon.setFixedSize(48, 48)
        pm = pixmap_from_png(icon_bytes)
        if pm is not None:
            icon.setPixmap(rounded_pixmap(pm, 48, 10))
        top.addWidget(icon)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        name_label = QLabel(name)
        name_label.setObjectName("modalTitle")
        path_label = QLabel()
        path_label.setObjectName("pathLabel")
        fm = QFontMetrics(path_label.font())
        path_label.setText(fm.elidedText(exe_path, Qt.ElideMiddle, 400))
        path_label.setToolTip(exe_path)
        titles.addWidget(name_label)
        titles.addWidget(path_label)
        top.addLayout(titles)
        top.addStretch(1)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("deleteBtn")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close_requested)
        top.addWidget(close_btn)
        layout.addLayout(top)

        periods_row = QHBoxLayout()
        periods_row.setSpacing(2)
        self._period_group = QButtonGroup(self)
        self._period_group.setExclusive(True)
        for idx, (label, _days, _cap) in enumerate(PERIODS):
            btn = QPushButton(label)
            btn.setObjectName("periodBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            if idx == self._period_idx:
                btn.setChecked(True)
            self._period_group.addButton(btn, idx)
            periods_row.addWidget(btn)
        periods_row.addStretch(1)
        self._period_group.idClicked.connect(self._on_period_clicked)
        layout.addLayout(periods_row)

        big_box = QVBoxLayout()
        big_box.setSpacing(2)
        self._big = QLabel("0м")
        self._big.setObjectName("statBig")
        self._big.setAlignment(Qt.AlignCenter)
        self._big_caption = QLabel("")
        self._big_caption.setObjectName("statLabel")
        self._big_caption.setAlignment(Qt.AlignCenter)
        big_box.addWidget(self._big)
        big_box.addWidget(self._big_caption)
        layout.addLayout(big_box)

        self.chart = MiniChart(150)
        self.chart.view_changed.connect(self._on_chart_view)
        layout.addWidget(self.chart)

        axis = QHBoxLayout()
        self._ax_first = QLabel("")
        self._ax_mid = QLabel("")
        self._ax_last = QLabel("")
        for lbl in (self._ax_first, self._ax_mid, self._ax_last):
            lbl.setObjectName("mutedLabel")
        self._ax_mid.setAlignment(Qt.AlignCenter)
        self._ax_last.setAlignment(Qt.AlignRight)
        axis.addWidget(self._ax_first)
        axis.addWidget(self._ax_mid, 1)
        axis.addWidget(self._ax_last)
        layout.addLayout(axis)

        layout.addStretch(1)

        bottom = QHBoxLayout()
        delete_btn = QPushButton("Удалить приложение")
        delete_btn.setObjectName("danger")
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setIcon(ui_icon("trash", "#f87171"))
        delete_btn.setIconSize(QSize(16, 16))
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(app_id))
        bottom.addWidget(delete_btn)
        bottom.addStretch(1)
        ok_btn = QPushButton("Закрыть")
        ok_btn.setObjectName("primary")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.clicked.connect(self.close_requested)
        bottom.addWidget(ok_btn)
        layout.addLayout(bottom)

        self._set_period(self._period_idx, animate=False)

    def _series_for(self, days: int) -> tuple[list[int], list[str]]:
        if days <= 0:
            n = (self._today - self._first_day).days + 1
        else:
            n = days
        series: list[int] = []
        labels: list[str] = []
        for i in range(n - 1, -1, -1):
            d = self._today - timedelta(days=i)
            if d == self._today:
                value = self._today_live
            else:
                value = self._history.get(d.isoformat(), 0)
            series.append(value)
            labels.append(ru_date(d))
        return series, labels

    def _on_period_clicked(self, idx: int) -> None:
        if idx == self._period_idx:
            return
        self._period_idx = idx
        self._set_period(idx, animate=True)

    def _set_period(self, idx: int, animate: bool) -> None:
        _label, days, caption = PERIODS[idx]

        if idx == 0:
            series = list(self._hours)
            day_labels = [f"{h:02d}:00" for h in range(24)]
        else:
            series, day_labels = self._series_for(days)

        total = sum(series)
        self._big_caption.setText(f"АКТИВНО ЗА {caption}")
        if animate:
            self._animate_big(total)
        else:
            if self._big_anim is not None:
                self._big_anim.stop()
            self._big_value = total
            self._big.setText(format_compact(total))

        self._cur_labels = day_labels
        self.chart.set_days(day_labels)
        self.chart.set_values(series, animate=animate)
        self.chart.set_view(30 if (idx == 3 and len(series) > 60) else None)
        self._on_chart_view(*self.chart._window())

    def _on_chart_view(self, off: int, vis: int) -> None:
        labels = self._cur_labels
        if not labels:
            return
        off = min(max(off, 0), max(0, len(labels) - 1))
        last = min(off + vis - 1, len(labels) - 1)
        self._ax_first.setText(labels[off])
        self._ax_mid.setText(labels[off + (last - off) // 2] if last - off >= 2 else "")
        self._ax_last.setText(labels[last])

    def _animate_big(self, value: int) -> None:
        if self._big_anim is not None:
            self._big_anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(self._big_value)
        anim.setEndValue(value)
        anim.setDuration(350)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda v: self._big.setText(format_compact(v)))
        anim.finished.connect(lambda: setattr(self, "_big_value", value))
        self._big_anim = anim
        anim.start()
