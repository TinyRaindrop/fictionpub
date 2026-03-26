"""
Top toolbar containing file management and settings actions.
All user actions are exposed as Qt signals; the widget holds no business logic.
Supports runtime language switching via register_listener / retranslate_ui.
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

        # Selection
        self._sel_all  = QPushButton()
        self._sel_none = QPushButton()
        layout.addWidget(self._sel_all)
        layout.addWidget(self._sel_none)

        # Selection counter
        self._count_label = QLabel("0 of 0 selected")
        self._count_label.setContentsMargins(6, 0, 6, 0)
        layout.addWidget(self._count_label)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(spacer)

        # Right group — settings / logs
        self._conv_settings = QPushButton()
        self._app_settings  = QPushButton()
        self._app_settings.setFixedWidth(32)
        self._logs          = QPushButton()

        for w in (self._conv_settings, self._app_settings, _vsep(), self._logs):
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

        self._retranslate_ui()

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
        self._sel_all.setText(t("toolbar.select_all"))
        self._sel_all.setToolTip(t("tooltip.select_all"))
        self._sel_none.setText(t("toolbar.select_none"))
        self._sel_none.setToolTip(t("tooltip.select_none"))
        self._conv_settings.setText(t("toolbar.settings"))
        self._conv_settings.setToolTip(t("tooltip.settings"))
        self._app_settings.setText(t("toolbar.app_settings"))
        self._app_settings.setToolTip(t("tooltip.app_settings"))
        self._logs.setText(t("toolbar.logs"))
        self._logs.setToolTip(t("tooltip.logs"))

    # ------------------------------------------------------------------
    # Public API called by MainWindow
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool) -> None:
        for w in (self._add_files, self._add_folder,
                  self._remove, self._remove_all, self._remove_done,
                  self._sel_all, self._sel_none):
            w.setEnabled(not busy)

    def update_selection_count(self, checked: int, total: int) -> None:
        self._count_label.setText(t("toolbar.n_of_m_selected", checked=checked, total=total))