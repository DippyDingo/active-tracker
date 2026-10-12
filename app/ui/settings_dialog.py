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
    saved = Signal(int, bool, bool, bool)
    close_requested = Signal()

    def __init__(
        self,
        threshold_minutes: int,
        background_enabled: bool,
        show_chart_help: bool = True,
        autostart_enabled: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("modalPanel")
        self.setFixedWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)

        top = QHBoxLayout()
        title = QLabel("Настройки")
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

        row3 = QHBoxLayout()
        texts3 = QVBoxLayout()
        texts3.setSpacing(2)
        help_title = QLabel("Подсказка по графику")
        help_note = QLabel("Показывать пункты «Как пользоваться графиком» в статистике")
        help_note.setObjectName("subtleLabel")
        texts3.addWidget(help_title)
        texts3.addWidget(help_note)
        row3.addLayout(texts3)
        row3.addStretch(1)
        self._help_toggle = ToggleSwitch(show_chart_help)
        row3.addWidget(self._help_toggle, 0, Qt.AlignVCenter)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        texts4 = QVBoxLayout()
        texts4.setSpacing(2)
        autostart_title = QLabel("Запускать при входе в Windows")
        autostart_note = QLabel("Приложение будет автоматически запускаться при входе в систему")
        autostart_note.setObjectName("subtleLabel")
        texts4.addWidget(autostart_title)
        texts4.addWidget(autostart_note)
        row4.addLayout(texts4)
        row4.addStretch(1)
        self._autostart_toggle = ToggleSwitch(autostart_enabled)
        row4.addWidget(self._autostart_toggle, 0, Qt.AlignVCenter)
        layout.addLayout(row4)

        note = QLabel(
            "Если активности нет дольше порога простоя — весь период\nпростоя не засчитывается."
        )
        note.setObjectName("mutedLabel")
        layout.addWidget(note)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.close_requested)
        save_btn = QPushButton("Сохранить")
        save_btn.setObjectName("primary")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        bottom.addWidget(cancel_btn)
        bottom.addWidget(save_btn)
        layout.addLayout(bottom)

    def _save(self) -> None:
        self.saved.emit(
            self._spin.value(), 
            self._toggle.isChecked(), 
            self._help_toggle.isChecked(),
            self._autostart_toggle.isChecked()
        )
        self.close_requested.emit()

    def value(self) -> int:
        return self._spin.value()

    def background_enabled(self) -> bool:
        return self._toggle.isChecked()
