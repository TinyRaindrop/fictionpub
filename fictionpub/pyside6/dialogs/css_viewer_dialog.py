"""
fictionpub/pyside6/dialogs/css_viewer_dialog.py

Non-modal CSS viewer / editor dialog.

Two modes
---------
editable=False  Read-only view of the built-in default stylesheet.
                A grey italic notice confirms that edits are not saved.
editable=True   Fully editable view of a user-supplied file, with a
                Save button that writes changes back to disk.

Both modes share:
  • CssSyntaxHighlighter for /* comments */, @rules, properties, strings,
    hex colours, numbers+units, and !important
  • "Wrap lines" checkbox
  • "Copy All" button
  • Monospace font

The dialog is non-modal (show(), not exec()) so the user can keep it
open alongside the settings dialog.  WA_DeleteOnClose + WeakMethod in
the i18n registry mean no manual cleanup is required.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..i18n import register_listener, t
from .highlighters import CssSyntaxHighlighter


class CSSViewerDialog(QDialog):
    """Modeless dialog to view (and optionally edit) a CSS file."""

    def __init__(
        self,
        path: Path | None,
        *,
        editable: bool = False,
        title: str = "CSS Viewer",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(740, 560)
        self.resize(820, 720)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._path     = path
        self._editable = editable and path is not None

        self._build_ui()
        self._load_content()
        register_listener(self._retranslate_ui)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── File path banner ────────────────────────────────────────────
        self._path_label = QLabel()
        self._path_label.setWordWrap(True)
        self._path_label.setStyleSheet(
            "font-size: 10px; color: palette(mid);"
        )
        layout.addWidget(self._path_label)

        # ── Read-only notice (built-in stylesheet only) ──────────────────
        if not self._editable:
            self._ro_label = QLabel()
            self._ro_label.setStyleSheet(
                "color: palette(mid); font-style: italic; font-size: 10px;"
            )
            layout.addWidget(self._ro_label)

        # ── Editor ──────────────────────────────────────────────────────
        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(not self._editable)
        font = QFont("Courier New", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._editor.setFont(font)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._editor)

        # Attach syntax highlighter to the editor's document
        self._highlighter = CssSyntaxHighlighter(self._editor.document())

        # ── Bottom row ──────────────────────────────────────────────────
        bottom = QHBoxLayout()

        self._wrap_cb = QCheckBox()
        self._wrap_cb.toggled.connect(self._on_wrap_toggled)
        bottom.addWidget(self._wrap_cb)

        bottom.addStretch()

        self._copy_btn = QPushButton()
        self._copy_btn.clicked.connect(self._copy_all)
        bottom.addWidget(self._copy_btn)

        if self._editable:
            self._save_btn = QPushButton()
            self._save_btn.clicked.connect(self._save)
            bottom.addWidget(self._save_btn)

        self._close_btn = QPushButton()
        self._close_btn.clicked.connect(self.close)
        bottom.addWidget(self._close_btn)

        layout.addLayout(bottom)

        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self._path_label.setText(
            str(self._path) if self._path else t("cssviewer.no_file")
        )
        if not self._editable and hasattr(self, "_ro_label"):
            self._ro_label.setText(t("cssviewer.readonly_note"))

        self._wrap_cb.setText(t("settings.wrap_lines"))
        self._copy_btn.setText(t("dlg.copy"))
        if self._editable and hasattr(self, "_save_btn"):
            self._save_btn.setText(t("dlg.save"))
        self._close_btn.setText(t("dlg.close"))

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def _load_content(self) -> None:
        if self._path and self._path.is_file():
            try:
                text = self._path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                text = f"/* Could not read file:\n   {exc} */"
        else:
            text = "/* File not found */"
        self._editor.setPlainText(text)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_wrap_toggled(self, checked: bool) -> None:
        mode = (
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if checked
            else QPlainTextEdit.LineWrapMode.NoWrap
        )
        self._editor.setLineWrapMode(mode)

    def _copy_all(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._editor.toPlainText())

    def _save(self) -> None:
        if not self._path:
            return
        try:
            self._path.write_text(self._editor.toPlainText(), encoding="utf-8")
            QMessageBox.information(
                self,
                t("cssviewer.saved_title"),
                t("cssviewer.saved_text", path=str(self._path)),
            )
        except OSError as exc:
            QMessageBox.critical(
                self,
                t("cssviewer.error_title"),
                t("cssviewer.error_text", error=str(exc)),
            )