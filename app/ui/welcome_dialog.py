from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..db import Database


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Трекер активности")
        self.setFixedSize(470, 290)
        self.mode = ""
        self.path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(12)

        title = QLabel("Трекер активности")
        title.setObjectName("pageTitle")
        sub = QLabel(
            "База данных не найдена.\n"
            "Создайте новую, чтобы начать, или загрузите ранее сохранённый файл базы."
        )
        sub.setObjectName("subtleLabel")
        sub.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addStretch(1)

        create_btn = QPushButton("＋  Создать новую базу")
        create_btn.setObjectName("primary")
        create_btn.setCursor(Qt.PointingHandCursor)
        create_btn.clicked.connect(self._create)
        layout.addWidget(create_btn)

        load_btn = QPushButton("📂  Загрузить базу данных")
        load_btn.setCursor(Qt.PointingHandCursor)
        load_btn.clicked.connect(self._load)
        layout.addWidget(load_btn)

    def _create(self) -> None:
        self.mode = "create"
        self.accept()

    def _load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузка базы данных", "", "База данных (*.db);;Все файлы (*.*)"
        )
        if not path:
            return
        if not Database.validate(path):
            QMessageBox.warning(
                self,
                "Неподходящий файл",
                "Выбранный файл не является корректной базой данных трекера.",
            )
            return
        self.mode = "load"
        self.path = path
        self.accept()
