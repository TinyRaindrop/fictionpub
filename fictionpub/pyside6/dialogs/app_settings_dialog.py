"""
Modal dialog for application preferences (theme, etc.).
Emits settingsChanged so MainWindow can apply changes immediately.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QVBoxLayout,
)

from ..state.settings import AppSettings
from ..themes import apply_theme


class AppSettingsDialog(QDialog):
    settingsChanged = Signal()

    def __init__(self, app_settings: AppSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Application Settings")
        self.setFixedWidth(320)
        self._settings = app_settings
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        appearance = QGroupBox("Appearance")
        form = QFormLayout(appearance)

        self._theme = QComboBox()
        self._theme.addItems(["System", "Light", "Dark"])
        current = self._settings.theme().capitalize()
        idx = self._theme.findText(current)
        if idx >= 0:
            self._theme.setCurrentIndex(idx)
        form.addRow("Theme:", self._theme)

        outer.addWidget(appearance)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _on_ok(self) -> None:
        theme = self._theme.currentText().lower()
        self._settings.set_theme(theme)

        from PySide6.QtWidgets import QApplication
        apply_theme(QApplication.instance(), theme)

        self.settingsChanged.emit()
        self.accept()
