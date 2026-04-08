"""
MainWindow — top-level window that wires all components together.

Layout (top → bottom inside central widget)
────────────────────────────────────────────
  ToolbarWidget
  FileTreeView  (stretch=1)
  AppStatusBar  ← persistent output-path hint + future notifications
  BottomBarWidget

QSS strategy
────────────
All button styles live in _apply_stylesheet() as a single stylesheet
string on the QMainWindow.  Descendant selectors style buttons inside
each named container class; the #convertButton ID selector overrides for
the primary-action button.  No inline QSS in widget files.

Why this is correct
───────────────────
Qt's stylesheet cascade resolves specificity exactly like CSS:
  • Type+ancestor selector  e.g. "ToolbarWidget QPushButton"
    specificity = (0, 0, 2) — two type selectors
  • ID selector  e.g. "QPushButton#convertButton"
    specificity = (0, 1, 1) — one ID + one type  → wins over the above
So the Convert button gets the blue primary-action style while every other
button in ToolbarWidget / BottomBarWidget gets the transparent hover style.

Scan → expand behaviour
────────────────────────
_on_scan_complete() snapshots the set of already-known root folder paths
*before* calling model.addFiles(), then expands only the new root nodes.
Existing expand/collapse state is preserved.

Output-path hint
────────────────
_update_output_hint() pushes a translated hint into AppStatusBar whenever
the configuration changes (settings dialog OK, language switch).

Cumulative session stats
────────────────────────
_cumulative_success / _warnings / _failures accumulate across all
conversion runs in a single GUI session.  A SESSION_REPORT line is written
to the log after each run so the log folder viewer always shows up-to-date
totals even if the application is closed unexpectedly.
"""

import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from .. import app_info
from ..models.conversion import (
    BatchAnchor,
    ConversionConfig,
    ConversionResult,
    ConversionStatus,
    compute_batch_anchor,
    resolve_epub_path,
)
from ..utils.logger import LOG_DIR
from .bottom_bar import BottomBarWidget
from .dialogs.about_dialog import AboutDialog
from .dialogs.app_settings_dialog import AppSettingsDialog
from .dialogs.log_folder_dialog import LogFolderDialog
from .dialogs.log_viewer_dialog import LogViewerDialog
from .dialogs.settings_dialog import SettingsDialog
from .file_panel import FileTreeView
from .i18n import register_listener, t
from .models.file_node import FileNode
from .models.file_tree_model import FileTreeModel
from .state.settings import AppSettings
from .status_bar import AppStatusBar
from .toolbar import ToolbarWidget
from .workers.batch_worker import BatchWorker
from .workers.meta_worker import MetaSignals, MetaWorker
from .workers.scan_worker import ScanWorker

log = logging.getLogger("fb2_converter")


# ---------------------------------------------------------------------------
# Conversion session
# ---------------------------------------------------------------------------


@dataclass
class ConversionSession:
    total: int
    completed: int = 0
    success: int = 0
    warnings: int = 0
    failures: int = 0
    cancelled: bool = False

    def update(self, result: ConversionResult) -> None:
        self.completed += 1
        match result.status:
            case ConversionStatus.SUCCESS:
                self.success += 1
            case ConversionStatus.WARNING:
                self.warnings += 1
            case ConversionStatus.FAILURE:
                self.failures += 1


# ---------------------------------------------------------------------------
# Centralised QSS
# ---------------------------------------------------------------------------

