"""
Async update check and file download workers.

UpdateCheckWorker  (QRunnable)
    Contacts the GitHub Releases API, parses the latest version, and
    emits a result via companion UpdateCheckSignals.
    Sleeps 3 s at startup so it never blocks the initial UI paint.
    All network / parse errors are swallowed silently — no user-visible
    error popups for background checks.

DownloadWorker  (QThread)
    Downloads one or two executables to sibling temp files beside the
    running exe.  Emits byte-level progress so the UI can show a
    determinate progress bar.  Emits finished() or error(str).
"""

from __future__ import annotations

import logging
import re
import sys
import urllib.request
from contextlib import suppress
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QObject, QRunnable, QThread, Signal

log = logging.getLogger("fb2_converter")

# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

_SEMVER_RE = re.compile(r"^v?(\d+)[\.\-]?(\d+)?[\.\-]?(\d+)?")


def parse_version(s: str) -> tuple[int, int, int]:
    """
    Parse a version string such as "1.2.3", "v1.2.3", "1.2.3.dev4",
    "1.2.3-beta" into a comparable (major, minor, patch) tuple.
    Returns (0, 0, 0) on any parse failure — safe for comparison.
    """
    m = _SEMVER_RE.match(s.strip())
    if not m:
        return (0, 0, 0)
    major = int(m.group(1) or 0)
    minor = int(m.group(2) or 0)
    patch = int(m.group(3) or 0)
    return (major, minor, patch)


def is_dev_build(version: str) -> bool:
    """Return True for versions like '1.2.3.dev*'."""
    return any(kw in version.lower() for kw in ["dev", "post"])


def is_newer(remote: str, local: str) -> bool:
    """Return True if *remote* version is newer than *local*.

    Any tagged release is considered newer than a dev build so that
    running from source always sees available updates.
    This is intentional: set update frequency to 'Never' to disable.
    """
    log.debug(f"Local version: {local} | Remote version: {remote}")

    if is_dev_build(local):
        return True

    return parse_version(remote) > parse_version(local)


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------


def _api_url_from_app_url(app_url: str) -> str:
    """
    Convert a GitHub repo URL to the Releases API endpoint.
    "https://github.com/owner/repo" → "https://api.github.com/repos/owner/repo/releases/latest"
    """
    # Strip trailing slash / .git
    clean = app_url.rstrip("/").removesuffix(".git")
    # Extract path component: /owner/repo
    parts = clean.split("github.com/", 1)
    if len(parts) != 2:
        raise ValueError(f"Cannot derive API URL from {app_url!r}")
    owner_repo = parts[1].strip("/")
    return f"https://api.github.com/repos/{owner_repo}/releases/latest"


