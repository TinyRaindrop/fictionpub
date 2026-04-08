"""
fictionpub/pyside6/dialogs/log_folder_dialog.py

Non-modal dialog listing all converter log files with parsed statistics.

Columns: Status | Date | Time | Mode | Total | ✓ | ⚠ | ✗

Status icon per row:
  ✓  SUCCESS  — failures == 0, warnings == 0
  ⚠  WARNING  — failures == 0, warnings > 0
  ✗  FAILURE  — failures > 0
  ?  UNKNOWN  — no SESSION_REPORT line found in the file

Two structured lines are parsed from each log file:

  APP_START mode=gui|cli
      Written at application startup.  Determines the Mode column.

  SESSION_REPORT mode=X total=N success=N warnings=N failures=N
      Written after every conversion batch completes.  The parser
      uses the LAST occurrence so that GUI sessions with multiple
      runs show the final cumulative tally.

Toolbar: [Open Log] [Delete] [Delete All]  |  [Open Folder]
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRect, QSettings, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...app_info import APP_NAME_SHORT, APP_ORG
from ...models.conversion import ConversionStatus
from ...utils.logger import LOG_DIR
from ..i18n import register_listener, t
from ..icons import get_status_icons
from .log_viewer_dialog import LogViewerDialog

# ── Column indices ────────────────────────────────────────────────────────────

COL_STATUS = 0
COL_DATE = 1
COL_TIME = 2
COL_MODE = 3
COL_TOTAL = 4
COL_OK = 5
COL_WARN = 6
COL_FAIL = 7
NCOLS = 8

_ICON_PX = 18
_STATUS_COL_W = 36

# ── Regex patterns ────────────────────────────────────────────────────────────

_RE_FILENAME = re.compile(
    r"^converter_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.log$"
)
_RE_APP_START = re.compile(r"APP_START mode=(\w+)")
_RE_SESSION_REPORT = re.compile(
    r"SESSION_REPORT mode=(\w+) total=(\d+) success=(\d+) warnings=(\d+) failures=(\d+)"
)

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

    # TODO: remove status column? 
    @property
    def status(self) -> ConversionStatus | None:
        """Overall status for the row icon; None → show '?' icon."""
        if self.total is None:
            return None
        if self.failures:
            return ConversionStatus.FAILURE
        if self.warnings:
            return ConversionStatus.WARNING
        return ConversionStatus.SUCCESS


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
            mode=last_report.group(1).upper(),  # authoritative when present
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


# ── Icon helpers ──────────────────────────────────────────────────────────────


def _make_unknown_icon(size: int) -> QIcon:
    """Create a muted '?' icon for log files with no SESSION_REPORT."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor("#888888"))
    font = p.font()
    font.setPixelSize(size - 2)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "?")
    p.end()
    return QIcon(px)


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


def _vsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


# ── Dialog ────────────────────────────────────────────────────────────────────

# TODO: unify with MainWindow styling
_TOOLBAR_QSS = """
QPushButton {
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 3px 10px;
}
QPushButton:hover {
    background-color: rgba(128, 128, 128, 0.20);
    border: 1px solid rgba(128, 128, 128, 0.35);
}
QPushButton:pressed {
    background-color: rgba(128, 128, 128, 0.35);
}
QPushButton:disabled {
    color: palette(mid);
}
"""


