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
    running exe (frozen build) or to a temp folder (dev build).
    Emits byte-level progress so the UI can show a determinate progress bar.
    Emits finished() or error(str).

Frozen vs dev build
--------------------
is_frozen_build()   — True when running as a Nuitka / PyInstaller onefile exe.
_download_dir()     — exe dir for frozen builds; <OS temp>/fictionpub-update/
                      for dev builds.  The dev directory is created once and
                      cached for the lifetime of the process so DownloadWorker
                      and launch_installer_bat() always agree on the same path.
"""

from __future__ import annotations

import logging
import re
import sys
import tempfile
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
    app_url       : value of app_info.APP_URL
    current_ver   : value of app_info.VERSION
    signals       : UpdateCheckSignals instance (created by caller, connected before submit)
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
# Frozen-build detection and download directory resolution
# ---------------------------------------------------------------------------


def is_frozen_build() -> bool:
    """
    Return True when the app is running as a compiled onefile executable
    (Nuitka or PyInstaller), False when running from source via the
    Python interpreter.

    Nuitka sets sys.frozen = True before executing the user program.
    PyInstaller sets the same attribute.  Checking the argv[0] extension
    is a belt-and-suspenders fallback for other packers.
    """
    if getattr(sys, "frozen", False):
        return True
    # Belt-and-suspenders: if argv[0] is a .exe we are almost certainly frozen.
    return Path(sys.argv[0]).suffix.lower() == ".exe"


# Module-level cache so DownloadWorker and launch_installer_bat()
# always resolve to the same directory within a single process.
_dev_download_dir: Path | None = None


def _download_dir() -> Path:
    """
    Return the directory where update payloads are written.

    Frozen build  → exe_path().parent  (beside the app, ready for the bat)
    Dev build     → <OS temp>/fictionpub-update/  (created on first call,
                    reused for the lifetime of the process)
    """
    global _dev_download_dir
    if is_frozen_build():
        return exe_path().parent
    if _dev_download_dir is None:
        _dev_download_dir = Path(tempfile.gettempdir()) / "fictionpub-update"
        _dev_download_dir.mkdir(parents=True, exist_ok=True)
        log.debug(f"Dev mode: update payloads → {_dev_download_dir}")
    return _dev_download_dir


# ---------------------------------------------------------------------------
# Path helpers
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


# ---------------------------------------------------------------------------
# Download filename helper
# ---------------------------------------------------------------------------


def _versioned_tmp_name(base: str, tag: str) -> str:
    """
    Return a versioned download filename safe for Windows and POSIX.

    Example
    --------
    _versioned_tmp_name("fictionpub",     "v1.4.0")  → "fictionpub_v1.4.0.exe"

    Any character that is not a word character, dot, or hyphen is replaced
    with an underscore so the result is always a valid filename on every OS.
    """
    safe_tag = re.sub(r"[^\w.\-]", "_", tag)
    return f"{base}_{safe_tag}.exe"


# ---------------------------------------------------------------------------
# Download worker (QThread)
# ---------------------------------------------------------------------------

_CHUNK = 64 * 1024  # 64 KB read chunks


class DownloadWorker(QThread):
    """
    Downloads one or two executables into the directory returned by
    _download_dir() — beside the app exe for frozen builds, or into a
    dedicated temp folder for dev builds (so python.exe is never at risk).

    Downloaded files are named with the release version tag:
        fictionpub_v1.4.0.exe
        fictionpub_cli_v1.4.0.exe

    The batch installer renames them to the final names (fictionpub.exe /
    fictionpub_cli.exe) atomically via `move /y`.

    Signals
    -------
    progress(received_bytes, total_bytes)  — total_bytes may be 0 if unknown
    file_completed(filename)                — each file finished (versioned name)
    finished()                             — all downloads done, safe to install
    error(message)                         — a download failed
    """

    progress = Signal(int, int)
    file_completed = Signal(str)
    finished = Signal()
    error = Signal(str)

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
        dest_dir = _download_dir()  # safe for both frozen and dev builds
        tag = self._info.tag
        pairs: list[tuple[str, Path]] = []

        if self._info.main_url:
            pairs.append(
                (
                    self._info.main_url,
                    dest_dir / _versioned_tmp_name("fictionpub", tag),
                )
            )
        if self._download_cli and self._info.cli_url:
            pairs.append(
                (
                    self._info.cli_url,
                    dest_dir / _versioned_tmp_name("fictionpub_cli", tag),
                )
            )

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
# Install helper — write batch script and exit  (frozen builds only)
# ---------------------------------------------------------------------------


def launch_installer_bat(download_cli: bool, tag: str) -> None:
    """
    Write a .bat file that waits for app exit, renames the versioned
    download to the canonical exe name, and relaunches the main app.

    Source files (in _download_dir()):
        fictionpub_v1.4.0.exe      → fictionpub.exe
        fictionpub_cli_v1.4.0.exe  → fictionpub_cli.exe  (optional)

    Must only be called in a frozen build — call is_frozen_build() first.
    """
    src_dir = _download_dir()  # where the versioned downloads live
    exe_dir = _exe_dir()  # where the live exe lives (same as src_dir in frozen builds)
    main_exe = exe_path()
    main_tmp = src_dir / _versioned_tmp_name("fictionpub", tag)

    lines = [
        "@echo off",
        "timeout /t 2 /nobreak >nul",
        # Rename versioned download → canonical exe name
        f'move /y "{main_tmp}" "{main_exe}"',
        "if errorlevel 1 (",
        f"  echo Failed to rename {main_tmp.name} to {main_exe.name} >&2",
        "  pause",
        "  goto :eof",
        ")",
    ]

    if download_cli:
        cli_exe = cli_exe_path()
        cli_tmp = src_dir / _versioned_tmp_name("fictionpub_cli", tag)
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

    # Launch the bat detached so it survives the process exit
    import subprocess

    subprocess.Popen(
        ["cmd.exe", "/c", bat_path_str],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