def _fetch_json(url: str, timeout: int = 10) -> dict:
    import json

    req = urllib.request.Request(url, headers={"User-Agent": "fictionpub-updater/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class UpdateInfo(NamedTuple):
    tag: str  # e.g. "v1.4.0"
    html_url: str  # GitHub release page URL
    main_url: str  # download URL for fictionpub.exe (or "")
    cli_url: str  # download URL for fictionpub_cli.exe (or "")


# ---------------------------------------------------------------------------
# Update check worker (QRunnable)
# ---------------------------------------------------------------------------


class UpdateCheckSignals(QObject):
    update_available = Signal(object)  # UpdateInfo
    no_update = Signal()
    # Errors are intentionally not surfaced to the user


class UpdateCheckWorker(QRunnable):
    """
    Checks GitHub for a newer release.
    Designed to be submitted to QThreadPool.globalInstance().

    Parameters
    ----------
    app_url     : value of app_info.APP_URL
    current_ver : value of app_info.VERSION
    signals     : UpdateCheckSignals instance (created by caller, connected before submit)
    startup_delay : seconds to sleep before first network call (default 3)
    """

    def __init__(
        self,
        app_url: str,
        current_ver: str,
        signals: UpdateCheckSignals,
        startup_delay: float = 3.0,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._app_url = app_url
        self._current_ver = current_ver
        self.signals = signals
        self._delay = startup_delay
        self._cancelled = False

    def run(self) -> None:
        import time

        time.sleep(self._delay)
        if self._cancelled:
            return

        try:
            api_url = _api_url_from_app_url(self._app_url)
            data = _fetch_json(api_url)

            tag: str = data.get("tag_name", "")
            if not tag:
                return

            # Only consider stable releases (not drafts or pre-releases)
            if data.get("draft") or data.get("prerelease"):
                return

            if not is_newer(tag, self._current_ver):
                self.signals.no_update.emit()
                return

            html_url: str = data.get("html_url", self._app_url)

            # Locate exe assets
            main_url = ""
            cli_url = ""
            for asset in data.get("assets", []):
                name: str = asset.get("name", "")
                dl: str = asset.get("browser_download_url", "")
                if name == "fictionpub.exe":
                    main_url = dl
                elif name == "fictionpub_cli.exe":
                    cli_url = dl

            self.signals.update_available.emit(
                UpdateInfo(tag=tag, html_url=html_url, main_url=main_url, cli_url=cli_url)
            )
        except Exception as e:
            log.warning(f"Update worker error: {e}")
            log.exception("Update worker error")

    def cancel(self) -> None:
        """Safe to call from any thread (GIL makes bool assignment atomic)."""
        self._cancelled = True


# ---------------------------------------------------------------------------
# Download worker (QThread)
# ---------------------------------------------------------------------------

_CHUNK = 64 * 1024  # 64 KB read chunks


class DownloadWorker(QThread):
    """
    Downloads one or two executables into sibling temp files beside
    the running exe.

    Signals
    -------
    progress(received_bytes, total_bytes)  — total_bytes may be 0 if unknown
    file_completed(filename)                — each file finished
    finished()                             — all downloads done, safe to install
    error(message)                         — a download failed
    """

    progress = Signal(int, int)
    file_completed = Signal(str)
    finished = Signal()
    error = Signal(str)

    # Temp-file names written beside the running exe
    MAIN_TMP = "fictionpub_new.exe"
    CLI_TMP = "fictionpub_cli_new.exe"

    def __init__(
        self,
        info: UpdateInfo,
        download_cli: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._info = info
        self._download_cli = download_cli and bool(info.cli_url)

    def run(self) -> None:
        exe_dir = _exe_dir()
        pairs: list[tuple[str, Path]] = []

        if self._info.main_url:
            pairs.append((self._info.main_url, exe_dir / self.MAIN_TMP))
        if self._download_cli and self._info.cli_url:
            pairs.append((self._info.cli_url, exe_dir / self.CLI_TMP))

        if not pairs:
            self.error.emit("No downloadable assets found in this release.")
            return

        total_files = len(pairs)
        for file_idx, (url, dest) in enumerate(pairs):
            try:
                self._download_one(url, dest, file_idx, total_files)
                self.file_completed.emit(dest.name)
            except Exception as exc:
                # Clean up partially written temp files
                for _, p in pairs:
                    if p.exists():
                        with suppress(OSError):
                            p.unlink()

                self.error.emit(str(exc))
                return

        self.finished.emit()

    def _download_one(
        self,
        url: str,
        dest: Path,
        file_idx: int,
        total_files: int,
    ) -> None:
        req = urllib.request.Request(url, headers={"User-Agent": "fictionpub-updater/1"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            received = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                    # Scale progress across all files:
                    # offset received from previous files is not tracked here;
                    # progress signal shows per-file bytes so the bar is always meaningful.
                    self.progress.emit(received, total)


# ---------------------------------------------------------------------------
# Install helper — write batch script and exit
# ---------------------------------------------------------------------------


def exe_path() -> Path:
    """
    Absolute path to the running launcher exe.
 
    sys.argv[0] is set by the OS before extraction of Nuitka --onefile builds
    and always holds the real path.
    In development sys.argv[0] is a .py script, so we fall back to sys.executable.
    """
    candidate = Path(sys.argv[0]).resolve()
    if candidate.suffix.lower() == ".exe":
        return candidate
    return Path(sys.executable).resolve()
 
 
def _exe_dir() -> Path:
    """Directory that contains the running launcher exe (or dev interpreter)."""
    return exe_path().parent


def cli_exe_path() -> Path:
    """Expected path of fictionpub_cli.exe beside the running exe."""
    return _exe_dir() / "fictionpub_cli.exe"


def launch_installer_bat(download_cli: bool) -> None:
    """
    Write a .bat file that waits for app exit, atomically replaces the
    exe(s), and relaunches the main app.  Then exits the current process.
    """
    import tempfile

    exe_dir = _exe_dir()
    main_exe = exe_path()
    main_tmp = exe_dir / DownloadWorker.MAIN_TMP

    lines = [
        "@echo off",
        "timeout /t 2 /nobreak >nul",
        # Replace main exe
        f'move /y "{main_tmp}" "{main_exe}"',
        "if errorlevel 1 (",
        "  echo Failed to replace fictionpub.exe >&2",
        "  pause",
        "  goto :eof",
        ")",
    ]

    if download_cli:
        cli_exe = cli_exe_path()
        cli_tmp = exe_dir / DownloadWorker.CLI_TMP
        lines += [
            f'if exist "{cli_tmp}" move /y "{cli_tmp}" "{cli_exe}"',
        ]

    lines += [
        f'start "" "{main_exe}"',
        'del "%~f0"',  # self-delete the bat
    ]

    _, bat_path_str = tempfile.mkstemp(suffix=".bat", dir=exe_dir)
    bat_path = Path(bat_path_str)
    bat_path.write_text("\r\n".join(lines) + "\r\n", encoding="ascii")

    # Launch the bat detached so it survives our process exit
    import subprocess

    subprocess.Popen(
        ["cmd.exe", "/c", bat_path_str],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
