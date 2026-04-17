"""
Non-modal CSS viewer / editor built on TextViewerDialog.

Two modes
─────────
editable=False  Read-only view of the built-in default stylesheet.
                A grey italic notice confirms edits are not saved.
editable=True   Editable; Save button writes changes back to disk.

Both modes share:
  * CssSyntaxHighlighter for /* comments */, @rules, properties, strings,
    hex colours, numbers+units, and !important
  * "Wrap lines" checkbox
  * "Copy All" button
  * Monospace font

The dialog is non-modal (show(), not exec()) so the user can keep it
open alongside the settings dialog.  WA_DeleteOnClose + WeakMethod in
the i18n registry mean no manual cleanup is required.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import register_listener, t
from .highlighters import CssSyntaxHighlighter
from .text_viewer import TextViewerDialog


class CSSViewerDialog(TextViewerDialog):
    """Modeless CSS viewer / editor with syntax highlighting."""

    def __init__(
        self,
        path: Path | None,
        *,
        editable: bool = False,
        title: str = "CSS Viewer",
        parent=None,
    ) -> None:
        self._path = path
        self._editable = editable and path is not None

        super().__init__(
            title=title,
            geom_key="css_viewer",
            width_fraction=0.50,
            height_fraction=0.85,
            parent=parent,
        )

        self._editor.setReadOnly(not self._editable)
        self._load_content()
        register_listener(self._retranslate_controls)

    # ── Extension points ──────────────────────────────────────────────────────

    def _build_top_controls(self) -> QWidget:
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 2)
        vbox.setSpacing(2)

        self._path_label = QLabel()
        self._path_label.setWordWrap(True)
        self._path_label.setStyleSheet("font-size: 10px; color: palette(mid);")
        vbox.addWidget(self._path_label)

        if not self._editable:
            self._ro_label = QLabel()
            self._ro_label.setStyleSheet(
                "color: palette(mid); font-style: italic; font-size: 10px;"
            )
            vbox.addWidget(self._ro_label)

        self._retranslate_controls()
        return container

    def _extra_bottom_buttons(self) -> list[QPushButton]:
        if not self._editable:
            return []
        self._save_btn = QPushButton()
        self._save_btn.clicked.connect(self._save)
        return [self._save_btn]

    def _attach_highlighter(self) -> None:
        self._highlighter = CssSyntaxHighlighter(self._editor.document())

    # ── i18n ─────────────────────────────────────────────────────────────────

    def _retranslate_controls(self) -> None:
        self._path_label.setText(str(self._path) if self._path else t("cssviewer.no_file"))
        if not self._editable and hasattr(self, "_ro_label"):
            self._ro_label.setText(t("cssviewer.readonly_note"))
        if self._editable and hasattr(self, "_save_btn"):
            self._save_btn.setText(t("dlg.save"))

    # ── Content ───────────────────────────────────────────────────────────────

    def _load_content(self) -> None:
        if self._path and self._path.is_file():
            try:
                with open(self._path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError as exc:
                text = f"/* Could not read file:\n   {exc} */"
        else:
            text = "/* File not found */"
        self.set_content(text)

    # ── Actions ───────────────────────────────────────────────────────────────

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
