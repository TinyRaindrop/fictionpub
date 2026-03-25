"""
MainWindow — top-level window that wires all components together.

Responsibilities:
  - Create and own the model, toolbar, file panel, bottom bar
  - Start / stop scan and batch workers
  - Route model signals to UI components
  - Persist settings on close
"""

import logging
import os
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from .. import app_info
from ..models.conversion import ConversionConfig, ConversionResult, ConversionStatus
from ..utils.logger import LOG_DIR
from .bottom_bar import BottomBarWidget
from .dialogs.app_settings_dialog import AppSettingsDialog
from .dialogs.log_viewer_dialog import LogViewerDialog
from .dialogs.settings_dialog import SettingsDialog
from .file_panel import FileTreeView
from .models.file_node import FileNode, FolderNode
from .models.file_tree_model import FileTreeModel
from .state.settings import AppSettings
from .toolbar import ToolbarWidget
from .workers.batch_worker import BatchWorker
from .workers.meta_worker import MetaSignals, MetaWorker
from .workers.scan_worker import ScanWorker

log = logging.getLogger("fb2_converter")


# ---------------------------------------------------------------------------
# Conversion session — lightweight tracking object
# ---------------------------------------------------------------------------

@dataclass
class ConversionSession:
    total: int
    completed: int = 0
    success:   int = 0
    warnings:  int = 0
    failures:  int = 0
    cancelled: bool = False

    def update(self, result: ConversionResult) -> None:
        self.completed += 1
        match result.status:
            case ConversionStatus.SUCCESS: self.success  += 1
            case ConversionStatus.WARNING: self.warnings += 1
            case ConversionStatus.FAILURE: self.failures += 1


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._config: ConversionConfig = settings.conversion_config()

        self._scan_worker:  ScanWorker  | None = None
        self._batch_worker: BatchWorker | None = None

        # Thread pool for metadata parsing (max 8 concurrent)
        self._meta_pool = QThreadPool.globalInstance()
        self._meta_pool.setMaxThreadCount(8)

        self.setWindowTitle(f"{app_info.APP_NAME} {app_info.VERSION}")
        self._build_ui()
        self._connect_signals()
        self._apply_stylesheet()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._toolbar    = ToolbarWidget()
        self._model      = FileTreeModel()
        self._file_view  = FileTreeView(self._model)
        self._bottom_bar = BottomBarWidget()

        layout.addWidget(self._toolbar)
        layout.addWidget(self._file_view, stretch=1)
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
        tb.logsRequested.connect(self._on_open_logs)

        self._model.selectionCountChanged.connect(self._toolbar.update_selection_count)

        fv = self._file_view
        fv.statusClicked.connect(self._on_status_clicked)
        fv.fileDoubleClicked.connect(self._on_file_double_clicked)
        fv.folderDoubleClicked.connect(self._on_folder_double_clicked)
        fv.selectionRemoveRequested.connect(self._on_remove_selected)

        bb = self._bottom_bar
        bb.convertRequested.connect(self._on_convert)
        bb.cancelRequested.connect(self._on_cancel)
        bb.openLogsDirRequested.connect(self._on_open_logs)
        bb.openLastLogRequested.connect(self._on_open_last_log)

    def _apply_stylesheet(self) -> None:
        """Apply a minimal stylesheet that highlights the Convert button."""
        self.setStyleSheet("""
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
        """)

    # ------------------------------------------------------------------
    # Toolbar action handlers
    # ------------------------------------------------------------------

    def _on_add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select FB2 Files",
            "",
            "FB2 Files (*.fb2 *.fb2.zip);;All Files (*)",
        )
        if paths:
            self._start_scan([Path(p) for p in paths])

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self._start_scan([Path(folder)])

    def _on_remove_selected(self) -> None:
        if self._is_converting():
            return
        indices = self._file_view.selectedModelIndices()
        if indices:
            self._model.removeNodes(indices)

    def _on_remove_all(self) -> None:
        if self._is_converting():
            return
        if not self._model.rowCount():
            return
        reply = QMessageBox.question(
            self, "Remove All",
            "Remove all files from the list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._model.removeAll()
            self._bottom_bar.set_idle()

    def _on_remove_completed(self) -> None:
        if not self._is_converting():
            self._model.removeCompleted()

    def _on_select_all(self) -> None:
        self._model.setAllChecked(Qt.CheckState.Checked)

    def _on_deselect_all(self) -> None:
        self._model.setAllChecked(Qt.CheckState.Unchecked)

    def _on_conversion_settings(self) -> None:
        dlg = SettingsDialog(self._config, self)
        if dlg.exec() and dlg.result:
            self._config = dlg.result
            self._settings.set_conversion_config(self._config)

    def _on_app_settings(self) -> None:
        dlg = AppSettingsDialog(self._settings, self)
        dlg.exec()

    def _on_open_logs(self) -> None:
        if LOG_DIR.exists():
            _open_path(LOG_DIR)
        else:
            QMessageBox.information(self, "Logs", "No log directory found yet.")

    def _on_open_last_log(self) -> None:
        if not LOG_DIR.exists():
            QMessageBox.information(self, "Logs", "No log directory found yet.")
            return
        logs = sorted(LOG_DIR.glob("converter_*.log"), key=lambda p: p.stat().st_mtime)
        if not logs:
            QMessageBox.information(self, "Logs", "No log files found.")
            return
        dlg = LogViewerDialog.from_file(logs[-1], parent=self)
        dlg.show()

    # ------------------------------------------------------------------
    # File view action handlers
    # ------------------------------------------------------------------

    def _on_status_clicked(self, node: FileNode) -> None:
        """Open the per-file log viewer when the user clicks a status icon."""
        if node.log_output:
            title = f"Log — {node.path.name}"
            dlg = LogViewerDialog(node.log_output, title=title, parent=self)
            dlg.show()

    def _on_file_double_clicked(self, path: Path) -> None:
        """Double-click a converted file → open it; not converted → show log."""
        node = self._model._path_to_node.get(path)
        if node and node.status is not None:
            self._on_status_clicked(node)
        # Opening the output .epub file is complex (output path depends on config);
        # log viewer is the safest and most useful response here.

    def _on_folder_double_clicked(self, path: Path) -> None:
        if path.exists():
            _open_path(path)

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

    def _on_scan_complete(self, found: list[Path]) -> None:
        added = self._model.addFiles(found)
        self._file_view.expandAll()

        # Kick off metadata parsing for each new file
        for path in found:
            node = self._model._path_to_node.get(path)
            if node and node.meta_loading:
                signals = MetaSignals(self)
                signals.metaParsed.connect(self._model.updateMeta)
                signals.metaFailed.connect(self._model.updateMetaError)
                worker = MetaWorker(path, signals)
                self._meta_pool.start(worker)

        # Status update is handled in _on_scan_finished

    def _on_scan_finished(self) -> None:
        self._toolbar.set_busy(False)
        total = sum(len(f.children) for f in self._model._folders)
        self._bottom_bar.set_idle(f"Ready — {total} file(s) in list")

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _on_convert(self) -> None:
        if self._is_converting():
            return

        files = self._model.checkedFilePaths()
        if not files:
            QMessageBox.information(
                self, "No Files Selected",
                "Please check at least one file before converting."
            )
            return

        session = ConversionSession(total=len(files))

        self._toolbar.set_busy(True)
        self._bottom_bar.set_converting(len(files))

        self._batch_worker = BatchWorker(self._config, files, session, parent=self)
        self._batch_worker.progressUpdate.connect(self._on_progress_update)
        self._batch_worker.finished.connect(self._on_batch_finished)
        self._batch_worker.errorOccurred.connect(self._on_batch_error)
        self._batch_worker.start()

    def _on_cancel(self) -> None:
        if self._batch_worker and self._batch_worker.isRunning():
            self._batch_worker.requestCancel()
            self._bottom_bar._status.setText("Cancelling…")
            self._bottom_bar._cancel.setEnabled(False)

    def _on_progress_update(self, result: ConversionResult) -> None:
        self._model.setFileResult(result.path, result)
        worker = self._batch_worker
        if worker:
            s = worker._session
            self._bottom_bar.update_progress(
                s.completed, s.total, s.success, s.warnings, s.failures
            )

    def _on_batch_finished(self, session: ConversionSession) -> None:
        self._toolbar.set_busy(False)
        self._bottom_bar.set_done(
            session.success, session.warnings, session.failures,
            cancelled=session.cancelled,
        )
        log.info(
            "Batch done — success=%d warnings=%d failures=%d cancelled=%s",
            session.success, session.warnings, session.failures, session.cancelled,
        )

    def _on_batch_error(self, message: str) -> None:
        self._toolbar.set_busy(False)
        self._bottom_bar.set_idle("Conversion failed.")
        QMessageBox.critical(self, "Conversion Error", message)

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
                "Conversion in Progress",
                "A conversion is still running. Cancel it and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._batch_worker.requestCancel()

        # Wait for workers to finish cleanly
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
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        log.error("Failed to open path %s: %s", path, e)
