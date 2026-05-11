"""
Non-modal About dialog.
Pulls app name, version and URL from the top-level app_info module.

Update status
-------------
The bottom row contains one context-sensitive button:

  • No result yet / checking  → "Check Now"   (emits check_for_updates_requested)
  • Up to date                → "Check Now"   (same)
  • Update available          → "View Update" (emits view_update_requested(UpdateInfo))

The status label changes colour independently:
  • Checking / neutral  → palette(mid), small italic text
  • Up to date          → palette(mid)
  • Update available    → green bold — acts as a secondary click target
    (clicking the green label also emits view_update_requested)

Public API called by MainWindow
--------------------------------
  set_update_info(info: UpdateInfo)  — update found; store info, switch button
  set_update_status(new_version)     — None = up to date, "" = checking
  (set_update_status still works for the checking / up-to-date states so
   MainWindow does not need changes for those two paths)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from fictionpub import app_info
from fictionpub.gui.i18n import register_listener, t, unregister_listener

if TYPE_CHECKING:
    from fictionpub.gui.workers.update_worker import UpdateInfo


class _ClickableLabel(QLabel):
    """QLabel that emits clicked() when the user presses the left mouse button."""

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    @override
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AboutDialog(QDialog):
    check_for_updates_requested = Signal()
    view_update_requested = Signal(object)  # UpdateInfo

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(420)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._update_info: UpdateInfo | None = None  # set by set_update_info()

        self._build_ui()
        register_listener(self._retranslate_ui)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

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

        # Horizontal rule
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

        # Clickable status label — acts as a secondary "View Update" affordance
        self._update_status_label = _ClickableLabel()
        self._update_status_label.setWordWrap(True)
        self._update_status_label.setStyleSheet("font-size: 10px;")
        self._update_status_label.clicked.connect(self._on_status_label_clicked)
        upd_row.addWidget(self._update_status_label, stretch=1)

        # Single context-sensitive button: "Check Now" ↔ "View Update"
        self._update_btn = QPushButton()
        self._update_btn.clicked.connect(self._on_update_btn_clicked)
        upd_row.addWidget(self._update_btn)

        layout.addLayout(upd_row)

        self._retranslate_ui()

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("about.title"))
        self._name_label.setText(app_info.APP_NAME)
        self._version_label.setText(f"version {app_info.VERSION}")
        self._url_label.setText(f'<a href="{app_info.APP_URL}">{app_info.APP_URL}</a>')
        self._desc_label.setText(t("about.description"))
        self._tech_label.setText(t("about.built_with"))
        # Refresh button label; don't touch status text — it was set by the caller
        self._refresh_update_btn()
        # Only reset status text on first render (when it is still empty)
        if not self._update_status_label.text():
            self._update_status_label.setText(t("update.status_checking"))

    def _refresh_update_btn(self) -> None:
        """Set button text based on whether update info is available."""
        if self._update_info is not None:
            self._update_btn.setText(t("update.btn_do_update"))
        else:
            self._update_btn.setText(t("update.check_now"))

    # ------------------------------------------------------------------
    # Button / label handlers
    # ------------------------------------------------------------------

    def _on_update_btn_clicked(self) -> None:
        """Dispatch to the correct action depending on current update state."""
        if self._update_info is not None:
            self.view_update_requested.emit(self._update_info)
        else:
            self.check_for_updates_requested.emit()

    def _on_status_label_clicked(self) -> None:
        """Clicking the green status text opens the update dialog (if available)."""
        if self._update_info is not None:
            self.view_update_requested.emit(self._update_info)

    # ------------------------------------------------------------------
    # Public API (called by MainWindow)
    # ------------------------------------------------------------------

    def set_update_info(self, info: UpdateInfo) -> None:
        """
        Call when a newer release has been found.

        Stores the full UpdateInfo so the button can open UpdateDialog,
        and updates the status label to green.
        """
        self._update_info = info
        ver = info.tag.lstrip("v")
        self._update_status_label.setStyleSheet(
            "font-size: 10px; color: #27ae60; font-weight: bold;"
            " text-decoration: underline;"
        )
        self._update_status_label.setText(
            t("update.status_available", new=ver, current=app_info.VERSION)
        )
        # Re-enable hand cursor (it is always on, but be explicit after any style reset)
        self._update_status_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._refresh_update_btn()

    def set_update_status(self, new_version: str | None) -> None:
        """
        Update the status label for the checking / up-to-date states.

        Parameters
        ----------
        new_version : None  → up to date
                      ""    → check in progress / not yet performed
                      tag   → update available (prefer set_update_info() for this case)
        """
        if new_version is None:
            # Up to date — clear stored info, revert button
            self._update_info = None
            self._update_status_label.setStyleSheet("font-size: 10px; color: palette(mid);")
            self._update_status_label.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self._update_status_label.setText(t("update.status_up_to_date"))

        elif new_version == "":
            # Checking / unknown — clear stored info, revert button
            self._update_info = None
            self._update_status_label.setStyleSheet("font-size: 10px; color: palette(mid);")
            self._update_status_label.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self._update_status_label.setText(t("update.status_checking"))

        else:
            # Legacy path: tag string passed without UpdateInfo object.
            # Show the available text but the button stays as "Check Now"
            # since we have no UpdateInfo to pass to UpdateDialog.
            ver = new_version.lstrip("v")
            self._update_status_label.setStyleSheet(
                "font-size: 10px; color: #27ae60; font-weight: bold;"
            )
            self._update_status_label.setText(
                t("update.status_available", new=ver, current=app_info.VERSION)
            )

        self._refresh_update_btn()

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    @override
    def closeEvent(self, event) -> None:
        # Unregister *before* WA_DeleteOnClose lets Qt destroy the C++ object.
        # Without this, set_language() may call _retranslate_ui() on an already-
        # deleted widget if MainWindow still holds a Python reference to this dialog.
        unregister_listener(self._retranslate_ui)
        super().closeEvent(event)
