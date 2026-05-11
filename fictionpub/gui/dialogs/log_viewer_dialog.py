r"""
Non-modal log viewer built on TextViewerDialog.

Log structure
─────────────
The log contains two kinds of content:

  1. Outer lines — emitted by the main process, directly to the file:
         2026-04-07 13:32:08 [10216] LEVEL - [module:line] - message

  2. File blocks — buffered worker output, wrapped in boundary markers:
         --- Log for filename.fb2 ---
         13:32:26 [2516] LEVEL - [module:line] - message
         ...
         --- End log for filename.fb2 ---

     Worker lines omit the date token; the shared _RE_LOG_LINE regex
     handles both timestamp formats.

Filtering — _render()
──────────────────────
Level filter (applied first):
  Lines matching _RE_LOG_LINE with level < min_level_idx are dropped.
  All other lines — block wrappers, tracebacks, blank lines — pass
  through unchanged. This matches the expected behaviour where a
  traceback stays with its ERROR line because neither the traceback
  lines nor the wrappers match _RE_LOG_LINE.

Search filter (applied on top of level-filtered content):
  Blocks   — block-level: if no line in the filtered block (including
             the header) contains the search term the whole block is
             suppressed.
  Non-block lines — line-level: blank lines always pass; other lines
             must contain the search term.

Empty-block suppression:
  When a block has no remaining lines after level/search filtering,
  its header, footer, and the blank lines that immediately follow the
  footer are all dropped.

Level radios: All | Info | Warning | Error
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QWidget,
)

from fictionpub.gui.i18n import register_listener, t
from fictionpub.gui.state.settings import GeometryStore

from .highlighters import LogSyntaxHighlighter
from .text_viewer import TextViewerDialog

# ─────────────────────────────────────────────────────────────────────────────
# Patterns and level table
# ─────────────────────────────────────────────────────────────────────────────

_RE_BLOCK_START = re.compile(r"^---\s+Log for\s+(.+?)\s+---\s*$")
_RE_BLOCK_END = re.compile(r"^---\s+End log for\s+.+?\s+---\s*$")

# Handles both logger timestamp formats produced by the app:
#   HH:MM:SS [PID] LEVEL - ...              (worker, no date prefix)
#   YYYY-MM-DD HH:MM:SS [PID] LEVEL - ...  (main process, date + time)
#
# Pattern breakdown:
#   ^\S+          first token  (time OR date)
#   (?:\S+ )?     optional second token (time, when date came first)
#   \[\d+\]       [PID]
#   (LEVEL) -     captured level word
_RE_LOG_LINE = re.compile(r"^\S+ (?:\S+ )?\[\d+\] (DEBUG|INFO|WARNING|ERROR|CRITICAL) - ")

_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_LEVEL_IDX: dict[str, int] = {lv: i for i, lv in enumerate(_LEVELS)}


# ─────────────────────────────────────────────────────────────────────────────
# Renderer
# ─────────────────────────────────────────────────────────────────────────────


def _render(content: str, min_level_idx: int, search: str) -> str:
    """
    Return a filtered view of *content*.

    Parameters
    ----------
    content       : raw log text
    min_level_idx : index into _LEVELS; log lines below this level are dropped
    search        : case-insensitive substring; empty string disables search
    """
    search_lower = search.strip().lower()
    result: list[str] = []
    lines = content.splitlines()
    n = len(lines)
    i = 0

    def _passes_level(line: str) -> bool:
        """True when *line* is not a log line, or its level meets the threshold."""
        m = _RE_LOG_LINE.match(line)
        return not m or _LEVEL_IDX.get(m.group(1), 0) >= min_level_idx

    def _skip_trailing_blanks() -> None:
        """Advance *i* past any blank lines that follow a suppressed block."""
        nonlocal i
        while i < n and not lines[i].strip():
            i += 1

    while i < n:
        line = lines[i]

        # ── File block ────────────────────────────────────────────────────
        if _RE_BLOCK_START.match(line):
            header = line
            body: list[str] = []
            footer = ""
            i += 1

            # Collect body lines until the closing boundary (or EOF)
            while i < n and not _RE_BLOCK_END.match(lines[i]):
                body.append(lines[i])
                i += 1

            if i < n:  # found the closing boundary
                footer = lines[i]
                i += 1

            # ── Level filter: only structured log lines are candidates ────
            filtered = [bl for bl in body if _passes_level(bl)]

            # ── Search: block-level ------------------------------─────────
            # If in header, include entire block, else filter lines
            if search_lower and search_lower not in header:
                filtered = [fl for fl in filtered if search_lower in fl]

            # ── Empty block after filters -> skip + skip blanks ───
            if not filtered:
                _skip_trailing_blanks()
                continue

            # ── Emit the block ────────────────────────────────────────────
            result.append(header)
            result.extend(filtered)
            if footer:
                result.append(footer)
            continue

        # ── Non-block line ────────────────────────────────────────────────
        i += 1

        if not _passes_level(line):
            continue

        # Search: line-level; blank lines always pass through
        if search_lower and line.strip() and search_lower not in line.lower():
            continue

        result.append(line)

    return "\n".join(result)


# ─────────────────────────────────────────────────────────────────────────────
# Dialog
# ─────────────────────────────────────────────────────────────────────────────


class LogViewerDialog(TextViewerDialog):
    """
    Modeless log viewer with level filtering and text search.

    Level radios:  All | Info | Warning | Error
    Text search:   substring match; blocks matched at block level,
                   non-block lines matched per-line.
    """

    def __init__(
        self,
        content: str,
        *,
        title: str = "Log Viewer",
        geom: GeometryStore | None = None,
        parent=None,
    ) -> None:
        self._raw_content = content

        super().__init__(
            title=title,
            geom=geom,
            geom_key="log_viewer",
            width_fraction=0.80,
            height_fraction=0.85,
            parent=parent,
        )

        self._editor.setReadOnly(True)
        self._apply_filters()
        register_listener(self._retranslate_controls)

    @classmethod
    def from_file(
        cls, path: Path, geom: GeometryStore | None = None, parent=None
    ) -> LogViewerDialog:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            content = f"Could not read log file:\n{e}"
        return cls(
            content,
            title=t("logviewer.title_file", name=path.name),
            geom=geom,
            parent=parent,
        )

    # ── Extension points ──────────────────────────────────────────────────────

    def _build_top_controls(self) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self._lbl_filter = QLabel()
        row.addWidget(self._lbl_filter)

        self._level_group = QButtonGroup(self)
        self._radio_all = QRadioButton()
        self._radio_info = QRadioButton()
        self._radio_warn = QRadioButton()
        self._radio_err = QRadioButton()
        self._radio_all.setChecked(True)

        for i, rb in enumerate(
            (self._radio_all, self._radio_info, self._radio_warn, self._radio_err)
        ):
            self._level_group.addButton(rb, i)
            row.addWidget(rb)

        row.addSpacing(12)

        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(200)
        row.addWidget(self._search, stretch=1)

        self._lbl_count = QLabel()
        row.addWidget(self._lbl_count)

        # Signals
        self._level_group.idToggled.connect(
            lambda _id, checked: checked and self._apply_filters()
        )
        self._search.textChanged.connect(lambda _: self._apply_filters())

        self._retranslate_controls()
        return container

    def _attach_highlighter(self) -> None:
        self._highlighter = LogSyntaxHighlighter(self._editor.document())

    # ── i18n ─────────────────────────────────────────────────────────────────

    def _retranslate_controls(self) -> None:
        self._lbl_filter.setText(t("logviewer.filter_label"))
        self._radio_all.setText(t("logviewer.filter_all"))
        self._radio_info.setText(t("logviewer.filter_info"))
        self._radio_warn.setText(t("logviewer.filter_warnings"))
        self._radio_err.setText(t("logviewer.filter_errors"))
        self._search.setPlaceholderText(t("logviewer.filter_tip"))

    # ── Filtering ─────────────────────────────────────────────────────────────

    def _min_level_idx(self) -> int:
        """Map radio button id (0-3) → minimum _LEVELS index (DEBUG-ERROR)."""
        # id 0 = All  → DEBUG  (0)
        # id 1 = Info → INFO   (1)
        # id 2 = Warn → WARNING(2)
        # id 3 = Err  → ERROR  (3)
        return self._level_group.checkedId()

    def _apply_filters(self) -> None:
        text = _render(
            self._raw_content,
            self._min_level_idx(),
            self._search.text(),
        )
        self._editor.setPlainText(text)
        n = text.count("\n") + 1 if text.strip() else 0
        self._lbl_count.setText(f"{n} line{'s' if n != 1 else ''}")
