"""
Non-modal About dialog.
Pulls app name, version and URL from the top-level app_info module.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)
from PySide6.QtCore import QUrl

from ... import app_info
from ..i18n import register_listener, t


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(420)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._build_ui()
        register_listener(self._retranslate_ui)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 20, 24, 16)

        # App name + version
        self._name_label = QLabel()
        name_font = QFont()
        name_font.setPointSize(16)
        name_font.setBold(True)
        self._name_label.setFont(name_font)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._name_label)

        self._version_label = QLabel()
        self._version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._version_label)

        # URL — clickable hyperlink
        self._url_label = QLabel()
        self._url_label.setOpenExternalLinks(True)
        self._url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._url_label)

        # Horizontal rule (thin separator)
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: palette(mid);")
        layout.addWidget(sep)

        # Description
        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._desc_label)

        # Tech stack
        self._tech_label = QLabel()
        self._tech_label.setWordWrap(True)
        self._tech_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._tech_label)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("about.title"))
        self._name_label.setText(app_info.APP_NAME)
        self._version_label.setText(f"v{app_info.VERSION}")
        self._url_label.setText(
            f'<a href="{app_info.APP_URL}">{app_info.APP_URL}</a>'
        )
        self._desc_label.setText(t("about.description"))
        self._tech_label.setText(t("about.built_with"))
