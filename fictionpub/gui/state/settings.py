"""
Typed wrapper around QSettings.

Geometry keys
─────────────
  app/geometry/{key} — key is window name: main or dialog

reset_to_defaults() clears ALL keys so every size, preference, and
conversion setting reverts to its hard-coded default on next launch.

Custom stylesheet path
──────────────────────
Persisted as a string.  On load, the path is validated; if the file no
longer exists the value is silently discarded (falls back to the built-in
stylesheet) so a stale path from a previous session never silently breaks
EPUB output.

Update settings
───────────────
  app/update_frequency      — "launch" | "daily" | "weekly" | "never"
  app/last_checked          — ISO-8601 datetime string (UTC), or ""
  app/last_notified_version — tag string of the last version shown in
                              the startup popup, or ""
"""

# TODO: review all usages of annotations
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

from ... import app_info
from ...models.conversion import ConversionConfig


class UpdateFrequency(StrEnum):
    """
    How often the app should contact GitHub to check for updates.

    Because StrEnum members *are* strings, QSettings stores and restores
    them without any conversion — ``settings.value(key, UpdateFrequency.LAUNCH)``
    returns a value that compares equal to the enum member directly.
    Declaration order defines the display order in the settings dialog.
    """

    LAUNCH = "launch"  # every startup
    DAILY = "daily"
    WEEKLY = "weekly"
    NEVER = "never"

    @property
    def delta(self) -> timedelta | None:
        """Minimum elapsed time before the next check, or None for 'always/never'."""
        return {
            UpdateFrequency.LAUNCH: None,
            UpdateFrequency.DAILY: timedelta(days=1),
            UpdateFrequency.WEEKLY: timedelta(weeks=1),
            UpdateFrequency.NEVER: None,
        }[self]


@dataclass(frozen=True)
class GeometryStore:
    load: Callable[[str], QByteArray | None]
    save: Callable[[str, QByteArray], None]


