"""
Modal "Update Available" dialog.

States
------
INFO        → shows version info, Install / Open GitHub / Dismiss buttons
DOWNLOADING → progress bar, cancel button
DONE (frozen)  → "Ready to install — restart?" with Restart / Later buttons
DONE (dev)     → "Downloaded to <folder>" with Open Folder / Close buttons

The dialog is re-used for both the startup popup and the toolbar button
click.  Pass ``show_once=True`` from the startup popup path so it saves
``last_notified_version`` immediately on construction (preventing a
second popup on the next launch even if the user closes without acting).

Checkbox behaviour
------------------
"Update CLI as well" is visible whenever a CLI download URL exists in
UpdateInfo.  It is pre-checked when fictionpub_cli.exe sits beside the
running exe.

Dev-mode behaviour
------------------
In a dev build (is_frozen_build() == False) the downloaded files land in
a temp folder rather than beside the exe.  After download completes the
dialog shows an "Open Folder" button instead of "Restart & Install".
"""

from __future__ import annotations

import os
import platform
import subprocess

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from fictionpub import app_info
from fictionpub.gui.i18n import t
from fictionpub.gui.workers.update_worker import (
    DownloadWorker,
    UpdateInfo,
    _download_dir,
    cli_exe_path,
    is_frozen_build,
    launch_installer_bat,
)


