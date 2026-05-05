"""
Modal dialog for application-level preferences.

Changes applied immediately on OK:
  • Theme (via apply_theme)
  • Language (via set_language / i18n listeners)
  • Update frequency (persisted, applied on next launch)

"Reset to defaults" button:
  • Asks for confirmation
  • Calls AppSettings.reset_to_defaults() (clears ALL persisted keys
    including language, theme, window geometries, conversion config)
  • Re-applies the default theme (System) and detects the OS language
  • Closes the dialog — the main window will re-read defaults at next
    launch (or immediately for theme/language)
"""

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..i18n import get_language, register_listener, set_language, t
from ..state.settings import (
    AppSettings,
    UpdateFrequency,
)
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

        # ── Appearance group ───────────────────────────────────────────────
        self._appearance_group = QGroupBox()
        form = QFormLayout(self._appearance_group)

        # Theme selector
        self._theme = QComboBox()
        self._theme.addItem("", "system")
        self._theme.addItem("", "light")
        self._theme.addItem("", "dark")
        current_theme = self._settings.theme()
        for i in range(self._theme.count()):
            if self._theme.itemData(i) == current_theme:
                self._theme.setCurrentIndex(i)
                break
        form.addRow("", self._theme)

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

        outer.addWidget(self._appearance_group)

        # ── Updates group ──────────────────────────────────────────────────
        self._updates_group = QGroupBox()
        upd_form = QFormLayout(self._updates_group)

        self._update_freq = QComboBox()
        for freq in UpdateFrequency:
            self._update_freq.addItem("", freq)
        current_freq = self._settings.update_frequency()
        for i, freq in enumerate(UpdateFrequency):
            if freq == current_freq:
                self._update_freq.setCurrentIndex(i)
                break
        upd_form.addRow("", self._update_freq)

        outer.addWidget(self._updates_group)

        # ── Reset button ──────────────────────
        self._reset_btn = QPushButton()
        self._reset_btn.setStyleSheet("color: palette(mid);")
        self._reset_btn.clicked.connect(self._on_reset)
        outer.addWidget(self._reset_btn)

        # ── Main buttons ───────────────────────────────────────────────────
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

        labels = [
            t("appsettings.theme_system"),
            t("appsettings.theme_light"),
            t("appsettings.theme_dark"),
        ]
        for i, label in enumerate(labels):
            self._theme.setItemText(i, label)

        # Update form row labels by iterating the QFormLayout
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

        # Updates group
        self._updates_group.setTitle(t("appsettings.updates"))
        freq_labels = [
            t("appsettings.update_freq_launch"),
            t("appsettings.update_freq_daily"),
            t("appsettings.update_freq_weekly"),
            t("appsettings.update_freq_never"),
        ]
        for i, label in enumerate(freq_labels):
            self._update_freq.setItemText(i, label)

        upd_layout = self._updates_group.layout()
        if isinstance(upd_layout, QFormLayout):
            for row in range(upd_layout.rowCount()):
                field = upd_layout.itemAt(row, QFormLayout.ItemRole.FieldRole)
                label_item = upd_layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if field and label_item:
                    lw = label_item.widget()
                    if lw and field.widget() is self._update_freq:
                        lw.setText(t("appsettings.check_for_updates"))

        self._reset_btn.setText(t("appsettings.reset_defaults"))
        self._reset_btn.setToolTip(t("tooltip.reset_defaults"))

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _on_ok(self) -> None:
        new_theme = self._theme.currentData()
        self._settings.set_theme(new_theme)
        apply_theme(QApplication.instance(), new_theme)

        new_lang = self._lang.currentData()
        self._settings.set_language(new_lang)
        set_language(new_lang)

        new_freq = self._update_freq.currentData()
        self._settings.set_update_frequency(new_freq)

        self.accept()

    def _on_reset(self) -> None:
        reply = QMessageBox.question(
            self,
            t("appsettings.reset_title"),
            t("appsettings.reset_text"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._settings.reset_to_defaults()

        # Re-apply default theme immediately
        apply_theme(QApplication.instance(), "system")

        # Re-apply default language (English) immediately
        set_language("en")

        self.reject()  # close dialog; caller sees no config change to persist
