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
    QWidget,
)

from ..db import Database
from ..tracker import Tracker
from ..utils import format_compact, ru_date, ru_date_short
from .widgets import RangeChart, pixmap_from_png, rounded_pixmap, ui_icon

PERIODS = [
    ("Сегодня", 1, "СЕГОДНЯ"),
    ("7 дней", 7, "7 ДНЕЙ"),
    ("2 недели", 14, "2 НЕДЕЛИ"),
    ("Месяц", 30, "МЕСЯЦ"),
    ("Год", 365, "ГОД"),
    ("Всё время", 0, "ВСЁ ВРЕМЯ"),
]

NO_SELECTION_HINT = "Выделение не выбрано — протяните по графику, чтобы посчитать время за период"

HELP_LINES = [
    "Протяните по графику — выделите период и увидите время в нём.",
    "Колесо или Ctrl+колесо — зум вокруг курсора.",
    "Shift+колесо или пробел+перетаскивание — перемотка.",
    "Границы выделения можно двигать мышью. Сброс — Esc, клик мимо или ✕.",
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
        self.setFixedSize(620, 700)

        self._db = db
        self._app_id = app_id
        self._today = date.today()
        self._big_value = 0
        self._big_anim = None
        self._period_idx = max(0, min(start_period_idx, len(PERIODS) - 1))
        self._period_unit = "days"
        self._period_dates: list[date] | None = None

        today_str = self._today.isoformat()
        history: dict[str, int] = {}
        for day, secs in db.query_app_stats(app_id, end_day=None):
            if day != today_str:
                history[day] = history.get(day, 0) + secs
        self._history = history
        self._today_live = db.get_day_stats(today_str).get(app_id, 0) + tracker.pending_seconds(
            app_id
        )
        self._hours = db.get_hours(app_id, today_str)

        past_days = sorted(history.keys())
        first_activity = date.fromisoformat(past_days[0]) if past_days else self._today
        daily_start = min(first_activity, self._today - timedelta(days=6))
        self._daily_dates: list[date] = []
        self._daily: list[int] = []
        d = daily_start
        while d <= self._today:
            if d == self._today:
                value = self._today_live
            else:
                value = history.get(d.isoformat(), 0)
            self._daily_dates.append(d)
            self._daily.append(value)
            d += timedelta(days=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(10)

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
        self._sel_note = QLabel("")
        self._sel_note.setObjectName("mutedLabel")
        self._sel_note.setAlignment(Qt.AlignCenter)
        self._sel_note.setMinimumHeight(14)
        big_box.addWidget(self._big)
        big_box.addWidget(self._big_caption)
        big_box.addWidget(self._sel_note)
        layout.addLayout(big_box)

        self._chart = RangeChart(170)
        self._chart.selection_changed.connect(self._on_range_selection)
        layout.addWidget(self._chart)

        self._result_box = QFrame()
        self._result_box.setObjectName("rangeResult")
        self._result_box.setFixedHeight(42)
        result_layout = QHBoxLayout(self._result_box)
        result_layout.setContentsMargins(14, 4, 8, 4)
        result_layout.setSpacing(10)
        self._result_label = QLabel(NO_SELECTION_HINT)
        self._result_label.setObjectName("subtleLabel")
        result_layout.addWidget(self._result_label, 1)
        self._result_clear = QPushButton("✕")
        self._result_clear.setObjectName("deleteBtn")
        self._result_clear.setFixedSize(24, 24)
        self._result_clear.setCursor(Qt.PointingHandCursor)
        self._result_clear.setToolTip("Сбросить выделение")
        self._result_clear.setVisible(False)
        self._result_clear.clicked.connect(self._chart.clear_selection)
        result_layout.addWidget(self._result_clear)
        layout.addWidget(self._result_box)

        self._help_box = self._build_help_box()
        layout.addWidget(self._help_box)

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

    def _build_help_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("helpBox")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 10, 10, 12)
        layout.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("Как пользоваться графиком")
        title.setObjectName("helpTitle")
        head.addWidget(title)
        head.addStretch(1)
        hide_btn = QPushButton("✕")
        hide_btn.setObjectName("deleteBtn")
        hide_btn.setFixedSize(22, 22)
        hide_btn.setCursor(Qt.PointingHandCursor)
        hide_btn.setToolTip("Скрыть подсказку (вернуть можно в настройках)")
        hide_btn.clicked.connect(self._hide_help)
        head.addWidget(hide_btn)
        layout.addLayout(head)

        for line in HELP_LINES:
            lbl = QLabel(f"•  {line}")
            lbl.setObjectName("helpBullet")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

        box.setVisible(bool(self._db.get_int("show_chart_help", 1)))
        return box

    def _hide_help(self) -> None:
        self._db.set_int("show_chart_help", 0)
        self._help_box.setVisible(False)

    def _on_period_clicked(self, idx: int) -> None:
        if idx == self._period_idx:
            return
        self._period_idx = idx
        self._set_period(idx, animate=True)

    def _series_days(self, n: int) -> tuple[list[int], list[date]]:
        values: list[int] = []
        dates: list[date] = []
        for i in range(n - 1, -1, -1):
            d = self._today - timedelta(days=i)
            if d == self._today:
                value = self._today_live
            else:
                value = self._history.get(d.isoformat(), 0)
            values.append(value)
            dates.append(d)
        return values, dates

    def _set_period(self, idx: int, animate: bool) -> None:
        _label, days, caption = PERIODS[idx]

        if idx == 0:
            values = list(self._hours)
            self._period_unit = "hours"
            self._period_dates = None
            self._chart.set_hours(values)
        else:
            if days <= 0:
                values = list(self._daily)
                dates = list(self._daily_dates)
            else:
                values, dates = self._series_days(days)
            self._period_unit = "days"
            self._period_dates = dates
            self._chart.set_days(values, dates)

        total = sum(values)
        self._big_caption.setText(f"АКТИВНО ЗА {caption}")
        if animate:
            self._animate_big(total)
        else:
            if self._big_anim is not None:
                self._big_anim.stop()
            self._big_value = total
            self._big.setText(format_compact(total))
        self._on_range_selection(self._chart.selection())

    def _on_range_selection(self, sel) -> None:
        if not sel:
            self._result_label.setText(NO_SELECTION_HINT)
            self._result_clear.setVisible(False)
            self._sel_note.setText("")
            return
        start, end = sel
        if self._period_unit == "hours":
            values = list(self._hours)
            total = sum(values[start : end + 1])
            count = end - start + 1
            avg = total / count if count else 0
            span = f"{start:02d}:00 — {end + 1:02d}:00"
            text = (
                f"{span}  ·  {count} ч  ·  {format_compact(total)}  ·  "
                f"в среднем {format_compact(avg)}/час"
            )
        else:
            dates = self._period_dates or []
            total = sum(self._chart._days[start : end + 1])
            count = end - start + 1
            avg = total / count if count else 0
            if start < len(dates) and end < len(dates):
                span = f"{ru_date_short(dates[start])} — {ru_date_short(dates[end])}"
            else:
                span = ""
            text = (
                f"{span}  ·  {count} дн.  ·  {format_compact(total)}  ·  "
                f"в среднем {format_compact(avg)}/день"
            )
        self._result_label.setText(text)
        self._result_clear.setVisible(True)
        self._sel_note.setText(f"Выделено: {format_compact(total)}")

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
