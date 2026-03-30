"""
fictionpub/pyside6/dialogs/log_viewer_dialog.py

Non-modal log viewer with level filtering, text search, syntax
highlighting, and line-wrap toggle.

Highlighting (LogSyntaxHighlighter, entire line coloured):
  book boundary  --- Log for / --- End log for ---  blue bold
  ERROR / CRITICAL / FAIL                           red
  WARNING / WARN                                    orange
  DEBUG                                             muted gray

Layout
------
  [Filter:] (● All) ( Warn) ( Err)  [search]         □ Wrap lines
  ┌──────────────────────────────────────────────────────────────┐
  │  log text                                                    │
  └──────────────────────────────────────────────────────────────┘
  {N lines}                   [Copy All]  [Close]
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
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
from .highlighters import LogSyntaxHighlighter

_WARNING_KEYWORDS = ("WARNING", "WARN")
_ERROR_KEYWORDS   = ("ERROR", "CRITICAL", "FAIL")


def _line_matches_level(line: str, level: str) -> bool:
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
        self.setMinimumSize(740, 560)
        self.resize(960, 720)
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
        return cls(
            content,
            title=t("logviewer.title_file", name=path.name),
            parent=parent,
        )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Filter / search row ─────────────────────────────────────────
        top_row = QHBoxLayout()

        self._lbl_filter = QLabel()
        top_row.addWidget(self._lbl_filter)

        self._radio_group = QButtonGroup(self)
        self._radio_all   = QRadioButton()
        self._radio_warn  = QRadioButton()
        self._radio_err   = QRadioButton()
        self._radio_all.setChecked(True)

        for rb in (self._radio_all, self._radio_warn, self._radio_err):
            self._radio_group.addButton(rb)
            top_row.addWidget(rb)

        top_row.addSpacing(12)

        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(200)
        top_row.addWidget(self._search, stretch=1)

        top_row.addSpacing(8)

        self._wrap_cb = QCheckBox()
        self._wrap_cb.toggled.connect(self._on_wrap_toggled)
        top_row.addWidget(self._wrap_cb)

        layout.addLayout(top_row)

        # ── Log text ────────────────────────────────────────────────────
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        font = QFont("Courier New", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._text.setFont(font)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._text)

        # Attach syntax highlighter
        self._highlighter = LogSyntaxHighlighter(self._text.document())

        # ── Bottom row ──────────────────────────────────────────────────
        bottom_row = QHBoxLayout()
        self._line_count = QLabel()
        bottom_row.addWidget(self._line_count)
        bottom_row.addStretch()

        self._copy_btn = QPushButton()
        self._copy_btn.clicked.connect(self._copy_all)
        bottom_row.addWidget(self._copy_btn)

        self._close_btn = QPushButton()
        self._close_btn.clicked.connect(self.close)
        bottom_row.addWidget(self._close_btn)

        layout.addLayout(bottom_row)

        # ── Connect filter signals ───────────────────────────────────────
        self._radio_all.toggled.connect(self._apply_filters)
        self._radio_warn.toggled.connect(self._apply_filters)
        self._radio_err.toggled.connect(self._apply_filters)
        self._search.textChanged.connect(self._apply_filters)

        self._retranslate_ui()

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _active_level(self) -> str:
        if self._radio_warn.isChecked():
            return "warnings"
        if self._radio_err.isChecked():
            return "errors"
        return "all"

    def _apply_filters(self, *_) -> None:
        level      = self._active_level()
        search_txt = self._search.text().lower()
        filtered   = [
            line for line in self._full_content.splitlines()
            if _line_matches_level(line, level)
            and (not search_txt or search_txt in line.lower())
        ]
        # setPlainText replaces the whole document; the highlighter re-runs
        # automatically because it is attached to the document.
        self._text.setPlainText("\n".join(filtered))
        n = len(filtered)
        self._line_count.setText(f"{n} line{'s' if n != 1 else ''}")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_wrap_toggled(self, checked: bool) -> None:
        # TODO: save wrap toggle state
        mode = (
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if checked
            else QPlainTextEdit.LineWrapMode.NoWrap
        )
        self._text.setLineWrapMode(mode)

    def _copy_all(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._text.toPlainText())

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------

    def _retranslate_ui(self) -> None:
        self._lbl_filter.setText(t("logviewer.filter_label"))
        self._radio_all.setText(t("logviewer.filter_all"))
        self._radio_warn.setText(t("logviewer.filter_warnings"))
        self._radio_err.setText(t("logviewer.filter_errors"))
        self._search.setPlaceholderText(t("logviewer.filter_tip"))
        self._wrap_cb.setText(t("settings.wrap_lines"))
        self._copy_btn.setText(t("dlg.copy"))
        self._close_btn.setText(t("dlg.close"))