_WINDOW_QSS = """
/* ── Toolbar and bottom-bar plain buttons ──────────────────────── */
ToolbarWidget QPushButton,
BottomBarWidget QPushButton {
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 3px 8px;
    background: transparent;
}
ToolbarWidget QPushButton:hover,
BottomBarWidget QPushButton:hover {
    background-color: rgba(128, 128, 128, 0.20);
    border: 1px solid rgba(128, 128, 128, 0.35);
}
ToolbarWidget QPushButton:pressed,
BottomBarWidget QPushButton:pressed {
    background-color: rgba(128, 128, 128, 0.35);
    border: 1px solid rgba(128, 128, 128, 0.50);
}
ToolbarWidget QPushButton:checked,
BottomBarWidget QPushButton:checked {
    background-color: rgba(128, 128, 128, 0.35);
    border: 1px solid rgba(128, 128, 128, 0.50);
}
ToolbarWidget QPushButton:disabled,
BottomBarWidget QPushButton:disabled {
    color: palette(mid);
}

/* ── Convert button — primary action (higher specificity via #id) ── */
QPushButton#convertButton {
    background-color: #2980b9;
    color: white;
    font-weight: bold;
    padding: 4px 16px;
    border-radius: 3px;
    border: none;
}
QPushButton#convertButton:hover {
    background-color: #3498db;
}
QPushButton#convertButton:disabled {
    background-color: #7f8c8d;
}
"""


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._config: ConversionConfig = settings.conversion_config()

        self._scan_worker: ScanWorker | None = None
        self._batch_worker: BatchWorker | None = None
        self._batch_anchor: BatchAnchor | None = None

        self._meta_pool = QThreadPool.globalInstance()
        self._meta_pool.setMaxThreadCount(8)

        # Cumulative conversion stats across all runs in this GUI session.
        self._cumulative_success = 0
        self._cumulative_warnings = 0
        self._cumulative_failures = 0

        self._build_ui()
        self._connect_signals()
        self._apply_shortcuts()
        self._apply_stylesheet()

        register_listener(self._retranslate_ui)
        self._retranslate_ui()
        self._update_output_hint()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._toolbar = ToolbarWidget()
        self._model = FileTreeModel()
        self._file_view = FileTreeView(self._model)
        self._status_bar = AppStatusBar()
        self._bottom_bar = BottomBarWidget()

        layout.addWidget(self._toolbar)
        layout.addWidget(self._file_view, stretch=1)
        layout.addWidget(self._status_bar)
        layout.addWidget(self._bottom_bar)

    def _connect_signals(self) -> None:
        tb = self._toolbar
        tb.addFilesRequested.connect(self._on_add_files)
        tb.addFolderRequested.connect(self._on_add_folder)
        tb.removeSelectedRequested.connect(self._on_remove_selected)
        tb.removeAllRequested.connect(self._on_remove_all)
        tb.removeCompletedRequested.connect(self._on_remove_completed)
        tb.selectAllRequested.connect(self._on_select_all)
        tb.deselectAllRequested.connect(self._on_deselect_all)
        tb.conversionSettingsRequested.connect(self._on_conversion_settings)
        tb.appSettingsRequested.connect(self._on_app_settings)
        tb.aboutRequested.connect(self._on_about)

        self._model.selectionCountChanged.connect(self._toolbar.update_selection_count)

        fv = self._file_view
        fv.statusClicked.connect(self._on_status_clicked)
        fv.folderDoubleClicked.connect(self._on_folder_double_clicked)
        fv.openEpubRequested.connect(self._on_open_epub)
        fv.openFb2Requested.connect(self._on_open_fb2)
        fv.openFolderRequested.connect(self._on_open_folder)
        fv.selectionRemoveRequested.connect(self._on_remove_selected)

        bb = self._bottom_bar
        bb.convertRequested.connect(self._on_convert)
        bb.cancelRequested.connect(self._on_cancel)
        bb.openLogsDirRequested.connect(self._on_open_logs)
        bb.openLastLogRequested.connect(self._on_open_last_log)

    def _apply_shortcuts(self) -> None:
        QShortcut(QKeySequence.StandardKey.Delete, self._file_view).activated.connect(
            self._on_remove_selected
        )
        QShortcut(QKeySequence.StandardKey.SelectAll, self).activated.connect(
            lambda: self._model.setAllChecked(True)
        )

    def _apply_stylesheet(self) -> None:
        """
        Single stylesheet for the whole window.

        ToolbarWidget QPushButton / BottomBarWidget QPushButton
            → transparent hover/press for all plain buttons in those panels.

        QPushButton#convertButton
            → blue primary-action override (higher specificity than the above).
        """
        self.setStyleSheet(_WINDOW_QSS)

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(f"{app_info.APP_NAME} {app_info.VERSION}")
        self._update_output_hint()

    # ------------------------------------------------------------------
    # Output-path hint
    # ------------------------------------------------------------------

    def _update_output_hint(self) -> None:
        """Push a translated output-path hint to AppStatusBar."""
        if self._config.output_path is None:
            self._status_bar.show_hint(t("bar.hint_same_folder"))
        else:
            self._status_bar.show_hint(
                t("bar.hint_output_dir", path=str(self._config.output_path))
            )

    # ------------------------------------------------------------------
    # Toolbar action handlers
    # ------------------------------------------------------------------

    def _on_add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            t("toolbar.add_files"),
            "",
            f"{t('filter.fb2')};;{t('filter.all')}",
        )
        if paths:
            self._start_scan([Path(p) for p in paths])

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("toolbar.add_folder"))
        if folder:
            self._start_scan([Path(folder)])

    def _on_remove_selected(self) -> None:
        if self._is_converting():
            return
        indices = self._file_view.selectedSourceIndices()
        if indices:
            self._model.removeNodes(indices)

    def _on_remove_all(self) -> None:
        if self._is_converting():
            return
        if not self._model.totalFileCount():
            return
        reply = QMessageBox.question(
            self,
            t("msg.remove_all_title"),
            t("msg.remove_all_text"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._model.removeAll()
            self._bottom_bar.set_idle()

    def _on_remove_completed(self) -> None:
        if not self._is_converting():
            self._model.removeCompleted()

    def _on_select_all(self) -> None:
        self._model.setAllChecked(True)

    def _on_deselect_all(self) -> None:
        self._model.setAllChecked(False)

    def _on_conversion_settings(self) -> None:
        dlg = SettingsDialog(self._config, self)
        if dlg.exec() and dlg.result:
            self._config = dlg.result
            self._settings.set_conversion_config(self._config)
            self._update_output_hint()

    def _on_app_settings(self) -> None:
        AppSettingsDialog(self._settings, self).exec()

    def _on_open_logs(self) -> None:
        """Open the log folder viewer dialog."""
        LogFolderDialog(parent=self).show()

    def _on_open_last_log(self) -> None:
        if not LOG_DIR.exists():
            QMessageBox.information(self, t("msg.no_logs_title"), t("msg.no_logs_dir"))
            return
        logs = sorted(LOG_DIR.glob("converter_*.log"), key=lambda p: p.stat().st_mtime)
        if not logs:
            QMessageBox.information(self, t("msg.no_logs_title"), t("msg.no_logs_files"))
            return
        LogViewerDialog.from_file(logs[-1], parent=self).show()

    def _on_about(self) -> None:
        AboutDialog(self).show()

    # ------------------------------------------------------------------
    # File view action handlers
    # ------------------------------------------------------------------

    def _on_status_clicked(self, node: FileNode) -> None:
        if node.log_output:
            LogViewerDialog(
                node.log_output,
                title=t("logviewer.title_file", name=node.path.name),
                parent=self,
            ).show()

    def _on_folder_double_clicked(self, path: Path) -> None:
        if path.exists():
            _open_path(path)

    def _on_open_epub(self, source_path: Path) -> None:
        epub = resolve_epub_path(source_path, self._config, self._batch_anchor)
        if epub.exists():
            _open_path(epub)
        else:
            QMessageBox.warning(
                self,
                t("msg.no_epub_title"),
                t("msg.no_epub_text", path=str(epub)),
            )

    def _on_open_fb2(self, path: Path) -> None:
        if path.exists():
            _open_path(path)

    def _on_open_folder(self, path: Path) -> None:
        target = path if path.is_dir() else path.parent
        if target.exists():
            _open_path(target)

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _start_scan(self, paths: list[Path]) -> None:
        if self._scan_worker and self._scan_worker.isRunning():
            return
        self._toolbar.set_busy(True)
        self._bottom_bar.set_scanning()
        self._scan_worker = ScanWorker(paths, parent=self)
        self._scan_worker.filesFound.connect(self._on_scan_complete)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.start()

    def _on_scan_complete(self, found: list[tuple[Path, Path]]) -> None:
        """
        Add files, then expand only the newly created root FolderNodes.

        Snapshot the current root-folder path set before adding so we can
        identify which roots are new after the call.
        """
        existing_roots = {f.path for f in self._model._root_folders}

        self._model.addFiles(found)

        new_roots = [f for f in self._model._root_folders if f.path not in existing_roots]
        self._file_view.expandNewFolders(new_roots)

        for _root, file_path in found:
            node = self._model._path_to_node.get(file_path)
            if node and node.meta_loading:
                signals = MetaSignals(self)
                signals.metaParsed.connect(self._model.updateMeta)
                signals.metaFailed.connect(self._model.updateMetaError)
                self._meta_pool.start(MetaWorker(file_path, signals))

    def _on_scan_finished(self) -> None:
        self._toolbar.set_busy(False)
        total = self._model.totalFileCount()
        self._bottom_bar.set_idle(t("bar.ready_n_files", n=total))

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _on_convert(self) -> None:
        if self._is_converting():
            return

        files = self._model.checkedFilePaths()
        if not files:
            QMessageBox.information(self, t("msg.no_files_title"), t("msg.no_files_text"))
            return

        self._batch_anchor = compute_batch_anchor(files)

        session = ConversionSession(total=len(files))
        self._toolbar.set_busy(True)
        self._bottom_bar.set_converting(len(files))

        self._batch_worker = BatchWorker(self._config, files, session, parent=self)
        self._batch_worker.progressUpdate.connect(self._on_progress_update)
        self._batch_worker.batchFinished.connect(self._on_batch_finished)
        self._batch_worker.errorOccurred.connect(self._on_batch_error)
        self._batch_worker.start()

    def _on_cancel(self) -> None:
        if self._batch_worker and self._batch_worker.isRunning():
            self._batch_worker.requestCancel()
            self._bottom_bar.set_cancelling()

    def _on_progress_update(self, result: ConversionResult) -> None:
        self._model.setFileResult(result.path, result)
        if self._batch_worker:
            s = self._batch_worker._session
            self._bottom_bar.update_progress(
                s.completed, s.total, s.success, s.warnings, s.failures
            )

    def _on_batch_finished(self, session: ConversionSession) -> None:
        self._toolbar.set_busy(False)
        self._bottom_bar.set_done(
            session.success,
            session.warnings,
            session.failures,
            cancelled=session.cancelled,
        )
        log.info(
            "BATCH_REPORT mode=gui total=%d success=%d warnings=%d failures=%d cancelled=%s",
            session.total,
            session.success,
            session.warnings,
            session.failures,
            session.cancelled,
        )

        # Written to the log as SESSION_REPORT after each run 
        # so the log folder viewer always reflects the latest totals.
        self._cumulative_success += session.success
        self._cumulative_warnings += session.warnings
        self._cumulative_failures += session.failures
        cumulative_total = (
            self._cumulative_success
            + self._cumulative_warnings
            + self._cumulative_failures
        )
        log.info(
            "SESSION_REPORT mode=gui total=%d success=%d warnings=%d failures=%d",
            cumulative_total,
            self._cumulative_success,
            self._cumulative_warnings,
            self._cumulative_failures,
        )

    def _on_batch_error(self, message: str) -> None:
        self._toolbar.set_busy(False)
        self._bottom_bar.set_idle(t("bar.ready"))
        QMessageBox.critical(self, app_info.APP_NAME, message)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_converting(self) -> bool:
        return bool(self._batch_worker and self._batch_worker.isRunning())

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._is_converting():
            reply = QMessageBox.question(
                self,
                t("msg.close_title"),
                t("msg.close_text"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._batch_worker.requestCancel()  # type: ignore

        if self._scan_worker:
            self._scan_worker.quit()
            self._scan_worker.wait(2000)
        if self._batch_worker:
            self._batch_worker.wait(3000)

        self._settings.set_geometry(self.saveGeometry())
        self._settings.set_conversion_config(self._config)
        self._settings.sync()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Platform helper
# ---------------------------------------------------------------------------


def _open_path(path: Path) -> None:
    try:
        if platform.system() == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        log.error("Failed to open path %s: %s", path, e)
