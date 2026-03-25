"""
Non-modal dialog for viewing log output.
Can display per-file logs (from ConversionResult.log_output)
or a full log file read from disk.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class LogViewerDialog(QDialog):
    """Modeless dialog that displays a block of log text with live filtering."""

    def __init__(self, content: str, title: str = "Log Viewer", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(700, 450)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._full_content = content

        self._build_ui()
        self._text.setPlainText(content)

    @classmethod
    def from_file(cls, path: Path, parent=None) -> "LogViewerDialog":
        """Open a log file from disk."""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            content = f"Could not read log file:\n{e}"
        return cls(content, title=f"Log — {path.name}", parent=parent)

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Type to filter lines…")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._filter)
        layout.addLayout(filter_row)

        # Log text
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._text.setFont(font)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._text)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = QPushButton("Copy All")
        copy_btn.clicked.connect(self._copy_all)
        btn_row.addWidget(copy_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _apply_filter(self, text: str) -> None:
        if not text:
            self._text.setPlainText(self._full_content)
            return
        lower = text.lower()
        filtered = "\n".join(
            line for line in self._full_content.splitlines()
            if lower in line.lower()
        )
        self._text.setPlainText(filtered)

    def _copy_all(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._text.toPlainText())
