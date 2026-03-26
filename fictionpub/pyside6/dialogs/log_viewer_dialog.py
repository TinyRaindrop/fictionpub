"""
Non-modal log viewer dialog with level filter radio buttons and text search.

Features:
  - Radio button filter: All / Warnings / Errors (level keywords in log lines)
  - Text search box that narrows within the active radio filter
  - Live line count
  - Copy All button

Listener cleanup: WeakMethod in i18n core handles GC automatically.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from ..i18n import register_listener, t

_WARNING_KEYWORDS = ("WARNING", "WARN")
_ERROR_KEYWORDS   = ("ERROR", "CRITICAL", "FAIL")


def _line_matches_level(line: str, level: str) -> bool:
    """Return True if the line belongs to the given level category."""
    upper = line.upper()
    if level == "warnings":
        return any(k in upper for k in _WARNING_KEYWORDS)
    if level == "errors":
        return any(k in upper for k in _ERROR_KEYWORDS)
    return True


class LogViewerDialog(QDialog):
    """Modeless dialog that displays a block of log text with level + text filtering."""

    def __init__(self, content: str, title: str = "Log Viewer", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(780, 500)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._full_content = content

        self._build_ui()
        self._apply_filters()

        register_listener(self._retranslate_ui)

    @classmethod
    def from_file(cls, path: Path, parent=None) -> "LogViewerDialog":
        """Open a log file from disk."""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            content = f"Could not read log file:\n{e}"
        return cls(content, title=t("logviewer.title_file", name=path.name), parent=parent)
    
    # -----------------------
    # UI construction

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Filter row
        top_row = QHBoxLayout()
        self._lbl_filter = QLabel()
        top_row.addWidget(self._lbl_filter)

        # Radio buttons
        self._radio_group = QButtonGroup(self)
        self._radio_all   = QRadioButton()
        self._radio_warn  = QRadioButton()
        self._radio_err   = QRadioButton()
        self._radio_all.setChecked(True)

        for rb in (self._radio_all, self._radio_warn, self._radio_err):
            self._radio_group.addButton(rb)
            top_row.addWidget(rb)

        top_row.addSpacing(12)

        # Text search
        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(200)
        top_row.addWidget(self._search, stretch=1)
        layout.addLayout(top_row)

        # Log text
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._text.setFont(font)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._text)

        # Bottom row
        bottom_row = QHBoxLayout()
        self._line_count = QLabel()
        bottom_row.addWidget(self._line_count)
        bottom_row.addStretch()
        copy_btn = QPushButton()
        copy_btn.clicked.connect(self._copy_all)
        bottom_row.addWidget(copy_btn)
        self._copy_btn = copy_btn
        close_btn = QPushButton()
        close_btn.clicked.connect(self.close)
        bottom_row.addWidget(close_btn)
        self._close_btn = close_btn
        layout.addLayout(bottom_row)

        # Connect filters
        self._radio_all.toggled.connect(self._apply_filters)
        self._radio_warn.toggled.connect(self._apply_filters)
        self._radio_err.toggled.connect(self._apply_filters)
        self._search.textChanged.connect(self._apply_filters)

        self._retranslate_ui()

    # -----------------------
    # Filtering logic

    def _active_level(self) -> str:
        if self._radio_warn.isChecked(): return "warnings"
        if self._radio_err.isChecked():  return "errors"
        return "all"

    def _apply_filters(self, *_) -> None:
        level      = self._active_level()
        search_txt = self._search.text().lower()
        filtered   = [
            line for line in self._full_content.splitlines()
            if _line_matches_level(line, level)
            and (not search_txt or search_txt in line.lower())
        ]
        self._text.setPlainText("\n".join(filtered))
        n = len(filtered)
        self._line_count.setText(f"{n} line{'s' if n != 1 else ''}")

    # -----------------------
    # Actions
    def _copy_all(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._text.toPlainText())

    # -----------------------
    # i18n
    def _retranslate_ui(self) -> None:
        self._lbl_filter.setText(t("logviewer.filter_label"))
        self._radio_all.setText(t("logviewer.filter_all"))
        self._radio_warn.setText(t("logviewer.filter_warnings"))
        self._radio_err.setText(t("logviewer.filter_errors"))
        self._search.setPlaceholderText(t("logviewer.filter_tip"))
        self._copy_btn.setText(t("dlg.copy"))
        self._close_btn.setText(t("dlg.close"))
