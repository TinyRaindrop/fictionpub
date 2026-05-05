"""
Non-modal About dialog.
Pulls app name, version and URL from the top-level app_info module.

Update status
-------------
An update-status label and "Check Now" button are added below the tech-
stack line.  The parent window calls set_update_status() whenever the
check worker returns a result.  The "Check Now" button emits
checkForUpdatesRequested so MainWindow can trigger a fresh check.
"""

from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ... import app_info
from ..i18n import register_listener, t, unregister_listener


class AboutDialog(QDialog):
    check_for_updates_requested = Signal()

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
        self._desc_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        layout.addWidget(self._desc_label)

        # Tech stack
        self._tech_label = QLabel()
        self._tech_label.setWordWrap(True)
        self._tech_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._tech_label)

        # Thin separator before update area
        sep2 = QLabel()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: palette(mid);")
        layout.addWidget(sep2)

        # Update status row
        upd_row = QHBoxLayout()
        upd_row.setSpacing(8)

        # TODO: open UpdateDialog by clicking update_status_label
        self._update_status_label = QLabel()
        self._update_status_label.setWordWrap(True)
        self._update_status_label.setStyleSheet("font-size: 10px;")
        upd_row.addWidget(self._update_status_label, stretch=1)

        self._check_now_btn = QPushButton()
        self._check_now_btn.clicked.connect(self.check_for_updates_requested)
        upd_row.addWidget(self._check_now_btn)

        layout.addLayout(upd_row)

        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("about.title"))
        self._name_label.setText(app_info.APP_NAME)
        self._version_label.setText(f"version {app_info.VERSION}")
        self._url_label.setText(f'<a href="{app_info.APP_URL}">{app_info.APP_URL}</a>')
        self._desc_label.setText(t("about.description"))
        self._tech_label.setText(t("about.built_with"))
        self._check_now_btn.setText(t("update.check_now"))
        # Preserve existing status text through retranslate; only reset the button
        if not self._update_status_label.text():
            self._update_status_label.setText(t("update.status_checking"))

    # ------------------------------------------------------------------
    # Public API (called by MainWindow)
    # ------------------------------------------------------------------

    @override
    def closeEvent(self, event) -> None:
        # Unregister *before* WA_DeleteOnClose lets Qt destroy the C++ object.
        # Without this, set_language() may call _retranslate_ui() on an already-
        # deleted widget if MainWindow still holds a Python reference to this dialog.
        unregister_listener(self._retranslate_ui)
        super().closeEvent(event)

    def set_update_status(self, new_version: str | None) -> None:
        """
        Update the status label.

        Parameters
        ----------
        new_version : tag string (e.g. "v1.4.0") when update available,
                      None when up to date,
                      "" when check not performed / in progress
        """
        if new_version is None:
            self._update_status_label.setStyleSheet("font-size: 10px; color: palette(mid);")
            self._update_status_label.setText(t("update.status_up_to_date"))
        elif new_version == "":
            self._update_status_label.setStyleSheet("font-size: 10px; color: palette(mid);")
            self._update_status_label.setText(t("update.status_checking"))
        else:
            ver = new_version.lstrip("v")
            self._update_status_label.setStyleSheet(
                "font-size: 10px; color: #27ae60; font-weight: bold;"
            )
            self._update_status_label.setText(
                t("update.status_available", new=ver, current=app_info.VERSION)
            )
