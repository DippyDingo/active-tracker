"""Offscreen smoke-test тем оформления (не часть приложения)."""
import os
import re
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPixmap  # noqa: E402

from app.ui import theme  # noqa: E402
from app.ui.widgets import AppCard, MiniChart, RangeChart  # noqa: E402

errors: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def render(w):
    pm = QPixmap(w.size())
    pm.fill(Qt.transparent)
    w.render(pm)
    return pm


def dist(a: QColor, b: QColor) -> float:
    return (
        (a.red() - b.red()) ** 2
        + (a.green() - b.green()) ** 2
        + (a.blue() - b.blue()) ** 2
    ) ** 0.5


# --- 1. QSS каждой палитры: не пустой, без неподставленных плейсхолдеров ------
for key, p in theme.PALETTES.items():
    qss = theme.build_qss(p)
    check(len(qss) > 1000, f"QSS темы {key} подозрительно короткий")
    left = re.findall(r"\$[a-z_][a-z0-9_]*", qss)
    check(not left, f"QSS темы {key} содержит неподставленные токены: {left[:5]}")
    check(p.bg in qss, f"QSS темы {key} не содержит цвет фона {p.bg}")
    check(p.accent in qss, f"QSS темы {key} не содержит акцент {p.accent}")

# --- 2. Неизвестная тема молча возвращает тёмную по умолчанию -----------------
p = theme.apply_theme(app, "no-such-theme")
check(p.key == theme.DEFAULT_THEME, "битая тема не вернула дефолт")
check(theme.pal().key == theme.DEFAULT_THEME, "pal() не обновился после битой темы")

# --- 3. Рендер виджетов в каждой теме: фон отличается от текста ---------------
values = [120, 400, 90, 700, 30, 260, 500]
labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

for key in theme.PALETTES:
    theme.apply_theme(app, key)
    pal = theme.pal()
    app.setStyleSheet(theme.build_qss(pal))

    card = AppCard(1, "Тест", "C:\\test.exe", None)
    card.resize(280, 206)
    card.set_chart(values)
    card.set_period_seconds(7200)
    card.set_today_seconds(1800)
    # grab() корректно рендерит виджет с QGraphicsDropShadowEffect (render() — нет)
    pm_card = card.grab()
    center = pm_card.toImage().pixelColor(140, 60)
    card_c = QColor(pal.card)
    text_c = QColor(pal.text)
    check(
        dist(center, card_c) < 90,
        f"{key}: центр карточки {center.name()} далёк от цвета карточки {pal.card}",
    )
    check(
        dist(center, text_c) > 40,
        f"{key}: фон карточки сливается с цветом текста",
    )

    mini = MiniChart(46)
    mini.resize(240, 46)
    mini.set_values(values)
    render(mini)

    rc = RangeChart(170)
    rc.resize(560, 170)
    rc.set_series(values, labels, labels, min_visible=4)
    pm_rc = render(rc)
    check(pm_rc.width() == 560, f"{key}: RangeChart не отрендерился")

    # Токены для painted-кода существуют и валидны
    for token in (
        "chart_line", "chart_fill_top", "chart_fill_bottom", "chart_dim",
        "tooltip_bg", "tooltip_border", "tooltip_text", "point_ring",
        "dim", "shadow", "shadow_hover", "overlay", "toggle_off", "knob",
        "popup_bg", "popup_border", "icon",
    ):
        c = theme.color(token)
        check(c.isValid(), f"{key}: невалидный токен {token}")

    # Тултип графика контрастен на фоне карточки
    tip_bg = theme.color("tooltip_bg")
    check(
        dist(tip_bg, text_c) > 60 or pal.is_light,
        f"{key}: тултип сливается с текстом",
    )

    card.deleteLater()
    mini.deleteLater()
    rc.deleteLater()

# --- 4. БД хранит имя темы -----------------------------------------------------
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from app.db import Database  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    db = Database(Path(tmp) / "t.db")
    check(db.get_text("theme", "midnight") == "midnight", "get_text не вернул дефолт")
    db.set_text("theme", "fog")
    check(db.get_text("theme") == "fog", "set_text не сохранил значение")
    db.set_text("theme", "morning")
    check(db.get_text("theme") == "morning", "set_text не перезаписал значение")
    db.close()

theme.apply_theme(app, theme.DEFAULT_THEME)

if errors:
    print("FAIL")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("OK: all theme smoke checks passed")
