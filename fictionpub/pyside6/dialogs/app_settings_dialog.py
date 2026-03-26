"""
Modal dialog for application preferences.
Language and theme changes are applied immediately on OK.
"""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QVBoxLayout,
)

from ..i18n import get_language, register_listener, set_language, t
from ..state.settings import AppSettings
from ..themes import apply_theme


class AppSettingsDialog(QDialog):
    def __init__(self, app_settings: AppSettings, parent=None):
        super().__init__(parent)
        self._settings = app_settings
        self.setFixedWidth(340)
        self._build_ui()
        register_listener(self._retranslate_ui)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        self._appearance_group = QGroupBox()
        form = QFormLayout(self._appearance_group)

        # Theme selector
        self._theme_label_text = ""   # set in retranslate
        self._theme = QComboBox()
        # Use internal keys; display text set in retranslate_ui
        self._theme.addItem("", "system")
        self._theme.addItem("", "light")
        self._theme.addItem("", "dark")
        current_theme = self._settings.theme()
        for i in range(self._theme.count()):
            if self._theme.itemData(i) == current_theme:
                self._theme.setCurrentIndex(i)
                break
        self._theme_row = form.addRow("", self._theme)

        # Language selector
        self._lang = QComboBox()
        self._lang.addItem("English", "en")
        self._lang.addItem("Українська", "uk")
        current_lang = get_language()
        for i in range(self._lang.count()):
            if self._lang.itemData(i) == current_lang:
                self._lang.setCurrentIndex(i)
                break
        form.addRow("", self._lang)
        self._lang_row_label = form.labelForField(self._lang)

        outer.addWidget(self._appearance_group)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_ok)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("appsettings.title"))
        self._appearance_group.setTitle(t("appsettings.appearance"))

        # Update theme combo display text
        labels = [
            t("appsettings.theme_system"),
            t("appsettings.theme_light"),
            t("appsettings.theme_dark"),
        ]
        for i, label in enumerate(labels):
            self._theme.setItemText(i, label)

        # Update form labels — find them by field widget
        from PySide6.QtWidgets import QFormLayout
        layout = self._appearance_group.layout()
        if isinstance(layout, QFormLayout):
            for row in range(layout.rowCount()):
                field = layout.itemAt(row, QFormLayout.ItemRole.FieldRole)
                label = layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if field and label:
                    widget = field.widget()
                    lw = label.widget()
                    if lw:
                        if widget is self._theme:
                            lw.setText(t("appsettings.theme"))
                        elif widget is self._lang:
                            lw.setText(t("appsettings.language"))

    def _on_ok(self) -> None:
        from PySide6.QtWidgets import QApplication

        # Apply theme
        new_theme = self._theme.currentData()
        self._settings.set_theme(new_theme)
        apply_theme(QApplication.instance(), new_theme)

        # Apply language
        new_lang = self._lang.currentData()
        self._settings.set_language(new_lang)
        set_language(new_lang)   # notifies all registered listeners

        self.accept()