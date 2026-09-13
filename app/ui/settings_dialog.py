from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .widgets import ToggleSwitch


class SettingsPanel(QFrame):
    saved = Signal(int, bool)
    close_requested = Signal()

    def __init__(self, threshold_minutes: int, background_enabled: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("modalPanel")
        self.setFixedSize(480, 330)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)

        top = QHBoxLayout()
        title = QLabel("⚙  Настройки")
        title.setObjectName("modalTitle")
        top.addWidget(title)
        top.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("deleteBtn")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close_requested)
        top.addWidget(close_btn)
        layout.addLayout(top)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Порог простоя"))
        row1.addStretch(1)
        self._spin = QSpinBox()
        self._spin.setRange(1, 240)
        self._spin.setValue(int(threshold_minutes))
        self._spin.setSuffix(" мин")
        self._spin.setFixedWidth(110)
        row1.addWidget(self._spin)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(2)
        bg_title = QLabel("Фоновый учёт")
        bg_note = QLabel("Засчитывать время запущенных приложений даже вне фокуса")
        bg_note.setObjectName("subtleLabel")
        texts.addWidget(bg_title)
        texts.addWidget(bg_note)
        row2.addLayout(texts)
        row2.addStretch(1)
        self._toggle = ToggleSwitch(background_enabled)
        row2.addWidget(self._toggle, 0, Qt.AlignVCenter)
        layout.addLayout(row2)

        note = QLabel(
            "Если активности нет дольше порога простоя — весь период\nпростоя не засчитывается."
        )
        note.setObjectName("mutedLabel")
        layout.addWidget(note)
        layout.addStretch(1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.close_requested)
        save = QPushButton("Сохранить")
        save.setObjectName("primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save)
        bottom.addWidget(cancel)
        bottom.addWidget(save)
        layout.addLayout(bottom)

    def _save(self) -> None:
        self.saved.emit(self._spin.value(), self._toggle.isChecked())
        self.close_requested.emit()
