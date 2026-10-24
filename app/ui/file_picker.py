"""Собственный диалог выбора exe-файла в стиле приложения.

Зачем: системный QFileDialog в Windows — отдельное нативное окно, которое
всегда рисуется в светлой системной теме. При открытии/закрытии оно давало
белое окно с заголовком. Здесь — обычный QFrame внутри модального слоя,
полностью в палитре приложения.
"""

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import theme


class FilePickerPanel(QFrame):
    picked = Signal(str)
    close_requested = Signal()

    def __init__(self, start_dir: str = "", title: str = "Выберите приложение", parent=None):
        super().__init__(parent)
        self.setObjectName("modalPanel")
        self.setFixedSize(720, 560)
        self._picked_path = ""

        self._dir = start_dir if os.path.isdir(start_dir) else os.path.expanduser("~")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        head = QLabel(title)
        head.setObjectName("modalTitle")
        top.addWidget(head)
        top.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("deleteBtn")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close_requested)
        top.addWidget(close_btn)
        layout.addLayout(top)

        nav = QHBoxLayout()
        self._up_btn = QPushButton("↑")
        self._up_btn.setFixedSize(30, 30)
        self._up_btn.setCursor(Qt.PointingHandCursor)
        self._up_btn.setToolTip("На уровень выше")
        self._up_btn.clicked.connect(self._go_up)
        nav.addWidget(self._up_btn)

        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        nav.addWidget(self._path_edit, 1)
        layout.addLayout(nav)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setObjectName("addScroll")
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._host.setObjectName("addHost")
        self._list = QVBoxLayout(self._host)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(2)
        self._scroll.setWidget(self._host)
        layout.addWidget(self._scroll, 1)

        bottom = QHBoxLayout()
        self._name_label = QLabel("Файл не выбран")
        self._name_label.setObjectName("subtleLabel")
        bottom.addWidget(self._name_label, 1)
        cancel = QPushButton("Отмена")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.close_requested)
        bottom.addWidget(cancel)
        self._ok = QPushButton("Выбрать")
        self._ok.setObjectName("primary")
        self._ok.setCursor(Qt.PointingHandCursor)
        self._ok.setEnabled(False)
        self._ok.clicked.connect(self._accept)
        bottom.addWidget(self._ok)
        layout.addLayout(bottom)

        theme.paint_background(self._scroll)
        self._fill()

    # ------------------------------------------------------------------ навигация
    def _fill(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._path_edit.setText(self._dir)
        self._up_btn.setEnabled(os.path.dirname(self._dir) != self._dir)

        entries: list[tuple[str, bool]] = []
        try:
            for name in os.listdir(self._dir):
                full = os.path.join(self._dir, name)
                is_dir = os.path.isdir(full)
                if is_dir or name.lower().endswith(".exe"):
                    entries.append((name, is_dir))
        except OSError:
            entries = []
        entries.sort(key=lambda e: (not e[1], e[0].lower()))

        if not entries:
            empty = QLabel("В этой папке нет папок и .exe файлов")
            empty.setObjectName("subtleLabel")
            self._list.addWidget(empty)

        for name, is_dir in entries[:2000]:
            self._list.addWidget(self._make_row(name, is_dir))
        self._list.addStretch(1)

    def _make_row(self, name: str, is_dir: bool) -> QWidget:
        row = QFrame()
        row.setObjectName("addRow")
        row.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(10)

        icon = QLabel("📁" if is_dir else "▸")
        icon.setFixedSize(20, 20)
        lay.addWidget(icon)

        label = QLabel()
        label.setObjectName("sideName")
        fm = QFontMetrics(label.font())
        label.setText(fm.elidedText(name, Qt.ElideMiddle, 560))
        lay.addWidget(label, 1)

        full = os.path.join(self._dir, name)

        def on_click(_e, path=full, directory=is_dir):
            if directory:
                self._dir = path
                self._fill()
            else:
                self._picked_path = path
                self._name_label.setText(path)
                self._ok.setEnabled(True)

        row.mouseReleaseEvent = on_click
        return row

    def _go_up(self) -> None:
        parent = os.path.dirname(self._dir)
        if parent and parent != self._dir:
            self._dir = parent
            self._fill()

    def _accept(self) -> None:
        if self._picked_path:
            self.picked.emit(self._picked_path)

    def sizeHint(self) -> QSize:
        return QSize(720, 560)