class UpdateDialog(QDialog):
    """
    Shown when a newer release is available.

    Parameters
    ----------
    info        : UpdateInfo from the check worker
    settings    : AppSettings (for persisting last_notified_version)
    show_once   : if True, persist last_notified_version immediately so
                  the startup popup is not repeated on the next launch
    parent      : Qt parent widget
    """

    def __init__(
        self,
        info: UpdateInfo,
        settings,
        show_once: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._info = info
        self._settings = settings
        self._worker: DownloadWorker | None = None
        self._frozen = is_frozen_build()

        self.setWindowTitle(t("update.dialog_title"))
        self.setFixedWidth(420)

        if show_once:
            settings.set_last_notified_version(info.tag)

        self._build_ui()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 16, 20, 14)

        # Title
        title = QLabel(t("update.available_title"))
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        # Version lines
        self._ver_label = QLabel(
            t(
                "update.version_info",
                current=app_info.VERSION,
                new=self._info.tag.lstrip("v"),
            )
        )
        self._ver_label.setWordWrap(True)
        layout.addWidget(self._ver_label)

        # Dev-mode notice: show where files will be downloaded
        if not self._frozen:
            self._dev_notice = QLabel()
            self._dev_notice.setWordWrap(True)
            self._dev_notice.setStyleSheet("font-size: 10px; color: palette(mid);")
            self._update_dev_notice()
            layout.addWidget(self._dev_notice)

        # CLI checkbox (only when CLI asset exists)
        self._cli_cb = QCheckBox(t("update.include_cli"))
        cli_exists = cli_exe_path().is_file()
        self._cli_cb.setChecked(cli_exists)
        self._cli_cb.setVisible(bool(self._info.cli_url))
        layout.addWidget(self._cli_cb)

        # Progress bar (hidden initially)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate until we get Content-Length
        self._progress.setTextVisible(True)
        self._progress.hide()
        layout.addWidget(self._progress)

        # Status label
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size: 10px; color: palette(mid);")
        self._status.hide()
        layout.addWidget(self._status)

        # ── Primary button row ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._github_btn = QPushButton(t("update.btn_github"))
        self._github_btn.clicked.connect(self._on_open_github)
        btn_row.addWidget(self._github_btn)

        btn_row.addStretch()

        self._install_btn = QPushButton(t("update.btn_install"))
        self._install_btn.setObjectName("installUpdate")
        self._install_btn.clicked.connect(self._on_install)
        btn_row.addWidget(self._install_btn)

        layout.addLayout(btn_row)

        # ── Post-download row (frozen: Restart; dev: Open Folder) ─────────
        post_row = QHBoxLayout()
        post_row.addStretch()

        self._later_btn = QPushButton(t("update.btn_later"))
        self._later_btn.clicked.connect(self.reject)
        self._later_btn.hide()
        post_row.addWidget(self._later_btn)

        if self._frozen:
            # Frozen build: offer in-place restart & install
            self._restart_btn = QPushButton(t("update.btn_restart"))
            self._restart_btn.setObjectName("restartUpdate")
            self._restart_btn.clicked.connect(self._on_restart)
            self._restart_btn.hide()
            post_row.addWidget(self._restart_btn)
        else:
            # Dev build: just open the download folder
            self._open_folder_btn = QPushButton(t("update.btn_open_folder"))
            self._open_folder_btn.setObjectName("openFolderUpdate")
            self._open_folder_btn.clicked.connect(self._on_open_download_folder)
            self._open_folder_btn.hide()
            post_row.addWidget(self._open_folder_btn)

        layout.addLayout(post_row)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_install(self) -> None:
        if not self._info.main_url:
            # No downloadable exe — fall back to opening GitHub
            self._on_open_github()
            return

        self._set_downloading(True)

        self._worker = DownloadWorker(
            self._info,
            download_cli=self._cli_cb.isChecked(),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.file_completed.connect(self._on_file_done)
        self._worker.finished.connect(self._on_download_finished)
        self._worker.error.connect(self._on_download_error)
        self._worker.start()

    def _on_open_github(self) -> None:
        import webbrowser

        webbrowser.open(self._info.html_url)

    def _on_restart(self) -> None:
        """Write the batch script and quit the application (frozen builds only)."""
        download_cli = self._cli_cb.isChecked() and bool(self._info.cli_url)
        try:
            launch_installer_bat(download_cli, self._info.tag)
        except Exception as exc:
            self._status.setText(t("update.bat_error", error=str(exc)))
            self._status.show()
            return
        from PySide6.QtWidgets import QApplication

        QApplication.instance().quit()

    def _on_open_download_folder(self) -> None:
        """Open the temp download folder in the OS file manager (dev builds only)."""
        folder = _download_dir()
        try:
            if platform.system() == "Windows":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            self._status.setText(str(exc))
            self._status.show()

    # ------------------------------------------------------------------
    # Download callbacks
    # ------------------------------------------------------------------

    def _on_progress(self, received: int, total: int) -> None:
        self._install_btn.setEnabled(False)

        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(received)
            mb_recv = received / 1_048_576
            mb_total = total / 1_048_576
            self._progress.setFormat(f"{mb_recv:.1f} / {mb_total:.1f} MB")
        else:
            self._progress.setRange(0, 0)
            self._progress.setFormat(
                t("update.downloading_bytes", n=f"{received / 1_048_576:.1f}")
            )

    def _on_file_done(self, filename: str) -> None:
        self._status.setText(t("update.file_done", name=filename))
        self._status.show()
        # Reset progress for next file
        self._progress.setRange(0, 0)
        self._progress.setValue(0)

    def _on_download_finished(self) -> None:
        self._set_downloading(False)
        self._progress.hide()
        self._install_btn.hide()
        self._github_btn.hide()
        self._cli_cb.setEnabled(False)
        self._later_btn.show()

        if self._frozen:
            self._status.setText(t("update.download_done"))
            self._restart_btn.show()
        else:
            # Dev mode: tell the user where the files landed
            folder = _download_dir()
            self._status.setText(t("update.download_done_dev", path=str(folder)))
            self._open_folder_btn.show()
            # Refresh the dev notice in case _download_dir() was just created
            self._update_dev_notice()

        self._status.show()

    def _on_download_error(self, message: str) -> None:
        self._set_downloading(False)
        self._progress.hide()
        self._status.setText(t("update.download_error", error=message))
        self._status.show()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_downloading(self, active: bool) -> None:
        self._install_btn.setEnabled(not active)
        self._github_btn.setEnabled(not active)
        self._cli_cb.setEnabled(not active)
        self._progress.setVisible(active)
        if active:
            self._status.setText(t("update.downloading"))
            self._status.show()

    def _update_dev_notice(self) -> None:
        """Refresh the dev-mode folder-path notice label."""
        if not hasattr(self, "_dev_notice"):
            return
        folder = _download_dir()
        self._dev_notice.setText(t("update.dev_notice", path=str(folder)))

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(2000)
        super().closeEvent(event)
