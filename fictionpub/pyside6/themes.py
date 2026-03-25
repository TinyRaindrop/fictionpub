"""
Theme utilities for the PySide6 GUI.
apply_theme() must be called after QApplication is constructed.
"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def _dark_palette() -> QPalette:
    p = QPalette()
    bg      = QColor(45,  45,  45)
    bg_alt  = QColor(35,  35,  35)
    bg_deep = QColor(25,  25,  25)
    text    = QColor(220, 220, 220)
    dim     = QColor(140, 140, 140)
    accent  = QColor(66,  135, 245)
    white   = QColor(255, 255, 255)

    p.setColor(QPalette.ColorRole.Window,          bg)
    p.setColor(QPalette.ColorRole.WindowText,      text)
    p.setColor(QPalette.ColorRole.Base,            bg_alt)
    p.setColor(QPalette.ColorRole.AlternateBase,   bg)
    p.setColor(QPalette.ColorRole.ToolTipBase,     bg_deep)
    p.setColor(QPalette.ColorRole.ToolTipText,     text)
    p.setColor(QPalette.ColorRole.Text,            text)
    p.setColor(QPalette.ColorRole.Button,          bg)
    p.setColor(QPalette.ColorRole.ButtonText,      text)
    p.setColor(QPalette.ColorRole.BrightText,      white)
    p.setColor(QPalette.ColorRole.Link,            accent)
    p.setColor(QPalette.ColorRole.Highlight,       accent)
    p.setColor(QPalette.ColorRole.HighlightedText, white)

    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, dim)

    return p


def apply_theme(app: QApplication, theme: str) -> None:
    """
    Apply 'light', 'dark', or 'system' theme.
    Must be called after QApplication.setStyle('Fusion').
    """
    if theme == "dark":
        app.setPalette(_dark_palette())
    else:
        # 'light' and 'system' both use the default Fusion palette.
        app.setPalette(app.style().standardPalette())
