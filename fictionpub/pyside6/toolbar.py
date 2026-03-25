"""
Top toolbar containing file management and settings actions.
All user actions are exposed as Qt signals; the widget holds no business logic.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)


def _btn(text: str, tooltip: str = "") -> QPushButton:
    b = QPushButton(text)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


class ToolbarWidget(QWidget):
    # File management
    addFilesRequested      = Signal()
    addFolderRequested     = Signal()
    removeSelectedRequested  = Signal()
    removeAllRequested     = Signal()
    removeCompletedRequested = Signal()

    # Selection
    selectAllRequested   = Signal()
    deselectAllRequested = Signal()

    # App
    conversionSettingsRequested = Signal()
    appSettingsRequested        = Signal()
    logsRequested               = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Left group — file management
        self._add_files  = _btn("Add Files",   "Add individual .fb2 or .fb2.zip files")
        self._add_folder = _btn("Add Folder",  "Scan a directory recursively for FB2 files")
        self._remove     = _btn("Remove",      "Remove selected items from the list")
        self._remove_all = _btn("Remove All",  "Clear the entire file list")
        self._remove_done = _btn("Remove Done", "Remove all successfully converted files")

        for w in (self._add_files, self._add_folder, _separator(),
                  self._remove, self._remove_all, self._remove_done):
            layout.addWidget(w)

        layout.addWidget(_separator())

        # Select all / none
        self._sel_all  = _btn("✓ All",  "Select all files")
        self._sel_none = _btn("✗ None", "Deselect all files")
        layout.addWidget(self._sel_all)
        layout.addWidget(self._sel_none)

        # Selection counter label
        self._count_label = QLabel("0 of 0 selected")
        self._count_label.setContentsMargins(6, 0, 6, 0)
        layout.addWidget(self._count_label)

        # Spacer pushes settings to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(spacer)

        # Right group — settings / logs
        self._conv_settings = _btn("⚙ Settings", "Configure conversion options")
        self._app_settings  = _btn("🔧",          "Application preferences")
        self._app_settings.setFixedWidth(32)
        self._logs          = _btn("📋 Logs",     "Open the logs directory")

        for w in (self._conv_settings, self._app_settings, _separator(), self._logs):
            layout.addWidget(w)

        # Wire signals
        self._add_files.clicked.connect(self.addFilesRequested)
        self._add_folder.clicked.connect(self.addFolderRequested)
        self._remove.clicked.connect(self.removeSelectedRequested)
        self._remove_all.clicked.connect(self.removeAllRequested)
        self._remove_done.clicked.connect(self.removeCompletedRequested)
        self._sel_all.clicked.connect(self.selectAllRequested)
        self._sel_none.clicked.connect(self.deselectAllRequested)
        self._conv_settings.clicked.connect(self.conversionSettingsRequested)
        self._app_settings.clicked.connect(self.appSettingsRequested)
        self._logs.clicked.connect(self.logsRequested)

    # ------------------------------------------------------------------
    # Public API called by MainWindow
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool) -> None:
        """Disable file-management buttons during conversion / scanning."""
        for w in (self._add_files, self._add_folder,
                  self._remove, self._remove_all, self._remove_done,
                  self._sel_all, self._sel_none):
            w.setEnabled(not busy)

    def update_selection_count(self, checked: int, total: int) -> None:
        self._count_label.setText(f"{checked} of {total} selected")
