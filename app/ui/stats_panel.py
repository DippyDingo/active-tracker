from datetime import date, timedelta

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation, Signal
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
from .widgets import MiniChart, pixmap_from_png, rounded_pixmap

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

        today_str = self._today.isoformat()
        history: dict[str, int] = {}
        for _id, day, secs in db.query_stats():
            if _id == app_id and day != today_str:
                history[day] = history.get(day, 0) + secs
        self._history = history
        self._today_live = db.get_day_stats(today_str).get(app_id, 0) + tracker.pending_seconds(
            app_id
        )

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
        delete_btn = QPushButton("🗑  Удалить приложение")
        delete_btn.setObjectName("danger")
        delete_btn.setCursor(Qt.PointingHandCursor)
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
            start_dates = [date.fromisoformat(d) for d in self._history]
            start_dates.append(self._today)
            start = min(start_dates)
            n = (self._today - start).days + 1
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

        self.chart.set_days(day_labels)
        self.chart.set_values(series, animate=animate)

        n = len(series)
        self._ax_first.setText(day_labels[0])
        self._ax_mid.setText(day_labels[n // 2] if n > 2 else "")
        self._ax_last.setText(day_labels[-1])

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
