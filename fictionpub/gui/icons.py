"""
Shared status-icon registry for the whole GUI.

The icons are loaded lazily on the first call to get_status_icons() so
that no QPixmap is created before QApplication exists.
The result is cached for the lifetime of the process.

Each icon is a QIcon sourced from resources/icons/*.png and downscaled to
the requested size. A glyph fallback is used when the PNG is unavailable.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from fictionpub.models.conversion import ConversionStatus

_CACHE: dict[ConversionStatus, QIcon] | None = None


def _load_png_icon(filename: str, size: int) -> QIcon | None:
    try:
        from fictionpub.resources.loader import get_icon_path

        path = get_icon_path(filename)
        if path and path.is_file():
            px = QPixmap(str(path))
            if not px.isNull():
                return QIcon(
                    px.scaled(
                        size,
                        size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
    except Exception:
        pass
    return None


def _make_fallback_icon(symbol: str, color: str, size: int) -> QIcon:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(color))
    font = p.font()
    font.setPixelSize(size - 1)
    p.setFont(font)
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, symbol)
    p.end()
    return QIcon(px)


def get_status_icons(size: int = 16) -> dict[ConversionStatus, QIcon]:
    """
    Return the shared {ConversionStatus → QIcon} mapping.

    The icons are loaded once at the given size and cached.  If you need
    a different size, call this function before the cache is populated
    (i.e. before the first FileTreeModel or BottomBarWidget is constructed).
    """
    global _CACHE
    if _CACHE is None:
        _CACHE = {
            ConversionStatus.SUCCESS: (
                _load_png_icon("status_success.png", size)
                or _make_fallback_icon("✓", "#27ae60", size)
            ),
            ConversionStatus.WARNING: (
                _load_png_icon("status_warning.png", size)
                or _make_fallback_icon("⚠", "#e67e22", size)
            ),
            ConversionStatus.FAILURE: (
                _load_png_icon("status_failure.png", size)
                or _make_fallback_icon("✗", "#e74c3c", size)
            ),
        }
    return _CACHE
