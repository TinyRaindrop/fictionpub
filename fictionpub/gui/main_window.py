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
conversion runs in a single GUI session.
A SESSION_REPORT line is written to the log after each run
so the log folder viewer always shows up-to-date totals
even if the application is closed unexpectedly.

Auto-update
───────────
_start_update_check() is called from showEvent() with a short delay if
AppSettings.should_check_now() returns True.  The check uses
UpdateCheckWorker (QRunnable) submitted to QThreadPool.  Results are
handled by _on_update_available() / _on_no_update():

  • _on_update_available  → show toolbar indicator, update about dialog,
                            optionally show startup popup (once per version)
  • _on_no_update         → record last_checked, update about dialog
  • toolbar indicator     → opens UpdateDialog on click
  • About "Check Now"     → triggers a fresh check immediately
"""

import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import override

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from fictionpub import app_info
from fictionpub.gui.bottom_bar import BottomBarWidget
from fictionpub.gui.dialogs.about_dialog import AboutDialog
from fictionpub.gui.dialogs.app_settings_dialog import AppSettingsDialog
from fictionpub.gui.dialogs.log_folder_dialog import LogFolderDialog
from fictionpub.gui.dialogs.log_viewer_dialog import LogViewerDialog
from fictionpub.gui.dialogs.settings_dialog import SettingsDialog
from fictionpub.gui.dialogs.update_dialog import UpdateDialog
from fictionpub.gui.file_panel import FileTreeView
from fictionpub.gui.i18n import register_listener, t
from fictionpub.gui.models.file_node import FileNode
from fictionpub.gui.models.file_tree_model import FileTreeModel
from fictionpub.gui.state.settings import AppSettings, GeometryStore
from fictionpub.gui.status_bar import AppStatusBar
from fictionpub.gui.toolbar import ToolbarWidget
from fictionpub.gui.workers.batch_worker import BatchWorker
from fictionpub.gui.workers.meta_worker import MetaSignals, MetaWorker
from fictionpub.gui.workers.scan_worker import ScanWorker
from fictionpub.gui.workers.update_worker import (
    UpdateCheckSignals,
    UpdateCheckWorker,
    UpdateInfo,
)
from fictionpub.models.conversion import (
    BatchAnchor,
    ConversionConfig,
    ConversionResult,
    ConversionStatus,
    compute_batch_anchor,
    resolve_epub_path,
)
from fictionpub.utils.logger import LOG_DIR

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

# TODO: unify styling, use theme colors from themes.py instead of hardcoded values

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

/* ── Toolbar ── */
QPushButton#updateIndicator {
    color: #27ae60; font-weight: bold;
}
QPushButton#updateIndicator:hover {
    background: rgba(39,174,96,0.15);
}

/* ── Action buttons ── */
QPushButton#convertButton,
QPushButton#installUpdate,
QPushButton#restartUpdate {
    background-color: #2980b9;
    color: white;
    font-weight: bold;
    padding: 4px 16px;
    border-radius: 3px;
    border: none;
}
QPushButton#restartUpdate {
    background-color: #27ae60;
}
QPushButton#convertButton:hover,
QPushButton#installUpdate:hover {
    background-color: #3498db;
}
QPushButton#restartUpdate:hover {
    background-color: #2fcc71;
}
QPushButton#convertButton:disabled,
QPushButton#installUpdate:disabled {
    background-color: #7f8c8d;
}

"""


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._settings: AppSettings = settings
        self._geom: GeometryStore = settings.geometry_store()
        self._geom_key = "main"
        self._config: ConversionConfig = settings.conversion_config()

        self._scan_worker: ScanWorker | None = None
        self._batch_worker: BatchWorker | None = None
        self._batch_anchor: BatchAnchor | None = None
        self._update_check_worker: UpdateCheckWorker | None = None

        self._meta_pool = QThreadPool.globalInstance()
        self._meta_pool.setMaxThreadCount(8)

        # Cumulative conversion stats across all runs in this GUI session.
        self._cumulative_success = 0
        self._cumulative_warnings = 0
        self._cumulative_failures = 0

        # Update state
        self._update_info: UpdateInfo | None = None  # set when update available
        self._about_dialog: AboutDialog | None = None  # current open About dialog
        self._update_check_signals: UpdateCheckSignals | None = None  # kept alive on self
        self._update_check_running: bool = False  # prevents concurrent checks
        self._startup_check_scheduled: bool = False  # showEvent one-shot guard

        self._build_ui()
        self._connect_signals()
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
        tb: ToolbarWidget = self._toolbar
        tb.add_files_requested.connect(self._on_add_files)
        tb.add_folder_requested.connect(self._on_add_folder)
        tb.remove_selected_requested.connect(self._on_remove_selected)
        tb.remove_all_requested.connect(self._on_remove_all)
        tb.remove_completed_requested.connect(self._on_remove_completed)
        tb.expand_all_requested.connect(self._file_view.expandAll)
        tb.collapse_all_requested.connect(self._file_view.collapseAll)
        tb.select_all_requested.connect(self._on_select_all)
        tb.deselect_all_requested.connect(self._on_deselect_all)
        tb.conversion_settings_requested.connect(self._on_conversion_settings)
        tb.app_settings_requested.connect(self._on_app_settings)
        tb.update_indicator_clicked.connect(self._on_update_indicator_clicked)
        tb.about_requested.connect(self._on_about)

        self._model.selection_count_changed.connect(self._toolbar.update_selection_count)
        self._model.selection_count_changed.connect(self._on_file_count_changed)
        self._model.status_counts_changed.connect(self._toolbar.update_status_counts)

        fv: FileTreeView = self._file_view
        fv.status_clicked.connect(self._on_status_clicked)
        fv.folder_double_clicked.connect(self._on_folder_double_clicked)
        fv.add_files_requested.connect(self._on_add_files)
        fv.add_folder_requested.connect(self._on_add_folder)
        fv.open_epub_requested.connect(self._on_open_epub)
        fv.open_fb2_requested.connect(self._on_open_fb2)
        fv.open_folder_requested.connect(self._on_open_folder)
        fv.has_view_selection_changed.connect(self._toolbar.update_view_selection)
        fv.selection_remove_requested.connect(self._on_remove_selected)
        fv.files_dropped.connect(self._start_scan)

        bb: BottomBarWidget = self._bottom_bar
        bb.convert_requested.connect(self._on_convert)
        bb.cancel_requested.connect(self._on_cancel)
        bb.open_logs_dir_requested.connect(self._on_open_logs)
        bb.open_last_log_requested.connect(self._on_open_last_log)

    def _apply_stylesheet(self) -> None:
        """Single stylesheet for the whole window."""
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

    def _on_add_folder_single(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("toolbar.add_folder"))
        if folder:
            self._start_scan([Path(folder)])

    def _on_add_folder(self) -> None:
        """
        Open a folder-picker that supports selecting multiple directories.

        QFileDialog.getExistingDirectory() only ever returns one path, so we
        open the dialog manually with DontUseNativeDialog and extend the
        selection mode of its internal list- and tree-views at runtime.
        """
        # TODO: consider falling back to the default picker (_on_add_folder_single)
        dlg = QFileDialog(self, t("toolbar.add_folder"))
        dlg.setFileMode(QFileDialog.FileMode.Directory)
        # Must disable the native dialog to be able to patch the internal views.
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        # Patch every QAbstractItemView inside the dialog to allow multi-select.
        # Qt uses a QListView ("listView") for icon/list mode and a QTreeView
        # ("treeView") for detail mode; both need patching.
        for view in dlg.findChildren(QAbstractItemView):
            view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        if dlg.exec():
            folders = [Path(f) for f in dlg.selectedFiles() if Path(f).is_dir()]
            if folders:
                self._start_scan(folders)

    def _on_remove_selected(self) -> None:
        if self._is_converting():
            return
        indices = self._file_view.selected_source_indices()
        if indices:
            self._model.remove_nodes(indices)

    def _on_remove_all(self) -> None:
        if self._is_converting():
            return
        if not self._model.total_file_count():
            return
        reply = QMessageBox.question(
            self,
            t("msg.remove_all_title"),
            t("msg.remove_all_text"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._model.remove_all()
            self._bottom_bar.set_idle()

    def _on_remove_completed(self) -> None:
        if self._is_converting():
            return
        self._model.remove_completed()

    def _on_file_count_changed(self, _checked: int, total: int) -> None:
        """Keep the bottom-bar status text in sync whenever files are added or removed."""
        # TODO: ensure all counts are queried from a single source of truth
        self._bottom_bar.update_file_count(total)
        if self._is_converting():
            return
        if self._scan_worker and self._scan_worker.isRunning():
            return
        self._bottom_bar.set_idle()

    def _on_select_all(self) -> None:
        self._model.set_all_checked(True)

    def _on_deselect_all(self) -> None:
        self._model.set_all_checked(False)

    def _on_conversion_settings(self) -> None:
        dlg = SettingsDialog(self._config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result: ConversionConfig | None = dlg.get_result()
            if result is not None:
                self._config = result
                self._settings.set_conversion_config(self._config)
                self._update_output_hint()

    def _on_app_settings(self) -> None:
        AppSettingsDialog(self._settings, self).exec()

    def _on_open_logs(self) -> None:
        """Open the log folder viewer dialog."""
        LogFolderDialog(geom=self._geom, parent=self).show()

    def _on_open_last_log(self) -> None:
        if not LOG_DIR.exists():
            QMessageBox.information(self, t("msg.no_logs_title"), t("msg.no_logs_dir"))
            return
        logs = sorted(LOG_DIR.glob("converter_*.log"), key=lambda p: p.stat().st_mtime)
        if not logs:
            QMessageBox.information(self, t("msg.no_logs_title"), t("msg.no_logs_files"))
            return
        LogViewerDialog.from_file(logs[-1], self._geom, parent=self).show()

    def _on_about(self) -> None:
        dlg = AboutDialog(self)
        # Null out the stored reference the moment Qt destroys the C++ object
        # (WA_DeleteOnClose).  This prevents any later code from calling into
        # a deleted widget via self._about_dialog.
        dlg.destroyed.connect(lambda: setattr(self, "_about_dialog", None))
        # Connect Check Now button
        dlg.check_for_updates_requested.connect(
            lambda: self._start_update_check(force=True)
        )
        # Populate current update status
        dlg.set_update_status(self._update_info.tag if self._update_info else None)
        self._about_dialog = dlg
        dlg.show()
        # If we have no cached result yet (fresh launch before the timer fired,
        # or check still in progress), kick off a check tied to this dialog.
        if self._update_info is None and not self._update_check_running:
            self._start_update_check(force=False)

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
        self._scan_worker.files_found.connect(self._on_scan_complete)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.start()

    def _on_scan_complete(self, found: list[tuple[Path, Path]]) -> None:
        """
        Add files, then expand only the newly created root FolderNodes.

        Snapshot the current root-folder path set before adding so we can
        identify which roots are new after the call.
        """
        existing_roots = {f.path for f in self._model._root_folders}

        self._model.add_files(found)

        new_roots = [f for f in self._model._root_folders if f.path not in existing_roots]
        self._file_view.expand_new_folders(new_roots)

        if new_roots:
            self._toolbar.set_tree_expanded()

        for _root, file_path in found:
            node = self._model._path_to_node.get(file_path)
            if node and node.meta_loading:
                signals = MetaSignals(self)
                signals.meta_parsed.connect(self._model.update_meta)
                signals.meta_failed.connect(self._model.update_meta_error)
                self._meta_pool.start(MetaWorker(file_path, signals))

    def _on_scan_finished(self) -> None:
        self._toolbar.set_busy(False)
        self._bottom_bar.set_idle()

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _on_convert(self) -> None:
        if self._is_converting():
            return

        files = self._model.checked_file_paths()
        if not files:
            QMessageBox.information(self, t("msg.no_files_title"), t("msg.no_files_text"))
            return

        self._batch_anchor = compute_batch_anchor(files)

        session = ConversionSession(total=len(files))
        self._toolbar.set_busy(True)
        self._bottom_bar.set_converting(len(files))

        self._batch_worker = BatchWorker(self._config, files, session, parent=self)
        self._batch_worker.progress_update.connect(self._on_progress_update)
        self._batch_worker.batch_finished.connect(self._on_batch_finished)
        self._batch_worker.error_occurred.connect(self._on_batch_error)
        self._batch_worker.start()

    def _on_cancel(self) -> None:
        if self._batch_worker and self._batch_worker.isRunning():
            self._batch_worker.request_cancel()
            self._bottom_bar.set_cancelling()

    def _on_progress_update(self, result: ConversionResult) -> None:
        self._model.set_file_result(result.path, result)
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
            self._cumulative_success + self._cumulative_warnings + self._cumulative_failures
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
    # Update check
    # ------------------------------------------------------------------

    def _start_update_check(
        self,
        force: bool = False,
    ) -> None:
        """
        Submit an UpdateCheckWorker to the global thread pool.

        Parameters
        ----------
        force        : skip the should_check_now() gate (used by "Check Now")
        about_dialog : if provided, set its status to "checking…" immediately

        GC note
        -------
        UpdateCheckSignals is a QObject that carries the signal connections.
        If it were a local variable it could be garbage-collected during the
        worker's startup_delay sleep, silently breaking the connections.
        Storing it on self keeps the Python wrapper alive until the next
        check overwrites it (which is fine — the old signals object has
        already fired by then).
        """
        if not force and not self._settings.should_check_now():
            return

        # Prevent a second concurrent check (e.g. About opened while timer
        # callback is still pending).
        if self._update_check_running:
            if self._about_dialog is not None:
                self._about_dialog.set_update_status("")
            return

        self._update_check_running = True

        if self._about_dialog is not None:
            self._about_dialog.set_update_status("")  # "Checking…"

        # Store on self — prevents GC from collecting the QObject before
        # the worker thread emits its signal after the startup_delay sleep.
        self._update_check_signals = UpdateCheckSignals(self)
        self._update_check_signals.update_available.connect(self._on_update_available)
        self._update_check_signals.no_update.connect(self._on_no_update)
        # Clear the running flag once either signal fires
        self._update_check_signals.update_available.connect(
            lambda _info: setattr(self, "_update_check_running", False)
        )
        self._update_check_signals.no_update.connect(
            lambda: setattr(self, "_update_check_running", False)
        )

        worker = UpdateCheckWorker(
            app_url=app_info.APP_URL,
            current_ver=app_info.VERSION,
            signals=self._update_check_signals,
            startup_delay=0.0 if force else 3.0,
        )
        self._update_check_worker = worker  # keep Python reference alive
        QThreadPool.globalInstance().start(worker)

    def _on_update_available(self, info: UpdateInfo) -> None:
        """Called on the main thread when a newer release is found."""
        self._update_info = info
        self._settings.set_last_checked()
        self._settings.sync()

        # Update toolbar indicator
        self._toolbar.set_update_available(True)

        # self._about_dialog is None when closed (cleared by destroyed signal)
        if self._about_dialog is not None and not self._about_dialog.isHidden():
            self._about_dialog.set_update_status(info.tag)

        # Show startup popup once per newly discovered version
        if self._settings.should_notify_popup(info.tag):
            self._show_update_popup(info, from_startup=True)

        log.info(f"Update available: {info.tag}")

    def _on_no_update(self) -> None:
        """Called on the main thread when we are already on the latest version."""
        self._update_info = None
        self._settings.set_last_checked()
        self._settings.sync()

        self._toolbar.set_update_available(False)

        # self._about_dialog is None when closed (cleared by destroyed signal)
        if self._about_dialog is not None and not self._about_dialog.isHidden():
            self._about_dialog.set_update_status(None)

    def _on_update_indicator_clicked(self) -> None:
        """Toolbar green arrow clicked — open the update dialog."""
        if self._update_info:
            self._show_update_popup(self._update_info, from_startup=False)

    def _show_update_popup(self, info: UpdateInfo, *, from_startup: bool) -> None:
        dlg = UpdateDialog(
            info,
            self._settings,
            show_once=from_startup,
            parent=self,
        )
        dlg.exec()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_converting(self) -> bool:
        return bool(self._batch_worker and self._batch_worker.isRunning())

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    @override
    def showEvent(self, event) -> None:
        raw = self._geom.load(self._geom_key)
        self.restoreGeometry(raw) if raw else self.resize(1280, 720)
        super().showEvent(event)

        # Schedule exactly one startup check, regardless of how many times
        # showEvent fires (minimise/restore re-triggers it).
        if not self._startup_check_scheduled and self._settings.should_check_now():
            self._startup_check_scheduled = True
            QTimer.singleShot(1500, self._start_update_check)

    @override
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
            self._batch_worker.request_cancel()  # type: ignore

        if self._update_check_worker is not None:
            self._update_check_worker.cancel()
            self._update_check_worker = None
        if self._scan_worker:
            self._scan_worker.quit()
            self._scan_worker.wait(2000)
        if self._batch_worker:
            self._batch_worker.wait(3000)

        self._geom.save(self._geom_key, self.saveGeometry())
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
