"""
Top toolbar containing file management and settings actions.

Selection toggle
----------------
The two former "✓ All" / "✗ None" buttons are replaced by a single
QPushButton whose label always shows the current selection count.
Clicking it alternates between "select all" and "deselect all":
  - if every file is already checked  → deselect all
  - otherwise (none or partial)       → select all
The current state is tracked via update_selection_count().
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QWidget,
)

from .i18n import register_listener, t


def _vsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


class ToolbarWidget(QWidget):
    # File management
    addFilesRequested        = Signal()
    addFolderRequested       = Signal()
    removeSelectedRequested  = Signal()
    removeAllRequested       = Signal()
    removeCompletedRequested = Signal()

    # Selection — single toggle emits whichever is appropriate
    selectAllRequested   = Signal()
    deselectAllRequested = Signal()

    # App
    conversionSettingsRequested = Signal()
    appSettingsRequested        = Signal()
    logsRequested               = Signal()
    aboutRequested              = Signal()

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
        self._add_files   = QPushButton()
        self._add_folder  = QPushButton()
        self._remove      = QPushButton()
        self._remove_all  = QPushButton()
        self._remove_done = QPushButton()

        for w in (self._add_files, self._add_folder, _vsep(),
                  self._remove, self._remove_all, self._remove_done):
            layout.addWidget(w)

        layout.addWidget(_vsep())

        # Single select-toggle button
        self._select_toggle = QPushButton()
        self._select_toggle.setMinimumWidth(130)
        layout.addWidget(self._select_toggle)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(spacer)

        # Right group
        self._conv_settings = QPushButton()
        self._app_settings  = QPushButton()
        self._app_settings.setFixedWidth(32)
        self._logs          = QPushButton()

        self._about = QPushButton()
        info_icon = QApplication.style().standardIcon(
            QStyle.StandardPixmap.SP_MessageBoxInformation
        )
        self._about.setIcon(info_icon)
        self._about.setFixedWidth(32)

        for w in (self._conv_settings, self._app_settings,
                  _vsep(), self._logs, _vsep(), self._about):
            layout.addWidget(w)

        # Signals
        self._add_files.clicked.connect(self.addFilesRequested)
        self._add_folder.clicked.connect(self.addFolderRequested)
        self._remove.clicked.connect(self.removeSelectedRequested)
        self._remove_all.clicked.connect(self.removeAllRequested)
        self._remove_done.clicked.connect(self.removeCompletedRequested)
        self._select_toggle.clicked.connect(self._on_select_toggle)
        self._conv_settings.clicked.connect(self.conversionSettingsRequested)
        self._app_settings.clicked.connect(self.appSettingsRequested)
        self._logs.clicked.connect(self.logsRequested)
        self._about.clicked.connect(self.aboutRequested)

        self._retranslate_ui()

    def _on_select_toggle(self) -> None:
        if self._all_selected:
            self.deselectAllRequested.emit()
        else:
            self.selectAllRequested.emit()

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
        self._app_settings.setText(t("toolbar.app_settings"))
        self._app_settings.setToolTip(t("tooltip.app_settings"))
        self._logs.setText(t("toolbar.logs"))
        self._logs.setToolTip(t("tooltip.logs"))
        self._about.setToolTip(t("tooltip.about"))
        self._select_toggle.setToolTip(t("tooltip.select_toggle"))
        # Re-render count label with current counts
        self._refresh_toggle_label()

    def _refresh_toggle_label(self) -> None:
        checked = getattr(self, "_last_checked", 0)
        total   = getattr(self, "_last_total",   0)
        self._select_toggle.setText(
            t("toolbar.select_toggle", checked=checked, total=total)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool) -> None:
        for w in (self._add_files, self._add_folder,
                  self._remove, self._remove_all, self._remove_done,
                  self._select_toggle):
            w.setEnabled(not busy)

    def update_selection_count(self, checked: int, total: int) -> None:
        self._last_checked   = checked
        self._last_total     = total
        self._all_selected   = (total > 0 and checked == total)
        self._refresh_toggle_label()
