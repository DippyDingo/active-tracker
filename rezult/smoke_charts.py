"""Offscreen smoke-test для RangeChart / MiniChart / AppCard (не часть приложения)."""
import os
import sys
from datetime import date, timedelta

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

app = QApplication([])

from app.ui.widgets import AppCard, MiniChart, RangeChart  # noqa: E402

errors: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def render(w) -> None:
    from PySide6.QtGui import QPixmap

    pm = QPixmap(w.size())
    w.render(pm)


# --- RangeChart: 3 дня истории («Всё время» с короткой историей) -------------
rc = RangeChart(170)
rc.resize(560, 170)
today = date.today()
dates = [today - timedelta(days=2), today - timedelta(days=1), today]
rc.set_days([100, 200, 50], dates)
pad_l, pad_t, inner_w, inner_h = rc._plot()
check(rc._visible == 3.0, f"visible должен быть 3 при n=3, получено {rc._visible}")
check(abs(rc._day_to_x(0.5) - pad_l) < 1e-6, "первая точка не у левого края")
check(abs(rc._day_to_x(2.5) - (pad_l + inner_w)) < 1e-6, "последняя точка не у правого края")
render(rc)
check(len(rc._vis_pts) == 3, f"ожидалось 3 видимые точки, получено {len(rc._vis_pts)}")
check(rc.day_tip(0) != "", "day_tip пустой для дневного ряда")
# обратное преобразование
for x in (pad_l, pad_l + inner_w / 2, pad_l + inner_w):
    d = rc._x_to_day(x)
    check(abs(rc._day_to_x(d) - x) < 1e-6, f"x->day->x не сходится в {x}")
# выделение всего диапазона: полоса точно в пределах плота
rc._sel = (0, 2)
band = rc._sel_band_px()
check(band[0] <= pad_l + 1e-6 and band[1] >= pad_l + inner_w - 1e-6, "полоса выделения не покрывает плот целиком")

# --- RangeChart: длинная история (месяцы) и зум ---------------------------------
n = 400
dates = [today - timedelta(days=n - 1 - i) for i in range(n)]
rc.set_days([i % 50 for i in range(n)], dates)
render(rc)
check(rc._visible == float(n), "полный вид должен показывать все дни")
first_b, last_b = rc._buckets[0], rc._buckets[-1]
check(abs(rc._day_to_x((first_b[0] + first_b[1]) / 2) - pad_l) < 1e-6, "центр первого бакета не у левого края")
check(abs(rc._day_to_x((last_b[0] + last_b[1]) / 2) - (pad_l + inner_w)) < 1e-6, "центр последнего бакета не у правого края")
check(len(rc._vis_pts) == len(rc._buckets), "не все бакеты видны в полном виде")
# зум в середину
rc._visible = 14.0
rc._offset = 100.0
rc._clamp_view()
rc._rebuild_buckets()
render(rc)
check(len(rc._vis_pts) >= 14, f"после зума ожидалось ≥14 точек, получено {len(rc._vis_pts)}")
check(rc._buckets[0][1] - rc._buckets[0][0] == 1, "при vis=14 бакеты должны быть дневными")

# --- RangeChart: одна точка --------------------------------------------------------
rc.set_days([42], [today])
render(rc)
check(len(rc._vis_pts) == 1, "одна точка не отрисована")
check(abs(rc._day_to_x(0.5) - (pad_l + inner_w / 2)) < 1e-6, "одна точка не по центру")

# --- RangeChart: часы (explicit) ------------------------------------------------
rc.set_hours([i for i in range(24)])
render(rc)
check(rc.day_tip(5) == "05:00–06:00", f"тултип часа: {rc.day_tip(5)!r}")
check(abs(rc._day_to_x(0.5) - pad_l) < 1e-6, "часы: первая точка не у края")

# --- MiniChart: hover переживает set_values с тем же числом точек --------------
mc = MiniChart(46)
mc.resize(240, 60)
mc.set_values([1, 2, 3, 4, 5, 6, 7])
mc._progress = 1.0
mc._hover = 3
mc.set_values([1, 2, 3, 4, 5, 6, 8])  # «тик» — изменилось только сегодня
check(mc._hover == 3, "hover сброшен при обновлении значений той же длины")
mc.set_values([1, 2, 3])
check(mc._hover == -1, "hover не сброшен при смене длины ряда")
mc.set_values([5] * 7)
mc.set_axis([0, 3, 6], ["Пн", "Чт", "Вс"])
pts = mc._points()
check(abs(pts[0].x() - mc.PAD_L) < 1e-6, "MiniChart: первая точка не у левого края")
check(abs(pts[-1].x() - (mc.width() - mc.PAD_R)) < 1e-6, "MiniChart: последняя точка не у правого края")
check(mc._index_at_x(pts[3].x()) == 3, "MiniChart: _index_at_x не совпадает с точкой")
render(mc)

# --- AppCard ------------------------------------------------------------------------
card = AppCard(1, "Test", "C:/x.exe", None)
card.resize(300, 206)
card.set_axis([0, 3, 6], ["Пн", "Чт", "Вс"])
card.set_day_tooltips([f"d{i}" for i in range(7)])
card.set_chart([1, 2, 3, 4, 5, 6, 7])
check(not hasattr(card, "_day_labels"), "у AppCard остались QLabel подписей")
render(card)

