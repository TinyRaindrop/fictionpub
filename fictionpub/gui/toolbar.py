"""
Top toolbar containing file management and settings actions.

Selection toggle
----------------
A single QPushButton whose label shows the current selection count.
Clicking it alternates between "select all" and "deselect all":
  - if every file is already checked  → deselect all
  - otherwise (none or partial)       → select all
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QStyle,
    QWidget,
)

from .i18n import register_listener, t


# FIXME: extract vsep() from modules to a helper module
def _vsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


def _btn() -> QPushButton:
    """Plain QPushButton — visual styling is applied by the parent window's QSS."""
    return QPushButton()


class ToolbarWidget(QWidget):
    # File management
    add_files_requested = Signal()
    add_folder_requested = Signal()
    remove_selected_requested = Signal()
    remove_all_requested = Signal()
    remove_completed_requested = Signal()

    # Selection
    select_all_requested = Signal()
    deselect_all_requested = Signal()

    # App
    conversion_settings_requested = Signal()
    app_settings_requested = Signal()
    about_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_selected = False  # tracks whether all files are currently checked
        self._build_ui()
        register_listener(self._retranslate_ui)

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Left group — file management
        self._add_files = _btn()
        self._add_folder = _btn()
        self._remove = _btn()
        self._remove_all = _btn()
        self._remove_done = _btn()

        for w in (
            self._add_files,
            self._add_folder,
            _vsep(),
            self._remove,
            self._remove_all,
            self._remove_done,
        ):
            layout.addWidget(w)

        spacer1 = QWidget()
        spacer1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(spacer1)

        # Single select-toggle button
        self._select_toggle = _btn()
        self._select_toggle.setCheckable(True)
        self._select_toggle.setChecked(False)
        self._select_toggle.setMinimumWidth(130)
        layout.addWidget(self._select_toggle)

        spacer2 = QWidget()
        spacer2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(spacer2)

        # Right group — settings | about
        self._conv_settings = _btn()
        self._app_settings = _btn()

        self._about = _btn()
        self._about.setIcon(
            QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_MessageBoxInformation
            )
        )
        self._about.setFixedWidth(32)

        for w in (self._conv_settings, _vsep(), self._app_settings, _vsep(), self._about):
            layout.addWidget(w)

        # Signals
        self._add_files.clicked.connect(self.add_files_requested)
        self._add_folder.clicked.connect(self.add_folder_requested)
        self._remove.clicked.connect(self.remove_selected_requested)
        self._remove_all.clicked.connect(self.remove_all_requested)
        self._remove_done.clicked.connect(self.remove_completed_requested)
        self._select_toggle.clicked.connect(self._on_select_toggle)
        self._conv_settings.clicked.connect(self.conversion_settings_requested)
        self._app_settings.clicked.connect(self.app_settings_requested)
        self._about.clicked.connect(self.about_requested)

        self._retranslate_ui()

    def _on_select_toggle(self) -> None:
        if self._all_selected:
            self.deselect_all_requested.emit()
        else:
            self.select_all_requested.emit()

    def _retranslate_ui(self) -> None:
        self._add_files.setText(t("toolbar.add_files"))
        self._add_files.setToolTip(t("tooltip.add_files"))
        self._add_folder.setText(t("toolbar.add_folder"))
        self._add_folder.setToolTip(t("tooltip.add_folder"))
        self._remove.setText(t("toolbar.remove"))
        self._remove.setToolTip(t("tooltip.remove"))
        self._remove_all.setText(t("toolbar.remove_all"))
        self._remove_all.setToolTip(t("tooltip.remove_all"))
        self._remove_done.setText(t("toolbar.remove_done"))
        self._remove_done.setToolTip(t("tooltip.remove_done"))
        self._conv_settings.setText(t("toolbar.settings"))
        self._conv_settings.setToolTip(t("tooltip.settings"))
        self._app_settings.setText(t("toolbar.app_settings_label"))
        self._app_settings.setToolTip(t("tooltip.app_settings"))
        self._about.setToolTip(t("tooltip.about"))
        self._select_toggle.setToolTip(t("tooltip.select_toggle"))
        self._refresh_toggle_label()

    def _refresh_toggle_label(self) -> None:
        checked = getattr(self, "_last_checked", 0)
        total = getattr(self, "_last_total", 0)
        self._select_toggle.setText(
            t("toolbar.select_toggle", checked=checked, total=total)
        )
        self._select_toggle.setChecked(self._all_selected)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool) -> None:
        for w in (
            self._add_files,
            self._add_folder,
            self._remove,
            self._remove_all,
            self._remove_done,
            self._select_toggle,
        ):
            w.setEnabled(not busy)

    def update_selection_count(self, checked: int, total: int) -> None:
        self._last_checked = checked
        self._last_total = total
        self._all_selected = total > 0 and checked == total
        self._refresh_toggle_label()
