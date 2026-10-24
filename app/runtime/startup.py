"""Единый runtime приложения.

Задача модуля — гарантировать, что в процессе существует РОВНО ОДНО окно
Windows и ровно один QApplication, а все внутренние экраны (добавление,
настройки, статистика, обновления, импорт/экспорт) показываются ВНУТРИ
главного окна (QStackedWidget), а не как самостоятельные top-level окна.

Раньше белое окно с заголовком «Nodexy» появлялось потому, что:
  * QApplication создавался повторно в разных ветках запуска (без темы);
  * QSplashScreen был отдельным HWND;
  * модальные панели поднимались как самостоятельные окна;
  * QFileDialog/QMessageBox открывали нативные светлые окна Windows.

Здесь всё это исключено конструктивно.
"""

import os
import sys

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtWidgets import QApplication

from .. import config
from ..ui import theme


def create_application(argv: list[str] | None = None) -> QApplication:
    """Создаёт (один раз) QApplication с уже применённой темой.

    Вызывать ДО создания любых окон и диалогов.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Nodexy")
    app.setApplicationDisplayName("Nodexy")
    app.setOrganizationName("Nodexy")
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)
    # Fusion + тёмная палитра до первого виджета: системные части (фоны
    # диалогов, вьюпорты, тултипы) рождаются уже в цветах темы.
    app.setStyle("Fusion")
    theme.apply_theme(app, theme.DEFAULT_THEME)
    app.setWindowIcon(theme.load_app_icon())
    app.setQuitOnLastWindowClosed(False)
    return app


class InstanceGuard:
    """Защита от второго экземпляра через именованный мьютекс Windows.

    Мьютекс нужен установщику Inno (AppMutex=NodexySingleInstanceMutex).
    Второй экземпляр НЕ создаёт никаких окон: он лишь просит первый
    показать окно и завершается.
    """

    def __init__(self) -> None:
        self._lock = QLockFile(str(config.app_dir() / "nodexy.lock"))
        self._mutex_ok = False

    def acquire(self) -> bool:
        if sys.platform == "win32":
            try:
                from .. import win32_utils

                self._mutex_ok = win32_utils.acquire_instance_mutex()
            except Exception:
                self._mutex_ok = True
            if not self._mutex_ok:
                return False
        return self._lock.tryLock(100)

    def release(self) -> None:
        try:
            self._lock.unlock()
        except Exception:
            pass
