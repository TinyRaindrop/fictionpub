"""
fictionpub/pyside6/dialogs/highlighters.py

Lightweight QSyntaxHighlighter subclasses that require no external
libraries — everything is built on Qt's document-model primitives.

CssSyntaxHighlighter
--------------------
Handles multi-line /* block comments */ via block-state tracking (state 1
= inside comment).  All other rules are applied only to non-comment
segments, so strings or at-rules inside a comment are never mis-colored.

Highlight categories and their colors (chosen to be readable on both
light Fusion palette ≈ white and dark Fusion palette ≈ #2d2d2d):
  comments    #6a8a5a  gray-green italic
  @at-rules   #7755bb  medium purple bold
  properties  #2255aa  medium blue
  strings     #bb6600  amber
  #hex colors #228844  medium green
  numbers     #007788  dark teal
  !important  #cc2222  red bold

LogSyntaxHighlighter
--------------------
Colors entire lines based on the most severe keyword found:
  book boundary  --- Log for / --- End log for ---  #2266cc  blue bold
  error/critical/fail                               #cc2222  red
  warning/warn                                      #cc7700  orange
  debug                                             #888888  muted gray
  (anything else)                                   default text color
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _fmt(
    color: str,
    bold: bool = False,
    italic: bool = False,
) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


# ---------------------------------------------------------------------------
# CSS highlighter
# ---------------------------------------------------------------------------

class CssSyntaxHighlighter(QSyntaxHighlighter):
    """
    Highlight CSS source in a QPlainTextEdit / QTextEdit document.

    Block state contract
    --------------------
    0  – normal (default)
    1  – inside a /* block comment */
    """

    _IN_COMMENT = 1

    def __init__(self, document) -> None:
        super().__init__(document)

        self._fmt_comment   = _fmt("#6a8a5a", italic=True)
        self._fmt_atrule    = _fmt("#7755bb", bold=True)
        self._fmt_prop      = _fmt("#2255aa")
        self._fmt_string    = _fmt("#bb6600")
        self._fmt_hex       = _fmt("#228844")
        self._fmt_number    = _fmt("#007788")
        self._fmt_important = _fmt("#cc2222", bold=True)

        _unit = (
            r'(?:px|em|rem|vw|vh|vmin|vmax|pt|pc|cm|mm|in|ms|s|fr'
            r'|deg|rad|turn|ch|ex|dpi|dpcm|dppx|%)'
        )
        # Patterns applied to non-comment segments.
        # Strings are last so they override any false property match inside quotes.
        self._patterns: list[tuple[QRegularExpression, QTextCharFormat]] = [
            (QRegularExpression(r'@[\w-]+'),                             self._fmt_atrule),
            (QRegularExpression(r'#[0-9a-fA-F]{3,8}(?!\w)'),            self._fmt_hex),
            (QRegularExpression(r'\d+(?:\.\d+)?' + _unit + r'?(?!\w)'), self._fmt_number),
            (QRegularExpression(r'!important\b'),                        self._fmt_important),
            # Property names: word chars before a colon (e.g. font-size:)
            (QRegularExpression(r'[\w-]+(?=\s*:)'),                     self._fmt_prop),
            # Strings – applied last to win over property mis-matches inside quotes
            (QRegularExpression(r'"[^"\\]*(?:\\.[^"\\]*)*"'),           self._fmt_string),
            (QRegularExpression(r"'[^'\\]*(?:\\.[^'\\]*)*'"),           self._fmt_string),
        ]

        self._re_cs = QRegularExpression(r'/\*')   # comment start
        self._re_ce = QRegularExpression(r'\*/')   # comment end

    # ------------------------------------------------------------------

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        self.setCurrentBlockState(0)
        pos = 0

        # ── Continue a comment that started on a previous line ──────────
        if self.previousBlockState() == self._IN_COMMENT:
            it = self._re_ce.globalMatch(text)
            if not it.hasNext():
                # Whole line is still inside the comment.
                self.setFormat(0, len(text), self._fmt_comment)
                self.setCurrentBlockState(self._IN_COMMENT)
                return
            m = it.next()
            end = m.capturedEnd()
            self.setFormat(0, end, self._fmt_comment)
            pos = end

        # ── Scan the rest of the line for comment starts ─────────────────
        while pos <= len(text):
            it_cs = self._re_cs.globalMatch(text, pos)
            if it_cs.hasNext():
                cs_match = it_cs.next()
                cs = cs_match.capturedStart()
            else:
                cs = len(text)

            # Apply non-comment patterns to the segment before the comment start
            if cs > pos:
                self._apply_patterns(text, pos, cs)

            if cs == len(text):
                break   # no comment start found; done

            # ── Found '/*' — look for matching '*/' ──────────────────────
            search_from = cs_match.capturedEnd()   # just past '/*'
            it_ce = self._re_ce.globalMatch(text, search_from)
            if it_ce.hasNext():
                ce_match = it_ce.next()
                ce = ce_match.capturedEnd()
                self.setFormat(cs, ce - cs, self._fmt_comment)
                pos = ce
            else:
                # Comment continues into the next block
                self.setFormat(cs, len(text) - cs, self._fmt_comment)
                self.setCurrentBlockState(self._IN_COMMENT)
                break

    def _apply_patterns(self, text: str, start: int, end: int) -> None:
        """Apply all non-comment patterns to text[start:end]."""
        segment = text[start:end]
        for regex, fmt in self._patterns:
            it = regex.globalMatch(segment)
            while it.hasNext():
                m = it.next()
                self.setFormat(
                    start + m.capturedStart(),
                    m.capturedLength(),
                    fmt,
                )


# ---------------------------------------------------------------------------
# Log highlighter
# ---------------------------------------------------------------------------

_RE_BOUNDARY = re.compile(
    r'^---\s*(?:End\s+)?[Ll]og\s+for\b', re.IGNORECASE
)
_ERROR_KEYS = frozenset(('ERROR', 'CRITICAL', 'FAIL'))
_WARN_KEYS  = frozenset(('WARNING'))
_DEBUG_KEYS  = frozenset(('DEBUG'))


class LogSyntaxHighlighter(QSyntaxHighlighter):
    """
    Colorise entire log lines based on severity.

    Priority (first match wins):
      1. Book boundary  --- Log for … ---   → blue bold
      2. Contains ERROR / CRITICAL / FAIL   → red
      3. Contains WARNING                   → orange
      4. Contains DEBUG                     → muted gray
      5. Anything else                      → no override (default text color)
    """

    def __init__(self, document) -> None:
        super().__init__(document)
        self._fmt_boundary = _fmt("#2266cc", bold=True)
        self._fmt_error    = _fmt("#cc2222")
        self._fmt_warning  = _fmt("#cc7700")
        self._fmt_debug    = _fmt("#888888")

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        if not text:
            return

        if _RE_BOUNDARY.match(text):
            self.setFormat(0, len(text), self._fmt_boundary)
            return

        # upper = text.upper()

        if any(k in text for k in _ERROR_KEYS):
            self.setFormat(0, len(text), self._fmt_error)
        elif any(k in text for k in _WARN_KEYS):
            self.setFormat(0, len(text), self._fmt_warning)
        elif any(k in text for k in _DEBUG_KEYS):
            self.setFormat(0, len(text), self._fmt_debug)
            