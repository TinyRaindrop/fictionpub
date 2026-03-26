"""
Bottom bar: status text | progress bar | counters | log access | Convert / Cancel.
Supports runtime language switching.
"""

from PySide6.QtCore import Signal
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


def _vsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


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

        self._status = QLabel()
        self._status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setFixedWidth(220)
        self._progress.setTextVisible(True)
        self._progress.hide()
        layout.addWidget(self._progress)

        self._counters = QLabel()
        self._counters.hide()
        layout.addWidget(self._counters)

        layout.addWidget(_vsep())

        self._logs_dir = QPushButton()
        self._logs_dir.setFlat(True)
        self._logs_dir.clicked.connect(self.openLogsDirRequested)
        layout.addWidget(self._logs_dir)

        self._last_log = QPushButton()
        self._last_log.setFlat(True)
        self._last_log.clicked.connect(self.openLastLogRequested)
        layout.addWidget(self._last_log)

        layout.addWidget(_vsep())

        self._cancel = QPushButton()
        self._cancel.clicked.connect(self.cancelRequested)
        self._cancel.hide()
        layout.addWidget(self._cancel)

        self._convert = QPushButton()
        self._convert.setObjectName("convertButton")
        self._convert.setMinimumWidth(100)
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

    # ------------------------------------------------------------------
    # State transitions — all called from MainWindow on the main thread
    # ------------------------------------------------------------------

    def set_idle(self, message: str | None = None) -> None:
        self._status.setText(message if message is not None else t("bar.ready"))
        self._progress.hide()
        self._cancel.hide()
        self._convert.show()
        self._convert.setEnabled(True)
        self._counters.hide()

    def set_scanning(self) -> None:
        self._status.setText(t("bar.scanning"))
        self._convert.setEnabled(False)

    def set_converting(self, total: int) -> None:
        self._status.setText(t("bar.converting_n", n=total))
        self._progress.setRange(0, total)
        self._progress.setValue(0)
        self._progress.show()
        self._convert.hide()
        self._cancel.show()
        self._cancel.setEnabled(True)
        self._counters.hide()

    def set_cancelling(self) -> None:
        """Called after the user clicks Cancel; disables the button to avoid double-fire."""
        self._status.setText(t("bar.cancelling"))
        self._cancel.setEnabled(False)

    def update_progress(self, completed: int, total: int,
                        success: int, warnings: int, failures: int) -> None:
        self._progress.setValue(completed)
        self._status.setText(t("bar.converting_progress", done=completed, total=total))
        self._counters.setText(f"  ✅ {success}   ⚠ {warnings}   ❌ {failures}")
        self._counters.show()

    def set_done(self, success: int, warnings: int, failures: int,
                 cancelled: bool = False) -> None:
        if cancelled:
            self._status.setText(t("bar.cancelled"))
        else:
            total = success + warnings + failures
            self._status.setText(t("bar.done", total=total))
        self._progress.hide()
        self._cancel.hide()
        self._convert.show()
        self._convert.setEnabled(True)
        self._counters.setText(f"  ✅ {success}   ⚠ {warnings}   ❌ {failures}")
        self._counters.show()