class AppSettings:
    def __init__(self):
        self._s = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            app_info.APP_ORG,
            app_info.APP_NAME_SHORT,
        )

    # ------------------------------------------------------------------
    # App-level preferences
    # ------------------------------------------------------------------

    def theme(self) -> str:
        return str(self._s.value("app/theme", "system"))

    def set_theme(self, value: str) -> None:
        self._s.setValue("app/theme", value)

    def language(self) -> str:
        return str(self._s.value("app/language", "en"))

    def set_language(self, value: str) -> None:
        self._s.setValue("app/language", value)

    # ------------------------------------------------------------------
    # Window / dialog geometry
    # ------------------------------------------------------------------

    def geometry_store(self) -> GeometryStore:
        """
        Factory method for geometry store/retrieval.
        Default key is 'main' for MainWindow.
        """
        return GeometryStore(
            load=lambda key: self.load_geometry(key),
            save=lambda key, g: self.save_geometry(g, key),
        )

    def save_geometry(self, value: QByteArray, key: str) -> None:
        """Save geometry to app settings."""
        self._s.setValue(f"geometry/{key}", value)

    def load_geometry(self, key: str) -> QByteArray | None:
        """Retrieve geometry from app settings."""
        raw = self._s.value(f"geometry/{key}")
        return raw if isinstance(raw, QByteArray) else None

    # TextViewerDialog subclasses call QSettings directly via their own
    # instance using the same org/app strings, so their geometry keys
    # (geometry/log_viewer, geometry/css_viewer) land in the same file
    # and are cleared by reset_to_defaults().

    # ------------------------------------------------------------------
    # ConversionConfig persistence
    # ------------------------------------------------------------------

    def conversion_config(self) -> ConversionConfig:
        s = self._s

        # custom_stylesheet: restore only if the file still exists.
        # A stale path (file moved / deleted) is silently discarded so the
        # app falls back to the built-in stylesheet rather than producing an
        # EPUB without any CSS.
        css_raw = str(s.value("conv/custom_stylesheet", "")).strip()
        custom_css: Path | None = None
        if css_raw:
            p = Path(css_raw)
            if p.is_file():
                custom_css = p

        return ConversionConfig(
            # output_path is session-only — not loaded from settings
            retain_folder_structure=self._bool("conv/retain_folder_structure", False),
            toc_depth=int(s.value("conv/toc_depth", 4)),
            split_level=int(s.value("conv/split_level", 2)),
            split_size_kb=int(s.value("conv/split_size_kb", 0)),
            remove_unused_images=self._bool("conv/remove_unused_images", True),
            improve_typography=self._bool("conv/improve_typography", False),
            word_len_nbsp_range=self._tuple("conv/word_len_nbsp_range", (1, 1)),
            word_len_nobreak_range=self._tuple("conv/word_len_nobreak_range", (4, 6)),
            custom_stylesheet=custom_css,
            num_threads=int(s.value("conv/num_threads", 0)),
        )

    def set_conversion_config(self, cfg: ConversionConfig) -> None:
        s = self._s
        s.setValue("conv/retain_folder_structure", cfg.retain_folder_structure)
        s.setValue("conv/toc_depth", cfg.toc_depth)
        s.setValue("conv/split_level", cfg.split_level)
        s.setValue("conv/split_size_kb", cfg.split_size_kb)
        s.setValue("conv/remove_unused_images", cfg.remove_unused_images)
        s.setValue("conv/improve_typography", cfg.improve_typography)
        s.setValue(
            "conv/word_len_nbsp_range",
            f"{cfg.word_len_nbsp_range[0]},{cfg.word_len_nbsp_range[1]}",
        )
        s.setValue(
            "conv/word_len_nobreak_range",
            f"{cfg.word_len_nobreak_range[0]},{cfg.word_len_nobreak_range[1]}",
        )
        # Store as empty string when None so QSettings doesn't write a null entry
        s.setValue(
            "conv/custom_stylesheet",
            str(cfg.custom_stylesheet) if cfg.custom_stylesheet else "",
        )
        s.setValue("conv/num_threads", cfg.num_threads)

    # ------------------------------------------------------------------
    # Update settings
    # ------------------------------------------------------------------

    def update_frequency(self) -> UpdateFrequency:
        """Return the configured check frequency as an UpdateFrequency member."""
        raw = str(self._s.value("app/update_frequency", UpdateFrequency.LAUNCH))
        try:
            return UpdateFrequency(raw)
        except ValueError:
            return UpdateFrequency.LAUNCH

    def set_update_frequency(self, value: UpdateFrequency) -> None:
        self._s.setValue("app/update_frequency", value)  # StrEnum → stored as its string

    def last_checked(self) -> datetime | None:
        """Return the UTC datetime of the last completed update check, or None."""
        raw = str(self._s.value("app/last_checked", "")).strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def set_last_checked(self) -> None:
        """Record now (UTC) as the last-checked timestamp."""
        self._s.setValue("app/last_checked", datetime.now(UTC).isoformat())

    def last_notified_version(self) -> str:
        """Tag of the version last shown in the startup popup, or ''."""
        return str(self._s.value("app/last_notified_version", ""))

    def set_last_notified_version(self, tag: str) -> None:
        self._s.setValue("app/last_notified_version", tag)

    def should_check_now(self) -> bool:
        """
        Return True if an update check should be performed right now,
        according to the configured frequency and last-check timestamp.
        """
        freq = self.update_frequency()

        if freq == UpdateFrequency.NEVER:
            return False
        if freq == UpdateFrequency.LAUNCH:
            return True

        delta = freq.delta  # timedelta for DAILY / WEEKLY
        last = self.last_checked()
        if last is None:
            return True  # never checked before

        now = datetime.now(UTC)
        # Make sure last is timezone-aware before comparing
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        return (now - last) >= delta

    def should_notify_popup(self, tag: str) -> bool:
        """
        Return True if we should show the startup popup for *tag*.
        False when we already showed it for this version.
        """
        return self.last_notified_version() != tag

    def sync(self) -> None:
        self._s.sync()

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_to_defaults(self) -> None:
        """
        Clear all persisted settings.

        After this call, every preference (language, theme, window sizes,
        conversion settings) reverts to its hard-coded default on the next read.
        The caller is responsible for applying any immediate UI
        changes (theme, language) before closing the settings dialog.
        """
        self._s.clear()
        self._s.sync()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _bool(self, key: str, default: bool) -> bool:
        v = self._s.value(key, default)
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("true", "1", "yes")

    def _tuple(self, key: str, default: tuple[int, int]) -> tuple[int, int]:
        raw = self._s.value(key, f"{default[0]},{default[1]}")
        try:
            parts = str(raw).split(",")
            return (int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return default
