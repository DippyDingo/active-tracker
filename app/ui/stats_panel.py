from datetime import date, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
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
        period_label: str,
        period_seconds: int,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("modalPanel")
        self.setFixedSize(620, 600)

        today = date.today()
        today_str = today.isoformat()
        yesterday = (today - timedelta(days=1)).isoformat()
        today_live = db.get_day_stats(today_str).get(app_id, 0) + tracker.pending_seconds(app_id)

        series = [0] * 14
        for _id, day, secs in db.query_stats((today - timedelta(days=13)).isoformat(), yesterday):
            if _id != app_id:
                continue
            delta = (today - date.fromisoformat(day)).days
            if 1 <= delta <= 13:
                series[13 - delta] += secs
        series[13] += today_live

        week_sum = sum(series[7:])
        month_sum = today_live
        for _id, _day, secs in db.query_stats((today - timedelta(days=29)).isoformat(), yesterday):
            if _id == app_id:
                month_sum += secs
        all_sum = db.get_totals().get(app_id, 0) + tracker.pending_seconds(app_id)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)

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

        big_box = QVBoxLayout()
        big_box.setSpacing(2)
        big = QLabel(format_compact(period_seconds))
        big.setObjectName("statBig")
        big.setAlignment(Qt.AlignCenter)
        big_label = QLabel(f"АКТИВНО ЗА {period_label}")
        big_label.setObjectName("statLabel")
        big_label.setAlignment(Qt.AlignCenter)
        big_box.addWidget(big)
        big_box.addWidget(big_label)
        layout.addLayout(big_box)

        boxes = QHBoxLayout()
        boxes.setSpacing(12)
        for label, value in (
            ("СЕГОДНЯ", today_live),
            ("7 ДНЕЙ", week_sum),
            ("30 ДНЕЙ", month_sum),
            ("ВСЁ ВРЕМЯ", all_sum),
        ):
            box = QFrame()
            box.setObjectName("statBox")
            box_lay = QVBoxLayout(box)
            box_lay.setContentsMargins(12, 10, 12, 10)
            box_lay.setSpacing(4)
            caption = QLabel(label)
            caption.setObjectName("statLabel")
            caption.setAlignment(Qt.AlignCenter)
            value_label = QLabel(format_compact(value))
            value_label.setObjectName("statValue")
            value_label.setAlignment(Qt.AlignCenter)
            box_lay.addWidget(caption)
            box_lay.addWidget(value_label)
            boxes.addWidget(box, 1)
        layout.addLayout(boxes)

        chart = MiniChart(110)
        chart.set_days([ru_date(today - timedelta(days=13 - i)) for i in range(14)])
        QTimer.singleShot(280, chart, lambda: chart.set_values(series, animate=True))
        layout.addWidget(chart)

        axis = QHBoxLayout()
        dates = [today - timedelta(days=13 - i) for i in range(14)]
        first = QLabel(ru_date(dates[0]))
        middle = QLabel(ru_date(dates[7]))
        last = QLabel(ru_date(dates[-1]))
        for lbl in (first, middle, last):
            lbl.setObjectName("mutedLabel")
        middle.setAlignment(Qt.AlignCenter)
        last.setAlignment(Qt.AlignRight)
        axis.addWidget(first)
        axis.addWidget(middle, 1)
        axis.addWidget(last)
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
