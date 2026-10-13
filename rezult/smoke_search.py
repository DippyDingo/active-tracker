"""Smoke-test релевантного поиска по сетке карточек (не часть приложения)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from app.db import Database  # noqa: E402
from app.tracker import Tracker  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

errors: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


tmp = tempfile.TemporaryDirectory()
db = Database(Path(tmp.name) / "t.db")

# Порядок добавления специально «неудобный»: Telegram в конце списка.
rows = [
    ("Notepad", "C:\\Windows\\notepad.exe"),
    ("My telegram bot", "C:\\dev\\bot.exe"),
    ("Notes", "C:\\telegram\\notes.exe"),
    ("Mtelegram", "C:\\soft\\mtelegram.exe"),
    ("Telegram Desktop", "C:\\soft\\tdesktop.exe"),
    ("Telegram", "C:\\soft\\telegram.exe"),
]
ids = {}
for name, path in rows:
    ids[name] = db.add_app(name, path)

tr = Tracker(db)
w = MainWindow(db, tr)
w.resize(1210, 780)
w.show()
app.processEvents()


def grid_names() -> list[str]:
    return [w._names[i] for i in w._current_grid_order()]


def visible_names() -> list[str]:
    order = [w._names[i] for i in w._current_grid_order()]
    placed = sorted(
        (
            (w._grid.indexOf(host), w._names[app_id])
            for app_id, host in w._hosts.items()
            if host.isVisible()
        ),
        key=lambda t: t[0],
    )
    check([n for _i, n in placed] == order, "порядок в сетке совпадает с расчётным")
    return [n for _i, n in placed]


# Без фильтра — исходный пользовательский порядок
w._apply_filter("")
check(grid_names() == [n for n, _p in rows], "без фильтра сохраняется исходный порядок")
check(len(visible_names()) == len(rows), "без фильтра видны все карточки")

# «телеграм»-сценарий: точное имя должно встать первым независимо от места в списке
w._apply_filter("telegram")
order = grid_names()
check(order[0] == "Telegram", f"точное совпадение первым, получено: {order}")
check(order[1] == "Telegram Desktop", "имя, начинающееся с запроса, вторым")
check(order[2] == "My telegram bot", "слово, начинающееся с запроса, третьим")
check(order[3] == "Mtelegram", "подстрока в имени — четвёртой")
check(order[4] == "Notes", "подстрока в пути — последней из совпавших")
check("Notepad" not in order, "несовпавшие не попадают в выдачу")
check(visible_names() == order, "видимые карточки выстроены с начала сетки")
check(w._empty_label.isHidden(), "пустая заглушка скрыта при наличии результатов")

# Равная релевантность сохраняет исходный порядок
w._apply_filter("e")
order = grid_names()
names = [n for n, _p in rows]
expected = [n for n in names if "e" in n.lower() or "e" in dict(rows)[n].lower()]
check(order == expected, f"стабильный порядок при равной релевантности: {order} != {expected}")

# Очистка поиска возвращает пользовательский порядок
w._apply_filter("")
check(grid_names() == [n for n, _p in rows], "очистка поиска вернула исходный порядок")

# Ничего не найдено
w._apply_filter("zzz")
check(grid_names() == [], "пустая выдача")
check(not w._empty_label.isHidden(), "заглушка показана")
check("zzz" in w._empty_label.text(), f"в заглушке указан запрос: {w._empty_label.text()!r}")
w._apply_filter("")

# Левая колонка порядок не меняет
side = [
    item
    for item in w._side_items.values()
]
check(len(side) == len(rows), "все строки левой колонки на месте")

# Пользовательский порядок (перетаскивание) не теряется после поиска
w._apply_filter("telegram")
w._apply_filter("")
w._order.reverse()
w._apply_filter(w._filter)
check(grid_names() == [n for n, _p in rows][::-1], "перестановка пользователя сохраняется")

db.close()

if errors:
    print("FAIL")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("OK: all search smoke checks passed")
