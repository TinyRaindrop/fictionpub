"""
Bottom bar: status text | progress bar | counters | log access | Convert / Cancel.
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


class BottomBarWidget(QWidget):
    convertRequested     = Signal()
    cancelRequested      = Signal()
    openLogsDirRequested = Signal()
    openLastLogRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self._build_ui()
        self.set_idle("Ready")

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Status label
        self._status = QLabel("Ready")
        self._status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._status)

        # Progress bar (hidden when idle)
        self._progress = QProgressBar()
        self._progress.setFixedWidth(220)
        self._progress.setTextVisible(True)
        self._progress.hide()
        layout.addWidget(self._progress)

        # Result counters
        self._counters = QLabel()
        self._counters.hide()
        layout.addWidget(self._counters)

        layout.addWidget(_vsep())

        # Log access
        self._logs_dir = QPushButton("📂 Logs folder")
        self._logs_dir.setFlat(True)
        self._logs_dir.setToolTip("Open the logs directory in your file manager")
        self._logs_dir.clicked.connect(self.openLogsDirRequested)
        layout.addWidget(self._logs_dir)

        self._last_log = QPushButton("📋 Last log")
        self._last_log.setFlat(True)
        self._last_log.setToolTip("View the log from the most recent run")
        self._last_log.clicked.connect(self.openLastLogRequested)
        layout.addWidget(self._last_log)

        layout.addWidget(_vsep())

        # Cancel (hidden while idle)
        self._cancel = QPushButton("Cancel")
        self._cancel.clicked.connect(self.cancelRequested)
        self._cancel.hide()
        layout.addWidget(self._cancel)

        # Convert — primary action
        self._convert = QPushButton("Convert")
        self._convert.setObjectName("convertButton")
        self._convert.setMinimumWidth(100)
        self._convert.clicked.connect(self.convertRequested)
        layout.addWidget(self._convert)

    # ------------------------------------------------------------------
    # State transitions called by MainWindow
    # ------------------------------------------------------------------

    def set_idle(self, message: str = "Ready") -> None:
        self._status.setText(message)
        self._progress.hide()
        self._cancel.hide()
        self._convert.show()
        self._convert.setEnabled(True)
        self._counters.hide()

    def set_scanning(self) -> None:
        self._status.setText("Scanning…")
        self._convert.setEnabled(False)

    def set_converting(self, total: int) -> None:
        self._status.setText(f"Converting {total} file(s)…")
        self._progress.setRange(0, total)
        self._progress.setValue(0)
        self._progress.show()
        self._convert.hide()
        self._cancel.show()
        self._counters.hide()

    def update_progress(self, completed: int, total: int,
                        success: int, warnings: int, failures: int) -> None:
        self._progress.setValue(completed)
        self._status.setText(
            f"Converting… {completed}/{total}"
        )
        self._counters.setText(
            f"  ✅ {success}   ⚠ {warnings}   ❌ {failures}"
        )
        self._counters.show()

    def set_done(self, success: int, warnings: int, failures: int,
                 cancelled: bool = False) -> None:
        if cancelled:
            self._status.setText("Cancelled.")
        else:
            total = success + warnings + failures
            self._status.setText(
                f"Done — {total} file(s) processed."
            )
        self._progress.hide()
        self._cancel.hide()
        self._convert.show()
        self._convert.setEnabled(True)
        self._counters.setText(f"  ✅ {success}   ⚠ {warnings}   ❌ {failures}")
        self._counters.show()


def _vsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep
