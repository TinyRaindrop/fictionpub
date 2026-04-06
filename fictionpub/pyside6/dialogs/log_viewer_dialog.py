r"""
fictionpub/pyside6/dialogs/log_viewer_dialog.py

Non-modal log viewer built on TextViewerDialog.

Filtering strategy  (single linear pass, no intermediate objects)
──────────────────────────────────────────────────────────────────
For every line in the source content:

  m_start  (--- Log for FILE ---)
      Always emit.  Begin accumulating a block.

  m_end    (--- End log for FILE ---)
      If the accumulated block has content lines → emit header, content,
      footer.  If empty (all lines were filtered) → suppress header,
      footer, and the one blank line that follows (per-user spec).

  m_log    (structured log line: "DATE? TIME [PID] LEVEL - ...")
      If level ≥ selected minimum → emit.  Set skip_continuation=False.
      Otherwise → drop.  Set skip_continuation=True.

  anything else  (blank lines, Traceback, bare exception text)
      If skip_continuation is True → drop (continuation of a filtered
      line).  Otherwise → emit as-is.  This preserves Tracebacks with
      their ERROR line and preserves blank lines between sections.

suppress_next_blank
      Set to True when an empty block or a search-miss block is skipped.
      The one blank line immediately following is consumed without output.
      This avoids leaving double-blank gaps where a filtered block was.

Blank lines before m_start and after m_end
      These live outside any block and are handled by the "anything else"
      branch (skip_continuation starts as False, so they pass through).
      No second pass is needed, so no trailing-blank stripping occurs.

Regex (_RE_LOG_LINE)
      Handles both logger formats produced by the app:
        Old worker:  "HH:MM:SS [PID] LEVEL - ..."     (no date)
        Outer batch: "YYYY-MM-DD HH:MM:SS [PID] LEVEL - ..."

      Pattern: r'^\S+ (?:\S+ )?\[\d+\] (LEVEL) - '
        ^\S+          = first token  (time OR date)
        (?:\S+ )?     = optional second token (time, when date was first)
        \[\d+\]       = [PID]
        (LEVEL) - '   = level word

      Regex engine backtracks correctly: if the optional group consumes
      [PID], the following \[\d+\] fails, so the engine retries without
      the optional group and finds [PID] at the original position.

Text search
      Applied at block level: the search string must appear somewhere in
      the block's filtered lines (or its header) for the block to be
      emitted.  Non-block lines are never suppressed by search.

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

from ..i18n import register_listener, t
from .highlighters import LogSyntaxHighlighter
from .text_viewer import TextViewerDialog

# TODO: add log folder view with a file list. Parse last log line and display number of processed files
# [Date | Time | Total files | Success | Warnings | Errors]
# App should write a unified final report line (in gui and cli), which would then be read by Log folder parser
# Display [ok|warn|err] status icons or [?] if report line is not found.

# ─────────────────────────────────────────────────────────────────────────────
# Patterns and level table
# ─────────────────────────────────────────────────────────────────────────────

_RE_BLOCK_START = re.compile(r"^---\s+Log for\s+(.+?)\s+---\s*$")
_RE_BLOCK_END = re.compile(r"^---\s+End log for\s+.+?\s+---\s*$")

# Matches log lines produced by both logger configurations:
#   HH:MM:SS [PID] LEVEL - ...
#   YYYY-MM-DD HH:MM:SS [PID] LEVEL - ...
# The optional (?:\S+ )? handles the extra date token.
_RE_LOG_LINE = re.compile(r"^\S+ (?:\S+ )?\[\d+\] (DEBUG|INFO|WARNING|ERROR|CRITICAL) - ")

_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_LEVEL_IDX = {lv: i for i, lv in enumerate(_LEVELS)}


# ─────────────────────────────────────────────────────────────────────────────
# Single-pass renderer
# ─────────────────────────────────────────────────────────────────────────────


def _render(content: str, min_level_idx: int, search: str) -> str:
    result: list[str] = []

    in_block = False
    pending_header = ""
    block_lines: list[str] = []
    skip_continuation = False
    suppress_next_blank = False  # consume one blank after a skipped block

    for line in content.splitlines():
        m_start = _RE_BLOCK_START.match(line)
        m_end = _RE_BLOCK_END.match(line)
        m_log = _RE_LOG_LINE.match(line)

        # ── Block start ───────────────────────────────────────────────────────
        if m_start:
            suppress_next_blank = False
            in_block = True
            pending_header = line
            block_lines = []
            skip_continuation = False

        # ── Block end ─────────────────────────────────────────────────────────
        elif m_end and in_block:
            in_block = False
            if block_lines:
                keep: bool = (
                    not search
                    or search.lower()
                    in (pending_header + "\n" + "\n".join(block_lines)).lower()
                )
                if keep:
                    result.append(pending_header)
                    result.extend(block_lines)
                    result.append(line)
                    suppress_next_blank = False
                else:
                    # Search miss: drop block + the one following blank
                    suppress_next_blank = True
            else:
                # All lines were level-filtered: drop header, footer, + one blank
                suppress_next_blank = True
            pending_header = ""
            block_lines = []
            skip_continuation = False

        # ── Structured log line ───────────────────────────────────────────────
        elif m_log:
            level = m_log.group(1)
            if _LEVEL_IDX.get(level, 0) >= min_level_idx:
                skip_continuation = False
                suppress_next_blank = False
                (block_lines if in_block else result).append(line)
            elif in_block:
                skip_continuation = True  # drop this line + its continuations

        # ── Blank line / Traceback / other continuation ───────────────────────
        else:
            if suppress_next_blank and not line.strip():
                pass
                # suppress_next_blank = False  # consume exactly one blank
            elif not skip_continuation:
                suppress_next_blank = False
                (block_lines if in_block else result).append(line)
            # if skip_continuation: drop (continuation of a filtered log line)

    return "\n".join(result)


# ─────────────────────────────────────────────────────────────────────────────
# Dialog
# ─────────────────────────────────────────────────────────────────────────────


class LogViewerDialog(TextViewerDialog):
    """
    Modeless log viewer with level filtering and text search.

    Level radios:  All | Info | Warning | Error
    Text search:   substring match at block level (keeps traceback context)
    """

    def __init__(
        self,
        content: str,
        title: str = "Log Viewer",
        parent=None,
    ) -> None:
        self._raw_content = content

        super().__init__(
            title=title,
            geom_key="log_viewer",
            width_fraction=0.80,
            height_fraction=0.85,
            parent=parent,
        )

        self._editor.setReadOnly(True)
        self._apply_filters()
        register_listener(self._retranslate_controls)

    @classmethod
    def from_file(cls, path: Path, parent=None) -> LogViewerDialog:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            content = f"Could not read log file:\n{e}"
        return cls(
            content,
            title=t("logviewer.title_file", name=path.name),
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
        """Return the minimum _LEVELS index for the selected radio."""
        # button ids: 0=All(DEBUG=0), 1=Info, 2=Warning, 3=Error
        return {0: 0, 1: 1, 2: 2, 3: 3}.get(self._level_group.checkedId(), 0)

    def _apply_filters(self) -> None:
        text = _render(
            self._raw_content,
            self._min_level_idx(),
            self._search.text(),
        )
        self._editor.setPlainText(text)
        n = text.count("\n") + 1 if text.strip() else 0
        self._lbl_count.setText(f"{n} line{'s' if n != 1 else ''}")
