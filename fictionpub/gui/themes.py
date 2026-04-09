"""
Theme utilities.
apply_theme() must be called after QApplication.setStyle('Fusion').

After setting the application palette, we force every widget through the
style engine's unpolish / polish cycle.  This is the Qt-recommended way to
make already-rendered widgets pick up palette changes immediately.

Without this step, widgets like QTreeView that cache palette-derived brush
values at paint time (alternating row colours, text colours) will not update
until the next natural repaint event — producing the "partial theme change"
symptom where some areas update and others do not.

PLAIN_BUTTON_QSS
────────────────
Shared stylesheet for the plain QPushButtons throughout the application.

It uses bare "QPushButton" selectors so it can be applied at any scope:
  • MainWindow composes it into _WINDOW_QSS with ToolbarWidget /
    BottomBarWidget ancestor selectors for correct specificity isolation.
  • Modal / modeless dialogs (e.g. LogFolderDialog) set it directly on
    themselves, so all their QPushButtons inherit the shared style.
"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Shared button style — should be used by both MainWindow and standalone dialogs
# ---------------------------------------------------------------------------
# TODO: unify button styles across modules. Use palette colors.
PLAIN_BUTTON_QSS = """
QPushButton {
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 3px 8px;
    background: transparent;
}
QPushButton:hover {
    background-color: rgba(128, 128, 128, 0.20);
    border: 1px solid rgba(128, 128, 128, 0.35);
}
QPushButton:pressed {
    background-color: rgba(128, 128, 128, 0.35);
    border: 1px solid rgba(128, 128, 128, 0.50);
}
QPushButton:checked {
    background-color: rgba(128, 128, 128, 0.35);
    border: 1px solid rgba(128, 128, 128, 0.50);
}
QPushButton:disabled {
    color: palette(mid);
}
"""


def _light_palette() -> QPalette:
    p = QPalette()
    window = QColor(240, 240, 240)
    # window_alt = QColor(248, 248, 248)
    base = QColor(255, 255, 255)
    base_alt = QColor(245, 245, 245)
    text = QColor(30, 30, 30)
    dim = QColor(140, 140, 140)
    btn = QColor(225, 225, 225)
    btn_text = QColor(30, 30, 30)
    highlight = QColor(38, 120, 200)
    hi_text = QColor(255, 255, 255)
    link = QColor(10, 100, 200)
    tooltip_bg = QColor(255, 255, 220)
    tooltip_fg = QColor(30, 30, 30)
    white = QColor(255, 255, 255)
    mid = QColor(180, 180, 180)
    dark = QColor(160, 160, 160)
    shadow = QColor(100, 100, 100)

    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, base_alt)
    p.setColor(QPalette.ColorRole.ToolTipBase, tooltip_bg)
    p.setColor(QPalette.ColorRole.ToolTipText, tooltip_fg)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, btn)
    p.setColor(QPalette.ColorRole.ButtonText, btn_text)
    p.setColor(QPalette.ColorRole.BrightText, white)
    p.setColor(QPalette.ColorRole.Link, link)
    p.setColor(QPalette.ColorRole.Highlight, highlight)
    p.setColor(QPalette.ColorRole.HighlightedText, hi_text)
    p.setColor(QPalette.ColorRole.Mid, mid)
    p.setColor(QPalette.ColorRole.Dark, dark)
    p.setColor(QPalette.ColorRole.Shadow, shadow)

    _set_disabled(p, dim)
    return p


def _dark_palette() -> QPalette:
    p = QPalette()

    bg = QColor(45, 45, 45)
    bg_alt = QColor(35, 35, 35)
    bg_deep = QColor(25, 25, 25)
    text = QColor(220, 220, 220)
    dim = QColor(130, 130, 130)
    accent = QColor(66, 135, 245)
    white = QColor(255, 255, 255)
    mid = QColor(60, 60, 60)
    dark = QColor(30, 30, 30)
    shadow = QColor(10, 10, 10)

    p.setColor(QPalette.ColorRole.Window, bg)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, bg_alt)
    p.setColor(QPalette.ColorRole.AlternateBase, bg)
    p.setColor(QPalette.ColorRole.ToolTipBase, bg_deep)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, bg)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, white)
    p.setColor(QPalette.ColorRole.Link, accent)
    p.setColor(QPalette.ColorRole.Highlight, accent)
    p.setColor(QPalette.ColorRole.HighlightedText, white)
    p.setColor(QPalette.ColorRole.Mid, mid)
    p.setColor(QPalette.ColorRole.Dark, dark)
    p.setColor(QPalette.ColorRole.Shadow, shadow)

    _set_disabled(p, dim)
    return p


def _set_disabled(p: QPalette, dim: QColor) -> None:
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, dim)


def apply_theme(app: QApplication, theme: str) -> None:
    """
    Apply 'light', 'dark', or 'system' palette and force a full re-paint
    of every widget so the change takes effect immediately.
    """
    if theme == "dark":
        app.setPalette(_dark_palette())
    elif theme == "light":
        app.setPalette(_light_palette())
    else:
        # 'system': restore the style's unmodified default palette
        app.setPalette(app.style().standardPalette())

    _force_repaint(app)


def _force_repaint(app: QApplication) -> None:
    """
    Push the new application palette to every widget and cycle them through
    the style engine so all cached colour values are replaced immediately.
    """
    new_palette = app.palette()
    style = app.style()
    for widget in app.allWidgets():
        widget.setPalette(new_palette)
        style.unpolish(widget)
        style.polish(widget)
        widget.update()
