"""
fictionpub/pyside6/state/settings.py

Typed wrapper around QSettings.
Provides persistence for app preferences and ConversionConfig.

Persisted ConversionConfig fields
──────────────────────────────────
output_path        — NOT persisted (session-specific file path)
custom_stylesheet  — persisted as a string path; restored only when the
                     file still exists at launch time, so stale paths from
                     a previous session don't silently produce broken output.
retain_folder_structure — persisted (structural user preference)
"""

from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

from ...models.conversion import ConversionConfig


class AppSettings:
    def __init__(self):
        self._s = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            "fictionpub",
            "fb2converter",
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

    def geometry(self) -> QByteArray | None:
        raw = self._s.value("app/geometry")
        return raw if isinstance(raw, QByteArray) else None

    def set_geometry(self, value: QByteArray) -> None:
        self._s.setValue("app/geometry", value)

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

    def sync(self) -> None:
        self._s.sync()

    # ------------------------------------------------------------------
    # Helpers
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
