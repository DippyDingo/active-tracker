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
from ..utils import (
    MONTHS_NOM,
    PERIOD_KEYS,
    PERIOD_TITLES,
    SHORT_MONTHS,
    WEEKDAYS,
    add_months,
    format_compact,
    label_day,
    label_month,
    label_week,
    label_year,
    month_days,
    ru_date,
    ru_date_short,
    week_start,
)
from .widgets import RangeChart, pixmap_from_png, rounded_pixmap, ui_icon

# Подпись «АКТИВНО ЗА …» для каждой вкладки.
PERIOD_CAPTIONS = ["ДЕНЬ", "НЕДЕЛЮ", "МЕСЯЦ", "ГОД", "ВСЁ ВРЕМЯ"]

NO_SELECTION_HINT = "Выделение не выбрано — протяните по графику, чтобы посчитать время за период"

HELP_LINES = [
    "Протяните по графику — выделите период и увидите время в нём.",
    "Стрелки ‹ › рядом с цифрой листают день / неделю / месяц / год.",
    "«Всё время»: колесо — зум, Shift+колесо или пробел+перетаскивание — перемотка.",
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
        self._tracker = tracker
        self._app_id = app_id
        self._today = date.today()
        self._big_value = 0
        self._big_anim = None
        self._period_idx = max(0, min(start_period_idx, len(PERIOD_KEYS) - 1))
        self._anchor: date = self._today
        self._unit = "days"
        self._hours_cache: dict[str, list[int]] = {}

        today_str = self._today.isoformat()
        history: dict[str, int] = {}
        for day, secs in db.query_app_stats(app_id, end_day=None):
            if day != today_str:
                history[day] = history.get(day, 0) + secs
        self._history = history
        self._today_live = db.get_day_stats(today_str).get(app_id, 0) + tracker.pending_seconds(
            app_id
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(10)

        # --- шапка ---------------------------------------------------------
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

        # --- вкладки периодов -----------------------------------------------
        periods_row = QHBoxLayout()
        periods_row.setSpacing(2)
        self._period_group = QButtonGroup(self)
        self._period_group.setExclusive(True)
        for idx, label in enumerate(PERIOD_TITLES):
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

        # --- крупная цифра + стрелки навигации -------------------------------
        big_box = QVBoxLayout()
        big_box.setSpacing(2)

        big_row = QHBoxLayout()
        big_row.setSpacing(12)
        self._prev_btn = QPushButton()
        self._prev_btn.setObjectName("navBtn")
        self._prev_btn.setFixedSize(32, 32)
        self._prev_btn.setCursor(Qt.PointingHandCursor)
        self._prev_btn.setIcon(ui_icon("chevron_left", "#9db2c7", 18))
        self._prev_btn.setIconSize(QSize(18, 18))
        self._prev_btn.setToolTip("Предыдущий период")
        self._prev_btn.clicked.connect(lambda: self._shift_anchor(-1))

        self._next_btn = QPushButton()
        self._next_btn.setObjectName("navBtn")
        self._next_btn.setFixedSize(32, 32)
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setIcon(ui_icon("chevron_right", "#9db2c7", 18))
        self._next_btn.setIconSize(QSize(18, 18))
        self._next_btn.setToolTip("Следующий период")
        self._next_btn.clicked.connect(lambda: self._shift_anchor(1))

        self._big = QLabel("0м")
        self._big.setObjectName("statBig")
        self._big.setAlignment(Qt.AlignCenter)

        big_row.addStretch(1)
        big_row.addWidget(self._prev_btn, 0, Qt.AlignVCenter)
        big_row.addWidget(self._big, 0, Qt.AlignVCenter)
        big_row.addWidget(self._next_btn, 0, Qt.AlignVCenter)
        big_row.addStretch(1)
        big_box.addLayout(big_row)

        self._big_caption = QLabel("")
        self._big_caption.setObjectName("statLabel")
        self._big_caption.setAlignment(Qt.AlignCenter)
        big_box.addWidget(self._big_caption)

        self._period_label = QLabel("")
        self._period_label.setObjectName("periodLabel")
        self._period_label.setAlignment(Qt.AlignCenter)
        big_box.addWidget(self._period_label)

        self._sel_note = QLabel("")
        self._sel_note.setObjectName("mutedLabel")
        self._sel_note.setAlignment(Qt.AlignCenter)
        self._sel_note.setMinimumHeight(14)
        big_box.addWidget(self._sel_note)
        layout.addLayout(big_box)

        # --- график ----------------------------------------------------------
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
        # Видимость выставляем только после добавления в layout: setVisible(True)
        # у виджета без родителя показывает его как отдельное окно (мигание при открытии).
        self._help_box.setVisible(bool(self._db.get_int("show_chart_help", 1)))

        layout.addStretch(1)

        # --- низ -------------------------------------------------------------
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

    # ------------------------------------------------------------------ help
    def _build_help_box(self) -> QFrame:
        box = QFrame(self)
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

        return box

    def _hide_help(self) -> None:
        self._db.set_int("show_chart_help", 0)
        self._help_box.setVisible(False)

    # -------------------------------------------------------------- периоды
    def _on_period_clicked(self, idx: int) -> None:
        if idx == self._period_idx:
            return
        self._anchor = self._today
        self._set_period(idx, animate=True)

    def _period_start(self, d: date) -> date:
        """Нормализованное начало периода для даты d."""
        key = PERIOD_KEYS[self._period_idx]
        if key == "week":
            return week_start(d)
        if key == "month":
            return d.replace(day=1)
        if key == "year":
            return d.replace(month=1, day=1)
        return d

    def _shift_anchor(self, direction: int) -> None:
        key = PERIOD_KEYS[self._period_idx]
        a = self._anchor
        if key == "day":
            a = a + timedelta(days=direction)
        elif key == "week":
            a = a + timedelta(days=7 * direction)
        elif key == "month":
            y, m = add_months(a.year, a.month, direction)
            a = date(y, m, 1)
        elif key == "year":
            a = date(a.year + direction, 1, 1)
        else:
            return
        if self._period_start(a) > self._period_start(self._today):
            return
        self._anchor = a
        self._set_period(self._period_idx, animate=True)

    def _day_value(self, d: date) -> int:
        if d == self._today:
            return self._today_live
        return self._history.get(d.isoformat(), 0)

    def _hours_for(self, d: date) -> list[int]:
        key = d.isoformat()
        if d == self._today:
            hours = list(self._db.get_hours(self._app_id, key))
            # pending-секунды трекера ещё не в базе — кладём в текущий час.
            pending = max(0, self._today_live - sum(hours))
            if pending:
                from datetime import datetime

                hours[datetime.now().hour] += pending
            return hours
        cached = self._hours_cache.get(key)
        if cached is None:
            cached = list(self._db.get_hours(self._app_id, key))
            self._hours_cache[key] = cached
        return cached

    def _series_for(self) -> tuple[list[int], list[str], list[str], str, str]:
        """→ (values, axis_labels, tip_labels, unit, period_label)."""
        key = PERIOD_KEYS[self._period_idx]
        a = self._anchor

        if key == "day":
            values = self._hours_for(a)
            axis = [f"{h:02d}" for h in range(24)]
            tips = [f"{h:02d}:00–{(h + 1) % 24:02d}:00" for h in range(24)]
            return values, axis, tips, "hours", label_day(a, self._today)

        if key == "week":
            start = week_start(a)
            days = [start + timedelta(days=i) for i in range(7)]
            values = [self._day_value(d) for d in days]
            axis = [WEEKDAYS[d.weekday()] for d in days]
            tips = [f"{WEEKDAYS[d.weekday()]}, {ru_date(d)}" for d in days]
            return values, axis, tips, "days", label_week(start)

        if key == "month":
            n = month_days(a.year, a.month)
            days = [date(a.year, a.month, i + 1) for i in range(n)]
            values = [self._day_value(d) for d in days]
            axis = [str(d.day) for d in days]
            tips = [f"{WEEKDAYS[d.weekday()]}, {ru_date(d)}" for d in days]
            return values, axis, tips, "days", label_month(a.year, a.month)

        if key == "year":
            totals = [0] * 12
            for day_str, secs in self._history.items():
                if day_str.startswith(f"{a.year:04d}-"):
                    totals[int(day_str[5:7]) - 1] += secs
            if a.year == self._today.year:
                totals[self._today.month - 1] += self._today_live
            axis = list(SHORT_MONTHS)
            tips = [f"{MONTHS_NOM[m]} {a.year}" for m in range(12)]
            return totals, axis, tips, "months", label_year(a.year)

        # all — по месяцам от первой активности до сегодня
        past = sorted(self._history.keys())
        first = date.fromisoformat(past[0]) if past else self._today
        y, m = first.year, first.month
        values: list[int] = []
        axis: list[str] = []
        tips: list[str] = []
        while (y, m) <= (self._today.year, self._today.month):
            prefix = f"{y:04d}-{m:02d}-"
            total = sum(s for d, s in self._history.items() if d.startswith(prefix))
            if (y, m) == (self._today.year, self._today.month):
                total += self._today_live
            values.append(total)
            axis.append(SHORT_MONTHS[m - 1])
            tips.append(f"{MONTHS_NOM[m - 1]} {y}")
            y, m = add_months(y, m, 1)
        label = f"{ru_date_short(first)} {first.year} — {ru_date_short(self._today)} {self._today.year}"
        return values, axis, tips, "months", label

    def _set_period(self, idx: int, animate: bool) -> None:
        self._period_idx = idx
        key = PERIOD_KEYS[idx]
        self._anchor = self._period_start(self._anchor)

        values, axis, tips, unit, period_label = self._series_for()
        self._unit = unit
        min_vis = 4.0 if unit == "hours" else (6.0 if unit == "months" else 7.0)
        self._chart.set_series(values, axis, tips, unit=unit, min_visible=min_vis)

        total = sum(values)
        self._big_caption.setText(f"АКТИВНО ЗА {PERIOD_CAPTIONS[idx]}")
        self._period_label.setText(period_label)
        if animate:
            self._animate_big(total)
        else:
            if self._big_anim is not None:
                self._big_anim.stop()
            self._big_value = total
            self._big.setText(format_compact(total))

        navigable = key != "all"
        self._prev_btn.setVisible(navigable)
        self._next_btn.setVisible(navigable)
        if navigable:
            self._next_btn.setEnabled(self._period_start(self._anchor) < self._period_start(self._today))
        self._on_range_selection(self._chart.selection())

    # ------------------------------------------------------------ выделение
    def _on_range_selection(self, sel) -> None:
        if not sel:
            self._result_label.setText(NO_SELECTION_HINT)
            self._result_clear.setVisible(False)
            self._sel_note.setText("")
            return
        start, end = sel
        values = self._chart._days
        tips = self._chart.bucket_tips()
        total = sum(values[start : end + 1])
        count = end - start + 1
        avg = total / count if count else 0

        def tip(i: int) -> str:
            return tips[i] if 0 <= i < len(tips) else ""

        if self._unit == "hours":
            span = f"{start:02d}:00 — {end + 1:02d}:00"
            text = f"{span}  ·  {count} ч  ·  {format_compact(total)}  ·  в среднем {format_compact(avg)}/час"
        elif self._unit == "months":
            span = tip(start) if start == end else f"{tip(start)} — {tip(end)}"
            text = f"{span}  ·  {count} мес.  ·  {format_compact(total)}  ·  в среднем {format_compact(avg)}/мес"
        else:
            span = tip(start) if start == end else f"{tip(start)} — {tip(end)}"
            text = f"{span}  ·  {count} дн.  ·  {format_compact(total)}  ·  в среднем {format_compact(avg)}/день"
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
