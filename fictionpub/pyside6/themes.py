"""
Theme utilities.
apply_theme() must be called after QApplication is constructed.
Both 'light' and 'dark' use explicit QPalette definitions so the result
is predictable on every platform regardless of the system palette.
'system' defers to the OS default palette (no override).
"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def _light_palette() -> QPalette:
    p = QPalette()

    window     = QColor(240, 240, 240)
    window_alt = QColor(248, 248, 248)
    base       = QColor(255, 255, 255)
    base_alt   = QColor(245, 245, 245)
    text       = QColor(30,  30,  30)
    dim        = QColor(140, 140, 140)
    btn        = QColor(225, 225, 225)
    btn_text   = QColor(30,  30,  30)
    highlight  = QColor(38,  120, 200)
    hi_text    = QColor(255, 255, 255)
    link       = QColor(10,  100, 200)
    tooltip_bg = QColor(255, 255, 220)
    tooltip_fg = QColor(30,  30,  30)

    p.setColor(QPalette.ColorRole.Window,          window)
    p.setColor(QPalette.ColorRole.WindowText,      text)
    p.setColor(QPalette.ColorRole.Base,            base)
    p.setColor(QPalette.ColorRole.AlternateBase,   base_alt)
    p.setColor(QPalette.ColorRole.ToolTipBase,     tooltip_bg)
    p.setColor(QPalette.ColorRole.ToolTipText,     tooltip_fg)
    p.setColor(QPalette.ColorRole.Text,            text)
    p.setColor(QPalette.ColorRole.Button,          btn)
    p.setColor(QPalette.ColorRole.ButtonText,      btn_text)
    p.setColor(QPalette.ColorRole.BrightText,      QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Link,            link)
    p.setColor(QPalette.ColorRole.Highlight,       highlight)
    p.setColor(QPalette.ColorRole.HighlightedText, hi_text)
    p.setColor(QPalette.ColorRole.Mid,             QColor(180, 180, 180))
    p.setColor(QPalette.ColorRole.Dark,            QColor(160, 160, 160))
    p.setColor(QPalette.ColorRole.Shadow,          QColor(100, 100, 100))

    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, dim)

    return p


def _dark_palette() -> QPalette:
    p = QPalette()

    bg      = QColor(45,  45,  45)
    bg_alt  = QColor(35,  35,  35)
    bg_deep = QColor(25,  25,  25)
    text    = QColor(220, 220, 220)
    dim     = QColor(130, 130, 130)
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
    p.setColor(QPalette.ColorRole.Mid,             QColor(60,  60,  60))
    p.setColor(QPalette.ColorRole.Dark,            QColor(30,  30,  30))
    p.setColor(QPalette.ColorRole.Shadow,          QColor(10,  10,  10))

    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, dim)

    return p


def apply_theme(app: QApplication, theme: str) -> None:
    """
    Apply 'light', 'dark', or 'system' palette to the application.
    Must be called after QApplication.setStyle('Fusion').
    """
    if theme == "dark":
        app.setPalette(_dark_palette())
    elif theme == "light":
        app.setPalette(_light_palette())
    else:
        # 'system': restore the style's unmodified default palette
        app.setPalette(app.style().standardPalette())
