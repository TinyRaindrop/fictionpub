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
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtGui import QKeySequence, QShortcut
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
from .dialogs.about_dialog import AboutDialog
from .dialogs.app_settings_dialog import AppSettingsDialog
from .dialogs.log_viewer_dialog import LogViewerDialog
from .dialogs.settings_dialog import SettingsDialog
from .file_panel import FileTreeView
from .i18n import register_listener, t
from .models.file_node import FileNode, FolderNode
from .models.file_tree_model import FileTreeModel
from .state.settings import AppSettings
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
    total:     int
    completed: int  = 0
    success:   int  = 0
    warnings:  int  = 0
    failures:  int  = 0
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

        self._meta_pool = QThreadPool.globalInstance()
        self._meta_pool.setMaxThreadCount(8)

        self._build_ui()
        self._connect_signals()
        self._apply_shortcuts()
        self._apply_stylesheet()

        register_listener(self._retranslate_ui)
        self._retranslate_ui()

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
        tb.aboutRequested.connect(self._on_about)

        self._model.selectionCountChanged.connect(self._toolbar.update_selection_count)

        fv = self._file_view
        fv.statusClicked.connect(self._on_status_clicked)
        fv.fileDoubleClicked.connect(self._on_file_double_clicked)
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
        QShortcut(QKeySequence.StandardKey.Delete, self._file_view).activated.connect(self._on_remove_selected)
        QShortcut(QKeySequence.StandardKey.SelectAll, self).activated.connect(
            lambda: self._model.setAllChecked(True)
        )

    def _apply_stylesheet(self) -> None:
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

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(f"{app_info.APP_NAME} {app_info.VERSION}")

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
        # Use selectedSourceIndices() — already mapped through the proxy
        indices = self._file_view.selectedSourceIndices()
        if indices:
            self._model.removeNodes(indices)

    def _on_remove_all(self) -> None:
        if self._is_converting():
            return
        if not self._model.rowCount():
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

    def _on_app_settings(self) -> None:
        AppSettingsDialog(self._settings, self).exec()

    def _on_open_logs(self) -> None:
        if LOG_DIR.exists():
            _open_path(LOG_DIR)
        else:
            QMessageBox.information(self, t("msg.no_logs_title"), t("msg.no_logs_dir"))

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

    def _on_file_double_clicked(self, path: Path) -> None:
        node = self._model._path_to_node.get(path)
        if node and node.status is not None:
            self._on_status_clicked(node)

    def _on_folder_double_clicked(self, path: Path) -> None:
        if path.exists():
            _open_path(path)

    def _on_open_epub(self, source_path: Path) -> None:
        epub = self._epub_path_for(source_path)
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
    # EPUB path resolution
    # ------------------------------------------------------------------

    def _epub_path_for(self, source: Path) -> Path:
        name = source.name
        if name.endswith(".fb2.zip"):
            stem = name[:-8]
        elif name.endswith(".fb2"):
            stem = name[:-4]
        else:
            stem = source.stem
        out_dir = self._config.output_path or source.parent
        return out_dir / f"{stem}.epub"

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
        self._model.addFiles(found)
        self._file_view.expandAll()

        for path in found:
            node = self._model._path_to_node.get(path)
            if node and node.meta_loading:
                signals = MetaSignals(self)
                signals.metaParsed.connect(self._model.updateMeta)
                signals.metaFailed.connect(self._model.updateMetaError)
                self._meta_pool.start(MetaWorker(path, signals))

    def _on_scan_finished(self) -> None:
        self._toolbar.set_busy(False)
        total = sum(len(f.children) for f in self._model._folders)
        self._bottom_bar.set_idle(t("bar.ready_n_files", n=total))

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _on_convert(self) -> None:
        if self._is_converting():
            return

        files = self._model.checkedFilePaths()
        if not files:
            QMessageBox.information(
                self, t("msg.no_files_title"), t("msg.no_files_text")
            )
            return

        session = ConversionSession(total=len(files))
        self._toolbar.set_busy(True)
        self._bottom_bar.set_converting(len(files))

        # Fresh worker instance — _cancel_requested is always False at start
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
            session.success, session.warnings, session.failures,
            cancelled=session.cancelled,
        )
        log.info(
            "Batch done — success=%d warnings=%d failures=%d cancelled=%s",
            session.success, session.warnings, session.failures, session.cancelled,
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
            self._batch_worker.requestCancel()

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
            os.startfile(path)          # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        log.error("Failed to open path %s: %s", path, e)
