from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    def __init__(self, threshold_minutes: int, background_enabled: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        self._spin = QSpinBox()
        self._spin.setRange(1, 240)
        self._spin.setValue(int(threshold_minutes))
        self._spin.setSuffix(" мин")

        self._bg = QCheckBox("Засчитывать время отслеживаемых приложений, работающих в фоне")
        self._bg.setChecked(bool(background_enabled))

        note = QLabel(
            "Порог простоя: если пользователь не активен дольше заданного\n"
            "времени, весь период простоя не засчитывается.\n\n"
            "Фоновый учёт: время идёт всем отслеживаемым приложениям,\n"
            "которые запущены, пока пользователь активен — даже если\n"
            "они не в фокусе окна."
        )
        note.setObjectName("subtleLabel")
        note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Простой без активности", self._spin)
        layout.addLayout(form)
        layout.addWidget(self._bg)
        layout.addWidget(note)
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self) -> int:
        return self._spin.value()

    def background_enabled(self) -> bool:
        return self._bg.isChecked()
