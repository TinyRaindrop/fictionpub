"""
Bottom bar: status | progress | counters | logs | Convert/Cancel.

Single-row layout (left → right):
  [status text]  [progress bar]  [counters]  │  [📂 Logs]  [📋 Last]  │  [Cancel]  [Convert]

Layout stability
────────────────
* Progress bar and Counters use setRetainSizeWhenHidden(True) so
  their layout slot is preserved — nothing shifts when conversion starts.
* Counters widget is also retain-size hidden at idle.

Counter icons
─────────────
The three status counts use the shared QIcon instances from icons.py (same as FileTreeModel)

QSS
───
Styling is handled by MainWindow._apply_stylesheet()
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ..models.conversion import ConversionStatus
from .i18n import register_listener, t
from .icons import get_status_icons


def _vsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


def _retain_size(widget: QWidget) -> None:
    """Make the widget keep its layout space even when hidden."""
    sp: QSizePolicy = widget.sizePolicy()
    sp.setRetainSizeWhenHidden(True)
    widget.setSizePolicy(sp)


_ICON_PX = 14  # status-icon render size inside the bar


class BottomBarWidget(QWidget):
    convert_requested = Signal()
    cancel_requested = Signal()
    open_logs_dir_requested = Signal()
    open_last_log_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self._total_files: int = 0
        self._build_ui()
        self.set_idle()
        register_listener(self._retranslate_ui)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Status text — left-aligned, takes available horizontal space
        self._status = QLabel()
        self._status.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._status.setMinimumWidth(140)
        layout.addWidget(self._status)

        # Progress bar — fixed width, retains layout slot when hidden
        self._progress = QProgressBar()
        self._progress.setFixedWidth(200)
        self._progress.setTextVisible(True)
        _retain_size(self._progress)
        self._progress.hide()
        layout.addWidget(self._progress)

        # Counter icon+value pairs — retains layout slot when hidden
        self._counters_widget = self._build_counters()
        _retain_size(self._counters_widget)
        self._counters_widget.hide()
        layout.addWidget(self._counters_widget)

        layout.addWidget(_vsep())

        # Log access
        self._logs_dir = QPushButton()
        self._logs_dir.clicked.connect(self.open_logs_dir_requested)
        layout.addWidget(self._logs_dir)

        self._last_log = QPushButton()
        self._last_log.clicked.connect(self.open_last_log_requested)
        layout.addWidget(self._last_log)

        layout.addWidget(_vsep())

        # Cancel — retains layout slot when hidden
        self._cancel = QPushButton()
        self._cancel.setMinimumWidth(150)
        self._cancel.clicked.connect(self.cancel_requested)
        self._cancel.hide()
        layout.addWidget(self._cancel)

        # Convert — primary action
        self._convert = QPushButton()
        self._convert.setObjectName("convertButton")
        self._convert.setMinimumWidth(150)
        self._convert.clicked.connect(self.convert_requested)
        layout.addWidget(self._convert)

        self._retranslate_ui()

    def _build_counters(self) -> QWidget:
        """Three icon + count label pairs in a horizontal container."""
        icons = get_status_icons(_ICON_PX)

        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(3)

        def _pair(status: ConversionStatus):
            icon_lbl = QLabel()
            icon_lbl.setPixmap(icons[status].pixmap(_ICON_PX, _ICON_PX))
            icon_lbl.setFixedSize(_ICON_PX, _ICON_PX)
            count_lbl = QLabel("—")
            count_lbl.setMinimumWidth(20)
            count_lbl.setAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            return icon_lbl, count_lbl

        self._ok_icon, self._ok_count = _pair(ConversionStatus.SUCCESS)
        self._warn_icon, self._warn_count = _pair(ConversionStatus.WARNING)
        self._fail_icon, self._fail_count = _pair(ConversionStatus.FAILURE)

        for w in (
            self._ok_icon,
            self._ok_count,
            self._warn_icon,
            self._warn_count,
            self._fail_icon,
            self._fail_count,
        ):
            row.addWidget(w)

        return container

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------

    def _retranslate_ui(self) -> None:
        self._logs_dir.setText(t("bar.logs_folder"))
        self._logs_dir.setToolTip(t("tooltip.logs_folder"))
        self._last_log.setText(t("bar.last_log"))
        self._last_log.setToolTip(t("tooltip.last_log"))
        self._cancel.setText(t("bar.cancel"))
        self._convert.setText(t("bar.convert"))

    # ------------------------------------------------------------------
    # Counter helpers
    # ------------------------------------------------------------------

    def _update_res_counters(self, success: int, warnings: int, failures: int) -> None:
        self._ok_count.setText(str(success))
        self._warn_count.setText(str(warnings))
        self._fail_count.setText(str(failures))

    def _reset_res_counters(self) -> None:
        for lbl in (self._ok_count, self._warn_count, self._fail_count):
            lbl.setText("—")

    def update_file_count(self, total: int) -> None:
        """Called whenever the model's file count changes."""
        self._total_files: int = total

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def set_idle(self, message: str | None = None) -> None:
        if message is None:
            message = (
                t("bar.ready_n_files", n=self._total_files)
                if self._total_files
                else t("bar.ready")
            )
        self._status.setText(message)
        self._status.setText(message if message is not None else t("bar.ready"))
        self._progress.hide()
        self._cancel.hide()
        self._convert.show()
        self._convert.setEnabled(True)
        self._reset_res_counters()
        self._counters_widget.hide()

    def set_scanning(self) -> None:
        self._status.setText(t("bar.scanning"))
        self._convert.setEnabled(False)

    def set_converting(self, total: int) -> None:
        self._status.setText(t("bar.converting_n", n=total))
        self._progress.setRange(0, total)
        self._progress.setValue(0)
        self._progress.show()
        self._update_res_counters(0, 0, 0)
        self._counters_widget.show()
        self._convert.hide()
        self._cancel.show()
        self._cancel.setEnabled(True)

    def set_cancelling(self) -> None:
        self._status.setText(t("bar.cancelling"))
        self._cancel.setEnabled(False)

    def update_progress(
        self,
        completed: int,
        total: int,
        success: int,
        warnings: int,
        failures: int,
    ) -> None:
        self._progress.setValue(completed)
        self._status.setText(t("bar.converting_progress", done=completed, total=total))
        self._update_res_counters(success, warnings, failures)

    def set_done(
        self,
        success: int,
        warnings: int,
        failures: int,
        cancelled: bool = False,
    ) -> None:
        if cancelled:
            self._status.setText(t("bar.cancelled"))
        else:
            self._status.setText(t("bar.done", total=success + warnings + failures))
        self._progress.hide()
        self._cancel.hide()
        self._convert.show()
        self._convert.setEnabled(True)
        self._update_res_counters(success, warnings, failures)
        self._counters_widget.show()
