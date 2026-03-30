"""
Bottom bar: status | progress | counters | logs | Convert/Cancel.

Layout stability
----------------
The progress bar and Cancel button use setRetainSizeWhenHidden(True) so
their layout slot is preserved even when they are hidden.  This means
nothing shifts when conversion starts or finishes.

Counter label is always visible (shows "✅ 0  ⚠ 0  ❌ 0" at idle) for the
same reason — it has a fixed minimum width, so it never causes reflow.

Visual order (left → right):
  [status text]  [progress bar]  [counters]  │  [📂 Logs]  [📋 Last]  │  [Cancel]  [Convert]
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

from .i18n import register_listener, t


_LOG_BTN_QSS = """
QPushButton {
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 2px 8px;
    background: transparent;
}
QPushButton:hover {
    background-color: rgba(128, 128, 128, 0.20);
    border: 1px solid rgba(128, 128, 128, 0.35);
}
QPushButton:pressed {
    background-color: rgba(128, 128, 128, 0.35);
}
"""


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


class BottomBarWidget(QWidget):
    convertRequested     = Signal()
    cancelRequested      = Signal()
    openLogsDirRequested = Signal()
    openLastLogRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self._build_ui()
        self.set_idle()
        register_listener(self._retranslate_ui)

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Status — left-aligned, takes available space
        self._status = QLabel()
        self._status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._status.setMinimumWidth(140)
        layout.addWidget(self._status)

        # Progress — fixed width, always in layout (retains space when hidden)
        self._progress = QProgressBar()
        self._progress.setFixedWidth(200)
        self._progress.setTextVisible(True)
        _retain_size(self._progress)
        self._progress.hide()
        layout.addWidget(self._progress)

        # Counters — always visible, fixed minimum width to prevent reflow
        self._counters = QLabel()
        self._counters.setMinimumWidth(130)
        self._counters.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self._counters.hide()
        layout.addWidget(self._counters)

        layout.addWidget(_vsep())

        # Log access
        self._logs_dir = QPushButton()
        self._logs_dir.setStyleSheet(_LOG_BTN_QSS)
        self._logs_dir.clicked.connect(self.openLogsDirRequested)
        layout.addWidget(self._logs_dir)

        self._last_log = QPushButton()
        self._last_log.setStyleSheet(_LOG_BTN_QSS)
        self._last_log.clicked.connect(self.openLastLogRequested)
        layout.addWidget(self._last_log)

        layout.addWidget(_vsep())

        # Cancel — always in layout, retains space when hidden
        self._cancel = QPushButton()
        self._cancel.setMinimumWidth(150)
        # _retain_size(self._cancel)
        self._cancel.clicked.connect(self.cancelRequested)
        self._cancel.hide()
        layout.addWidget(self._cancel)

        # Convert — primary action
        self._convert = QPushButton()
        self._convert.setObjectName("convertButton")
        self._convert.setMinimumWidth(150)
        self._convert.clicked.connect(self.convertRequested)
        layout.addWidget(self._convert)

        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self._logs_dir.setText(t("bar.logs_folder"))
        self._logs_dir.setToolTip(t("tooltip.logs_folder"))
        self._last_log.setText(t("bar.last_log"))
        self._last_log.setToolTip(t("tooltip.last_log"))
        self._cancel.setText(t("bar.cancel"))
        self._convert.setText(t("bar.convert"))

    def _update_counters_label(self, success, warnings, failures) -> None:
        self._counters.setText(
            f"  ✅ {success}   ⚠ {warnings}   ❌ {failures}"
        )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def set_idle(self, message: str | None = None) -> None:
        self._status.setText(message if message is not None else t("bar.ready"))
        self._progress.hide()
        self._cancel.hide()
        self._convert.show()
        self._convert.setEnabled(True)
        self._counters.setText("  ✅ —   ⚠ —   ❌ —")

    def set_scanning(self) -> None:
        self._status.setText(t("bar.scanning"))
        self._convert.setEnabled(False)

    def set_converting(self, total: int) -> None:
        self._status.setText(t("bar.converting_n", n=total))
        self._progress.setRange(0, total)
        self._progress.setValue(0)
        self._progress.show()
        self._counters.show()
        self._update_counters_label(0,0,0)
        self._convert.hide()
        self._cancel.show()
        self._cancel.setEnabled(True)

    def set_cancelling(self) -> None:
        self._status.setText(t("bar.cancelling"))
        self._cancel.setEnabled(False)

    def update_progress(self, completed: int, total: int,
                        success: int, warnings: int, failures: int) -> None:
        self._progress.setValue(completed)
        self._status.setText(
            t("bar.converting_progress", done=completed, total=total)
        )
        self._update_counters_label(success, warnings, failures)

    def set_done(self, success: int, warnings: int, failures: int,
                 cancelled: bool = False) -> None:
        if cancelled:
            self._status.setText(t("bar.cancelled"))
        else:
            self._status.setText(t("bar.done", total=success + warnings + failures))
        self._progress.hide()
        self._cancel.hide()
        self._convert.show()
        self._convert.setEnabled(True)
        self._update_counters_label(success, warnings, failures)