# --- Проверка _axis_label_rect: границы подписей не выходят за виджет -----------
print("Проверка _axis_label_rect...")
# Тест для разных ширин виджета
for widget_w in [300, 620, 1200]:
    for count in [3, 12, 24]:  # 3 точки, 12 месяцев, 24 часа
        pad_l, pad_r = 6.0, 6.0
        for k in range(count):
            # Позиции x равномерно распределены
            x = pad_l + (widget_w - pad_l - pad_r) * k / max(count - 1, 1)
            rect, align = RangeChart._axis_label_rect(k, count, x, widget_w, pad_l, pad_r, 90.0, 16.0, 0.0)
            check(rect.left() >= -1.0, f"w={widget_w}, count={count}, k={k}: rect.left()={rect.left():.1f} < 0")
            check(rect.right() <= widget_w + 1.0, f"w={widget_w}, count={count}, k={k}: rect.right()={rect.right():.1f} > {widget_w}")
            # Первая подпись должна быть прижата к левому краю
            if k == 0:
                check(abs(rect.left() - (pad_l - 2)) < 1e-6, f"w={widget_w}, count={count}: первая подпись не прижата к левому краю")
                check(align & Qt.AlignLeft, f"w={widget_w}, count={count}: первая подпись не AlignLeft")
            # Последняя подпись должна быть прижата к правому краю
            elif k == count - 1:
                check(abs(rect.right() - (widget_w - pad_r + 2)) < 1e-6, f"w={widget_w}, count={count}: последняя подпись не прижата к правому краю")
                check(align & Qt.AlignRight, f"w={widget_w}, count={count}: последняя подпись не AlignRight")
            # Средние подписи должны быть центрированы
            else:
                check(align & Qt.AlignCenter or align & Qt.AlignHCenter, f"w={widget_w}, count={count}, k={k}: средняя подпись не центрирована")

# --- RangeChart: проверка подписей на разных ширинах ---------------------------
print("Проверка подписей RangeChart на разных ширинах...")
for width in [300, 620, 1200]:
    # Тест с 12 месяцами (год)
    rc_test = RangeChart(170)
    rc_test.resize(width, 170)
    dates_year = [today - timedelta(days=365 - i) for i in range(365)]
    rc_test.set_days([i % 30 for i in range(365)], dates_year)
    render(rc_test)
    # Проверяем, что есть видимые бакеты
    check(len(rc_test._buckets) > 0, f"width={width}: нет бакетов в годовом графике")
    
    # Тест с 24 часами (сегодня)
    rc_hours = RangeChart(170)
    rc_hours.resize(width, 170)
    rc_hours.set_hours([i for i in range(24)])
    render(rc_hours)
    check(len(rc_hours._buckets) == 24, f"width={width}: ожидалось 24 часовых бакета, получено {len(rc_hours._buckets)}")

# --- MiniChart: проверка подписей на узких карточках ---------------------------
print("Проверка подписей MiniChart на узких карточках...")
for width in [180, 240, 300]:
    mc_test = MiniChart(46)
    mc_test.resize(width, 60)
    mc_test.set_values([1, 2, 3, 4, 5, 6, 7])
    mc_test.set_axis([0, 3, 6], ["Пн", "Чт", "Вс"])
    mc_test._progress = 1.0
    render(mc_test)
    check(mc_test._values == [1, 2, 3, 4, 5, 6, 7], f"width={width}: значения не установлены")

# Проверяем именно прямоугольники drawText, включая дробный зум и панорамирование.
import app.ui.widgets as widgets
from PySide6.QtGui import QPainter

axis_rects = []


class RecordingPainter(QPainter):
    def drawText(self, *args):
        if len(args) == 3 and isinstance(args[2], str):
            axis_rects.append((args[0], args[2]))
        return super().drawText(*args)


widgets.QPainter = RecordingPainter
try:
    for width in [200, 240, 300, 400, 620, 1200]:
        rc.resize(width, 170)
        for count in [24, 7, 31]:
            labels = [f"{i:02d}" if count == 24 else f"{i + 1} окт" for i in range(count)]
            rc.set_series(list(range(count)), labels, labels, min_visible=4)
            for visible in [float(count), 6.5, 4.0]:
                for fraction in [0, 0.13, 0.5, 1]:
                    rc._visible = visible
                    rc._offset = (count - visible) * fraction
                    rc._clamp_view()
                    rc._rebuild_buckets()
                    axis_rects.clear()
                    render(rc)
                    context = f"w={width}, n={count}, zoom={visible}, pan={fraction}"
                    if count == 24 and visible == 24:
                        drawn = [text for _, text in axis_rects]
                        check(drawn[0] == "00" and drawn[-1] == "23", f"missing endpoint hours: {context}")
                        if width >= 620:
                            check(drawn == labels, f"missing hours in full view: {context}: {drawn}")
                    check(len(axis_rects) >= 2, f"too few labels: {context}")
                    for rect, text in axis_rects:
                        check(rect.left() >= 0 and rect.right() <= width, f"clipped {text}: {context}")
                    for (a, _), (b, _) in zip(axis_rects, axis_rects[1:]):
                        check(b.left() >= a.right() + 1.9, f"overlapping labels: {context}: {a} {b}")
finally:
    widgets.QPainter = QPainter

if errors:
    print("FAIL")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("OK: all chart smoke checks passed")
