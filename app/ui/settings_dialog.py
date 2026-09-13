from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from .widgets import ToggleSwitch


class SettingsPanel(QDialog):
    saved = Signal(int, bool, bool)
    close_requested = Signal()

    def __init__(
        self,
        threshold_minutes: int,
        background_enabled: bool,
        show_chart_help: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)

        top = QHBoxLayout()
        title = QLabel("Настройки")
        title.setObjectName("modalTitle")
        top.addWidget(title)
        top.addStretch(1)
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

        note = QLabel(
            "Если активности нет дольше порога простоя — весь период\nпростоя не засчитывается."
        )
        note.setObjectName("mutedLabel")
        layout.addWidget(note)
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        self.saved.emit(
            self._spin.value(), self._toggle.isChecked(), self._help_toggle.isChecked()
        )
        self.accept()

    def value(self) -> int:
        return self._spin.value()

    def background_enabled(self) -> bool:
        return self._toggle.isChecked()
