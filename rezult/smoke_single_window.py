"""Offscreen smoke-тест архитектуры «одно окно» (не часть приложения).

Проверяет, что ни одно действие пользователя не создаёт дополнительных
top-level окон: добавление приложения, настройки, статистика, данные
(экспорт/импорт), подтверждение удаления — всё живёт внутри главного окна.
"""

import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

app = QApplication([])

from app.ui import theme  # noqa: E402
from app.db import Database  # noqa: E402
from app.tracker import Tracker  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.shell import PanelHostPage  # noqa: E402

errors: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def visible_count() -> int:
    return len([w for w in QApplication.topLevelWidgets() if w.isVisible()])


theme.apply_theme(app, theme.DEFAULT_THEME)
d = Database(os.path.join(tempfile.mkdtemp(), "x.db"))
app_id = d.add_app("Test App", r"C:\test\app.exe", None)
w = MainWindow(d, Tracker(d), {})
w.show()
app.processEvents()

check(visible_count() == 1, "старт: должно быть одно видимое окно")

# --- страница добавления
w._open_add()
app.processEvents()
check(visible_count() == 1, "страница добавления: одно окно")
w._pages.currentWidget().close_requested.emit()
app.processEvents()
check(visible_count() == 1, "закрытие добавления: одно окно")

# --- настройки
w._open_settings()
app.processEvents()
check(visible_count() == 1, "настройки: одно окно")
check(isinstance(w._pages.currentWidget(), PanelHostPage), "настройки: страница-обёртка")
w._pages.currentWidget().close_requested.emit()
app.processEvents()

# --- статистика
w._open_stats(app_id)
app.processEvents()
check(visible_count() == 1, "статистика: одно окно")
w._pages.currentWidget().close_requested.emit()
app.processEvents()

# --- данные (экспорт/импорт)
w._export_database()
app.processEvents()
check(visible_count() == 1, "страница данных: одно окно")
check(type(w._pages.currentWidget()).__name__ == "DataPage", "страница данных: тип")
w._pages.currentWidget().close_requested.emit()
app.processEvents()

# --- инлайн-подтверждение удаления (без QMessageBox)
w._confirm_delete(app_id)
app.processEvents()
check(visible_count() == 1, "подтверждение удаления: одно окно")
strip = getattr(w, "_confirm_strip", None)
check(strip is not None, "полоса подтверждения показана")

cancel = [b for b in strip.findChildren(QPushButton) if b.text() == "Отмена"][0]
cancel.click()
app.processEvents()
check(getattr(w, "_confirm_strip", None) is None, "полоса скрыта после «Отмена»")
check(any(a.id == app_id for a in d.list_apps()), "приложение не удалено после «Отмена»")

w._confirm_delete(app_id)
app.processEvents()
yes = [b for b in w._confirm_strip.findChildren(QPushButton) if b.text() == "Удалить"][0]
yes.click()
app.processEvents()
check(not any(a.id == app_id for a in d.list_apps()), "приложение удалено после «Удалить»")

# --- повторные циклы открытия/закрытия (нет утечек страниц)
for _ in range(3):
    w._open_add()
    app.processEvents()
    w._pages.currentWidget().close_requested.emit()
    app.processEvents()
check(w._pages.count() == 1, "после циклов в стеке только главная страница")

w.close()
app.processEvents()

if errors:
    print("FAIL")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("OK: all single-window smoke checks passed")
