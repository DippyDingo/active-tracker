"""Страница «Данные»: экспорт и импорт базы данных.

Никаких QFileDialog и QMessageBox: путь вводится текстом (или вставляется),
подтверждение и результат показываются на самой странице. Это исключает
создание второго окна Windows при работе с базой.
"""

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..db import Database
from .shell import ScrollPage


class DataPage(ScrollPage):
    export_done = Signal(str)
    import_done = Signal(str)

    def __init__(self, current_db_path: str, parent=None):
        super().__init__("База данных", parent)
        self._current = current_db_path

        # ------------------------------------------------------------ экспорт
        export_box = QFrame()
        export_box.setObjectName("manualBlock")
        ex_lay = QVBoxLayout(export_box)
        ex_lay.setContentsMargins(16, 12, 16, 12)
        ex_lay.setSpacing(8)

        ex_title = QLabel("Экспорт базы данных")
        ex_title.setObjectName("modalTitle")
        ex_lay.addWidget(ex_title)

        ex_note = QLabel(
            "Создаётся полная консистентная копия базы. Укажите, куда сохранить файл."
        )
        ex_note.setObjectName("subtleLabel")
        ex_note.setWordWrap(True)
        ex_lay.addWidget(ex_note)

        row = QHBoxLayout()
        self._export_path = QLineEdit()
        self._export_path.setPlaceholderText(r"C:\Users\...\tracker_backup.db")
        row.addWidget(self._export_path, 1)
        export_btn = QPushButton("Экспортировать")
        export_btn.setObjectName("primary")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._do_export)
        row.addWidget(export_btn)
        ex_lay.addLayout(row)

        self._export_status = QLabel("")
        self._export_status.setObjectName("subtleLabel")
        self._export_status.setWordWrap(True)
        ex_lay.addWidget(self._export_status)

        self.add_content(export_box)

        # ------------------------------------------------------------ импорт
        import_box = QFrame()
        import_box.setObjectName("manualBlock")
        im_lay = QVBoxLayout(import_box)
        im_lay.setContentsMargins(16, 12, 16, 12)
        im_lay.setSpacing(8)

        im_title = QLabel("Загрузка базы данных")
        im_title.setObjectName("modalTitle")
        im_lay.addWidget(im_title)

        im_note = QLabel(
            "Текущая база останется на диске без изменений. "
            "Укажите путь к файлу .db, на который нужно переключиться."
        )
        im_note.setObjectName("subtleLabel")
        im_note.setWordWrap(True)
        im_lay.addWidget(im_note)

        row2 = QHBoxLayout()
        self._import_path = QLineEdit()
        self._import_path.setPlaceholderText(r"C:\Users\...\tracker.db")
        row2.addWidget(self._import_path, 1)
        import_btn = QPushButton("Переключиться")
        import_btn.setObjectName("primary")
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.clicked.connect(self._do_import)
        row2.addWidget(import_btn)
        im_lay.addLayout(row2)

        self._import_status = QLabel("")
        self._import_status.setObjectName("subtleLabel")
        self._import_status.setWordWrap(True)
        im_lay.addWidget(self._import_status)

        self.add_content(import_box)

        info = QLabel(f"Текущая база: {self._current}")
        info.setObjectName("mutedLabel")
        info.setWordWrap(True)
        self.add_content(info)

    # ---------------------------------------------------------------- экспорт
    def _do_export(self) -> None:
        path = self._export_path.text().strip().strip('"')
        if not path:
            self._export_status.setText("Укажите путь, куда сохранить копию.")
            return
        if not path.lower().endswith(".db"):
            path += ".db"
        self.export_done.emit(path)

    # ----------------------------------------------------------------- импорт
    def _do_import(self) -> None:
        path = self._import_path.text().strip().strip('"')
        if not path:
            self._import_status.setText("Укажите путь к файлу базы.")
            return
        if not os.path.isfile(path):
            self._import_status.setText("Файл не найден. Проверьте путь.")
            return
        if not Database.validate(path):
            self._import_status.setText(
                "Файл не является корректной базой данных трекера."
            )
            return
        self.import_done.emit(path)

    # ------------------------------------------------------------- результаты
    def set_export_result(self, ok: bool, path: str) -> None:
        if ok:
            self._export_status.setText(f"Готово: {path}")
        else:
            self._export_status.setText("Не удалось экспортировать базу данных.")

    def set_import_result(self, ok: bool, path: str) -> None:
        if ok:
            self._import_status.setText(f"База загружена: {path}")
        else:
            self._import_status.setText("Не удалось переключиться на базу.")
