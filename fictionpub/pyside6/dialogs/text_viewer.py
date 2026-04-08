"""
fictionpub/pyside6/dialogs/text_viewer.py

Shared infrastructure for all monospace text viewer dialogs.

CodeViewer
──────────
QPlainTextEdit subclass with a painted line-number gutter.
Gutter colours use QPalette roles so light / dark themes work without
hardcoded values.

TextViewerDialog
────────────────
Base QDialog that:
  • Shows the OS maximize button in the title bar via
    Qt.WindowMaximizeButtonHint — the correct, expected location on
    every platform.
  • Hosts a CodeViewer with a Wrap-lines checkbox and Copy / Close buttons.
  • Provides extension hooks _build_top_controls(), _extra_bottom_buttons(),
    _attach_highlighter(), set_content().
  • Persists and restores its geometry per dialog variant using QSettings.
  • Computes a sensible default size from the primary screen dimensions.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QRect,
    QSettings,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QFont,
    QPainter,
    QPalette,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import register_listener, t
from ... import app_info


# ─────────────────────────────────────────────────────────────────────────────
# Line-number gutter
# ─────────────────────────────────────────────────────────────────────────────


class _LineNumberArea(QWidget):
    def __init__(self, editor: CodeViewer) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor._gutter_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802
        self._editor._paint_line_numbers(event)


class CodeViewer(QPlainTextEdit):
    """
    Monospace text widget with a line-number gutter.

    Gutter background  → QPalette.AlternateBase
    Number colour      → QPalette.PlaceholderText
    Both roles adapt to the active Fusion palette (light / dark).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._gutter = _LineNumberArea(self)

        self.blockCountChanged.connect(self._on_block_count_changed)
        self.updateRequest.connect(self._on_update_request)
        self._on_block_count_changed(0)

        font_families = ["Hack", "Fira Code", "Consolas", "Lucida Console"]
        font = QFont(font_families, 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    # ── Gutter width ─────────────────────────────────────────────────────────

    def _gutter_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        char_w = self.fontMetrics().horizontalAdvance("9")
        return 6 + char_w * digits + 4

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_block_count_changed(self, _: int) -> None:
        self.setViewportMargins(self._gutter_width(), 0, 0, 0)

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._on_block_count_changed(0)

    # ── Layout ────────────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(
            QRect(cr.left(), cr.top(), self._gutter_width(), cr.height())
        )

    # ── Painting ──────────────────────────────────────────────────────────────

    def _paint_line_numbers(self, event) -> None:
        p = QPainter(self._gutter)
        p.fillRect(event.rect(), self.palette().color(QPalette.ColorRole.AlternateBase))
        p.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))

        block = self.firstVisibleBlock()
        number = block.blockNumber()
        geo = self.blockBoundingGeometry(block).translated(self.contentOffset())
        top = round(geo.top())
        bottom = top + round(self.blockBoundingRect(block).height())
        lh = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                p.drawText(
                    0,
                    top,
                    self._gutter.width() - 4,
                    lh,
                    Qt.AlignmentFlag.AlignRight,
                    str(number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# Base dialog
# ─────────────────────────────────────────────────────────────────────────────


class TextViewerDialog(QDialog):
    """
    Base class for all monospace text viewer / editor dialogs.

    The OS maximize button is enabled via WindowMaximizeButtonHint so it
    appears in the title bar in its standard position — no custom button
    needed in the UI.

    Subclass hooks
    ──────────────
    _build_top_controls() → QWidget | None
        Widget inserted above the editor (filter row, path label, etc.).

    _extra_bottom_buttons() → list[QPushButton]
        Buttons inserted before the Copy button in the bottom row.

    _attach_highlighter() → None
        Bind a QSyntaxHighlighter to self._editor.document().

    set_content(text) → None
        Replace editor content.
    """

    def __init__(
        self,
        *,
        title: str,
        geom_key: str,
        width_fraction: float = 0.60,
        height_fraction: float = 0.85,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Add the OS-native maximize button to the title bar.
        # WA_DeleteOnClose + WindowCloseButtonHint are already present by
        # default on QDialog; we just OR in the maximize hint.
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinimizeButtonHint)

        self._geom_key = f"geometry/{geom_key}"
        self._width_fraction = width_fraction
        self._height_fraction = height_fraction

        self._build_base_ui()
        self._attach_highlighter()
        register_listener(self._retranslate_base)

    # ── Base UI ───────────────────────────────────────────────────────────────

    def _build_base_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(6)
        outer.setContentsMargins(8, 8, 8, 8)

        top = self._build_top_controls()
        if top is not None:
            outer.addWidget(top)

        self._editor = CodeViewer()
        outer.addWidget(self._editor, stretch=1)

        # ── Bottom row ────────────────────────────────────────────────────────
        bottom = QHBoxLayout()

        self._wrap_cb = QCheckBox()
        self._wrap_cb.toggled.connect(self._on_wrap_toggled)
        bottom.addWidget(self._wrap_cb)
        bottom.addStretch()

        for btn in self._extra_bottom_buttons():
            bottom.addWidget(btn)

        self._copy_btn = QPushButton()
        self._copy_btn.clicked.connect(self._copy_all)
        bottom.addWidget(self._copy_btn)

        self._close_btn = QPushButton()
        self._close_btn.clicked.connect(self.close)
        bottom.addWidget(self._close_btn)

        outer.addLayout(bottom)
        self._retranslate_base()

    # ── Extension points ──────────────────────────────────────────────────────

    def _build_top_controls(self) -> QWidget | None:
        return None

    def _extra_bottom_buttons(self) -> list[QPushButton]:
        return []

    def _attach_highlighter(self) -> None:
        pass

    # ── i18n ─────────────────────────────────────────────────────────────────

    def _retranslate_base(self) -> None:
        self._wrap_cb.setText(t("settings.wrap_lines"))
        self._copy_btn.setText(t("dlg.copy"))
        self._close_btn.setText(t("dlg.close"))

    # ── Content ───────────────────────────────────────────────────────────────

    def set_content(self, text: str) -> None:
        self._editor.setPlainText(text)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_wrap_toggled(self, checked: bool) -> None:
        self._editor.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if checked
            else QPlainTextEdit.LineWrapMode.NoWrap
        )

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(self._editor.toPlainText())

    # ── Geometry persistence ──────────────────────────────────────────────────

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        s = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            app_info.APP_ORG,
            app_info.APP_NAME_SHORT,
        )
        raw = s.value(self._geom_key)
        if raw:
            self.restoreGeometry(raw)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            w = int(screen.width() * self._width_fraction)
            h = int(screen.height() * self._height_fraction)
            self.resize(w, h)
            # Centre on screen
            self.move(
                screen.left() + (screen.width() - w) // 2,
                screen.top() + (screen.height() - h) // 2,
            )

    def closeEvent(self, event) -> None:  # noqa: N802
        s = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            app_info.APP_ORG,
            app_info.APP_NAME_SHORT,
        )
        s.setValue(self._geom_key, self.saveGeometry())
        super().closeEvent(event)