class LogFolderDialog(QDialog):
    """
    Non-modal dialog showing all log files with parsed statistics.
    Double-click a row to open that log in LogViewerDialog.
    """

    _GEOM_KEY = "geometry/log_folder"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )

        self._status_icons = get_status_icons(_ICON_PX)
        self._unknown_icon = _make_unknown_icon(_ICON_PX)
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

        self.setStyleSheet(_TOOLBAR_QSS)
        self._retranslate_ui()

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)

        self._btn_open = QPushButton()
        self._btn_delete = QPushButton()
        self._btn_delete_all = QPushButton()
        self._btn_open_folder = QPushButton()

        for btn in (self._btn_open, self._btn_delete, self._btn_delete_all):
            row.addWidget(btn)
        row.addWidget(_vsep())
        row.addWidget(self._btn_open_folder)
        row.addStretch()

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
        h.setStretchLastSection(False)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_STATUS, _STATUS_COL_W)
        self._table.setColumnWidth(COL_DATE, 92)
        self._table.setColumnWidth(COL_TIME, 68)
        self._table.setColumnWidth(COL_MODE, 48)
        self._table.setColumnWidth(COL_TOTAL, 54)
        self._table.setColumnWidth(COL_OK, 50)
        self._table.setColumnWidth(COL_WARN, 50)
        self._table.setColumnWidth(COL_FAIL, 50)

        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._table.itemDoubleClicked.connect(lambda _: self._on_open())

        return self._table

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

        icons = self._status_icons

        # Status column header: blank (icon column)
        self._table.setHorizontalHeaderItem(COL_STATUS, QTableWidgetItem(""))
        self._table.setHorizontalHeaderItem(COL_DATE, QTableWidgetItem(t("logfolder.col_date")))
        self._table.setHorizontalHeaderItem(COL_TIME, QTableWidgetItem(t("logfolder.col_time")))
        self._table.setHorizontalHeaderItem(COL_MODE, QTableWidgetItem(t("logfolder.col_mode")))
        self._table.setHorizontalHeaderItem(COL_TOTAL, QTableWidgetItem(t("logfolder.col_total")))

        # Count columns use status icons as headers
        for col, status in (
            (COL_OK, ConversionStatus.SUCCESS),
            (COL_WARN, ConversionStatus.WARNING),
            (COL_FAIL, ConversionStatus.FAILURE),
        ):
            hdr = QTableWidgetItem()
            hdr.setIcon(icons[status])
            hdr.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setHorizontalHeaderItem(col, hdr)

        self._update_buttons()

    def _update_title(self) -> None:
        base = t("logfolder.title")
        if self._file_count > 0:
            self.setWindowTitle(f"{base} ({self._file_count})")
        else:
            self.setWindowTitle(base)

    # ── Table population ──────────────────────────────────────────────────────

    def _populate(self) -> None:
        """Load summaries from disk and rebuild the table."""
        summaries = _load_summaries()
        self._file_count = len(summaries)
        self._update_title()

        self._table.setRowCount(0)
        self._table.setRowCount(len(summaries))

        center = Qt.AlignmentFlag.AlignCenter
        left = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        for row, s in enumerate(summaries):
            # Status icon cell — stores the file path for later retrieval
            status_cell = QTableWidgetItem()
            icon = (
                self._status_icons.get(s.status)
                if s.status is not None
                else self._unknown_icon
            )
            if icon:
                status_cell.setIcon(icon)
            status_cell.setTextAlignment(center)
            status_cell.setData(Qt.ItemDataRole.UserRole, str(s.path))
            self._table.setItem(row, COL_STATUS, status_cell)

            def _cell(text: str, align=left) -> QTableWidgetItem:
                it = QTableWidgetItem(text)
                it.setTextAlignment(align)
                return it

            def _num(val: int | None) -> str:
                return "?" if val is None else str(val)

            self._table.setItem(row, COL_DATE, _cell(s.date))
            self._table.setItem(row, COL_TIME, _cell(s.time_str))
            self._table.setItem(row, COL_MODE, _cell(s.mode, center))
            self._table.setItem(row, COL_TOTAL, _cell(_num(s.total), center))
            self._table.setItem(row, COL_OK, _cell(_num(s.success), center))
            self._table.setItem(row, COL_WARN, _cell(_num(s.warnings), center))
            self._table.setItem(row, COL_FAIL, _cell(_num(s.failures), center))

        self._update_buttons()

    def _current_path(self) -> Path | None:
        """Return the log file path for the currently selected row."""
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, COL_STATUS)
        if item is None:
            return None
        raw = item.data(Qt.ItemDataRole.UserRole)
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
        if path is None:
            return
        LogViewerDialog.from_file(path, parent=self).show()

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
            row = self._table.currentRow()
            self._table.removeRow(row)
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
        if n == 0:
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
            item = self._table.item(row, COL_STATUS)
            if item is None:
                continue
            raw = item.data(Qt.ItemDataRole.UserRole)
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

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        s = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            APP_ORG,
            APP_NAME_SHORT,
        )
        raw = s.value(self._GEOM_KEY)
        if raw:
            self.restoreGeometry(raw)
        else:
            self.resize(560, 400)

    def closeEvent(self, event) -> None:  # noqa: N802
        s = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            APP_ORG,
            APP_NAME_SHORT,
        )
        s.setValue(self._GEOM_KEY, self.saveGeometry())
        super().closeEvent(event)