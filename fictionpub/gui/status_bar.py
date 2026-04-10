"""
Thin application-level status strip displayed between the file-tree and
the bottom action bar.

Responsibilities
────────────────
• Display a persistent informational hint (current output path mode).
• Accept temporary transient messages from any part of the application
  (future: conversion progress hints, warnings, etc.).

Usage
─────
    bar.show_hint("EPUBs will be saved alongside source files")
    bar.show_hint("Output: /home/user/books")
    # after a transient operation:
    bar.clear_transient()   # reverts to the last hint

Design notes
────────────
A single QLabel. The widget intentionally has no i18n listener of its own:
the caller (MainWindow) handles translation and pushes translated strings in.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


# TODO: remove / rework
class AppStatusBar(QWidget):
    """
    Thin informational strip.

    show_hint(text)      — set persistent context hint (e.g. output path)
    show_message(text)   — show a transient message over the hint
    clear_transient()    — restore the hint after a transient message
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._hint = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 1, 8, 2)
        layout.setSpacing(0)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        # Muted, small — this strip should recede visually
        self._label.setStyleSheet("font-size: 10px; color: palette(mid);")
        layout.addWidget(self._label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_hint(self, text: str) -> None:
        """Update the persistent context hint and display it."""
        self._hint = text
        self._label.setText(text)

    def show_message(self, text: str) -> None:
        """
        Display a transient message over the current hint.
        Call clear_transient() to revert to the hint.
        """
        self._label.setText(text)

    def clear_transient(self) -> None:
        """Revert to the persistent hint after a transient message."""
        self._label.setText(self._hint)

    def clear(self) -> None:
        """Clear both the hint and the displayed text."""
        self._hint = ""
        self._label.clear()
