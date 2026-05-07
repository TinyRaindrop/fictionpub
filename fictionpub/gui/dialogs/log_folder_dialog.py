"""
Non-modal dialog listing all converter log files with parsed statistics.

Columns: # | Date | Time | Mode | Total | ✓ | ⚠ | ✗

The ✗ (failures) cell is coloured red when its value is greater than zero.
The row corresponding to the current process's log file is highlighted.

Parsing
───────
Two structured lines are read from each log file:

  APP_START mode=gui|cli
      Written at startup; identifies the launch mode.

  SESSION_REPORT mode=X total=N success=N warnings=N failures=N
      Written after every batch.  The LAST occurrence is used so
      GUI sessions with multiple runs reflect the final cumulative tally.

Toolbar: [Open Log] [Delete] [Delete All]          [Open Folder]
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import override

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from fictionpub.gui.state.settings import GeometryStore

# TODO: switch to absolute imports everywhere
from ...models.conversion import ConversionStatus
from ...utils.logger import LOG_DIR, get_current_log_path
from ..i18n import register_listener, t
from ..icons import get_status_icons
from ..themes import PLAIN_BUTTON_QSS
from .log_viewer_dialog import LogViewerDialog

# ── Column indices ────────────────────────────────────────────────────────────

# TODO: switch to IntEnum?
COL_NUM = 0
COL_DATE = 1
COL_TIME = 2
COL_MODE = 3
COL_TOTAL = 4
COL_OK = 5
COL_WARN = 6
COL_FAIL = 7
NCOLS = 8

_ICON_PX = 16

# ── Regex patterns ────────────────────────────────────────────────────────────

_RE_FILENAME = re.compile(r"^converter_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.log$")
_RE_APP_START = re.compile(r"APP_START mode=(\w+)")
_RE_SESSION_REPORT = re.compile(
    r"SESSION_REPORT mode=(\w+) total=(\d+) success=(\d+) warnings=(\d+) failures=(\d+)"
)

# Colours
_RED_FAIL = QColor("#c0392b")
_CURRENT_BG = QColor(38, 120, 200, 35)  # faint highlight tint for current session

# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class LogSummary:
    """Parsed information about a single log file."""

    path: Path
    date: str
    time_str: str
    mode: str  # "GUI", "CLI", or "?"
    total: int | None = None
    success: int | None = None
    warnings: int | None = None
    failures: int | None = None


def _parse_log_summary(path: Path) -> LogSummary:
    """Extract date/time from filename and mode/stats from file content."""
    m = _RE_FILENAME.match(path.name)
    if m:
        date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        time_str = f"{m.group(4)}:{m.group(5)}:{m.group(6)}"
    else:
        date = time_str = "?"

    mode = "?"
    last_report = None

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                # Only look for APP_START until we find it (it's always near the top)
                if mode == "?":
                    am = _RE_APP_START.search(line)
                    if am:
                        mode = am.group(1).upper()
                # Keep scanning for SESSION_REPORT — we want the LAST one
                bm = _RE_SESSION_REPORT.search(line)
                if bm:
                    last_report = bm
    except OSError:
        pass

    if last_report:
        return LogSummary(
            path=path,
            date=date,
            time_str=time_str,
            mode=last_report.group(1).upper(),
            total=int(last_report.group(2)),
            success=int(last_report.group(3)),
            warnings=int(last_report.group(4)),
            failures=int(last_report.group(5)),
        )
    return LogSummary(path=path, date=date, time_str=time_str, mode=mode)


def _load_summaries() -> list[LogSummary]:
    """Scan LOG_DIR and return summaries sorted newest-first."""
    if not LOG_DIR.exists():
        return []
    logs = sorted(
        [p for p in LOG_DIR.glob("converter_*.log") if p.is_file()],
        key=lambda p: p.name,
        reverse=True,
    )
    return [_parse_log_summary(p) for p in logs]


# ── Platform helper ───────────────────────────────────────────────────────────


def _open_path(path: Path) -> None:
    """Open a file or directory using the OS default handler."""
    try:
        if platform.system() == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


# ── Dialog ────────────────────────────────────────────────────────────────────


class LogFolderDialog(QDialog):
    """
    Non-modal dialog showing all log files with parsed statistics.
    Double-click a row to open that log in LogViewerDialog.
    """

    def __init__(self, geom: GeometryStore, parent=None) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )

        self._geom: GeometryStore = geom
        self._geom_key = "log_folder"

        self._status_icons = get_status_icons(_ICON_PX)
        self._current_log = get_current_log_path()
        self._file_count = 0

        self._build_ui()
        self._populate()
        register_listener(self._retranslate_ui)

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        outer.addLayout(self._build_toolbar())
        outer.addWidget(self._build_table(), stretch=1)

        self.setStyleSheet(PLAIN_BUTTON_QSS)
        # We can override the style
        # self.setStyleSheet(PLAIN_BUTTON_QSS + "QPushButton { padding: 3px 10px; }")

        # Calculate minimum width to prevent horizontal overflow:
        # 6 fixed columns, 2 stretch columns
        # Extra buffer for layout margins, frame borders, and vertical scrollbar
        min_window_width = 6 * 64 + 2 * 120 + 36
        self.setMinimumWidth(min_window_width)

        self._retranslate_ui()

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)

        self._btn_open = QPushButton()
        self._btn_delete = QPushButton()
        self._btn_delete_all = QPushButton()
        self._btn_open_folder = QPushButton()

        row.addWidget(self._btn_open)
        row.addWidget(self._btn_delete)
        row.addWidget(self._btn_delete_all)
        row.addStretch()
        row.addWidget(self._btn_open_folder)

        self._btn_open.clicked.connect(self._on_open)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_delete_all.clicked.connect(self._on_delete_all)
        self._btn_open_folder.clicked.connect(self._on_open_folder)

        return row

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget()
        self._table.setColumnCount(NCOLS)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(False)
        self._table.setShowGrid(False)
        self._table.setIconSize(QSize(_ICON_PX, _ICON_PX))
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(26)

        h = self._table.horizontalHeader()
        # Protects columns from getting too tiny if squeezed
        h.setMinimumSectionSize(64)
        h.setStretchLastSection(True)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

        # Set specific resize modes per column
        for col in range(NCOLS):
            # Fix the rest at an identical width
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)

        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._table.itemDoubleClicked.connect(lambda _: self._on_open())

        return self._table

    @override
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

        # Ensure table exists before trying to resize its columns
        if not hasattr(self, "_table"):
            return

        # Get the actual drawable width inside the table
        viewport_width = self._table.viewport().width()

        # Date and Time: weight = 1.5, other 6 columns: weight = 1.0.
        # Total weights = (2 * 1.5) + (6 * 1.0) = 9.0
        unit_width = viewport_width / 9.0

        for col in range(NCOLS):
            if col in (COL_DATE, COL_TIME):
                self._table.setColumnWidth(col, int(unit_width * 1.5))
            else:
                self._table.setColumnWidth(col, int(unit_width * 1.0))

    # ── i18n ─────────────────────────────────────────────────────────────────

    def _retranslate_ui(self) -> None:
        self._update_title()

        self._btn_open.setText(t("logfolder.open_log"))
        self._btn_open.setToolTip(t("tooltip.logfolder_open"))
        self._btn_delete.setText(t("logfolder.delete"))
        self._btn_delete.setToolTip(t("tooltip.logfolder_delete"))
        self._btn_delete_all.setText(t("logfolder.delete_all"))
        self._btn_delete_all.setToolTip(t("tooltip.logfolder_delete_all"))
        self._btn_open_folder.setText(t("logfolder.open_folder"))
        self._btn_open_folder.setToolTip(t("tooltip.logfolder_open_folder"))

        def _hdr(text: str) -> QTableWidgetItem:
            it = QTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            return it

        self._table.setHorizontalHeaderItem(COL_NUM, _hdr("#"))
        self._table.setHorizontalHeaderItem(COL_DATE, _hdr(t("logfolder.col_date")))
        self._table.setHorizontalHeaderItem(COL_TIME, _hdr(t("logfolder.col_time")))
        self._table.setHorizontalHeaderItem(COL_MODE, _hdr(t("logfolder.col_mode")))
        self._table.setHorizontalHeaderItem(COL_TOTAL, _hdr(t("logfolder.col_total")))

        # Count columns use status icons as headers
        for col, status in (
            (COL_OK, ConversionStatus.SUCCESS),
            (COL_WARN, ConversionStatus.WARNING),
            (COL_FAIL, ConversionStatus.FAILURE),
        ):
            it = QTableWidgetItem()
            it.setIcon(self._status_icons[status])
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setHorizontalHeaderItem(col, it)

        self._update_buttons()

    def _update_title(self) -> None:
        base = t("logfolder.title")
        self.setWindowTitle(f"{base} ({self._file_count})" if self._file_count else base)

    # ── Table population ──────────────────────────────────────────────────────

    def _populate(self) -> None:
        """Load summaries from disk and rebuild the table."""
        summaries = _load_summaries()
        self._file_count = len(summaries)
        self._update_title()

        self._table.setRowCount(0)
        self._table.setRowCount(len(summaries))

        bold_font = QFont()
        bold_font.setBold(True)

        current_log_resolved = self._current_log.resolve() if self._current_log else None

        for row, s in enumerate(summaries):
            is_current = (
                current_log_resolved is not None
                and s.path.resolve() == current_log_resolved
            )

            def _cell(text: str, is_current=is_current) -> QTableWidgetItem:
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_current:
                    it.setFont(bold_font)
                    it.setBackground(QBrush(_CURRENT_BG))
                return it

            def _num(val: int | None) -> str:
                return "?" if val is None else str(val)

            num_cell = _cell(str(row + 1))
            # Stash path on the number cell for retrieval by actions
            num_cell.setData(Qt.ItemDataRole.UserRole, str(s.path))
            self._table.setItem(row, COL_NUM, num_cell)
            self._table.setItem(row, COL_DATE, _cell(s.date))
            self._table.setItem(row, COL_TIME, _cell(s.time_str))
            self._table.setItem(row, COL_MODE, _cell(s.mode))
            self._table.setItem(row, COL_TOTAL, _cell(_num(s.total)))
            self._table.setItem(row, COL_OK, _cell(_num(s.success)))
            self._table.setItem(row, COL_WARN, _cell(_num(s.warnings)))

            fail_cell = _cell(_num(s.failures))
            if s.failures:
                fail_cell.setForeground(QBrush(_RED_FAIL))
                if not is_current:  # bold already set for current row
                    fail_cell.setFont(bold_font)
            self._table.setItem(row, COL_FAIL, fail_cell)

        self._update_buttons()

    def _current_path(self) -> Path | None:
        """Return the log file path for the currently selected row."""
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, COL_NUM)
        raw = item.data(Qt.ItemDataRole.UserRole) if item else None
        return Path(raw) if raw else None

    def _update_buttons(self) -> None:
        has_selection = self._table.currentRow() >= 0
        has_rows = self._table.rowCount() > 0
        self._btn_open.setEnabled(has_selection)
        self._btn_delete.setEnabled(has_selection)
        self._btn_delete_all.setEnabled(has_rows)

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _on_open(self) -> None:
        path = self._current_path()
        if path:
            LogViewerDialog.from_file(path, self._geom, parent=self).show()

    def _on_delete(self) -> None:
        path = self._current_path()
        if path is None:
            return
        reply = QMessageBox.question(
            self,
            t("logfolder.confirm_title"),
            t("logfolder.confirm_delete", name=path.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            path.unlink(missing_ok=True)
            self._table.removeRow(self._table.currentRow())
            self._file_count = self._table.rowCount()
            self._update_title()
            self._update_buttons()
        except OSError as e:
            QMessageBox.critical(
                self,
                t("logfolder.delete_error_title"),
                t("logfolder.delete_error", name=path.name, error=str(e)),
            )

    def _on_delete_all(self) -> None:
        n = self._table.rowCount()
        if not n:
            return
        reply = QMessageBox.question(
            self,
            t("logfolder.confirm_title"),
            t("logfolder.confirm_delete_all", n=n),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        errors: list[str] = []
        rows_ok: list[int] = []
        for row in range(n):
            item = self._table.item(row, COL_NUM)
            raw = item.data(Qt.ItemDataRole.UserRole) if item else None
            if not raw:
                continue
            try:
                Path(raw).unlink(missing_ok=True)
                rows_ok.append(row)
            except OSError as e:
                errors.append(f"{Path(raw).name}: {e}")

        for row in reversed(rows_ok):
            self._table.removeRow(row)
        self._file_count = self._table.rowCount()
        self._update_title()
        self._update_buttons()

        if errors:
            QMessageBox.warning(
                self,
                t("logfolder.delete_error_title"),
                t("logfolder.delete_error_multi", errors="\n".join(errors)),
            )

    def _on_open_folder(self) -> None:
        if LOG_DIR.exists():
            _open_path(LOG_DIR)

    # ── Geometry persistence ──────────────────────────────────────────────────

    @override
    def showEvent(self, event) -> None:
        super().showEvent(event)
        raw = self._geom.load(self._geom_key)
        if raw is not None:
            self.restoreGeometry(raw)
        else:
            self.resize(self.minimumWidth(), 380)

    @override
    def closeEvent(self, event) -> None:
        self._geom.save(self._geom_key, self.saveGeometry())
        super().closeEvent(event)
